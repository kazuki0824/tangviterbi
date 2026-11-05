# T側前処理のnative／SDK／残存FPGA結合評価

2026-11-05。**現在のhalfband移管候補は採用しない。** 新しいSDK実リンクから算定した費用を使う有限モデルは `MODEL_NG`、同じ構造の残存FPGAではDSP削減がなく、宣言した入力stressでFIFO容量不足、補足配置配線の既知モデル経路でも要求clock未達となった。

この結論は、下記の具体的なソース・費用仮定・受付方針・FPGA構造についての判定である。**「T側の処理はESP32-S3ではどの実装でも捌けない」とは判定していない。** とくに今回のSoCモデルの停止は、処理全体の上限を使った保守的な期限受付条件による。実機の計算能力不足や、実際のraw上書きを証明した結果ではない。

## T側の判定を実装ごとに分ける

対象は構成②のT担当ESP32-S3 N16R8 1個、2 core × 240MHz。Tang Nano20KとT/S各1個のS3による同時受信構成を前提とし、FPGA→SoCは制御のみ、品質を落とす追加decimation／再量子化は採用しない。

| 評価した実装 | 判定 | 根拠と適用範囲 |
|---|---|---|
| 既存QACC＋scalar prepare | NG | prepareの書込みだけで520.126984 Mcycles/s以上、2 coreの理想480 Mcycles/sを超える。[先行評価](../s3-t-preprocess-capacity/README.md#2-qacc未計上だったprepare-cだけで上限を超える) |
| 既存ACCX＋今回のmirrored-history C caller | NG | 最良Osでも入力処理・call・kernelだけで483.809524 Mcycles/s以上。[先行評価](../s3-t-preprocess-capacity/README.md#3-accxkernelだけでなくcallerを接続して判定) |
| 今回の31tap halfband・2 core分担＋native／SDK | MODEL_NG | 新しい費用台帳と同じC制御を使うモデルで、指定した受付条件を継続できない。[詳細](runtime/README.md) |
| このhalfbandを前段に置いた残存FPGA | REJECT | DSP4→4、FIFO込みBSRAM2→3、宣言した無間隔入力で損失、既知timing経路もclock未達。[詳細](quality-fpga/README.md) |
| 別のT実装、受信機全体、T/S同時受信の実機成立 | 未認定 | 今回の具体的候補の不採用から、全方式の不可能性は導けない |

QACC／ACCXの表は既存の実命令列に基づく先行判定を参照している。以下は今回新しく再構成して実行した結合評価であり、先行する外部処理予算だけの有限モデルをSDK結合の合格として流用していない。

## 評価したデータ経路と実ビルド

S3で16 Mcomplex/sのI10/Q10入力を31tap halfbandにより8 Mcomplex/sへ変換し、I16/Q16をFPGAへ送る診断候補である。FPGAは64/63の残存変換を行い、出力は512/63 Mcomplex/sとなる。出力転送は32 MB/sで、packed raw20の40 MB/sから20%減る。この転送量削減を、FPGAのDSP削減や元受信機との品質等価の証拠にはしない。

| 接続条件 | 今回の値 |
|---|---|
| halfband分担 | 1024 raw sample/block、64µs周期、入力側32出力／worker側480出力 |
| 算術 | halfband shift10、I16/Q16診断出力、pipeline 2 slots |
| DMA | 内部SRAMの16KiB frame × 8、SPI driver queue depth2 |
| SPI | 80MHz、data4線、command16bit＋address64bitは各1線 |
| 16KiBのwire時間 | data98,304＋header240＝98,544 CPU cycles、240MHzで410.6µs。service間隔は別計上 |
| SDK | ESP-IDF v5.5.1、commit `fcae32885b0296b32044cb99ecbdc50d98dddb83` |
| Compiler | GCC14.2.0、`esp-14.2.0_20241119` |
| 提供ELF SHA-256 | `41a01f1a76c3879f0b3757f2bd2b307d0f9977655c3e9ce293562dcf7f5f821c` |

[SDK説明](sdk/README.md)、[実リンクのprovenance](sdk/provenance.json)、[静的監査](sdk/audit.json)に、実際の入力・配置・CP3・起動停止・cache条件を保存した。完全なdebug ELFも分割gzipとして保持し、symbol ELFと全allocated sectionの内容・アドレスを照合している。`app_main`はlink-onlyであり、RF／SPI／taskを実機で開始してはいない。

SPIの旧モデルは80bitのheaderまで4線と数えていた。固定SDKの実装は`SPI_TRANS_MODE_QIO`だけなので、command/addressは1線である。現在のモデルは98,544 cyclesに修正し、実際にscheduleされたlaunch→wire completionの間隔も各行で検査する。

## SoC有限モデルの結果と読み方

[costs.json](runtime/costs.json)は36種類の費用を現在のELFから算定し、193条件を確認した。経路・呼出先・命令対応・IRQ証拠は、同じELFに結び付けた[cost-evidence.json.gz](runtime/cost-evidence.json.gz)に保存した。費用は `max(ceil(1.1 × 命令数), 明示した制御／依存費用)` という宣言モデルであり、cache、MMIO、bus競合等を含む実機WCETではない。

[実行結果](runtime/results.json)は19基本シナリオに上限感度・prepare感度を加えた21シナリオを実行し、28条件すべてを検証した。回収済みのowner制御Cをそのまま使い、native・adapter・pipelineへの計測hookは生成コピーだけに挿入した。出力は独立31tap畳み込みと照合し、解放後の入力bankを破壊しても全観測が変わらないことを確認した。

| シナリオ | 受け付けたbank数 | 生成した1024入力block数 | 結果 |
|---|---:|---:|---|
| 8 bankの短い観測窓 | 8 | 83 | 観測窓のみPASS。全入力処理・DMA drain完了ではない |
| 理想時計、追加stallなし、100 bank要求 | 25 | 294 | 期限受付条件で停止、MODEL_NG |
| clock errorの下限240 cycles | 19 | 220 | 同じ期限受付条件で停止 |
| モデルから導いた上限17,791 cycles | 25 | 294 | 上限を20,000から下げても同じ受付条件で停止 |
| prepare予算を1反復1024 wordsへ変更する感度試験 | 31 | 371 | 次bankの準備不足で停止 |

**期限受付拒否と物理的な処理不能は区別する。** 理想時計の停止時は残余11,084 cyclesに対し、宣言した処理全体の上限20,000 cyclesを確保できないため拒否した。一方、その時点の具体的な次経路を基本料金だけで見た反実仮想では、処理全体3,242 cycles、該当bankのsource解放まで1,014 cyclesである。clock error240のケースも、残余19,618に対し基本料金の処理全体12,923、source解放662である。

これらの反実仮想は割込みと追加stallを除くモデル内の数値であり、実機時間の下限・上限ではない。したがって、この結果を「source解放が必ず期限に遅れる」「S3は必ずrawを上書きする」という証明に使わない。現在の受付方針と費用を持つ候補が継続条件を満たさず、採用根拠にならないことを示している。

17,791 cyclesは最大6個のcopy chunkと、その間のSPI／tick各1回を含むこの離散モデル内の包絡である。未計上のISR/NMIや物理stallを含む上限ではない。単純に受付値を小さくすること、pollingやpendingの課金を固有CPU使用率とみなすこと、8 bankの受付だけを全処理完了とみなすことは行わない。詳細なstop分類、解放時刻、費用台帳、感度試験は[runtime説明](runtime/README.md)にある。

## 残存FPGA、品質、タイミング

[FPGA統合評価](quality-fpga/README.md)は、保存済み4構成の12ネットリストをhashで固定して再集計し、stream・品質・timing coverage・新しい補足routeを実行した。

- 同じRTL構造のFIFOあり比較で、DSPは4→4、BSRAMは2→3。前段halfbandを移しても、この残存32tap構造のDSPは減らない。
- 512µs周期の8フレームは32,768入力を無損失で受け付け、FIFO最大438。宣言した無間隔の2／8フレーム論理入力では4,798番目から損失する。後者は**パーサー後の論理入力stress**であり、SDKのheader・IRQ・フレーム間隔を含む正確な統合波形の観測結果ではない。
- 診断係数について、全位相・全対象image、12入力profile、独立整数oracle、厳密なfloor誤差上限と任意signed10入力の無飽和条件を検証した。元receiverの係数・出力契約・MER/C/N/BER受入基準は確認できず、品質等価はUNVERIFIED。
- 固定2026-10-04／2026-11-03の両nextpnrにDSP timing modelがない。新版はLUT1/2/3を追加しているが、積registerのD endpointは0/128のままである。
- 新版で同じresidual＋FIFO netlistを再配置配線すると、既知モデル経路は約7.635ns、130.975769MHzで、要求154.285706MHzに未達。完全な物理STAを合格とする根拠もない。

native／SDKの有限モデルとFPGAのpost-parser検証は、それぞれ明記した境界の評価である。RF入力からT/S同時TS出力までの実機受信認定とは扱わない。

## 静的確認と回帰検証

| 確認対象 | どこをどう確認したか | 結果 |
|---|---|---|
| native入力 | 回収Cとの一致、独立畳み込み、全1,023分割と全1,023折返し、所有権・tail・異常停止 | [36条件PASS](native/results.json)、7単体テストPASS |
| SDK | ソース27項目、11 compile unit、固定設定、ELF全分割片、ABI、SRAM/DMA配置、起動停止、CP3／cache条件 | [202条件PASS](sdk/audit.json)、4異常入力テストPASS |
| 実命令費用 | 現在のELF・ROM、呼出先、論理命令対応、copy全1〜1024 words、IRQ／tick、36必須費用、入力hash | [193条件PASS](runtime/costs.json)、実バイナリを使うものを含む5テストPASS |
| native／SDK実行モデル | 同じC制御、UBSan、独立出力oracle、入力破壊、source／DMA保存則、実wire間隔、故障注入、全証拠の結合 | [28条件PASS](runtime/results.json)、12単体テストPASS。候補はMODEL_NG |
| FPGA統合 | 各報告の全条件名、現在ソース、12 netlist、全stream／CSVの圧縮前後hash、全位相とimage、route／timing対応 | [657条件PASS](quality-fpga/audit.json)。候補はREJECT |
| FPGAの異常入力継続性 | 1 netlist欠落、全証拠欠落、独立3報告欠落、ゼロ係数、RTL tool欠落 | [5シナリオ・27条件PASS](quality-fpga/audit-robustness.json) |

これらのPASSは検証の実施・証拠整合性に対する判定であり、候補のMODEL_NG／REJECTや物理条件のUNVERIFIEDを合格へ変更しない。静的監査はfail-fastにせず、欠損時にも全必須条件を列挙し、独立して確認可能な項目を続行する。入力不足を容量NGと取り違えない。費用・ELF・SDK監査・経路証拠の必須hashが欠けた場合、最終runtime判定はBLOCKEDとなる。

## 再実行

[専用GitHub Actions](../../.github/workflows/t-preprocess-integration.yml)に、host／SDK／FPGAの3 jobを用意した。

| job | 実行内容 |
|---|---|
| host | native・runtime・SDK・費用の単体テスト、native監査、係数復元照合、保存CADの資源再集計 |
| SDK | 固定IDFから新しいELFをbuildし、そのELF・設定・provenanceをSDK監査→費用算定→strict runtimeへ明示的に渡す。実バイナリを使う費用異常系も全5件実行 |
| FPGA | SHA256固定の2版CAD suiteを取得し、stream、品質、契約資料、chipdb／endpoint、新しい補足route、657条件監査と欠損回帰を実行 |

各jobは独立した検査を途中で省略せず、失敗を集計して最後に終了コードへ反映し、作成できた証拠をartifactへ保存する。変更していない元の4 CAD構成を再合成したとは扱わない。SDK／runtimeの新しい出力先は`build/t-preprocess/`で、保存済みの成功結果へのfallbackや`--allow-provisional`を使用しない。

手元の詳細コマンドと必要な固定ツールは[SDK](sdk/README.md)、[runtime](runtime/README.md)、[FPGA](quality-fpga/README.md)、[timing](quality-fpga/TIMING-COVERAGE.md)の説明にある。

今回のソース・解析・ELF・報告は現在の入力から新しく作り直したもので、失われた旧成果物と同一bytesであるという主張はしない。[旧技術報告](../s3-t-preprocess-integration/README.md)は過去の観測として残している。受信機としての採用には、実RF／割込み／通信を含む時間上限、元方式の品質受入契約、DSPを含むSTA、T/S同時受信の端点確認が別途必要である。
