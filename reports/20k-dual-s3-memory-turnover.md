# 第1項目の継続：SDRAM転送間の待ちを削減

前回 `048b8cb` の実S競合で発生した期限・64 KiB違反を、同じ要求列・配置・入力精度・FIFO容量で再検証した。完了時に次要求を受理するcontrollerへ変更し、128-frame条件の待ちpayloadは201,792 Bから5,824 B、T期限違反は59,798件から0件になった。**これは記載した有限試験での改善であり、第1項目全体の完了ではない。T grouping/reorderと実capture/outputはまだ試験要求列である。**

前回の不合格によってcontrollerの手直しは実際に増えた。「作業範囲は同じ」と「残作業量が増えていない」は異なる。今回、その手直しを先に行った。

## RTLの変更と保持条件

`dual_sdram_burst.sv`で、open-pageのREAD最終beatまたはWRITE回復完了時に応答を提示し、受理された同じedgeで次のBL8要求を取り込む。最短要求間隔は12から11 memory clocksへ減る。tRCD/tRP/tWR/tRFC/CLと135 MHzの設計条件は変更していない。

応答先がそのedgeで停止した場合は応答をregisterへ保存し、次要求を受理しない。保持中はデータを変更しない。refreshは保留応答と独立して継続する。独立SDRAM端子モデルでデータ・byte mask・方向切替・row衝突・refreshを照合し、完了edgeでの連続受理と停止を追加試験で実際に通した。

単体の同一row連続転送は約354.121から385.338 MB/s、Mode 3 FFT順のbacklogged転送は約333.632から362.033 MB/s。これらを全アクセスの保証帯域に読み替えない。

- [単体controller結果](20k-dual-s3/memory-turnover/pipeline-sdram.json)
- [完了edgeでの停止・長時間停止結果](20k-dual-s3/memory-turnover/pipeline-stalls.json)
- 既存vector交換の全開始offset・masked write・端子モデル試験2件も通過。

## 実S・FFT・T/IO要求列の競合

| 条件 | FFT frames / S SF | 最大FFT µs / 期限 µs | 最大待ちpayload B | 全client期限違反 |
|---|---:|---:|---:|---:|
| [Mode 1 最大平均traffic](20k-dual-s3/memory-turnover/pipeline-real-s.json) | 128 / 3 | 219.940202 / 259.875 | 5824 | 0 |
| [Mode 1 T/IO半周期ずらし](20k-dual-s3/memory-turnover/pipeline-phase-long.json) | 128 / 3 | 219.344481 / 259.875 | 5920 | 0 |
| [Mode 2 最大平均traffic](20k-dual-s3/memory-turnover/pipeline-mode2-long.json) | 64 / 3 | 426.221124 / 519.750 | 2624 | 0 |
| [Mode 3 最大平均traffic](20k-dual-s3/memory-turnover/pipeline-mode3-long.json) | 32 / 3 | 853.106004 / 1039.500 | 2464 | 0 |

Sは実RTLがbyte列からSDRAM要求を生成する48 active TC8PSK profile。Tはdelay別の密ring要求列、IOは従来のstaging要求列、管理は10 MB/s。全FFT binとS全byteを照合した。旧試験と同じく、S出力は1 byte / 16 memory clocksという下流サービス条件を置く。共有RSがこの条件を供給することを保証した試験ではない。

Mode 3の最初の試行は全12 FFT frameが一致した後、18.519 ms付近で旧testbench watchdogが終了した。Sの最初の再利用期限は21.608 msであり、その前に試験が打ち切られていた。S frame数に応じてdeadlock監視時間を延長して再実行した。**Sの再利用期限もFFT期限も緩和していない。** [修正前の出力](20k-dual-s3/memory-turnover/mode3-watchdog-before.txt)を保存する。このtimeoutをcontrollerの性能不合格とは数えない。

上表の4条件は計352 FFT frames／12 S super-frames。Mode 1の同条件128 framesは`048b8cb`のfixture、他3条件はwatchdog修正後のfixtureを使用した。各JSONに実行時source hashesを記録した。controller RTLは全試験で同じ。全位相の上限証明や無期限のqueue安定性は、この有限試験からは得られない。短い予備試験（48/24/12 FFT frames、各S 1 SF）も同じ証拠directoryの`pipeline-phase.json`、`pipeline-mode2.json`、`pipeline-mode3.json`へ保存した。

CIの実S・128-frame条件はデータ一致だけでなく、`FFT_deadline_pass`、`client_deadline_pass`、`staging_64KiB_pass`をすべて必須にした。過去の不合格JSONは変更しない。

## 資源と帯域上限の再計算

FFT＋memory clients＋実S DMAの接続部分を固定OSS CAD Suite 2026-10-04で合成した。**7,104 logic、4,475 FF、15 BSRAM、8 DSP**。前回比はlogic +41、FF +1、BSRAM/DSPは同数。刺激・観測回路込みの部分topであり、全受信機の資源値ではない。[合成logとsource hashes](20k-dual-s3/memory-turnover/synthesis/summary.json)。

今回の応答経路には最終DQ beatから応答先までの組合せ経路がある。135 MHz達成や全経路STAは未確認であり、cycle精度のシミュレーション成功を物理タイミングの成功とはしない。

最短11 clocksと1053 clocks以内のrefresh予約13 clocksに基づく楽観的な持続帯域上限は、355.555556から **387.878788 MB/s** になる。旧12-clock controllerに対する棄却証明を、新controllerへ転用しない。[全13,260構成の再計算](20k-dual-s3/memory-turnover/memory-contract-v4.json)。

| Mode | 入力全symbolの保存・再読出し込み MB/s | 入出力両方の保存・再読出し込み MB/s |
|---|---:|---:|
| 1 | 380.040481 | 437.668186 |
| 2 | 356.521481 | 414.149187 |
| 3 | 344.761981 | 402.389687 |

入力側だけのstagingは、この必要条件だけでは全Modeとも棄却できなくなった。ただし出力順復元を含まず、採用可能とはいえない。入力・出力両方で全symbolをSDRAMへ保存して読み直す具体的方式は、row missや制御待ちを無視しても全Modeで上限を超えるため棄却する。他のgrouping/reorder方式まで不可能としたものではない。[計算・判定・依存hash](20k-dual-s3/memory-turnover/reorder-admission-v2.json)。

## 第1項目の完了条件は維持

| 前回からの完了条件 | 今回の到達状態 |
|---|---|
| 実clientの接続 | Sの限定profileは前回実装済み。T grouping/reorder、実capture/output所有権、SのTMCC連動slot制御は未完了 |
| producer有限保持と全体資源 | 現要求列の64 KiB違反を記載試験で解消。実T/IO producerの保持回路と重複を除いた全体資源台帳は未完了 |
| 待ち時間・長期安定性 | 旧反例を同条件で解消し、位相変更・他Modeを追加検証。全client・全位相・最大burstの上限証明は未完了 |

共有RSの第2項目には進んでいない。全体P&R/STA、S3実driverとWCET、RF/連続TS実測も従来どおり後段に残る。正式通信割当・受信機採用は0件のまま。

再現例：

```sh
DUAL_SDRAM_PIPELINE_REPORT=build/dual-sdram-pipeline.json python -m unittest discover -s tests -p test_dual_sdram_pipeline.py -v
DUAL_TRACE_REAL_S=3 DUAL_TRACE_FRAMES=128 DUAL_TRACE_MODES=11 DUAL_TRACE_LAYERS='[[3,4],[3,8],[7,16]]' DUAL_TRACE_REPORT=build/dual-s-frame-fft.json python -m unittest discover -s tests -p test_dual_memory_trace.py -v
DUAL_TRACE_REAL_S=3 DUAL_TRACE_FRAMES=32 DUAL_TRACE_MODES=13 DUAL_TRACE_LAYERS='[[3,1],[3,2],[7,4]]' DUAL_TRACE_REPORT=build/dual-s-mode3.json python -m unittest discover -s tests -p test_dual_memory_trace.py -v
DUAL_TRACE_REAL_S=3 DUAL_TRACE_FRAMES=64 DUAL_TRACE_MODES=12 DUAL_TRACE_LAYERS='[[3,2],[3,4],[7,8]]' DUAL_TRACE_REPORT=build/dual-s-mode2.json python -m unittest discover -s tests -p test_dual_memory_trace.py -v
# 位相変更条件は最初のMode 1コマンドにDUAL_TRACE_PHASE_DIV=2を追加する。
python ci/dual_memory_clients_evidence.py --yosys /path/to/pinned/yosys --components s_clients --output build/dual-turnover-synthesis
```
