# S3-N16R8 + Tang Nano 9K：論理削減と内部SRAM再利用案

対象は ESP32-S3-WROOM-1U-N16R8。T と legacy ISDB-S は同時実行せず、Tang Nano 9K 基板の外付け SPI NOR に保存した別々のビットストリームへ切り替える。両方式の制御ファームウェアは同居させる。追加のソフトウェア間引き・再量子化は行わず、RF I10/Q10 は情報を落とさず20 bitへ梱包する。

**結論：実装候補を具体化したが、受信機としての成立判定は未達。** 面積の部分合成、通信の容量計算、物理容量だけのSRAM計算を、実機のリアルタイム保証と区別する。

## 分担とモード切替

| 方式 | SoC担当 | FPGA担当 | TS出力 |
|---|---|---|---|
| T / S3-T-004/v0 | RF取得・制御、無損失梱包、8192点Q15複素FFT・並べ替え | FIR/レート変換、同期/GI切出し、等化・デマップ、時間デインタリーブ、Viterbi、RS、TS | FPGAの共通CLK/DATA/VALID/SYNC |
| S / S3-S-000/v0 | RF取得・制御、無損失梱包 | FIR/レート変換、同期、TC8PSK、フレームデインタリーブ、RS、TS | 同じ4本 |

FPGAのGI切出しによりFFTへ渡す有効データは8192複素sampleに限定する。帯域表は旧モデルの上り32.507937 MB/sを残して保守的に予約する。FFT出力は全8192 binで、pilot等を省略しない。同期・TMCC・デインタリーブ等の未完成RTLは残作業に含める。

切替は TS停止 → RF/DMA停止・完了確認 → GPIOをHi-Z → FIFO/世代番号無効化 → 外付けNORのT/S imageを選択して再構成 → PSRAM/PLL/受信状態を初期化 → RF再同調・同期獲得 → TS再開。切替時間は未測定。Background Programmingは、この外付けNOR複数image方式の範囲だけで使用する。ESPモジュール側16 MB FlashはFPGA構成メモリの代用品ではない。

## 論理削減の比較方法

前回のRS 2085は既にDSPを使わない2個のGF乗算器を用いた独立モジュール合成値である。DSP→LUT置換を新しい削減として数えない。ローカルYoWASP 0.69では旧基準を再現した。PRは既存と同じOSS CAD Suite 2026-10-04 / Yosys 0.69+190を固定し、同じツール内の対照群と比較する。

独立モジュールのLUT+ALUと、配置前packing後のLUT4占有は別の数値。後者にはALUの配置上の占有も含まれるのでALUを再加算しない。coreはFEC、memはFEC＋プロトコル用メモリ制御ハーネスであり、受信機全体でも実PSRAM PHYでもない。リポジトリ既存RTLと既存の110 MHz目標は変更しない。

[初回CI](https://github.com/kazuki0824/tangviterbi/actions/runs/37879016201)の4条件は reports/s3-area/*.json に保存した。追加の組合せ試験も同じ125 MHz/seed 1で比較する。結果表と選択理由を下に記載した。

Sの要求TSは6.521250 MB/s、RS入力7.0415625 MB/sである。3502 clocks/blockのRSには **121.475625 MHz** が必要。既存READMEの別のS sizing profileの61.93 MHzをこの要求に流用しない。初回で最速のRS単体は109.64 MHzであり、このままでは不足する。

S用の次の実装案は、(a) Chien探索のCHECK/NEXT専用周期を評価周期へ統合し位置更新のGF×2を定数XOR化、(b) 15周期のGF逆数計算を256×8 bitの同期ROMと1周期の受渡しへ置換、である。BM最大16回とForney最大8回の逆数計算を各14周期短縮する設計とする。

| RSフェーズ（次数≦8・訂正位置≦8） | 現行上限 | 変更後の設計目標 |
|---|---:|---:|
| 入力/定数syndrome | 204 | 204 |
| BM | 593 | 369 =593−16×14 |
| Omega | 177 | 177 |
| Chien | 2041 | 1633 =2041−204×2 |
| Forney | 297 | 185 =297−8×14 |
| 出力/reset | 190 | 190 |
| 合計 | 3502 | **2758** |

この目標で必要RS clockは95.668125 MHz、99 MHz時のserviceは27.858586 us、到着周期28.828829 usに対し約0.970 usの余裕となる。**2758周期はRTL未実装の設計目標であり、測定・証明済みの上限ではない。** 係数先読み・次数0・最後の位置・訂正位置保存・無訂正/訂正不能・ROM read latencyを含めて再実装/等価試験が必要。訂正不能時も遅延上限を守る早期fail処理を含める。

S用imageだけに追加256論理相当、128 FF、逆数ROM用1 BSRAM、追加FIFO/CDC用1 BSRAMを予算化する。主DSP/RS/メモリPHYの目標は99 MHz、TSは66 MHz。Nano 9Kの27 MHz基準に対する比は11/3と22/9、PLLを2個予約する。合法なdivider/VCO設定と全clockの実CST/STA確認は未完了。メモリ帯域予算も100→99 MHzで1%下げる。2 RS複製は旧面積予算に収まらないため主案にしない。

## PR上の合成・配置配線結果と採用する面積案

| 条件 | RS独立LUT+ALU | packed LUT4 core / mem | routed MHz core / mem | RS単体 MHz |
|---|---:|---:|---:|---:|
| dual | 2156 | 4976 / 5129 | 93.04 / 89.03 | 97.97 |
| dual4 | 1814 | 4992 / 5154 | 94.97 / 101.13 | 109.64 |
| shared4 | 1778 | 4937 / 5098 | 87.62 / 87.04 | 99.49 |
| resetless | 2085 | 4803 / 4954 | 78.85 / 88.20 | 91.22 |
| resetless4 | 1679 | 4832 / 4978 | 90.34 / 104.68 | 106.92 |
| shared-resetless4 | 1618 | 4770 / 4942 | 90.92 / 97.77 | 96.48 |

面積案には **resetless4（多項式配列の非同期reset削除＋LUT4 mapping、GF乗算器2個を維持）** を選ぶ。BM_INITで使用前に初期化する配列だけを対象にし、FSM・出力・syndromeのresetは維持する。

同一CIでRSは2156→1679、Viterbiは2952→2953。メモリ制御を含む部分ハーネスのpackingも5129→4978で**151 LUT4減**、FF2625/BSRAM3/DSP0は同じ。shared-resetless4はさらに小さいがmem Fmax97.77 MHzで99 MHz目標に不足するため主案にはしない。

測定対象は部分ハーネスである。**受信機全体の151削減を証明したものではない。** 125 MHzの時間条件は全18試行で未達。workflowのsuccessは測定完了を示す。測定clockと目標clockを取り違えない。

初回[4条件/12試行](https://github.com/kazuki0824/tangviterbi/actions/runs/37879016201)、追加[2条件/6試行](https://github.com/kazuki0824/tangviterbi/actions/runs/37879826128)。独立GF全65536組、定数4096組、48 blockの参照出力・12回のreset復帰・サービス試験を各候補に実施。共有案のcycle比較は入力26914 B/出力24252 B。これらは既存回路との等価性の検証でありARIB適合性の証明ではない。

## 修正した資源予算

旧見積もりのT8681/S8353に対し、CI基準への置換でまず+71。そこからRS−477/Viterbi+1を反映し、T8276/S7948になる。Sの周期削減用にさらに+256論理/+128 FF/+2 BSRAMを予約する。下表は**測定FEC＋未合成の残り回路の予算**であり、全体合成結果ではない。

| 項目 | T案 | S案（周期削減の予約込み） |
|---|---:|---:|
| 論理相当 /8640 | 8276 /95.79%（余364） | 8204 /94.95%（余436） |
| FF /6480 | 6250 /96.45% | 5738 /88.55% |
| BSRAM /26 | 15 /57.69% | 25 /96.15% |
| DSP18 /20 | 14 /70% | 15 /75% |
| PLL予約 /2 | 2 /100% | 2 /100% |
| SoC SRAM /524288 B | 509936 /97.26% | 409584 /78.12% |
| FPGA PSRAM /8388608 B | 5710848 /68.08% | 155904 /1.86% |
| FPGA PSRAM payload RW /実効137.739 MB/s仮定 | 96.046 /69.73% | 14.083 /10.22% |
| SoC PSRAM・定常DSP payload RW | 0（内部SRAMへ移動） | 0 |

3通信路のT案は+128論理/+128 FF/+4 BSRAM/+8184 B SRAMとなる。FPGA PSRAM実効値は旧shared-controller予算139.130 MB/sを99 MHzに合わせて1%減じた設計値である。物理PHYの実測帯域ではない。

## SRAM：前回の計上漏れと修正

旧346096 BにはRF取得の3×64 KiBと、別途必要なROM/IRAM予約98304 Bが入っていなかった。単純に中間バッファを移すと **641008 B** になり、512 KiBを116720 B超える。

RF予約はESP-SDRの[receiver.c](https://github.com/ESPARGOS/esp-sdr/blob/e74f2a470972ec163c247f1fe88d32e08579242a/main/targets/esp32s3/receiver.c)と[sram_guard.ld](https://github.com/ESPARGOS/esp-sdr/blob/e74f2a470972ec163c247f1fe88d32e08579242a/main/targets/esp32s3/sram_guard.ld)を再確認した。旧詳細見積もりにも196608 Bと98304 Bの別枠予約があった。SDKが使用する物理bank・cache・IRAM・heapは最終linker mapで重複なく照合する。

修正案は、旧FFT work 98304 Bと独立staging 133120 Bを廃止し、2個の33792 B領域でRX→in-place FFT→TX→再利用を行う。twiddleは別に32768 B確保する。バッファ所有権が重ならないことを期限付きで管理する。

| 内訳 | T (B) | S (B) |
|---|---:|---:|
| RF取得3 bank | 196608 | 196608 |
| ROM bank/IRAM等予約（旧詳細モデル） | 98304 | 98304 |
| kernel/stack/descriptor/OS/control予約 | 65536 | 65536 |
| RF packed queue | 32768 | 32768 |
| 2本の通信、各2×4092 B | 16368 | 16368 |
| FFT/転送兼用2×33792 B | 67584 | 0 |
| twiddle予約 | 32768 | 0 |
| **合計** | **509936 (97.263%)** | **409584 (78.122%)** |
| **512 KiBに対する残り** | **14352** | **114704** |

3本の通信を使うTの代案では+8184 Bで518120 B、残6168 B。4本では526304 Bとなり、この配置は不採用。512 KiBは物理総量であり、上表は空きDMA heapの実測値ではない。予約の不足は余白を消費するので、malloc成功だけを合格基準にしない。

バッファを初期化時に内部SRAMへ固定し、`MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA | MALLOC_CAP_8BIT` と必要なアラインメントを指定する。確保失敗時にPSRAMへ自動退避しない。RF固定bank、IRAM、stack、twiddleと重ならない配置をlinker mapで検査する。[ESP-IDFのheap属性](https://docs.espressif.com/projects/esp-idf/en/v5.2/esp32s3/api-reference/system/mem_alloc.html)。

PSRAMの中間write/read **128.061568 MB/s** はこの案では内部SRAMへ移る。内部SRAMのRF writer、CPU、GDMA間の競合は残る。CPUコピー費用の削減は先取りせず旧予算425.587 Mcycles/sを保持する。

## 主通信路と必要帯域

主案はSPI2 Octal80 + SPI3 Quad80、どちらもS3がmaster、FPGAがslave。SPI2は上下を時分割できる。SPI3も仕様上は双方向で、T主案では上り、Sでは下りに使う。上下を別々の独立容量とは数えない。QSPI等は独自FPGA endpointを実装する。

4092 B payload +16 B framing、24 command/dummy clocks、transaction gap 2 usの**設計契約**によりOctal実効76.272134 MB/s、Quad実効38.971429 MB/s。標準の割り込み型ドライバが2 us gapを保証するという意味ではない。事前設定DMA/LL進捗監視とgap実測が必要。

| 方式・情報 | 向き | 必要MB/s | 主案での通信路 |
|---|---|---:|---|
| T RF I10/Q10、無損失20 bit | SoC→FPGA | 40.000000 | SPI2 Octal80 |
| T 全8192 FFT bin、複素Q15 | SoC→FPGA | 31.522848 | SPI2 Octal80 |
| T 同期後IQ、複素Q15 | FPGA→SoC | 32.507937を予約 | SPI3 Quad80 |
| S RF I10/Q10、無損失20 bit | SoC→FPGA | 100.000000 | SPI2/SPI3へsample番号付き分散 |
| 制御、Tune、mode、世代番号、status | 双方向 | DSP payloadとは別の低速制御 | 独立制御線/停止時レジスタアクセス |
| T/S TS | FPGA→外部 | 2.904337 / 6.521250 | CLK/DATA/VALID/SYNC |

| モード | Octal負荷/余裕 MB/s | Quad負荷/余裕 MB/s | 容量の余裕 |
|---|---|---|---|
| T・単純割当 | 71.522848 / 4.749287 | 32.507937 / 6.463492 | 6.23% / 16.59% |
| S・均等使用率割当 | 66.183423 / 10.088712 | 33.816577 / 5.154851 | 両方13.23% |

Tの旧LP最適割当とは異なり、主案では上りIQをQuadへ固定してFFT返送と競合させない。全経路JSONには旧LPと同じ目的関数の割当も保存する。RF sample番号・epoch・長さをヘッダへ載せ、FPGAが順序を復元する。パケット欠落の無音補完を正常受信扱いにしない。

## リアルタイムの採用条件

| 対象 | 計算値/期限 | 実装・確認条件 |
|---|---|---|
| T CPU平均 | 425.587/480 Mcycles/s = 88.664% | 両coreの実測WCET、RF監視、DMA、barrierを含める。高コスト側のTモデルは超過する |
| S CPU平均 | 373.325/480 = 77.776% | RF梱包を両coreへ配分、40 MSpsを連続処理 |
| T FFT周期 | 1039.5 us/symbol | 一方のbuffer受信中に他方のFFTとTXを完了 |
| T 1 core FFT+並べ替え | 211119.2 cycles /240 = 879.663 us | 返送も含めると2 buffer再利用期限を超えるため、そのままの1 core版は除外 |
| T 2 core FFT目標 | 500 us以下（理想計算下限439.832 us） | 13段の分担・barrier・並べ替え・RF監視の割込み/協調実行込み。未実装の追加条件 |
| T FFT返送 | 32768 Bを9 transactionで432.100 us | 端数transactionのヘッダ/gapも計上。Octalに優先送信 |
| T buffer再利用 | 500 +53.65（先行1 transaction）+432.10 =985.75 us | 1039.5 usまで**53.75 us**。DMA arbitrationと追加gapはこの残りに含める |
| T RF packed queue | FFT送信中の蓄積17284 B +1 descriptor 4092 B | 32768 B内。FFT実行中の事前充填とRF bank解放も同時に満たす必要あり |
| RF bank解放 | T 1005.667 us、S 352.267 us（旧source guard式） | unit最大14352 sample、次bank準備20k cycle、LATE2000/MAX_EXTRA64を反映。T/Sの実スケジュールで再検証 |
| SPI定常追加gap | T Octal約3.56 us、Quad約20.88 us；S 約8.18/16.01 us | 2 us基礎gapに追加できる平均到着モデルの値。burst時はbuffer所有期限も別に守る |
| T FPGA段クロック | FIR/同期65.015873、Viterbi50.424242、RS54.101010 MHz以上 | 提案99 MHz domainで全体P&R。FIR等は未合成 |
| S FPGA段クロック | FIR76.96、同期/TC57.72 MHz以上 | 提案99 MHz domain。TCは未完成 |
| S RS | 現状3502周期→必要121.475625 MHz | 今回の測定は未達。2758周期目標案も等価性・面積・99 MHz P&Rが必要 |
| TS出力 | 66 MHz、1316 B batch：service161.454545 us | T到着453.115 us、S201.802 us。S余裕40.347 us。受信側がVALID付きTSを取得できること |

旧モデルのEDF集計は平均予算であり、現在のESP-SDRの割込み禁止loopへそのまま適用できない。RF監視とFFTを短いtileに分割し、最大非中断区間2 usを検証する協調スケジューラが必要。通常FreeRTOS task/ISRへ置き換えれば同じ期限を保証できる、とはしない。

## 通信路候補の列挙範囲

今回固定した2つの処理分担に対し、入力JSON記載の13 port profileの全subsetを検査する。まず処理・容量予算を置き、その後に方向/half-duplexを守るLPで通信を割り当て、割当可能な集合だけを容量候補に残す。実機条件が未成立のため、受信機の最終採用数は0のままである。

`experiments/s3_receiver_budget.py` と `reports/s3-receiver-inputs.json` に再現手順を収める。採用する面積候補のanchorではT 35集合（包含最小13）、S 5集合。3本の代案も省略せず、各flowの上下割当、各portの余裕、到着周期/追加gap、資源/メモリ/CPUをJSONに保存する。I2S追加等の冗長集合も含む。実装任意の全クロック・全アルゴリズムの網羅という意味ではない。

GPIOの本数条件と、電気的に実装可能なピン配置は別。主案はdata/clock/CS 16本 +制御2本 +再構成1本（S3）、FPGA側headerはこれにTS4本を加えた22本（再構成は専用端子）。同じ配線でT/Sを切替できる。GPIO35/36/37のOctal PSRAM予約と入力専用GPIO46を使わない。実際のclock-capable pin、onboard負荷、I/O電圧、setup/hold、NOR/JTAGとの共存をCST/STAで確定する。

## 成立までの作業と合格基準

1. 面積候補：同じツールで独立FECとcore/mem packingを比較し、削減を二重計上せず受信機予算を更新する。全受信機は8640論理/6480 FF/26 BSRAM/20 DSP以下をP&Rで確認する。
2. S RS：周期削減と実clockを両方測定し、6.521250 MB/sのTSを最悪訂正時にも止めない。段間CDCと追加FIFOも計上する。
3. SRAM/FFT：上記の固定領域を実linker mapで配置。2 core FFTの500 usと985.75 usのbuffer解放目標をRF取得・DMA併走下で測定する。Tの残14352 Bを未計測IRAM等に無条件で使い切らない。
4. RF/通信：全sampleの番号連続性、bank ownership、80 MHz I/O、gapとFIFO最大値を測定する。適切な外付け周波数変換・フィルタ・衛星LNB系を設計する。S3がUHF/衛星IFを必要性能で直接受けられるとは仮定しない。
5. 受信機機能：T/S双方のARIB適合vector、同期/TMCC、TC/Viterbi、interleaver、RS、TS連続性を検証する。現在のFEC benchmarkの等価テストだけでは受信機機能は確定しない。
6. 基板/boot：実PSRAM PHY、電源/clock、ピン、2 image NOR配置・復旧image容量と再構成手順を完成させる。T/S切替の無受信時間を実測する。

これらは実装計画の合格条件であり、今回すべて実装済みという主張ではない。

## 包含最小の通信路一覧

各数値は経路JSONのLP割当におけるport余裕 MB/sで、port名と同じ順序。主案の単純方向固定とは割当が異なる。SDIO8という旧識別子は8-bit SD/MMC host/eMMC相当endpointの設計枠を指し、8-bit SDIO標準があるという意味ではない。FPGA側のprotocol実装/資源予算検証が必要。

| 方式 | port集合 | 各portの余裕 MB/s |
|---|---|---|
| T | SPI2_Quad80 + LCD16_40 | 3.119 / 11.510 |
| T | SPI2_Octal80 + SPI3_Quad80 | 8.094 / 3.119 |
| T | SPI2_Octal80 + LCD8_40 | 8.881 / 3.204 |
| T | SPI2_Octal80 + CAM8_40 | 4.749 / 7.336 |
| T | SPI2_Octal80 + SDIO8_40 | 6.145 / 2.912 |
| T | SPI3_Quad80 + LCD16_40 | 3.119 / 11.510 |
| T | SPI2_Quad80 + SPI3_Quad80 + LCD8_40 | 4.295 / 4.295 / 5.167 |
| T | SPI2_Quad80 + SPI3_Quad80 + CAM8_40 | 3.210 / 3.210 / 7.336 |
| T | SPI2_Quad80 + SPI3_Quad80 + SDIO8_40 | 3.643 / 3.643 / 3.441 |
| T | SPI2_Quad80 + LCD8_40 + SDIO8_40 | 3.741 / 4.325 / 3.534 |
| T | SPI2_Quad80 + CAM8_40 + SDIO8_40 | 2.193 / 7.336 / 2.071 |
| T | SPI3_Quad80 + LCD8_40 + SDIO8_40 | 3.741 / 4.325 / 3.534 |
| T | SPI3_Quad80 + CAM8_40 + SDIO8_40 | 2.193 / 7.336 / 2.071 |
| S | SPI2_Quad80 + LCD16_40 | 6.128 / 12.531 |
| S | SPI2_Octal80 + SPI3_Quad80 | 10.089 / 5.155 |
| S | SPI2_Octal80 + LCD8_40 | 10.586 / 5.530 |
| S | SPI2_Octal80 + SDIO8_40 | 8.827 / 4.261 |
| S | SPI3_Quad80 + LCD16_40 | 6.128 / 12.531 |

全35+5集合は[JSON](s3-receiver-routes.json)と[CSV](s3-receiver-routes.csv)を参照。方式ごとの分担は本書先頭の1種類に固定している。両モードに同じ2本を使う主案では配線再配置を必要としない。

再計算：`python3 experiments/s3_receiver_budget.py --fec reports/s3-area/resetless4.json --output reports/s3-receiver-routes.json`（ortools使用）。旧stage予算は[s3-receiver-inputs.json](s3-receiver-inputs.json)に凍結し、FECだけ測定値へ更新する。

基板clock/PLL個数の一次資料：[Sipeed Tang Nano 9K](https://wiki.sipeed.com/hardware/en/tang/Tang-Nano-9K/Nano-9K)。
