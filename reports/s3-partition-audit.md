> **完全見積もりではない。** 全段のFPGA資源と、RF/FFT/RS/RPC/RTOS同時実行の期限が未確定。
> `complete_estimate=false`、`performance_stage_completed=false`、`receiver_adopted=false`。
> CPU平均一次条件24件・通信条件合格件数を、性能余裕のある分担数や成立数に読み替えない。
> PR5の測定済み実装の失敗は、9K＋S3のすべての実装の不可能性とは区別する。

# Tang Nano 9K＋ESP32-S3-WROOM-1U-N16R8
ISDB-T / S 処理分担の検算


2026-10-11 · T/S排他的実行 · 追加ソフトウェア間引き・再量子化なし

後続の[FPGA Forney同時合成](s3-rs-forney.md)と[RF polling・target FFT下限](s3-rf-schedule-closure.md)を反映。現行O3 scalar FFTは周期超過、今回のForney付きmapped netlistは9426位置で面積超過。下記の低費用CPU平均値は、この2つの実装の合格を意味しない。I2S共有clockとGDMA割当を追加した通信台帳は2169 subsetへ更新した。


**未完了の検算記録：**TのFFT移管、SのBM/Omega移管は今後の検証順であり、実現可能性を確認した分担の提案ではない。ただし、性能余裕を確認してから通信路を割り当てるという指定手順で、現時点で採用を確定できる完成受信機は0件。RS部分移管のCPU WCETと全体FPGA資源・STAが未確定だからである。帯域条件だけに通るものを成立済みに数えない。


参照した過去資料は `isdb-9k-four-soc-reestimate.html` 第24版。PR4はHEAD `2b9823f60a546cd3c6a1b9d4dcb7441387926fed` に固定した。過去の単一共有bitstreamの「S3採用0」を、そのまま今回の別bitstream構成の不可能性へ転用していない。本資料は見積もり・監査であり、新しい完成RTLの合成・配置配線や実機測定を行った報告ではない。


## 1. 前提、対象、検算した到着率


RF入力はS3内蔵RFの非公開raw IQ機能。外部ADC・外部復調ICを前提にしない。T/Sの周波数をS3の受信帯へ変換するRF前段、T/S帯域フィルタ、必要に応じLNB給電は別途必要。対象のSは従来ISDB-SでありISDB-S3ではない。フルセグは全13セグメントの復調とTS生成であり、映像・音声デコードは含まない。


native I10/Q10の未使用12 bitを落として、2 sampleを5 byteへ可逆梱包する。量子化精度は変えない。Tのnative16 MS/s→40 MB/s、Sのnative40 MS/s→100 MB/s。native80 MS/sのSは200 MB/sとなり、本資料の標準周辺機器経路では成立根拠を得ていない。40 MS/sの設定があること自体は、約38.961 MHzのS占有帯域、連続取得、C/N性能を保証しない。RFアナログ帯域とフィルタ遷移帯域を実測して閉じる必要がある。


| 量 | 検算値 | 意味 |
| --- | --- | --- |
| T TS最大 | 23.234700 Mbit/s = 2.904337 MB/s | FPGAの外部TS端子へ出力 |
| S TS | 52.17 Mbit/s = 6.521250 MB/s | 外部TS端子へ出力。TS平均をRS瞬間期限に使わない |
| T Mode3、GI1/32 | 8192点、1039.5 µs/symbol | GI除去後の全8192 complex Q15を各方向31.522848 MB/s |
| S TC8PSK | 28.86 MSymbol/s、情報2 bit/symbol | 3クロック距離演算の必要clockは86.58 MHz |
| S RS保守到着 | 35,541.871921 codeword/s | 28.86e6×2÷(203×8)。同期byte省略、TMCC等の空きを控除しない |
| S RS期限 | 28.135828 µs/codeword | 旧28.828829 µsはTS平均に基づくため撤回 |
| RS204語batch | 5,739.708940 µs | batch化で平均処理量の要求は減らない |


## 2. 全処理分担候補とスクリーニング範囲


「すべて」は有限の処理グラフについて列挙する。Tは FIR/resample・同期/GI・FFT・等化/demap・time deinterleave・Viterbi・RS・TS の8段をFPGA/SoCへ割り当てた256通り。Sは FIR・同期・TC8PSK・frame deinterleave・RS・TS の6段で64通り。RFは常にSoC。さらにSのRS内部について全RS、BM/Chien/Forney、BM/Omega、BM/Omega/Forneyの4切断を追加する。任意のRTL、SIMD命令列、RS内部のすべての切断、任意clockまで網羅したという主張はしない。全320通りの所有者、CPUモデル、交差情報、部分資源、除外理由を末尾に載せ、再計算データにも保存した。


要求された手順は①資源と期限に性能余裕がある分担を選別、②通信路を割当て、③通信路が0でないものを採用する。しかし今回は①が未完了である。以下の通信列挙は、CPU平均モデルと仮定した転送費用による探索資料であり、①を通った採用候補への割当てではない。320通り中24通りが低費用CPUモデルの一次条件に通る。しかしこれは平均CPU条件だけであり、未実装段や部分資源を0費用にはしない。24件を採用候補数と呼ばない。全体資源と期限のゲートが閉じないため、最終採用は0。RS部分案の通信表は、CPU/FPGAゲート未確定の案を将来評価するための独立した必要条件計算である。


| 分担群 | SoC処理 | FPGA処理・保持 | CPU見積もり / 判定 |
| --- | --- | --- | --- |
| T-A：FFT移管 | RF取得、可逆梱包、8192点FFT＋reorder | FIR/resample、同期/GI、TMCC、等化/demap、全interleave、Viterbi、RS、descramble、TS | 低424.549 Mcycles/s＝88.448%；高566.387＝117.997%。低費用モデルのみ条件付き |
| T-B：FFT＋等化/demap移管 | T-Aに等化/demap追加 | T-Aから等化/demapを除く。pilot/TMCCの扱いを整合 | 低460.126＝95.860%；高637.673＝132.849%。T-AよりCPUが厳しい |
| T-C：FIR移管、FFTをFPGA | RF取得、通常復調用FIR/resample | 同期、FFT、等化、FEC、TS | 低432.042＝90.009%；高594.073＝123.765%。FPGA FFTの18 BSRAM等が課題 |
| T-D：全復調FPGA | RF取得・梱包のみ | FFTを含む全復調 | CPU低約32.360%。旧stageだけで24/26 BSRAM、18/20 DSP。I/O等の追加後のfit未証明 |
| S-0：全RS FPGA | RF取得・梱包・制御 | FIR、同期、TC8PSK、TMCC/frame、deinterleave、RS、TS | RF等のみ低373.320＝77.775%；高453.320＝94.442%。現コンパクトFPGA実装は期限未達 |
| S-1：全RS SoC | S-0に全RS追加 | RS以外。204 BのCWを送ってTSを受け取る | 旧22060 cycles/CWはRSだけで784.054 Mcycles/s。選択したscalar実装は除外 |
| S-2：BM＋Chien＋Forney SoC | syndromeから誤り位置・値を算出 | syndrome、CW保存、byte訂正、その他復調 | CPU WCET未確定。旧scalar Chien6528 cycles/CWだけでRF控除後予算を超える |
| S-3：BM＋Omega SoC | syndromeからlambda/Omega算出 | syndrome、Chien、Forney、CW保存、byte訂正、その他復調 | Forney単体を検査・合成済み。同時mapped netlistは9426位置で超過。CPU WCET・別構成の全体資源は未確定 |
| S-4：BM＋Omega＋Forney SoC | solver、FPGAからの根を検査してmagnitudes算出 | syndrome、Chien、CW保存、byte訂正、その他復調 | 独立部品の証拠が最多。往復4段、保持追加後のpartial topが90 MHz未達 |
| SのFIR/TC8PSK/frameをSoCへ移す群 | 対応する全部又は組合せ | 残りの段 | 選択したFIRは低870.36 Mcycles/s、frame移管は総低490.000 Mcycles/s。16bit TC8PSK arithmetic profileも超過。該当実装を除外 |


CPUの高/低は選択した命令・コピー費用の感度条件であり、統計的信頼区間やWCET上限ではない。Tの公式1024点sc16 benchmark15623 cyclesをNlogNで8192へ外挿すると162479.2 cycles。reorder/unpackを加えた低モデルは211119.2 cycles＝1 core換算879.663 µs、理想2 core換算439.832 µs。500 µsは設計目標であり実測値ではない。同期、AGC/CFO、TMCC等の各機能を完成させた後に再測定する。


## 3. 資源占有率、期限、メモリ競合


容量は8640 logic位置、6480 FF、26 BSRAM、20 MULT18、2 PLL、8 MiB FPGA PSRAM。LUT4欄だけの占有率にはALUと独立FFの問題があり、次の位置数は各報告の測定範囲に限定する。異なるpartial topの測定値は加算して完成回路の配置結果にしない。


| 構成 / 証拠の範囲 | logic | FF | BSRAM / DSP / PLL | 期限と判定 |
| --- | --- | --- | --- | --- |
| T-A、旧全体設計予算 | 8179/8640＝94.664% | 6213/6480＝95.880% | 16/26＝61.538%；14/20＝70%；PLL2予定 | FIR/同期約65.016 MHz、Viterbi50.424 MHz。全体P&R結果ではない |
| T-B、T-Aから旧等化予算だけ引いた参考値 | 7795＝90.220% | 5829＝89.954% | 16/26、9/20＝45% | SoC交差部の変更・制御追加を含まない。fit判定に使わない |
| S-4、SHIFT22部分top、保持前 | 7958＝92.106% | 3438＝53.056% | 10/26＝38.462%；2/20；1/2 | seed3 91.4495 MHz、90 MHz目標合格。全復調・全RPC・CW保持なし |
| 同系列へCW保持を追加したPR5固定commitの部分top | 8281/8296＝95.845/96.019% | この表では未確定 | 25/26＝96.154% | stable83.45 MHz；同netlist seed75.52/80.34 MHz。90 MHz未達 |
| SHIFT24＋guard FIFOの部分top | 8226＝95.208% | 3580＝55.247% | 11/26＝42.308%；2/20；1/2 | 93.214 MHz合格。ただし弱信号で誤り増加の条件があり同等品質の代替採用はしない |
| S-2 / S-3の完成回路 | 未確定 | 未確定 | 未確定 | S-4の占有率を流用しない。S-3のForney付きpartial netlistは9426位置。全体回路の代用にはしない |


S距離3 clocks/symbolなら90 MHzで入力需要86.58 MHz、clock容量占有96.2%。32 ACSの2 clocks/symbolは64.133%。syndromeは8 clocks/byteで11.25 MB/s能力に対し7.250542 MB/s需要、64.449%。Chien224 clocks＝2.489 µs、byte訂正268 clocks＝2.978 µs。この独立stage値だけで仲裁付きパイプラインを保証しない。compact全RS2667 clocks/CWの必要clockは94.790172 MHzであり、既存83.86 MHz測定は不合格。


T-Aの通信部分モデルは256開始位相×256 symbolで通り、最大slot解放1039.000391 µs、期限1039.5 µs、残0.499609 µsだった。ただしRF bank取得とQuad側IQ到着を一緒に模擬していない。後の64 KiB bankモデルではT6 cycles/sample＋FFT500 µsのcore0占有98.95%、2面再使用期限2079 µsに対し最大2048.525 µs。8 cycles/sampleでは期限違反。平均88.448%だけで期限合格とはしない。


Sのraw bankは12288 samples、307.2 µs周期。従来単一packing ownerでは4 cycles/sampleでもcore0モデル93.79%、6 cyclesでは127.13%、8 cyclesではbank期限違反。従って「2 core合計に収まる」にはparallel packingの所有権・barrier・割込みを別途成立させる必要がある。


RF費用控除前の6752.598753 cycles/CWをRSの空き予算にしない。今回再計算したSのRF等モデルは低373.320313、高453.320313 Mcycles/s。2 core合計の残予算はそれぞれ3001.521353、750.655102 cycles/CWで、RSのRPC準備、CRC、RTOS、stallもこの中へ入れる。例としてsolver2000 cycles/CWなら低モデルでCPU全体92.584%、2500なら96.287%、3000なら99.989%。これらのsolver時間は仮定であって達成した測定値ではない。


FPGA PSRAMのT time interleave payloadは5,690,880 B＝67.84%。64 KiB RF staging、FFT/係数/管理を別計上し、scatter/gather・refresh・最大grant待ち時間を検証する。Sの同一batchモデル最大344 CWは70,176 Bで、204 CWだけの41,616 Bでは足りない条件があった。CWを1回保存して1回読むだけでも14.501084 MB/s、訂正の再アクセスは追加。100 MB/sのrawをPSRAMへ全部書いて読めば更に200 MB/sを消費するため、FPGA FIRへ直接streamする構成を優先評価する。ただしそのFIFO・CDC・保持制御の資源が削れたとは未測定。


S3内蔵SRAMは512 KiBで、RF raw3 bank192 KiB、packed ring64 KiB、T FFT2面64 KiB又はS RS/RPC56,032 Bを保持。T/S排他的なwork areaは再利用できる。最新版SDK linkは静的余白29,512 B、起動後・DMA前の空き上限19,312 B。N16の16 MiB Flashと8 MiB PSRAMは内部DMA SRAMを増やさない。4 KiB DMA poolの必要条件に通っただけで、private RF初期化と全driver同時live memoryは未確認。


## 4. 境界を渡る情報と全通信profile


以下で↑はSoC→FPGA、↓はFPGA→SoC。一般のup/down表記と混同しない。TSは原則FPGAから外部sinkへのserial clock/valid/sync/data。controlはtune、mode、epoch、credit、ready、CRC、error、再構成要求。これらのwire時間はheaderへ含めた部分以外は余裕で支払う。専用GPIOで通知してもCPU費用は消えない。


| 候補 | ↑データ | ↓データ | 通信量 |
| --- | --- | --- | --- |
| T-A | RF I10/Q10＋全8192 FFT bins Q15 | GI除去後8192 complex Q15 | ↑71.522848、↓31.522848 MB/s |
| T-B | RF I10/Q10＋6×8bit LLR/carrier | GI除去後8192 complex Q15 | ↑68.813853、↓31.522848 MB/s |
| T-C | 通常FIR後complex Q15 | 制御/status | ↑32.507937 MB/s。追加の品質低下処理なし |
| S-0 | RF I10/Q10 | 制御/status | ↑100 MB/s |
| S-1 | RF＋TS188 B/語＋id | CW204 B/語＋id | RPC 11頁↓＋10頁↑/batch、padding込14.986126 MB/s |
| S-2 | RF＋訂正位置/値20 B/語 | syndrome＋id19 B/語 | RPC 1頁↓＋1頁↑、1.427250 MB/s |
| S-3 | RF＋lambda/Omega29 B/語 | syndrome＋id19 B/語 | RPC 1頁↓＋2頁↑、2.140875 MB/s |
| S-4 | RF＋lambda13 B/語＋magnitudes12 B/語 | syndrome19 B/語＋roots12 B/語 | RPC ↓↑↓↑ 各1頁、2.854500 MB/s |


| 通信profile | 方向 | 信号pin | 線上MB/s | 実効、並列gap0 | 実効、並列gap8µs |
| --- | --- | --- | --- | --- | --- |
| SPI2_Quad80 | 半二重、両方向共用 | 6 | 40.000 | 33.396 | 33.396 |
| SPI2_Octal80 | 半二重、両方向共用 | 10 | 80.000 | 70.328 | 70.328 |
| SPI3_Quad80 | 半二重、両方向共用 | 6 | 40.000 | 33.396 | 33.396 |
| LCD16_40 | SoC→FPGA | 19 | 80.000 | 79.689 | 68.956 |
| LCD8_40 | SoC→FPGA | 11 | 40.000 | 39.844 | 36.968 |
| CAM16_40 | FPGA→SoC | 19 | 80.000 | 79.689 | 68.956 |
| CAM8_40 | FPGA→SoC | 11 | 40.000 | 39.844 | 36.968 |
| SDIO4_40 | 半二重、両方向共用 | 6 | 20.000 | 17.651 | 17.651 |
| eMMC8_SDR40 | 半二重、両方向共用 | 10 | 40.000 | 31.691 | 31.691 |
| I2S0_RX40 | FPGA→SoC | 3 | 5.000 | 4.981 | 4.981 |
| I2S0_TX40 | SoC→FPGA | 3 | 5.000 | 4.981 | 4.981 |
| I2S1_RX40 | FPGA→SoC | 3 | 5.000 | 4.981 | 4.981 |
| I2S1_TX40 | SoC→FPGA | 3 | 5.000 | 4.981 | 4.981 |
| SPI2_Single80 | 半二重、両方向共用 | 4 | 10.000 | 9.512 | 9.512 |
| SPI2_Dual80 | 半二重、両方向共用 | 4 | 20.000 | 18.180 | 18.180 |
| SPI3_Single80 | 半二重、両方向共用 | 4 | 10.000 | 9.512 | 9.512 |
| SPI3_Dual80 | 半二重、両方向共用 | 4 | 20.000 | 18.180 | 18.180 |
| eMMC4_DDR40 | 半二重、両方向共用 | 6 | 40.000 | 31.691 | 31.691 |


SPIはS3 master80 MHz、FPGA slave。S3をSPI slave80 MHzで動かす前提にはしない。OctalはRF3頁batch、API20 µs、segment0.25 µs；Quad/Dual/Singleは1頁/API20 µs。SPI header80 bit。4096 B RPC page内16 B headerを含め、部分案では各messageごとのpage数・API回数も加算した。20 µsは設計仮定でありprivate SCT APIのWCET保証ではない。SD/eMMCは40 MHz、20 µs gap、command/CRCを計上。8bit SDIOという旧名称を8bit eMMCへ訂正した。4bit eMMC DDR40はFPGA側card emulation未実装。LCD/CAMは8/16bit、40 MHz、4096＋16 B framing、gap0/8 µsの感度条件。I2Sは40 MHz bitclockの5 MB/s上限からframingを控除する。


18 profileの全subsetを列挙し、SPI2、SPI3、LCD、CAM、SDHOST内の重複を除いた。S3信号＋3control≤30、FPGA header信号＋6control/TS≤35の必要pin条件とGDMA容量条件に通る2169 subsetを検査。専用バスの方向と半二重時間を守る。I2Sの同一controller内でTX/RXのclock/slot設定を揃える場合はBCLK/WSを共有して2 pin削減する。controller間のclock共有は仮定しない。40 MHz profileはS3 master、PLL160→MCLK80→BCLK40 MHz、32-bit stereo625 kframe/s、MCLK pinなしの設計条件とする。同じ内部sourceのslave40 MHzはdriverの最小BCLK divisor8条件を満たさない。GDMAは5対でSPIがTX/RX対を予約し、LCD TX・CAM RX・I2S各方向が別channelを使う。SDMMCは自身のDMAを持つ。これらはcapacity条件であり、同時memory arbitrationの合格ではない。pin本数を満たすことは、N16R8のPSRAM予約GPIO、strap、CLK入力、固定基板負荷、setup/holdを解決した証明ではない。T/S両modeの固定配線のunion/remapは最後に別確認する。


全320段分担の通信表は方向別fluid容量の必要条件。最小peak割当の一例を各subsetに保存した。deadline、barrier、ページ境界到着の十分条件にはしない。RS部分4案は各RPC messageを分割せず各対応portへ割り当てる全組合せを列挙し、RPC時間を控除した残りへRF100 MB/sを配分した。全message割当とportごとの余裕は[通信割当CSV](s3-partition-audit/message-assignments.csv.gz)と[台帳JSON](s3-partition-audit/estimate.json.gz)にある。Octal/Quadの既存有限eventモデルも別収録した。


## 5. 主な通信路の余裕と採否


| 候補 / 配線 | 必要量と割当 | 帯域余裕 | 判定 |
| --- | --- | --- | --- |
| T-A：Octal80＋Quad80 | Octal↑RF40＋FFT31.523；Quad↓31.523 | Octal duty98.49%；Quad残1.872994 MB/s | CPU500 µs等を仮定した部分event合格。bank/RTOS/全RTL未確定 |
| T-A：LCD16_40＋SPI2又は3 Quad80 | LCD↑71.522848；Quad↓31.522848 | gap0：LCD残8.165868、Quad残1.872994 MB/s；LCD gap許容5.868 µs/頁 | gap8ではこの固定割当不合格。LCD endpoint未実装 |
| T-B：LCD16_40＋Quad80 | LCD↑68.813853；Quad↓31.522848 | gap0：LCD残10.874863、Quad残1.872994 MB/s | SoC CPU低95.860%、同期・RF期限未閉鎖 |
| S-0：Octal80＋Quad80 | RFを両portへstripe | 残3.723500 MB/s | 通信必要条件に通る。現全RS FPGA実装は採用不可 |
| S-2：Octal80＋Quad80 | ↓↑をO又はQへ割当、RF残時間を使用 | OO1.969507、OQ/QO2.132878、QQ2.296250 MB/s | 4通信割当。CPU/全体fit未確定 |
| S-3：Octal80＋Quad80 | ↓1頁・↑2頁をO又はQへ割当 | OO1.337568、OQ1.419253、QO1.500939、QQ1.582624 MB/s | 4通信割当。FPGA Forneyとsolver期限未確定 |
| S-4：Octal80＋Quad80 | ↓↑↓↑をO又はQへ割当 | 全O0.215515〜全Q0.868999 MB/s | 16通信割当。CW保持追加後の現RTLが90 MHz未達 |
| S-3：LCD16_40＋Quad80 | RPCすべてQ；RFはLCD＋Q残時間 | gap0 残10.943683、gap8 残0.211196 MB/s | 必要条件のみ。gap8の余裕は極小 |
| S-4：LCD16_40＋Quad80 | RPCすべてQ；RFはLCD＋Q残時間 | gap0 残10.230058 MB/s、gap8 不合格 | LCD gap許容約7.57 µs/頁；同期RPC deadline未証明 |
| S-1：Octal80＋Quad80 | 11頁↓＋10頁↑ | 全4割当で不足10.037344〜11.262626 MB/s | この2本構成を除外。3本等に帯域上の候補はあり、全経路不可能とはしない |


S-4のO/Q全16割当は、Qの個数0/1/2/3/4に応じ残0.215515/0.378886/0.542257/0.705628/0.868999 MB/s。順序↓↑↓↑に対応する全16文字列をJSONへ保存した。S-2とS-3も全4文字列を収録。RFとRPCに別々のfull capacityを与えて二重計上していない。RPCのCPU実行時間、same-batch依存、credit/ACK/retentionを閉じない限り採用しない。


| RS分担 | gap0 port集合 | gap0 message割当 | gap8 port集合 | gap8 message割当 | 最終採用 |
| --- | --- | --- | --- | --- | --- |
| CPU_all_RS | 31 | 240 | 28 | 230 | 0 / 性能未達又は未確定 |
| CPU_BM_Chien_Forney | 180 | 1041 | 169 | 1003 | 0 / 性能未達又は未確定 |
| CPU_BM_Omega | 178 | 1033 | 163 | 971 | 0 / 性能未達又は未確定 |
| CPU_BM_Omega_Forney | 198 | 14953 | 185 | 14473 | 0 / 性能未達又は未確定 |


これは明示profile、pin数、取引モデルの範囲の全候補。USB Full Speedは線上12 Mbit/sでT/S TS最大にもraw RFにも足りない。Tang上BL702のUSB-JTAG/UARTは汎用高速TS経路とはみなさない。内蔵RFをSDR取得に使うS3で独立Wi-Fi転送を同時保証しない。S3にないPARLIOやEthernet MACは借用しない。GPIO独自転送のeSpDR実例はあるが、200 MB/s受信側はArtixの240 MHz sampler等を使うため9Kへの保証に転用しない。これらを用いて帯域不足をソフトウェア間引きで救う案は採用表へ入れない。


## 6. T/S別bitstreamと許可されたNOR切替


T/Sの資源を合算せず、各bitstreamで別々にP&Rする。基板外付け32 Mbit＝4 MiB SPI NORへT/Sを置く方式に限ってBackground Programmingを扱う。各512 KiB slotならT=0、S=0x80000、任意の復旧image=0x100000でも容量内。実image長・CRC・headerは完成後に確認する。これ以外の内部Flash background更新や受信中の部分再構成を前提にしない。


MSPI Multi Bootはimage headerに次image addressを持たせ、停止→RF/TS/DMA排出→RECONFIG_N→identity/epoch確認→tune/再捕捉する。T→S→Tの固定2 image循環なら不要なmode切替をスキップし、要求modeまで再構成する。PR4のT→S→recovery→Tの例ではS→Tは2回。再構成停止時間がある。S3から任意RAM registerへaddressを書けば即切替できるとは仮定しない。


参照3674基板はMODE1=0 strapをMSPI用1へ変更する必要があり、RECONFIG_Nは通常headerに出ない1.8 V領域。1.8 V対応open-drain接続等が要る。完成基板をそのまま無改造でNORからT/S選択起動できるとは扱わない。基板revisionに応じ回路図照合が必要。


## 7. この見積もりで優先する分担と、確定に必要な測定


次の評価ではT-Aのtarget SIMD FFT、S-3のraw直接stream等を含む資源再設計が必要。現行scalar FFTと今回のForney付きmapped netlistを保持した案は、追加測定で除外した。全体資源と同時実行時間を満たす案とはまだ判定していない。S-3はS-4より往復を減らすが、Forneyを実装して同時合成すると今回の構成では面積超過になった。配線候補はOctal＋QuadとLCD16＋Quadを比較する。後者はgap0なら通信余裕が大きいが、並列endpointと固定pin/IO制約の設計が必要。現在の証拠からどちらかを成立済みハードウェアとして選ぶことはできない。


閉じるべき値は①native40 MS/sの全帯域・連続RF取得、②parallel packingとFFT/solver/RPC/RTOS込み各core WCET、③T/S全RTLそれぞれのlogic/FF/BSRAM/DSP/PLL占有とSTA、④PSRAMの全負荷と最大仲裁待ち、⑤same-batch ACK/credit/CW保持の上限、⑥実配線でのAPI/DMA gapとIO遅延、⑦NOR実image起動。特にS-3のForneyを含む新全体資源見積もりがない状態で、S-4の残682位置をそのまま空きとして使わない。


## 8. 全320処理分担台帳


所有者欄はSoCへ置く段。残りはFPGA。CPU L/Hは低/高の平均モデル。stage B/DはI/O等を含まない既存段のBSRAM/DSP予算。logic/FF全体占有と期限の実証は全行未確定。経路数は低費用CPU条件を通った行だけに割当てた方向別必要条件の数であり、採用0は共通。


| ID | SoC段（RF共通） | CPU % L/H | stage B/D | ↑/↓ MB/s | 経路gap0/8 | 除外/保留 |
| --- | --- | --- | --- | --- | --- | --- |
| S3-T-000 | RFのみ | 32.360/39.027 | 24/18 | 40.000/0.000 | 1646/1646 | 全体資源/WCET未確定 |
| S3-T-001 | FIR | 90.009/123.765 | 22/10 | 32.508/0.000 | 1821/1821 | 全体資源/WCET未確定 |
| S3-T-002 | sync | 59.896/93.447 | 23/17 | 71.523/32.508 | 209/202 | 全体資源/WCET未確定 |
| S3-T-003 | FIR,sync | 103.338/150.435 | 21/9 | 31.523/0.000 | 未割当 | 全体資源/WCET未確定 |
| S3-T-004 | FFT | 88.448/117.997 | 6/14 | 71.523/31.523 | 225/218 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-005 | FIR,FFT | 146.096/202.736 | 4/6 | 64.031/31.523 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-006 | sync,FFT | 102.208/145.508 | 5/13 | 71.523/32.508 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-007 | FIR,sync,FFT | 145.650/202.495 | 3/5 | 31.523/0.000 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-008 | equalize_demap | 53.548/80.788 | 24/13 | 68.814/31.523 | 267/249 | 全体資源/WCET未確定 |
| S3-T-009 | FIR,equalize_demap | 111.196/165.527 | 22/5 | 61.322/31.523 | 未割当 | 全体資源/WCET未確定 |
| S3-T-00a | sync,equalize_demap | 81.084/135.209 | 23/12 | 100.337/64.031 | 0/0 | 全体資源/WCET未確定 |
| S3-T-00b | FIR,sync,equalize_demap | 124.526/192.197 | 21/4 | 60.337/31.523 | 未割当 | 全体資源/WCET未確定 |
| S3-T-00c | FFT,equalize_demap | 95.860/132.849 | 6/9 | 68.814/31.523 | 267/249 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-00d | FIR,FFT,equalize_demap | 153.508/217.587 | 4/1 | 61.322/31.523 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-00e | sync,FFT,equalize_demap | 109.620/160.359 | 5/8 | 68.814/32.508 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-00f | FIR,sync,FFT,equalize_demap | 153.062/217.346 | 3/0 | 28.814/0.000 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-010 | time_deinterleave | 60.960/95.640 | 24/18 | 68.814/28.814 | 316/300 | 全体資源/WCET未確定 |
| S3-T-011 | FIR,time_deinterleave | 118.608/180.378 | 22/10 | 61.322/28.814 | 未割当 | 全体資源/WCET未確定 |
| S3-T-012 | sync,time_deinterleave | 88.496/150.061 | 23/17 | 100.337/61.322 | 0/0 | 全体資源/WCET未確定 |
| S3-T-013 | FIR,sync,time_deinterleave | 131.938/207.048 | 21/9 | 60.337/28.814 | 未割当 | 全体資源/WCET未確定 |
| S3-T-014 | FFT,time_deinterleave | 117.047/174.610 | 6/14 | 100.337/60.337 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-015 | FIR,FFT,time_deinterleave | 174.696/259.349 | 4/6 | 92.845/60.337 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-016 | sync,FFT,time_deinterleave | 130.808/202.121 | 5/13 | 100.337/61.322 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-017 | FIR,sync,FFT,time_deinterleave | 174.250/259.108 | 3/5 | 60.337/28.814 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-018 | equalize_demap,time_deinterleave | 69.555/112.804 | 24/13 | 68.814/31.523 | 267/249 | 全体資源/WCET未確定 |
| S3-T-019 | FIR,equalize_demap,time_deinterleave | 127.204/197.542 | 22/5 | 61.322/31.523 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-01a | sync,equalize_demap,time_deinterleave | 97.092/167.225 | 23/12 | 100.337/64.031 | 0/0 | 全体資源/WCET未確定 |
| S3-T-01b | FIR,sync,equalize_demap,time_deinterleave | 140.534/224.212 | 21/4 | 60.337/31.523 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-01c | FFT,equalize_demap,time_deinterleave | 111.867/164.864 | 6/9 | 68.814/31.523 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-01d | FIR,FFT,equalize_demap,time_deinterleave | 169.516/249.603 | 4/1 | 61.322/31.523 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-01e | sync,FFT,equalize_demap,time_deinterleave | 125.628/192.374 | 5/8 | 68.814/32.508 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-01f | FIR,sync,FFT,equalize_demap,time_deinterleave | 169.070/249.362 | 3/0 | 28.814/0.000 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-020 | Viterbi | 1047.829/2069.640 | 22/18 | 43.152/28.814 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-021 | FIR,Viterbi | 1105.478/2154.379 | 20/10 | 35.659/28.814 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-022 | sync,Viterbi | 1075.366/2124.061 | 21/17 | 74.674/61.322 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-023 | FIR,sync,Viterbi | 1118.808/2181.049 | 19/9 | 34.674/28.814 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-024 | FFT,Viterbi | 1103.917/2148.611 | 4/14 | 74.674/60.337 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-025 | FIR,FFT,Viterbi | 1161.566/2233.350 | 2/6 | 67.182/60.337 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-026 | sync,FFT,Viterbi | 1117.677/2176.121 | 3/13 | 74.674/61.322 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-027 | FIR,sync,FFT,Viterbi | 1161.120/2233.109 | 1/5 | 34.674/28.814 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-028 | equalize_demap,Viterbi | 1069.017/2111.402 | 22/13 | 71.965/60.337 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-029 | FIR,equalize_demap,Viterbi | 1126.666/2196.141 | 20/5 | 64.473/60.337 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-02a | sync,equalize_demap,Viterbi | 1096.553/2165.823 | 21/12 | 103.488/92.845 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-02b | FIR,sync,equalize_demap,Viterbi | 1139.996/2222.810 | 19/4 | 63.488/60.337 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-02c | FFT,equalize_demap,Viterbi | 1111.329/2163.462 | 4/9 | 71.965/60.337 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-02d | FIR,FFT,equalize_demap,Viterbi | 1168.978/2248.201 | 2/1 | 64.473/60.337 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-02e | sync,FFT,equalize_demap,Viterbi | 1125.089/2190.973 | 3/8 | 71.965/61.322 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-02f | FIR,sync,FFT,equalize_demap,Viterbi | 1168.532/2247.960 | 1/0 | 31.965/28.814 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-030 | time_deinterleave,Viterbi | 1063.837/2101.656 | 22/18 | 43.152/28.814 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-031 | FIR,time_deinterleave,Viterbi | 1121.486/2186.394 | 20/10 | 35.659/28.814 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-032 | sync,time_deinterleave,Viterbi | 1091.373/2156.077 | 21/17 | 74.674/61.322 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-033 | FIR,sync,time_deinterleave,Viterbi | 1134.816/2213.064 | 19/9 | 34.674/28.814 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-034 | FFT,time_deinterleave,Viterbi | 1119.925/2180.626 | 4/14 | 74.674/60.337 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-035 | FIR,FFT,time_deinterleave,Viterbi | 1177.574/2265.365 | 2/6 | 67.182/60.337 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-036 | sync,FFT,time_deinterleave,Viterbi | 1133.685/2208.137 | 3/13 | 74.674/61.322 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-037 | FIR,sync,FFT,time_deinterleave,Viterbi | 1177.127/2265.124 | 1/5 | 34.674/28.814 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-038 | equalize_demap,time_deinterleave,Viterbi | 1072.433/2118.820 | 22/13 | 43.152/31.523 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-039 | FIR,equalize_demap,time_deinterleave,Viterbi | 1130.082/2203.558 | 20/5 | 35.659/31.523 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-03a | sync,equalize_demap,time_deinterleave,Viterbi | 1099.969/2173.241 | 21/12 | 74.674/64.031 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-03b | FIR,sync,equalize_demap,time_deinterleave,Viterbi | 1143.411/2230.228 | 19/4 | 34.674/31.523 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-03c | FFT,equalize_demap,time_deinterleave,Viterbi | 1114.745/2170.880 | 4/9 | 43.152/31.523 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-03d | FIR,FFT,equalize_demap,time_deinterleave,Viterbi | 1172.393/2255.619 | 2/1 | 35.659/31.523 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-03e | sync,FFT,equalize_demap,time_deinterleave,Viterbi | 1128.505/2198.390 | 3/8 | 43.152/32.508 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-03f | FIR,sync,FFT,equalize_demap,time_deinterleave,Viterbi | 1171.947/2255.378 | 1/0 | 3.152/0.000 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-040 | RS | 104.682/112.611 | 23/18 | 42.904/3.152 | 未割当 | 全体資源/WCET未確定 |
| S3-T-041 | FIR,RS | 162.331/197.349 | 21/10 | 35.412/3.152 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-042 | sync,RS | 132.219/167.032 | 22/17 | 74.427/35.659 | 未割当 | 全体資源/WCET未確定 |
| S3-T-043 | FIR,sync,RS | 175.661/224.019 | 20/9 | 34.427/3.152 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-044 | FFT,RS | 160.770/191.581 | 5/14 | 74.427/34.674 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-045 | FIR,FFT,RS | 218.419/276.320 | 3/6 | 66.935/34.674 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-046 | sync,FFT,RS | 174.530/219.092 | 4/13 | 74.427/35.659 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-047 | FIR,sync,FFT,RS | 217.973/276.079 | 2/5 | 34.427/3.152 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-048 | equalize_demap,RS | 125.870/154.373 | 23/13 | 71.718/34.674 | 未割当 | 全体資源/WCET未確定 |
| S3-T-049 | FIR,equalize_demap,RS | 183.519/239.111 | 21/5 | 64.226/34.674 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-04a | sync,equalize_demap,RS | 153.406/208.793 | 22/12 | 103.241/67.182 | 未割当 | 全体資源/WCET未確定 |
| S3-T-04b | FIR,sync,equalize_demap,RS | 196.849/265.781 | 20/4 | 63.241/34.674 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-04c | FFT,equalize_demap,RS | 168.182/206.433 | 5/9 | 71.718/34.674 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-04d | FIR,FFT,equalize_demap,RS | 225.831/291.171 | 3/1 | 64.226/34.674 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-04e | sync,FFT,equalize_demap,RS | 181.942/233.943 | 4/8 | 71.718/35.659 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-04f | FIR,sync,FFT,equalize_demap,RS | 225.385/290.930 | 2/0 | 31.718/3.152 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-050 | time_deinterleave,RS | 133.282/169.224 | 23/18 | 71.718/31.965 | 未割当 | 全体資源/WCET未確定 |
| S3-T-051 | FIR,time_deinterleave,RS | 190.931/253.963 | 21/10 | 64.226/31.965 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-052 | sync,time_deinterleave,RS | 160.818/223.645 | 22/17 | 103.241/64.473 | 未割当 | 全体資源/WCET未確定 |
| S3-T-053 | FIR,sync,time_deinterleave,RS | 204.261/280.632 | 20/9 | 63.241/31.965 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-054 | FFT,time_deinterleave,RS | 189.370/248.194 | 5/14 | 103.241/63.488 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-055 | FIR,FFT,time_deinterleave,RS | 247.019/332.933 | 3/6 | 95.749/63.488 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-056 | sync,FFT,time_deinterleave,RS | 203.130/275.705 | 4/13 | 103.241/64.473 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-057 | FIR,sync,FFT,time_deinterleave,RS | 246.572/332.692 | 2/5 | 63.241/31.965 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-058 | equalize_demap,time_deinterleave,RS | 141.878/186.388 | 23/13 | 71.718/34.674 | 未割当 | 全体資源/WCET未確定 |
| S3-T-059 | FIR,equalize_demap,time_deinterleave,RS | 199.527/271.127 | 21/5 | 64.226/34.674 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-05a | sync,equalize_demap,time_deinterleave,RS | 169.414/240.809 | 22/12 | 103.241/67.182 | 未割当 | 全体資源/WCET未確定 |
| S3-T-05b | FIR,sync,equalize_demap,time_deinterleave,RS | 212.856/297.796 | 20/4 | 63.241/34.674 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-05c | FFT,equalize_demap,time_deinterleave,RS | 184.190/238.448 | 5/9 | 71.718/34.674 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-05d | FIR,FFT,equalize_demap,time_deinterleave,RS | 241.838/323.187 | 3/1 | 64.226/34.674 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-05e | sync,FFT,equalize_demap,time_deinterleave,RS | 197.950/265.958 | 4/8 | 71.718/35.659 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-05f | FIR,sync,FFT,equalize_demap,time_deinterleave,RS | 241.392/322.946 | 2/0 | 31.718/3.152 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-060 | Viterbi,RS | 1118.775/2140.534 | 21/18 | 42.904/28.814 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-061 | FIR,Viterbi,RS | 1176.423/2225.273 | 19/10 | 35.412/28.814 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-062 | sync,Viterbi,RS | 1146.311/2194.955 | 20/17 | 74.427/61.322 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-063 | FIR,sync,Viterbi,RS | 1189.753/2251.942 | 18/9 | 34.427/28.814 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-064 | FFT,Viterbi,RS | 1174.862/2219.505 | 3/14 | 74.427/60.337 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-065 | FIR,FFT,Viterbi,RS | 1232.511/2304.243 | 1/6 | 66.935/60.337 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-066 | sync,FFT,Viterbi,RS | 1188.623/2247.015 | 2/13 | 74.427/61.322 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-067 | FIR,sync,FFT,Viterbi,RS | 1232.065/2304.002 | 0/5 | 34.427/28.814 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-068 | equalize_demap,Viterbi,RS | 1139.962/2182.296 | 21/13 | 71.718/60.337 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-069 | FIR,equalize_demap,Viterbi,RS | 1197.611/2267.035 | 19/5 | 64.226/60.337 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-06a | sync,equalize_demap,Viterbi,RS | 1167.499/2236.717 | 20/12 | 103.241/92.845 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-06b | FIR,sync,equalize_demap,Viterbi,RS | 1210.941/2293.704 | 18/4 | 63.241/60.337 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-06c | FFT,equalize_demap,Viterbi,RS | 1182.274/2234.356 | 3/9 | 71.718/60.337 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-06d | FIR,FFT,equalize_demap,Viterbi,RS | 1239.923/2319.095 | 1/1 | 64.226/60.337 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-06e | sync,FFT,equalize_demap,Viterbi,RS | 1196.035/2261.866 | 2/8 | 71.718/61.322 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-06f | FIR,sync,FFT,equalize_demap,Viterbi,RS | 1239.477/2318.854 | 0/0 | 31.718/28.814 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-070 | time_deinterleave,Viterbi,RS | 1134.782/2172.550 | 21/18 | 42.904/28.814 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-071 | FIR,time_deinterleave,Viterbi,RS | 1192.431/2257.288 | 19/10 | 35.412/28.814 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-072 | sync,time_deinterleave,Viterbi,RS | 1162.318/2226.970 | 20/17 | 74.427/61.322 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-073 | FIR,sync,time_deinterleave,Viterbi,RS | 1205.761/2283.958 | 18/9 | 34.427/28.814 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-074 | FFT,time_deinterleave,Viterbi,RS | 1190.870/2251.520 | 3/14 | 74.427/60.337 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-075 | FIR,FFT,time_deinterleave,Viterbi,RS | 1248.519/2336.259 | 1/6 | 66.935/60.337 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-076 | sync,FFT,time_deinterleave,Viterbi,RS | 1204.630/2279.030 | 2/13 | 74.427/61.322 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-077 | FIR,sync,FFT,time_deinterleave,Viterbi,RS | 1248.073/2336.018 | 0/5 | 34.427/28.814 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-078 | equalize_demap,time_deinterleave,Viterbi,RS | 1143.378/2189.714 | 21/13 | 42.904/31.523 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-079 | FIR,equalize_demap,time_deinterleave,Viterbi,RS | 1201.027/2274.452 | 19/5 | 35.412/31.523 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-07a | sync,equalize_demap,time_deinterleave,Viterbi,RS | 1170.914/2244.134 | 20/12 | 74.427/64.031 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-07b | FIR,sync,equalize_demap,time_deinterleave,Viterbi,RS | 1214.357/2301.122 | 18/4 | 34.427/31.523 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-07c | FFT,equalize_demap,time_deinterleave,Viterbi,RS | 1185.690/2241.774 | 3/9 | 42.904/31.523 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-07d | FIR,FFT,equalize_demap,time_deinterleave,Viterbi,RS | 1243.339/2326.512 | 1/1 | 35.412/31.523 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-07e | sync,FFT,equalize_demap,time_deinterleave,Viterbi,RS | 1199.450/2269.284 | 2/8 | 42.904/32.508 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-07f | FIR,sync,FFT,equalize_demap,time_deinterleave,Viterbi,RS | 1242.893/2326.271 | 0/0 | 2.904/0.000 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-080 | TS | 32.995/40.266 | 24/18 | 40.000/2.904 | 1625/1625 | 全体資源/WCET未確定 |
| S3-T-081 | FIR,TS | 90.643/125.005 | 22/10 | 32.508/2.904 | 1807/1807 | 全体資源/WCET未確定 |
| S3-T-082 | sync,TS | 60.531/94.687 | 23/17 | 71.523/35.412 | 200/196 | 全体資源/WCET未確定 |
| S3-T-083 | FIR,sync,TS | 103.973/151.674 | 21/9 | 31.523/2.904 | 未割当 | 全体資源/WCET未確定 |
| S3-T-084 | FFT,TS | 89.082/119.237 | 6/14 | 71.523/34.427 | 202/199 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-085 | FIR,FFT,TS | 146.731/203.975 | 4/6 | 64.031/34.427 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-086 | sync,FFT,TS | 102.843/146.747 | 5/13 | 71.523/35.412 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-087 | FIR,sync,FFT,TS | 146.285/203.735 | 3/5 | 31.523/2.904 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-088 | equalize_demap,TS | 54.182/82.028 | 24/13 | 68.814/34.427 | 234/230 | 全体資源/WCET未確定 |
| S3-T-089 | FIR,equalize_demap,TS | 111.831/166.767 | 22/5 | 61.322/34.427 | 未割当 | 全体資源/WCET未確定 |
| S3-T-08a | sync,equalize_demap,TS | 81.718/136.449 | 23/12 | 100.337/66.935 | 0/0 | 全体資源/WCET未確定 |
| S3-T-08b | FIR,sync,equalize_demap,TS | 125.161/193.436 | 21/4 | 60.337/34.427 | 未割当 | 全体資源/WCET未確定 |
| S3-T-08c | FFT,equalize_demap,TS | 96.494/134.088 | 6/9 | 68.814/34.427 | 234/230 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-08d | FIR,FFT,equalize_demap,TS | 154.143/218.827 | 4/1 | 61.322/34.427 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-08e | sync,FFT,equalize_demap,TS | 110.254/161.599 | 5/8 | 68.814/35.412 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-08f | FIR,sync,FFT,equalize_demap,TS | 153.697/218.586 | 3/0 | 28.814/2.904 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-090 | time_deinterleave,TS | 61.594/96.880 | 24/18 | 68.814/31.718 | 264/248 | 全体資源/WCET未確定 |
| S3-T-091 | FIR,time_deinterleave,TS | 119.243/181.618 | 22/10 | 61.322/31.718 | 未割当 | 全体資源/WCET未確定 |
| S3-T-092 | sync,time_deinterleave,TS | 89.130/151.300 | 23/17 | 100.337/64.226 | 0/0 | 全体資源/WCET未確定 |
| S3-T-093 | FIR,sync,time_deinterleave,TS | 132.573/208.288 | 21/9 | 60.337/31.718 | 未割当 | 全体資源/WCET未確定 |
| S3-T-094 | FFT,time_deinterleave,TS | 117.682/175.850 | 6/14 | 100.337/63.241 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-095 | FIR,FFT,time_deinterleave,TS | 175.331/260.589 | 4/6 | 92.845/63.241 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-096 | sync,FFT,time_deinterleave,TS | 131.442/203.360 | 5/13 | 100.337/64.226 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-097 | FIR,sync,FFT,time_deinterleave,TS | 174.885/260.348 | 3/5 | 60.337/31.718 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-098 | equalize_demap,time_deinterleave,TS | 70.190/114.044 | 24/13 | 68.814/34.427 | 234/230 | 全体資源/WCET未確定 |
| S3-T-099 | FIR,equalize_demap,time_deinterleave,TS | 127.839/198.782 | 22/5 | 61.322/34.427 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-09a | sync,equalize_demap,time_deinterleave,TS | 97.726/168.464 | 23/12 | 100.337/66.935 | 0/0 | 全体資源/WCET未確定 |
| S3-T-09b | FIR,sync,equalize_demap,time_deinterleave,TS | 141.168/225.452 | 21/4 | 60.337/34.427 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-09c | FFT,equalize_demap,time_deinterleave,TS | 112.502/166.104 | 6/9 | 68.814/34.427 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-09d | FIR,FFT,equalize_demap,time_deinterleave,TS | 170.151/250.842 | 4/1 | 61.322/34.427 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-09e | sync,FFT,equalize_demap,time_deinterleave,TS | 126.262/193.614 | 5/8 | 68.814/35.412 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-09f | FIR,sync,FFT,equalize_demap,time_deinterleave,TS | 169.704/250.601 | 3/0 | 28.814/2.904 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0a0 | Viterbi,TS | 1048.464/2070.880 | 22/18 | 43.152/31.718 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0a1 | FIR,Viterbi,TS | 1106.113/2155.619 | 20/10 | 35.659/31.718 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0a2 | sync,Viterbi,TS | 1076.000/2125.301 | 21/17 | 74.674/64.226 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0a3 | FIR,sync,Viterbi,TS | 1119.442/2182.288 | 19/9 | 34.674/31.718 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0a4 | FFT,Viterbi,TS | 1104.552/2149.851 | 4/14 | 74.674/63.241 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-0a5 | FIR,FFT,Viterbi,TS | 1162.200/2234.589 | 2/6 | 67.182/63.241 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0a6 | sync,FFT,Viterbi,TS | 1118.312/2177.361 | 3/13 | 74.674/64.226 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-0a7 | FIR,sync,FFT,Viterbi,TS | 1161.754/2234.348 | 1/5 | 34.674/31.718 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0a8 | equalize_demap,Viterbi,TS | 1069.652/2112.642 | 22/13 | 71.965/63.241 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0a9 | FIR,equalize_demap,Viterbi,TS | 1127.301/2197.381 | 20/5 | 64.473/63.241 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0aa | sync,equalize_demap,Viterbi,TS | 1097.188/2167.063 | 21/12 | 103.488/95.749 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0ab | FIR,sync,equalize_demap,Viterbi,TS | 1140.630/2224.050 | 19/4 | 63.488/63.241 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0ac | FFT,equalize_demap,Viterbi,TS | 1111.964/2164.702 | 4/9 | 71.965/63.241 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-0ad | FIR,FFT,equalize_demap,Viterbi,TS | 1169.612/2249.441 | 2/1 | 64.473/63.241 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0ae | sync,FFT,equalize_demap,Viterbi,TS | 1125.724/2192.212 | 3/8 | 71.965/64.226 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-0af | FIR,sync,FFT,equalize_demap,Viterbi,TS | 1169.166/2249.200 | 1/0 | 31.965/31.718 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0b0 | time_deinterleave,Viterbi,TS | 1064.472/2102.896 | 22/18 | 43.152/31.718 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0b1 | FIR,time_deinterleave,Viterbi,TS | 1122.120/2187.634 | 20/10 | 35.659/31.718 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0b2 | sync,time_deinterleave,Viterbi,TS | 1092.008/2157.316 | 21/17 | 74.674/64.226 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0b3 | FIR,sync,time_deinterleave,Viterbi,TS | 1135.450/2214.304 | 19/9 | 34.674/31.718 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0b4 | FFT,time_deinterleave,Viterbi,TS | 1120.560/2181.866 | 4/14 | 74.674/63.241 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-0b5 | FIR,FFT,time_deinterleave,Viterbi,TS | 1178.208/2266.605 | 2/6 | 67.182/63.241 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0b6 | sync,FFT,time_deinterleave,Viterbi,TS | 1134.320/2209.376 | 3/13 | 74.674/64.226 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-0b7 | FIR,sync,FFT,time_deinterleave,Viterbi,TS | 1177.762/2266.364 | 1/5 | 34.674/31.718 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0b8 | equalize_demap,time_deinterleave,Viterbi,TS | 1073.068/2120.060 | 22/13 | 43.152/34.427 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0b9 | FIR,equalize_demap,time_deinterleave,Viterbi,TS | 1130.716/2204.798 | 20/5 | 35.659/34.427 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0ba | sync,equalize_demap,time_deinterleave,Viterbi,TS | 1100.604/2174.480 | 21/12 | 74.674/66.935 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0bb | FIR,sync,equalize_demap,time_deinterleave,Viterbi,TS | 1144.046/2231.468 | 19/4 | 34.674/34.427 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0bc | FFT,equalize_demap,time_deinterleave,Viterbi,TS | 1115.379/2172.120 | 4/9 | 43.152/34.427 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-0bd | FIR,FFT,equalize_demap,time_deinterleave,Viterbi,TS | 1173.028/2256.858 | 2/1 | 35.659/34.427 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0be | sync,FFT,equalize_demap,time_deinterleave,Viterbi,TS | 1129.140/2199.630 | 3/8 | 43.152/35.412 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-0bf | FIR,sync,FFT,equalize_demap,time_deinterleave,Viterbi,TS | 1172.582/2256.617 | 1/0 | 3.152/2.904 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0c0 | RS,TS | 104.048/111.371 | 23/18 | 40.000/3.152 | 未割当 | 全体資源/WCET未確定 |
| S3-T-0c1 | FIR,RS,TS | 161.697/196.110 | 21/10 | 32.508/3.152 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0c2 | sync,RS,TS | 131.584/165.792 | 22/17 | 71.523/35.659 | 未割当 | 全体資源/WCET未確定 |
| S3-T-0c3 | FIR,sync,RS,TS | 175.026/222.779 | 20/9 | 31.523/3.152 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0c4 | FFT,RS,TS | 160.136/190.342 | 5/14 | 71.523/34.674 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-0c5 | FIR,FFT,RS,TS | 217.784/275.080 | 3/6 | 64.031/34.674 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0c6 | sync,FFT,RS,TS | 173.896/217.852 | 4/13 | 71.523/35.659 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-0c7 | FIR,sync,FFT,RS,TS | 217.338/274.839 | 2/5 | 31.523/3.152 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0c8 | equalize_demap,RS,TS | 125.236/153.133 | 23/13 | 68.814/34.674 | 未割当 | 全体資源/WCET未確定 |
| S3-T-0c9 | FIR,equalize_demap,RS,TS | 182.884/237.871 | 21/5 | 61.322/34.674 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0ca | sync,equalize_demap,RS,TS | 152.772/207.554 | 22/12 | 100.337/67.182 | 未割当 | 全体資源/WCET未確定 |
| S3-T-0cb | FIR,sync,equalize_demap,RS,TS | 196.214/264.541 | 20/4 | 60.337/34.674 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0cc | FFT,equalize_demap,RS,TS | 167.547/205.193 | 5/9 | 68.814/34.674 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-0cd | FIR,FFT,equalize_demap,RS,TS | 225.196/289.932 | 3/1 | 61.322/34.674 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0ce | sync,FFT,equalize_demap,RS,TS | 181.308/232.703 | 4/8 | 68.814/35.659 | 未割当 | 全体資源/WCET未確定；現行O3 scalar FFT超過 |
| S3-T-0cf | FIR,sync,FFT,equalize_demap,RS,TS | 224.750/289.691 | 2/0 | 28.814/3.152 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0d0 | time_deinterleave,RS,TS | 132.648/167.984 | 23/18 | 68.814/31.965 | 未割当 | 全体資源/WCET未確定 |
| S3-T-0d1 | FIR,time_deinterleave,RS,TS | 190.296/252.723 | 21/10 | 61.322/31.965 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0d2 | sync,time_deinterleave,RS,TS | 160.184/222.405 | 22/17 | 100.337/64.473 | 未割当 | 全体資源/WCET未確定 |
| S3-T-0d3 | FIR,sync,time_deinterleave,RS,TS | 203.626/279.392 | 20/9 | 60.337/31.965 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0d4 | FFT,time_deinterleave,RS,TS | 188.735/246.955 | 5/14 | 100.337/63.488 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0d5 | FIR,FFT,time_deinterleave,RS,TS | 246.384/331.693 | 3/6 | 92.845/63.488 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0d6 | sync,FFT,time_deinterleave,RS,TS | 202.495/274.465 | 4/13 | 100.337/64.473 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0d7 | FIR,sync,FFT,time_deinterleave,RS,TS | 245.938/331.452 | 2/5 | 60.337/31.965 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0d8 | equalize_demap,time_deinterleave,RS,TS | 141.243/185.148 | 23/13 | 68.814/34.674 | 未割当 | 全体資源/WCET未確定 |
| S3-T-0d9 | FIR,equalize_demap,time_deinterleave,RS,TS | 198.892/269.887 | 21/5 | 61.322/34.674 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0da | sync,equalize_demap,time_deinterleave,RS,TS | 168.779/239.569 | 22/12 | 100.337/67.182 | 未割当 | 全体資源/WCET未確定 |
| S3-T-0db | FIR,sync,equalize_demap,time_deinterleave,RS,TS | 212.222/296.556 | 20/4 | 60.337/34.674 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0dc | FFT,equalize_demap,time_deinterleave,RS,TS | 183.555/237.208 | 5/9 | 68.814/34.674 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0dd | FIR,FFT,equalize_demap,time_deinterleave,RS,TS | 241.204/321.947 | 3/1 | 61.322/34.674 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0de | sync,FFT,equalize_demap,time_deinterleave,RS,TS | 197.315/264.719 | 4/8 | 68.814/35.659 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0df | FIR,sync,FFT,equalize_demap,time_deinterleave,RS,TS | 240.758/321.706 | 2/0 | 28.814/3.152 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0e0 | Viterbi,RS,TS | 1118.140/2139.294 | 21/18 | 40.000/28.814 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0e1 | FIR,Viterbi,RS,TS | 1175.789/2224.033 | 19/10 | 32.508/28.814 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0e2 | sync,Viterbi,RS,TS | 1145.676/2193.715 | 20/17 | 71.523/61.322 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0e3 | FIR,sync,Viterbi,RS,TS | 1189.118/2250.703 | 18/9 | 31.523/28.814 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0e4 | FFT,Viterbi,RS,TS | 1174.228/2218.265 | 3/14 | 71.523/60.337 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-0e5 | FIR,FFT,Viterbi,RS,TS | 1231.876/2303.004 | 1/6 | 64.031/60.337 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0e6 | sync,FFT,Viterbi,RS,TS | 1187.988/2245.775 | 2/13 | 71.523/61.322 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-0e7 | FIR,sync,FFT,Viterbi,RS,TS | 1231.430/2302.763 | 0/5 | 31.523/28.814 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0e8 | equalize_demap,Viterbi,RS,TS | 1139.328/2181.056 | 21/13 | 68.814/60.337 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0e9 | FIR,equalize_demap,Viterbi,RS,TS | 1196.977/2265.795 | 19/5 | 61.322/60.337 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0ea | sync,equalize_demap,Viterbi,RS,TS | 1166.864/2235.477 | 20/12 | 100.337/92.845 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0eb | FIR,sync,equalize_demap,Viterbi,RS,TS | 1210.306/2292.464 | 18/4 | 60.337/60.337 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0ec | FFT,equalize_demap,Viterbi,RS,TS | 1181.640/2233.116 | 3/9 | 68.814/60.337 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-0ed | FIR,FFT,equalize_demap,Viterbi,RS,TS | 1239.288/2317.855 | 1/1 | 61.322/60.337 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0ee | sync,FFT,equalize_demap,Viterbi,RS,TS | 1195.400/2260.627 | 2/8 | 68.814/61.322 | 未割当 | T_VITERBI16_ARITHMETIC；現行O3 scalar FFT超過 |
| S3-T-0ef | FIR,sync,FFT,equalize_demap,Viterbi,RS,TS | 1238.842/2317.614 | 0/0 | 28.814/28.814 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0f0 | time_deinterleave,Viterbi,RS,TS | 1134.148/2171.310 | 21/18 | 40.000/28.814 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0f1 | FIR,time_deinterleave,Viterbi,RS,TS | 1191.796/2256.048 | 19/10 | 32.508/28.814 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0f2 | sync,time_deinterleave,Viterbi,RS,TS | 1161.684/2225.731 | 20/17 | 71.523/61.322 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0f3 | FIR,sync,time_deinterleave,Viterbi,RS,TS | 1205.126/2282.718 | 18/9 | 31.523/28.814 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0f4 | FFT,time_deinterleave,Viterbi,RS,TS | 1190.235/2250.280 | 3/14 | 71.523/60.337 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0f5 | FIR,FFT,time_deinterleave,Viterbi,RS,TS | 1247.884/2335.019 | 1/6 | 64.031/60.337 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0f6 | sync,FFT,time_deinterleave,Viterbi,RS,TS | 1203.996/2277.791 | 2/13 | 71.523/61.322 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0f7 | FIR,sync,FFT,time_deinterleave,Viterbi,RS,TS | 1247.438/2334.778 | 0/5 | 31.523/28.814 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0f8 | equalize_demap,time_deinterleave,Viterbi,RS,TS | 1142.744/2188.474 | 21/13 | 40.000/31.523 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0f9 | FIR,equalize_demap,time_deinterleave,Viterbi,RS,TS | 1200.392/2273.212 | 19/5 | 32.508/31.523 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0fa | sync,equalize_demap,time_deinterleave,Viterbi,RS,TS | 1170.280/2242.895 | 20/12 | 71.523/64.031 | 未割当 | T_VITERBI16_ARITHMETIC |
| S3-T-0fb | FIR,sync,equalize_demap,time_deinterleave,Viterbi,RS,TS | 1213.722/2299.882 | 18/4 | 31.523/31.523 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-T-0fc | FFT,equalize_demap,time_deinterleave,Viterbi,RS,TS | 1185.055/2240.534 | 3/9 | 40.000/31.523 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0fd | FIR,FFT,equalize_demap,time_deinterleave,Viterbi,RS,TS | 1242.704/2325.273 | 1/1 | 32.508/31.523 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0fe | sync,FFT,equalize_demap,time_deinterleave,Viterbi,RS,TS | 1198.816/2268.044 | 2/8 | 40.000/32.508 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-T-0ff | FIR,sync,FFT,equalize_demap,time_deinterleave,Viterbi,RS,TS | 1242.258/2325.032 | 0/0 | 0.000/0.000 | 未割当 | T_VITERBI16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM；現行O3 scalar FFT超過 |
| S3-S-000 | RFのみ | 77.775/94.442 | 15/15 | 100.000/0.000 | 210/196 | 全体資源/WCET未確定 |
| S3-S-001 | FIR | 233.307/334.149 | 9/3 | 115.440/0.000 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-002 | sync | 176.324/289.190 | 14/13 | 215.440/115.440 | 未割当 | 全体資源/WCET未確定 |
| S3-S-003 | FIR,sync | 281.407/430.349 | 8/1 | 115.440/0.000 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-004 | TC8PSK | 1231.226/2400.096 | 11/14 | 107.215/115.440 | 未割当 | S_TC8PSK16_ARITHMETIC |
| S3-S-005 | FIR,TC8PSK | 1386.758/2639.803 | 5/2 | 122.655/115.440 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-006 | sync,TC8PSK | 1279.326/2496.296 | 10/12 | 107.215/115.440 | 未割当 | S_TC8PSK16_ARITHMETIC |
| S3-S-007 | FIR,sync,TC8PSK | 1384.409/2637.454 | 4/0 | 7.215/0.000 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-008 | frame_deinterleave | 102.083/130.827 | 13/15 | 107.251/7.215 | 未割当 | 全体資源/WCET未確定 |
| S3-S-009 | FIR,frame_deinterleave | 257.615/370.534 | 7/3 | 122.691/7.215 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-00a | sync,frame_deinterleave | 200.632/325.575 | 12/13 | 222.691/122.655 | 未割当 | 全体資源/WCET未確定 |
| S3-S-00b | FIR,sync,frame_deinterleave | 305.715/466.734 | 6/1 | 122.691/7.215 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-00c | TC8PSK,frame_deinterleave | 1252.381/2430.321 | 9/14 | 107.251/115.440 | 未割当 | S_TC8PSK16_ARITHMETIC |
| S3-S-00d | FIR,TC8PSK,frame_deinterleave | 1407.913/2670.029 | 3/2 | 122.691/115.440 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-00e | sync,TC8PSK,frame_deinterleave | 1300.481/2526.521 | 8/12 | 107.251/115.440 | 未割当 | S_TC8PSK16_ARITHMETIC |
| S3-S-00f | FIR,sync,TC8PSK,frame_deinterleave | 1405.565/2667.680 | 2/0 | 7.251/0.000 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-010 | RS | 244.129/263.665 | 13/15 | 106.521/7.251 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-011 | FIR,RS | 399.661/503.372 | 7/3 | 121.961/7.251 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-012 | sync,RS | 342.677/458.413 | 12/13 | 221.961/122.691 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-013 | FIR,sync,RS | 447.761/599.572 | 6/1 | 121.961/7.251 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-014 | TC8PSK,RS | 1397.580/2569.319 | 9/14 | 113.736/122.691 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-015 | FIR,TC8PSK,RS | 1553.112/2809.026 | 3/2 | 129.176/122.691 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-016 | sync,TC8PSK,RS | 1445.680/2665.519 | 8/12 | 113.736/122.691 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-017 | FIR,sync,TC8PSK,RS | 1550.763/2806.677 | 2/0 | 13.736/7.251 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-018 | frame_deinterleave,RS | 265.268/293.860 | 11/15 | 106.521/7.215 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-019 | FIR,frame_deinterleave,RS | 420.801/533.567 | 5/3 | 121.961/7.215 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-01a | sync,frame_deinterleave,RS | 363.817/488.609 | 10/13 | 221.961/122.655 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-01b | FIR,sync,frame_deinterleave,RS | 468.901/629.767 | 4/1 | 121.961/7.215 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-01c | TC8PSK,frame_deinterleave,RS | 1415.566/2593.355 | 7/14 | 106.521/115.440 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-01d | FIR,TC8PSK,frame_deinterleave,RS | 1571.098/2833.062 | 1/2 | 121.961/115.440 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-01e | sync,TC8PSK,frame_deinterleave,RS | 1463.666/2689.555 | 6/12 | 106.521/115.440 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-01f | FIR,sync,TC8PSK,frame_deinterleave,RS | 1568.750/2830.713 | 0/0 | 6.521/0.000 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-020 | TS | 79.200/97.225 | 15/15 | 100.000/6.521 | 188/174 | 全体資源/WCET未確定 |
| S3-S-021 | FIR,TS | 234.732/336.932 | 9/3 | 115.440/6.521 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-022 | sync,TS | 177.749/291.974 | 14/13 | 215.440/121.961 | 未割当 | 全体資源/WCET未確定 |
| S3-S-023 | FIR,sync,TS | 282.832/433.132 | 8/1 | 115.440/6.521 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-024 | TC8PSK,TS | 1232.651/2402.879 | 11/14 | 107.215/121.961 | 未割当 | S_TC8PSK16_ARITHMETIC |
| S3-S-025 | FIR,TC8PSK,TS | 1388.183/2642.586 | 5/2 | 122.655/121.961 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-026 | sync,TC8PSK,TS | 1280.751/2499.079 | 10/12 | 107.215/121.961 | 未割当 | S_TC8PSK16_ARITHMETIC |
| S3-S-027 | FIR,sync,TC8PSK,TS | 1385.834/2640.238 | 4/0 | 7.215/6.521 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-028 | frame_deinterleave,TS | 103.508/133.610 | 13/15 | 107.251/13.736 | 未割当 | 全体資源/WCET未確定 |
| S3-S-029 | FIR,frame_deinterleave,TS | 259.040/373.317 | 7/3 | 122.691/13.736 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-02a | sync,frame_deinterleave,TS | 202.057/328.359 | 12/13 | 222.691/129.176 | 未割当 | 全体資源/WCET未確定 |
| S3-S-02b | FIR,sync,frame_deinterleave,TS | 307.140/469.517 | 6/1 | 122.691/13.736 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-02c | TC8PSK,frame_deinterleave,TS | 1253.806/2433.105 | 9/14 | 107.251/121.961 | 未割当 | S_TC8PSK16_ARITHMETIC |
| S3-S-02d | FIR,TC8PSK,frame_deinterleave,TS | 1409.338/2672.812 | 3/2 | 122.691/121.961 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-02e | sync,TC8PSK,frame_deinterleave,TS | 1301.906/2529.305 | 8/12 | 107.251/121.961 | 未割当 | S_TC8PSK16_ARITHMETIC |
| S3-S-02f | FIR,sync,TC8PSK,frame_deinterleave,TS | 1406.989/2670.463 | 2/0 | 7.251/6.521 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-030 | RS,TS | 242.704/260.881 | 13/15 | 100.000/7.251 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-031 | FIR,RS,TS | 398.236/500.588 | 7/3 | 115.440/7.251 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-032 | sync,RS,TS | 341.253/455.630 | 12/13 | 215.440/122.691 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-033 | FIR,sync,RS,TS | 446.336/596.788 | 6/1 | 115.440/7.251 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-034 | TC8PSK,RS,TS | 1396.155/2566.535 | 9/14 | 107.215/122.691 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-035 | FIR,TC8PSK,RS,TS | 1551.687/2806.242 | 3/2 | 122.655/122.691 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-036 | sync,TC8PSK,RS,TS | 1444.255/2662.735 | 8/12 | 107.215/122.691 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-037 | FIR,sync,TC8PSK,RS,TS | 1549.338/2803.893 | 2/0 | 7.215/7.251 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-038 | frame_deinterleave,RS,TS | 263.844/291.076 | 11/15 | 100.000/7.215 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-039 | FIR,frame_deinterleave,RS,TS | 419.376/530.784 | 5/3 | 115.440/7.215 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-03a | sync,frame_deinterleave,RS,TS | 362.392/485.825 | 10/13 | 215.440/122.655 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-03b | FIR,sync,frame_deinterleave,RS,TS | 467.476/626.984 | 4/1 | 115.440/7.215 | 未割当 | SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-03c | TC8PSK,frame_deinterleave,RS,TS | 1414.141/2590.571 | 7/14 | 100.000/115.440 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-03d | FIR,TC8PSK,frame_deinterleave,RS,TS | 1569.673/2830.278 | 1/2 | 115.440/115.440 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-03e | sync,TC8PSK,frame_deinterleave,RS,TS | 1462.241/2686.771 | 6/12 | 100.000/115.440 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |
| S3-S-03f | FIR,sync,TC8PSK,frame_deinterleave,RS,TS | 1567.325/2827.930 | 0/0 | 0.000/0.000 | 未割当 | S_TC8PSK16_ARITHMETIC; SELECTED_KERNEL_LOW_COST_SUM |


## 9. 再現・証拠・未完了の範囲

- [固定入力](s3-partition-audit/inputs.json.gz)：過去資料第24版からS3の320割当だけを抽出。入力provenanceへ元資料と台帳のSHA256を保存。
- [全台帳・全経路](s3-partition-audit/estimate.json.gz)：gzip圧縮JSON。各割当の全体資源・WCET・performance_passはnull。帯域表は必要条件。
- [全RS message割当](s3-partition-audit/message-assignments.csv.gz)：方向・page数・半二重RPC時間を控除したRF割当とport別余裕。
- [要約](s3-partition-audit/summary.json) / [Octal/Quad既存モデルの再計算](s3-partition-audit/exact-rs.json)。
- [今回のunittest実行ログ](s3-partition-audit/unittest.txt)：数値・台帳・通信条件の検査。全受信機・実機・新CADの試験ではない。

```sh
python3 experiments/s3_partition_audit.py
python3 -m unittest discover -s tests -p 'test_s3_partition_audit.py' -v
python3 -m unittest discover -s tests -p 'test_s3_rs_offload_budget.py' -v
```

通常の再計算は `build/s3-partition-audit/` に出力する。記録を更新する場合は
`--output reports/s3-partition-audit` を指定し、生成差分を確認する。
スクリプト自体に追加デシメート・再量子化による帯域救済はない。

### 同じ誤判断を防ぐための判定

| 論点 | 今回の扱い | 残る不足 |
|---|---|---|
| 前回の第一案を「完成できる」と決定 | 今回は決定・採用しない。T-A/S-3は検証順 | FPGA Forneyを含むS-3全体の資源見積もりもまだない |
| 部分topの合格・空きLUTを完成回路へ転用 | sourceとtopの範囲を限定し、保持追加後の失敗を併記 | 同期/FIR/TMCC/deinterleave/通信/保持を接続した各T/S topとSTA |
| 専用コア全容量をRS空き予算にする | RF等を控除した751〜3002 cycles/CWを**仮定モデル**として表示 | coreごとのWCET、割込み、DMA stall、solver/RPCの最悪実行時間 |
| CPU平均24件を性能条件の合格とする | `CPU_average_model_screen_pass` と命名。全体performance_passはnull | 資源・buffer寿命・各core期限を含む第一段階の完了 |
| 通信帯域が足りれば採用する | 未実装endpoint、pin数のみ、平均容量、同一batch依存未検証を明記 | GPIO割付、IO/CDC、ready/credit/ACK、符号語保持、PSRAM最悪仲裁 |
| 原依頼を完了したとして中断 | この記録は未完了の探索結果。完全見積もりの完了とはしない | 環境内でできる設計・RTL・SDK統合を実機待ちと分類しない |
| 実現不可の一般化 | PR5の保持付き実装は測定clockで不合格。全分担の不可能性は未証明 | 別分担・別RTLについて成立又は不成立の根拠を埋める |

今回の依頼に対しては、PR4への検算結果とこの未完了判定の反映を行う。
完全な処理分担見積もり、全RTLの完成、実機の受信動作まで完了したという報告はしない。

一次資料は [PR4の固定HEAD](https://github.com/kazuki0824/tangviterbi/tree/2b9823f60a546cd3c6a1b9d4dcb7441387926fed)、
[PR5保持追加後の固定証拠](https://github.com/kazuki0824/tangviterbi/blob/6ee70d8ff76d9bc6748a0a089cee4156d13427e0/reports/s3-receiver-followup.json)、
[Sipeed](https://wiki.sipeed.com/hardware/en/tang/Tang-Nano-9K/Nano-9K.html)、
[IDF SPI](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/spi_master.html)、
[IDF LCD](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/lcd/i80_lcd.html)、
[IDF SDMMC](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/sdmmc_host.html)、
[ITU-R BO.1408-1](https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-1-200204-I!!PDF-E.pdf)、
[Gowin UG290](https://cdn.gowinsemi.com.cn/UG290E.pdf)。

## 12. 後続の実装・測定と現在の未完了理由

Forney実装と選択partialの9426位置失敗、target scalar FFTの期限下限失敗、RF pollingと各core予算、同一I2S clock/GDMA割当、T FEC/実メモリの9001位置失敗・compact8605位置の配置探索中断、固定SIMD FFTと短いstage tileまで進めた。
[RF期限](s3-rf-schedule-closure.md)、[Forney](s3-rs-forney.md)、[T共配置](s3-t-fec-resource.md)、[SIMD FFT](s3-fft-simd.md)にsourceと判定範囲を記録する。

これらは実装を測定した部分判定であり、全候補の性能ゲート完了ではない。各stageの未実装費用を0にせず、320所有者台帳の全体performance_passは未確定のまま。元の4 SoC全対象の完了も、このS3台帳だけでは成立しない。

接続断から実行環境が復旧した。clean checkoutでSIMD/startupの15 unittest、tiled S3 target compile/未解決symbolなしの結合を再現し、raw object hash/log/disassemblyを回収した。追加SDK/joint scheduler検証は未完了。queued CIを合格扱いにしない。残る環境内の設計/実装と実機依存は[s3-receiver-blockers.md](s3-receiver-blockers.md)に記載する。
