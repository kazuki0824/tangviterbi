# T FEC＋実PSRAM/SPI経路の共配置

2026-10-11。実装済みT Viterbi/tracebackとRSを、物理PSRAM PHY・SPI2/3
受信経路・page queueと同じnetlistへ合成した。FIR、同期/GI除去、FFT、
等化/デマップ、全インターリーブ、TS制御は含まない。FECは独立の合成負荷で、
RFからTSへ接続した受信機ではない。

| 実装 | logic位置下限 / 8640 | FF | BSRAM / 26 | 配置・90 MHz |
|---|---:|---:|---:|---|
| 通常RS保存 | 9001（104.178%、361超過） | 3913 | 8 | 下限超過のため配置を省略。exit126 |
| BSRAMへRS保存圧縮 | 8605（99.595%、残35） | 3705 | 10 | seed1、180秒で探索中断。exit124、合法配置・Fmax不明 |

下限はLUT/ALUと同居可能なFFを最大限共有させ、CE/reset/近接制約を無視した
楽観値である。通常版の**このmapped netlist**は収容不可。圧縮版で下限を通っても
収容可にはならない。180秒中断は計算機の探索時間上限で、受信処理の期限違反ではない。
別の通信endpoint、RTL構成、FFT配置まで不可能とは判断しない。

旧18 BSRAMのFPGA FFT予算をそのまま追加する場合、通常版26、圧縮版28 BSRAMとなり、
後者は26を超える。FIR/同期や仲裁は更に必要。ただし、これは選んだ保存構成の容量検算であり、
FFTの新規メモリ再利用設計や別endpointを除外する普遍的下限ではない。

Tの保守FEC到着率はViterbi25.212 Mstep/s、RS15,448.604 CW/s。
2 clocks/stepのViterbiは90 MHz時の処理能力45 Mstep/s、clock時間占有56.027%。
圧縮RSの2667 clocks/CWは41.201426 MHz相当、90 MHz時45.779%。
独立stageの時間容量が足りても、実クロック・入出力停止・全体資源・共有メモリ仲裁の
保証は別に必要である。

測定したRS RTLそれぞれに独立encoderの262符号語、0〜8 byte誤り、dirty resetを適用。
T Viterbiは外部encoder、無限精度metric oracle、unknown-state/reset/stall試験に合格した。
生成RTLと測定sourceのhashを保存する。

再現：`python ci/s3_t_fec_evidence.py`（OSS CAD Suite 2026-10-04とIcarusが必要）。
[結果と全ログ](s3-t-fec-evidence/results.json)、通常/圧縮それぞれの生成RTL・合成・配置ログを同梱。
`whole_receiver_resources_verified=false`、`receiver_adopted=false`を維持する。
