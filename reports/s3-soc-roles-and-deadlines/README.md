# ②：SoCの全役割とpacking完了時の期限確認

対象は現在の優先候補：Tang Nano 20K＋S3-WROOM-1U-N16R8×2、T/S同時。T用とS用のSoCは同じ種類の責務を持ち、入力rateと選局対象が違う。①は変更しない。以下は目標受信機の役割分担と、そのうち実装・検証できた範囲を分離した表である。**SoCはRF取得とFPGAへの供給を担当し、全復調・TS生成はFPGAが担当する。**

## SoCの全役割（現在のraw案）

| # | 役割 | SoC内の担当と内容 | 現状 |
|---|---|---|---|
| 1 | 起動・資源準備 | CPU/SDKがFlash/PSRAM等の初期化、内部RAM予約、stack/TCB、SPI driver/DMA領域を準備 | 実SDKリンク・配置・既知起動確保列を検査済み。2task静的生成と部分失敗時の停止を追加。全bootと全runtime heapは未確認 |
| 2 | RF/PHY設定・維持 | CPUがRF設定・選局・帯域/rate等を制御し、RF回路が信号取得。PHY完全較正、PLL追従等 | SDKのPHY入口はリンク済み。対象RFでの選局・品質確認、制御系統との統合は未完了。外付け周波数変換/LNB等のRF回路自体をCPUソフトが代替する意味ではない |
| 3 | 生I/Q取得とbank引渡し | RFハードウェアのbank書込みをCPUが監視。index/sentinelによる境界確認、bank切替、sample順序の維持 | native取得コードと模型試験あり。未公開RF ABIを用いており実機での連続・無欠落取得は未確認 |
| 4 | 無損失packing | CPUの2workerで各sampleのI10/Q10を詰め、2sample＝5byteへ格納 | 実Cと並行ホスト試験済み。追加のデシメート・再量子化・FFT・復調は行わない |
| 5 | バッファと所有権の管理 | CPUがRF3bank・送信4×32 KiBを管理。両worker完了前のRF再使用を禁止。SPI逆順完了でも連続完了分だけ解放。奇数sampleのcarry維持 | 実装・ホスト試験済み。容量の実時間十分性は未確認 |
| 6 | core実行順・時計・期限管理 | CPUがRF poll、bounded packing slice、collect、SPI処理を実行。共通epoch/単位の時計で期限判定 | 校正CCOUNT時計とcore0/1の実task entry・起動handshakeを統合済み。WCET・IRQ込みresponse timeは未確認 |
| 7 | FPGA向けraw転送 | CPUがepoch/offset/lengthを付けてSPI2 Octal＋SPI3 Quadへ割当。SPI/GDMAが送信し、CPUが完了を回収 | raw専用32 KiB API・FPGA側有限試験あり。pin map、物理同時転送、実時間帯域の確認は未完了 |
| 8 | 指令の受信・反映 | FPGAからの選局/電源等の指令を受け、対象RF/制御ハードへ反映。復調データの戻りは受けない | raw受信系との指令入口・状態遷移の統合は未完了。診断アプリは指令待受けも開始しない |
| 9 | 異常停止・回復 | CPUが期限超過、bank境界/順序不整合、送信失敗等を検出してRFを停止。worker/DMA静止後にepoch更新・再初期化、FPGAの出力停止と整合を取る | RF停止・peer終了待ち・DMA lease保持・TWDT復元はtaskへ統合済み。削除完了/DMA drainを確認するsupervisor、再開・TS無効化は未完了 |

電源やLNB等の操作は採用する外付け回路に依存する指令であり、その回路・配線・実装が完成しているという意味ではない。SoCが担当しないのは、FPGA側の同期/周波数・位相補正/FFT/等化/軟判定、deinterleave、Viterbi/RS等のFEC、TS生成・出力である（各方式で必要な処理のみ）。

T側の候補rateは16 MSa/sでraw40 MB/s、S側は40 MSa/sでraw100 MB/s。いずれも20bit/sampleの無損失packing後で、header等は別費用。S40条件のRF品質は未確認。FPGA→SoCは指令だけという制約を維持する。

coordinatorがRF poll・bank公開/回収・両SPI APIを所有し、worker ID 0/1がpackingを分担する。2026-10-26時点ではcore0がcoordinator＋worker0、core1がworker1という実task entryと静的生成関数を追加済み（[最新の起動・停止/SDK証拠](../s3-raw-tasks/README.md)）。`s3_raw_probe/main/raw_probe.c`は引き続きlink-only診断で、実taskと生成経路を保持する。app_mainはRF/PHY/SPI/taskを起動しない。SoCが梱包だけを担当する、あるいは完成済み受信firmwareがある、とは説明しない。

## 完了時刻確認APIを追加した段階の記録（以降の数値は当時の版）

現在の時計接続・task配置・メモリ値は上記の最新報告を参照。以下の未実装という記載や旧CPU模型は、APIを追加した当時の状態を記録したもので、現在の採用判定へ流用しない。

### 当時追加した完了時刻の確認

従来の`s3_pp_step(now,bound,...)`は開始時に`now+bound < deadline`を確認するが、実行後の時計を読まない。呼出側が真のWCET上限を供給する契約が満たされれば整合する。一方、実測・統合途中でboundを超えて最後のsliceがDONEになった場合、後のcollectは「未完了job」だけを期限確認するため、完了した遅延を検出できない。これをWCET実証や実装済みの超過検出と混同しない。

`s3_pp_step_clocked()`を追加し、開始時とsource読み出し後にcallerの共通時計を読む。時刻の後退、観測区間のbound超過、bank deadline到達/超過でfaultを公開する。**終了時刻の確認前にDONEを公開しない。** coordinatorがDONEを観測するとbankを再使用できるため、公開後に遅延を検査する実装では遅い。

fault時はjobをDONEにせず、bank所有と出力領域を保持する。書込み済みpayloadが存在してもcollect/送信へ公開せず、再試行や自動再利用をしない。全workerが時間内に完了していれば、collectが遅いだけで完了を期限違反に変えない。既存のcaller提供boundを使うAPIは比較と既存呼出用に保持する。

新APIもclock callbackのepoch/単位・core間共通性を証明しない。native取得はまだcore別cycle counterを相対拡張しており、`esp_timer_get_time`の絶対µs値をそのまま混ぜてはならない。callback返却後・DONE公開等の費用、時刻の量子化誤差を含む全関数WCETも未測定。測定した2時刻の間隔と全関数WCETを同一視しない。新APIはlink-only診断で保持するが、実taskからの起動はまだ行わない。

## 検証と費用

[ホスト試験](host-tests.log)は新規1＋既存4 unittestすべて合格。新規試験では最終slice/部分sliceの期限到達・超過、deadline前でもbound超過、時計後退、時間内完了後の遅いcollect、事前拒否時の未書込み、null clockを実C＋UBSanで確認した。時刻は90,000,000,000をepochとする人工単位で、実RFのWCET値ではない。

さらにpost-read時計callback内へcoordinatorのcollectを割り込ませ、最後のworkerが時刻確認前にDONEを公開していないことを検査した（[強化試験ログ](publication-interleave-tests.log)）。作業用copyでDONE公開を時刻確認前へ移す故障を注入すると、bankが早期回収されるassertで失敗し、本番コードでは通過した（[mutation記録](mutation-check.json)）。既存の正例だけで公開順序を検証したことにはしない。

実SDK build commitは`db2a9399410830a03369b46d6fd2a905f7e1acf5`。[比較CI](https://github.com/kazuki0824/tangviterbi/actions/runs/40095592387)は成功。コード/anchor追加後の2構成で40＋45＝85静的チェックが合格した。clocked APIと共通実装関数のIRAM配置も確認。[実ELF/map/config/log](sdk/)、[artifact digest](provenance.json)を保存した。

raw専用版の`_iram_end`は0x40387700→0x40387800、`_heap_start`は0x3fcac440→0x3fcac540となり、追加内部RAM費用は256 B。state/buffer/stackのサイズは前回と一致する。[既知起動再生](startup-replay.json)は対照8＋専用8の16ケースをすべて実行し、専用版8/8が通過（元main 8,704 B含む）。[SPI配置監査](isr-placement.json)も26/26通過、当該SPI/heap依存条件に適合した。

[動的費用台帳](runtime-memory.json)の19チェックも合格。既知費用控除後の残量上限は較正中15,740 B、較正後17,612 Bへ更新する。前回17,868 Bから追加256 Bを控除した値で、他startup/PHY内部確保・断片化等は未計上。実利用可能量の下限ではない。

### 時計読出しの費用をゼロとしない

[旧core別計算](../s3-batch-bank-closure/README.md)を有理数で再計算すると、SのRF費用を理想的に均分・両SPI APIをcore0所有とした模型のcore0占有は99.528605%、余裕1,131,347.65625 cycles/s。RF poll/sentinelまで均分できる証拠はなく、この余裕自体が実装保証ではない。

S40 MSa/sでpairを半分ずつ処理する場合、各coreは10M pair/s。1sliceをP pair、1時計readをC cycle、その他追加費用をH cycle/sliceとすると、旧模型の他費用を同じとし、この2readとHを別に加える場合の追加費用は概算`(10M/P)×(2C+H)` cycles/s。末尾の短いslice、空jobへの呼出し等で費用は増える。

| P pair/slice | 他の追加費用をゼロとした時計1readの予算上限 | 仮に8 cycles/sampleの場合のpacking単独時間 |
|---:|---:|---:|
| 64 | 3.6203 cycles | 4.2667 µs |
| 128 | 7.2406 cycles | 8.5333 µs |
| 256 | 14.4813 cycles | 17.0667 µs |
| 512 | 28.9625 cycles | 34.1333 µs |
| 1024 | 57.925 cycles | 68.2667 µs |

[計算入力・式・結果](clock-budget.json)。大きいsliceなら時計費用を薄められるが、最後の行は旧模型のS poll許容50 µsをpacking単独で超える。小さいsliceも他処理/割込み/実時計費用を加えた期限確認が必要。どの行も実測合格・採用案ではない。新API追加後も以前のCPU占有率がそのまま成立するとは扱わない。

## 残作業

全SoC責務を同じruntimeへ統合する作業、共通時計/量子化・core別WCET、全startup/PHY内部heap、実RF品質、FPGA全資源/STAと同時RF→TSが残る。[全分担・資源期限・交換情報・通信候補](../partition-recheck-20261023/README.md)の性能→通信路→採用の順序は継続し、正式採用0件。

今回の保存単位は、全SoC責務の明示と、時計callbackを使うworker部品の公開順序・実リンク・起動確保列まで。同じepoch/単位の時計をnative取得と両coreへ結び付けるruntime統合はまだ行っておらず、この部品の試験結果を全実時間成立と混ぜない。全依頼の完了・探索終了ではない。

再現:
```sh
PYTHONPATH=tests python -m unittest test_s3_parallel_deadline test_s3_parallel_pack -v
python ci/s3_raw_probe_build.py --flash-mb 16 --late-stacks --no-phy-nvs --raw-only-spi
python ci/s3_tlsf32_replay.py --tlsf-source build/tlsf --input-root reports/s3-soc-roles-and-deadlines/sdk --profile n16r8-late-stacks-no-phy-nvs --profile n16r8-late-stacks-no-phy-nvs-raw-only-spi --output build/clocked-startup.json
```

## 続検算：IQ送信の費用と、均等packingの偏り

信号処理上のSoCの役割はIQ取得・無損失packing・送信である。ただしCPUが全bitをSPI端子へ書き続ける方式ではなく、SPI送信はDMAに任せる。CPUにはRF bank管理、32bit格納sampleから20bit/sampleへの無損失packing、DMA取引管理が残る。Sは40 MSa/sなので、RF rawの32bit/sample読出しは160 MB/s、packed出力は100 MB/s。これは必要データ量であって、内部bus利用率や実CPU時間の測定ではない。追加間引き・再量子化はしない。

現 `s3_pp_accept` は `cut=pairs/2` でpackingをほぼ均分する。RF bank準備・切替は `s3_native_poll` 内で同期実行し、SPIもcoordinator所有の想定である。この実装に「RF集約費用全部を均分」した99.529%を転用できない。

[再現計算](../../experiments/s3_pack_owner_budget.py)と[結果](owner-budget.json)では、旧RF集約費用を保存し、packingを8 cycles/sampleと仮定、残額をすべてcoordinatorに課金した。**残額は実測済みの直列処理内訳ではない。** 旧集約値から差し引いた未分類の費用であり、この配置は感度条件である。SPIは32 KiB/API、20 µs activeの旧条件を保持する。

| 条件 | T core0 / core1 | S core0 / core1 |
|---|---:|---:|
| packingのみ半分ずつ、残額＋両SPIはcore0 | 53.015% / 26.667% | **126.286% / 66.667%** |
| packing比率で両coreを均衡（未実装） | 39.841% / 39.841% | 96.477% / 96.477% |

Sのこの模型ではworker1にpackingの**69.715%超～75%未満**を配分する必要があり、均衡点は72.357%。そこでの残予算は各core **8.456 Mcycles/s**。実時計・slice管理・割込み・メモリ競合など、旧費用に含まれると確認できていない処理をここへ計上する必要がある。有限bankの丸め、slice期限、RF poll間隔、実driver待ちを含む実行可能scheduleではまだない。均等packing案のこの条件での超過を、全分担の不可能性とはしない。

6件の独立算術チェックを累積実行し合格（旧集約値との一致・均衡式・配分区間の存在）。source SHA256を結果に保存。実装を無根拠に72.357%へ固定する変更はしていない。次のCPU見積もりは、実kernelのpacking費用と直列費用を分離し、その値でworker配分・clock費用・期限を結合する必要がある。RF取得品質、全runtimeメモリ、実配線、全FPGA資源/STAも未完了であり、採用件数は増やさない。

再現：`python experiments/s3_pack_owner_budget.py --output build/owner-budget.json`

## 2026-10-25：前処理比較を一巡し、実packing命令列へ移行

[比較の区切りと全残作業](../s3-preprocess-break-even/COMPARISON-STATUS.md)を確定。raw最良の普遍的証明を待たず、raw案自身の各core期限・実費用の確認へ戻る。

[既存packingのtarget監査](pack-instructions/results.json)では、実際の `s3_parallel_pack.c` をESP32-S3 GCC14.2のO2/Osでcompileした。両方とも `pack_eight` は8sample当たり39命令（4.875命令/sample）、入力8word load・出力5word store・literal load2件。理想1命令/cycleならT78/S195 Mcycles/sである。

これはfreestanding relocatable objectの関数単体で、全SDK link・IRAM配置・実機計測をやり直した結果ではない。callerのcall、fast path判定、境界slow path、bank/slice管理、clock、メモリ待ち・競合・割込みが費用外。旧8 cycles/sample仮定を実証したとも、4.875 cycles/sampleのWCETへ更新できたとも言わない。旧owner-budgetの残額へ機械的に足引きせず、次にcaller経路を実装に対応させる。

[再現script](../../ci/s3_pack_instruction_audit.py)、[O2命令列](pack-instructions/O2.dis)、[Os命令列](pack-instructions/Os.dis)。packing/clocked deadlineと既存前処理比較の[8 unittest](pack-instructions/tests.log)に合格。新しいraw採用判定、core均等配分の是認は行っていない。
