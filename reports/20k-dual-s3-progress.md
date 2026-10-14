# 20K＋S3×2：共有RS実装とFFT期限の追加検算

**後続更新：[FFT・SDRAM実装と部分配置配線](20k-dual-s3-fft-sdram.md)。以下の19,052 logic等は共有RS追加時点の履歴。現在のallocationと実装結果は後続更新・主報告を参照。**

PR #6の継続作業。2026-10-14 JST。入力となる初回見積もりは`e388f88`。
**共有RSの仲裁RTLを追加し、旧BSRAM予算とSDRAM効率55%の仮定を修正した。受信機全体の採用はまだ0件。**
通信条件はnative I10/Q10の無損失転送のままであり、SoCによる追加間引き・再量子化は導入していない。

## 1. 共有RSの実装

[dual_shared_rs.sv](../rtl/dual_shared_rs.sv)はT、S、S-TMCCの3入力をコードワード単位でround-robin仲裁する。
修正版生成器`experiments/s3_rs_isdb.py`を使う。未修正の`rtl/rs204_188_compact.sv`とのリンクは禁止。

- T/Sは204バイト入力・188バイト出力。TMCCは64バイトの前に140バイトの0を付け、出力の先頭140バイトを除去して48バイトを返す。
- GF(256)、0x11d、α=2、根α^0…α^15、先頭高次係数という規約を独立の多項式除算encoderで検査する。
- grant時に出力188/188/48バイト分のcreditを予約する。出力にreadyはなく、開始後は止めない。
- pendingは「コードワード全体が取得済み」、grant後はsource_readyの全クロックで有効バイトを供給する契約。SDRAMから1バイトずつ直接返せるという意味ではない。
- 入力は最低2672クロック間隔で開始する。既存decoderの2667クロックにwrapperの選択・回復を含める。162 MHzなら16.493827 µs/word。T＋Sピーク＋TMCCの占有は約84.252%。
- source ID、先頭・末尾、decoderのfailを出力へ付ける。resetで進行中のwordを中止する。8バイト超の誤りをすべて検出する保証はRS符号自体にもない。

これはRSサービス部分の実装であり、外部入力queue、prefetch DMA、出力FIFO、TS serializer、TMCC全体の復調・解釈は未接続である。
TMCCの規約は[ITU-R BO.1408-1](https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-1-200204-I!!PDF-E.pdf) §6の短縮RSで確認し、TMCC制御を主信号へ先行適用する時系列は引き続き受信topで検証する。

[RTL試験](../tests/test_dual_shared_rs.py)はT/S各262語とTMCC262語を混在させる。
T/Sは全204位置、TMCCは全64位置の単一誤り、さらに2～8バイト誤り、連続word、credit停止、reset中断を含む。
小テーブルをBSRAMに置く場合とレジスタに置く場合を別々に試験し、credit有無の4条件、計3144語がすべて合格した。
停止のない条件でgrant間隔は最小・最大とも2672クロックだった。
[実行結果](20k-dual-s3/shared-rs-rtl.json)にdecoder/wrapper SHAとgrant間隔を保存する。
これらは有限vectorの機能試験であり、全入力の形式証明・162 MHz STAとは区別する。

## 2. 合成で判明した予算の不足

GW2A向け`-nowidelut`で共有wrapperと修正decoderを合成した。
使用ツールはYoWASP/Yosys 0.70、git `28ba3cb92`。過去の0.69測定とは別測定として記録する。
[合成結果とSHA](20k-dual-s3/shared-rs-synthesis.json)、[再現スクリプト](../ci/dual_shared_rs_evidence.py)。

| 修正版の実装 | LUT1～4 | ALU | FF | BSRAM | logic位置の必要下限 |
|---|---:|---:|---:|---:|---:|
| 小テーブルをBSRAM | 1548 | 154 | 847 | **4** | 2043 |
| 小テーブルをレジスタ | 1744 | 157 | 1055 | **2** | **2450** |

小テーブルBSRAM版の4ブロックは、CW RAM、逆元ROM、Omega、error table。
旧予算「共有RS全体2 BSRAM」はこの実装では成立しない。
レジスタ版も、旧2385 logic位置予算より必要下限が65大きい。
logic下限はLUT＋ALU＋FF−最大driver共有数であり、CE/reset、隣接配置などを無視している。合法配置を保証する数ではない。
今回の合成には入力staging、出力FIFO、SDRAM制御器、外部I/Oを含まない。

改訂案Bは**レジスタ版を優先**し、共有RS部分を2700 logic位置、1408 FF、3 BSRAMへ変更する。
3個のうち2個は合成されたcore、1個は連続供給に必要な204バイトwordのprefetch用allocation。
queue全体をこの1個へ押し込まない。未配置の必要下限2450に250位置を加えた値は、依然として設計目標である。

| 案 | 改訂logic位置 | FF | BSRAM | DSP18 | 資源容量の一次判定 |
|---|---:|---:|---:|---:|---|
| A：独立RS | 21152 | 14186 | 47 | 38 | logic/RAM超過。旧予算からの選択を撤回 |
| B：共有RS＋tile FFT | **19052** | **13034** | **44** | **38** | 91.88% /83.81% /95.65% /79.17%。未配置 |
| C：共有RS＋常駐FFT | 18652 | 13034 | 56 | 34 | RAM超過 |
| D：共有RS＋SoC FFT | 18152 | 12522 | 40 | 30 | FPGA容量一次判定のみ。SoC WCET未達 |

独立RSは各2400 logic、1280 FF、3 BSRAMを新しく予約する設計予算であり、独立版2個を測定したという意味ではない。
44/46 BSRAMのBも余裕は2個しかない。全体の合法配置・clock・FIFO実装による増加を吸収できなければ再設計する。

## 3. 平均処理率では見えなかった到着burst

[検算器](../experiments/dual_s3_deadlines.py)はOFDMシンボルでTのCWをまとめて到着させる。
シンボル当たりのword数は小数を切り捨てて失うのではなく、累積bit数から4/5、8/9、16/17語の到着列を作る。
Sは384語/superframeの外部保持領域から、ピーク間隔28.135828 µsで供給する。TMCCは毎superframeに1語。
各modeに16位相×16 superframe×3出力時刻パターン、非preemptive round-robin、全語2672クロックという条件で検査した。

出力FIFO allocationはT=4096 B、S=1024 B、TMCC=128 B。
27/81 Mbit/sのTS排出とTMCC=1 MB/sの排出を条件とする。TMCCの1 MB/sは新しいconsumer契約であり測定値ではない。
FIFOへの出力は全payloadを一括到着させる。slot末尾固定のほか、slot先頭/末尾を交互にする2パターンも検査する。
実decoderのclean/誤り訂正で出力時刻が変わるため、固定完了時刻だけの模型を最悪burst保証とはしない。
Tは2 BSRAM、S/TMCC/controlは同じ残り1 BSRAMを分割使用する計画で、元のI/O reserve 3個内に割り当てる。
共有RAMのport仲裁はまだ実装していない。

| T mode | 全入力queueの最大待ち語数 | T/S/TMCC最大完了遅延 µs | T/S/TMCC出力最大byte | credit待ち |
|---|---:|---|---|---:|
| 1 | 6 | 164.887 /64.037 /49.481 | 648 /418 /48 | 0 |
| 2 | 10 | 296.837 /83.444 /49.481 | 1170 /460 /48 | 0 |
| 3 | 18 | 560.739 /122.259 /49.481 | 2229 /544 /48 | 0 |

Sの完了遅延122.259 µsはCW到着間隔28.136 µsより長い。有限queueで吸収するので、各CWの即時完了という主張を撤回する。
18語×204=3672 Bはdecoder以外の外部queue保持分。grantされたwordとprefetch bufferは別に数える。
TのRS前queueをSDRAMへ書き戻す場合、write＋readは約6.303 MB/sとなり、既存の「その他10 MB/s」予約へ計上する。Sは既存frame領域をqueueとして保持し、同じwordを別領域へ再コピーしない。
この位相走査は全位相・長期間の形式的上限ではなく、未計上のDMA待ちが0というサービス契約に依存する。

比較用の失敗・負担増も[JSON](20k-dual-s3/deadlines.json)へ保存した。
Sをpaceせず384語一括入場させると最大401待ち語、81,804 Bが必要になる。Sの既存frame領域から読めるようにし、小さなBSRAM FIFOへ転記しない。
T/Sの出力FIFOをそれぞれ1語だけにすると、credit待ちで16 superframe後の待ちが1546語まで増える。
「出力に1語あれば十分」という実装はこの条件で不採用。
外部sinkが無期限に停止する場合、有限bufferで無欠落を保証できないため、連続排出は受信機の契約条件となる。

## 4. タイルFFT：55%効率の仮説を棄却

前の平均帯域計算271.266 <297 MB/sだけでは、tile bufferの所有権とFFT完了期限を表していなかった。
新モデルでは2個のbufferそれぞれを **read→compute→write→再利用** とし、読み書き共有busと単一演算器の競合を追跡する。
write待ちを先に処理し、同じbufferのreadとwrite/computeを重ねない。
第1pass完了後に第2passを始める具体的schedulerである。他の全schedulerの不可能性を証明するものではない。

各passのtileは8×N2 complex、512/512/1024点。2個とも最大4 KiBで元の8 BSRAM allocationを維持する。
第2passはN1点FFTをtile当たり8/8/16列処理する。元のFFT分解、全sample、全bin、Q15幅を保持する。
SDRAM平均能力からcapture/final read、T LLR、S frame、その他10 MB/sを先に引き、残る連続サービスをtile DMAへ割り当てる。
background予約は145.174485 MB/s、tile向けは55%時151.825515、65%時205.825515 MB/s。
この連続サービス近似にはrefresh停止や非均等grantの追加遅延がないため、SDRAM controllerそのものの合格判定ではない。

| Mode | 周期 µs | 55%効率、2 buffer | 判定 | 65%効率、2 buffer | 期限余裕 |
|---|---:|---:|---|---:|---:|
| 1 | 259.875 | **265.938** | 超過 | 237.626 | 22.249 µs |
| 2 | 519.750 | 506.592 | 条件付き内 | 449.968 | 69.782 µs |
| 3 | 1039.500 | **1063.752** | 超過 | 950.504 | 88.996 µs |

このschedulerの連続サービス模型では全modeが収まる最低効率は約56.674%。停止時間等の余白を持たせる新しい設計目標は**65%**とする。
65%時の平均能力351 MB/sに対する需要271.266 MB/sの余裕は79.734 MB/s（22.72%）。
ただしこれを「実効65%を達成した」と読まない。32-byte burst、row、方向転換、refreshを含めた離散controllerの設計・試験が残る。
1 bufferの場合は今回の55/65/75%全条件で期限超過。double bufferを宣言だけで省略しない。

## 5. 次の成立ゲートと再現

今回閉じた範囲は共有RS仲裁・短縮符号の機能試験、2種類の共有RS部分合成、有限到着列とbuffer所有権付き期限計算。
未達はfixed-point tile FFT RTL、SDRAM実controllerと最大grant間隔、全復調topの接続・P&R/STA、S3のRF/packing/driver同時WCET、完成基板pin/clock、RF実機品質。
上のソフトウェア・RTL作業を「実機がないため」とは扱わない。
当初の順序①性能確認→②通信割当→③採用は維持し、通信容量だけ通る18 raw経路を正式採用へ上げない。

```sh
python experiments/dual_s3_deadlines.py --output build/20k-deadlines.json
python -m unittest discover -s tests -p test_dual_s3_deadlines.py -v
DUAL_RS_REPORT=build/shared-rs-rtl.json python -m unittest discover -s tests -p test_dual_shared_rs.py -v
python ci/dual_shared_rs_evidence.py --yosys yosys --output build/shared-rs-synthesis.json
python experiments/dual_s3_20k_estimate.py --output build/20k-dual-s3
python -m unittest discover -s tests -p test_dual_s3_20k_estimate.py -v
```

Icarus Verilog 12.0を使用。合成結果を同じ版で比較する場合は`yowasp-yosys==0.70.0.0.post1259`を用いる。
資料は初回報告のITU/ARIB/メーカー一次資料を引き続き使用し、今回の新規数値は上のスクリプトから生成する。
