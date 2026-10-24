> 続行結果：[実SDKリンクと起動RAM配置の比較](../s3-raw-sdk/README.md)。N8R8/N16R8でリンク確認。BSS stack案は起動容量NG、late stack案は容量必要条件まで通過。実runtime統合・WCETは未確認です。

# ②：2worker無損失packing・RF bank所有権・SPI leaseの実装

前回 `9a1a397` の32 KiB通信実装に、**2worker packing、native RF bank受渡し、SPI送信完了までのlease管理**を接続した。ホスト上の並行動作とS3向けコンパイルは合格した。**実機の2コア性能・内部RAM配置・全FPGAの成立は未確認で、性能合格→正式通信路割当→採用は0→0→0を維持する。** ①は変更しない。

## 実装した責務分担

| 実行主体 | 責務 | 所有権と制約 |
|---|---|---|
| coordinator（想定core0） | RF poll・sentinel準備・bank受渡し・出力予約・完了収集・両SPIのsubmit/reap | bank/schedulerの管理情報はこの所有者だけが変更 |
| worker0（想定core0でcoordinatorと交互実行） | 各bankの前半pairをpacking | 同じworker IDを同時に2か所から呼ばない |
| worker1（想定core1） | 各bankの後半pairをpacking | worker0と出力byte範囲を分離。payload書込後にrelease公開 |
| SPI2／SPI3 DMA | 公開済み32 KiBを送信 | queue完了ではなくreap成功後にlease完了。2port逆順完了に対応 |

ホスト試験はcoordinator＋2workerの3スレッドで競合を検査する。S3に3コアを要求する実装ではなく、core0のcoordinator/worker0を時分割する予定。ただしFreeRTOS task実装・配置・poll頻度・時間保証はまだ提供していない。

`s3_parallel_pack` は4個の独立した32 KiB内部DMA領域を受け取る。全128 KiBが一続きである必要はないが、各32 KiBは連続・4byte整列・互いに非重複でなければならない。allocatorや内部DMA属性検査はこのpackerにはなく、属性はSPI APIでも検査する。

bank内のI10/Q10を2sample→5byteで組にし、pair単位で両workerへ分ける。bank末尾に残る1sampleはcoordinatorがコピー保持し、次bankの最初のpairに含める。入力の上位12bitはnative I10/Q10外のfieldとして捨てるが、下位20bitの追加再量子化やsampleのデシメートはしない。既存8sample→20byte helperを共通headerへ移し、整列・連続領域では共有して使う。

両worker完了前はbankをreclaimできない。出力はbank順の完了prefixだけを公開し、後続SPIが先に完了しても先頭のDMA完了まではringを再利用しない。部分末尾とcarryは保持し、黙って破棄しない。BUSYは入力未受領を意味する。native RF adapterが受渡しできない場合はRFを停止し、データを飛ばして継続しない。

` s3_pp_spi_submit/reap `で前回のbulk APIへ接続した。prepare/queue失敗時はfaultを保持し、取得済みbufferを勝手に返却しない。復旧はRF停止・両worker終了・DMA停止確認後の再初期化が必要で、faultが立っただけでDMAを停止したことにはしない。

## 検証

[26チェック・hash・targetサイズ](results.json)、[実行ログ](checks.log)、[前回bulk経路の回帰17試験](bulk-regression.log)。全チェックは失敗後も実行して集計する。

| 確認対象 | 結果 | 限界 |
|---|---|---|
| 実Cを2 pthread workerで並行実行、1/2/17/2000bank | OK。最大22,742,922sample、DMA 56,852,480 B＋末尾4825 Bを比較 | ホスト処理時間はS3性能に換算しない |
| ThreadSanitizer、2000bank | OK、競合報告なし | この有限実行の結果。全スケジュールの形式証明ではない |
| 片workerのみ完了、odd境界、環状入力、非連続出力arena、SPI逆順完了、stale完了、ring不足 | OK。未完了bank/未retire出力の再利用を拒否 | deadline判定の時刻は呼出側の契約 |
| native RF MMIO模型→新adapter→packing | 16/40 MSa/s模型で各80bank、2,424,832 B／2,457,600 Bを全比較 | tick=240cycles/poll、slice bound=1000cyclesはテスト値。実計測ではない |
| worker1停止 | 両rateで2bank後に取得停止、再利用前に異常検出 | 停止後の実RF電気動作は未検証 |
| 新ring→実bulk C API→SDK shim | OK、両port lease、逆順reap、queue失敗時の保持 | 実DMA/ISR/FreeRTOSではない |
| 従来native/bridge/ring/RF pumpと前回bulk17試験 | 全てOK | 既存機能の回帰確認 |
| S3用GCC14.2、SDK相当の一部flags | pack/native adapter/SPI adapter/sizeof probeをcompile、disassemble | ESP_PLATFORM・実SDK全体のlink/IRAM配置は未検証。SPI型はshim |

初回は `ATOMIC_INT_LOCK_FREE==2` が `-mdisable-hardware-atomics` と両立せずtarget compileに失敗した。faultは「最初の原因の厳密な順序付け」を不要とし、read-modify-writeを除去。状態共有は32bit atomic load/storeだけにした。最終target objectでは`__atomic`/`__sync`補助関数の参照がないことを検査し、命令列を保存した。並行fault時にどちらの非zero原因が残るかは未規定だが、fault解除は停止後のinitだけである。

S3のworker deadlineは**両coreで同じ基準の時刻**を要する。別々のcore cycle counterをそのまま同一時刻と仮定していない。共通時刻の実装・取得費用も残作業。

再現：

```sh
python experiments/check_s3_parallel_pack.py --cc /path/to/xtensa-esp32s3-elf-gcc
python experiments/check_s3_bulk_transport.py
```

後者にはIcarus Verilogが必要。target compilerは既存CIと同じesp-14.2.0_20241119をSHA256 `e3e6dcf3d275c3c9ab0e4c8a9d93fd10e7efc035d435460576c9d95b4140c676` 確認後に利用した。

## 見積もりの更新と未達

[全分担・全通信候補](../partition-recheck-20261023/README.md)と[core別条件](../s3-batch-bank-closure/README.md)を継続する。新しいデータ往復や品質低下はない。

- target ABIでpacker metadata **392 B**、追加sink **20 B**、SPI transfer **24 B×2**。前回の回収後余裕上限9524 Bからこれらを追加計上すると **9064 B上限**。旧管理objectをさらに回収できるとは計上しない。task stack・driver動的確保・連続DMA領域の配置未確認なのでRAM成立の数値ではない。
- S3 targetの共通fast helperは8sampleあたり39命令、入力word load8、出力word store5。workerのbank探索、境界処理、atomic公開、helper呼出等を含むWCETは未測定。helperの数値をworker全体のcycles/sampleとして代用しない。
- 現実装では**両SPIのAPIはcoordinator所有**。前回の「RF高費用を理想的に均等分配し、APIだけcore0」の模型を当てても99.529%／93.424%。97.460%／95.493%だったport別core案は未実装であり、現在値とは呼ばない。今回分割したのはpackingのpair数で、RF poll/sentinel/管理までCPU時間が半分になったわけではない。
- 上り帯域の前回32 KiB感度条件はS余裕15.089 MB/sを維持。API20 µs、RF CPU費用、128 KiB保持量の楽観模型は今回の実装で実測に置換していない。
- FPGA追加回路を含む全体資源・STA、K7最低周波数未達、RF/SDRAM/全段・同時TS確認は未解決。

今回Aは所有権とpayload保存を実C/host並行試験・target objectで確認した地点。Bはraw-only SDK link/実task統合・共通時計・core別WCET、および全FPGA成立検証。Aで独立した機能変更を保存する境界は妥当だが、Aで採用案確定まで完了とするのは妥当でない。SDK準備・task実装を続ける余地はあり、今回の保存を環境の強制打切りや探索終了とはしない。依頼全体は未完了。
