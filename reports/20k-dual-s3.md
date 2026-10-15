# Tang Nano 20K ×1＋ESP32-S3 ×2：ISDB-T/S同時受信の分担見積もり

**最新：[T入力保持RAMと資源削減](20k-dual-s3-t-buffer.md)。T上流1 symbol保持を実RTLへ接続し、6条件・228 FFT framesで記載の有限契約を通過。Mode 3は保持RAM込み42/46 BSRAM。第1項目全体・全位相・受信機採用は未完了。**

**前段：[実フレームcapture／出力とT/S DMAの接続](20k-dual-s3-frame-stream.md)。実stream・有限slot所有権を接続し、2 slot案の期限不合格を確認して3 slot案へ修正。第1項目全体の完了・受信機採用とは区別する。**

**前段：[実T時間deinterleaveとFFT／Sの接続](20k-dual-s3-t-time-dma.md)。第1項目内の実T grouping/reorderをRTL化し、自然順byte列からの同時動作を検証。受信機全体の成立・正式採用は未確定。**

**後続更新：[SDRAM転送間の待ち削減と再検証](20k-dual-s3-memory-turnover.md)。旧128-frame反例を同条件で解消し、他Mode・位相変更も通過。実T/IO接続等を含む第1項目全体は未完了。以下は各段階の記録。**

**後続更新：[実S frame DMA・有限保持・競合の再検算](20k-dual-s3-s-frame-dma.md)。第1項目全体は未完了。以下の順次S CWモデルによる帯域・期限結果を実S permutationへ転用しない。**

2026-10-14（JST）。基準はmain `4f92e8e`（PR #4取り込み後）。

**前段：[密配置・有限FIFO・bank分離・S優先入口](20k-dual-s3-memory-clients.md)。64 frameと旧24 frameの有限契約試験を通過し、接続部分は5,425 logic／13 BSRAM／8 DSP。ただし実T/S client生成・producer保持・全位相の保証は未完了で、第1項目は継続中。全体占有率・STAの合格値ではない。**

**優先して検証する設計案はB：S3は各RF取得・native IQの無損失転送、20Kは両復調を同時実行、TのFFTはタイル化してSDRAMを使用、RSはT/S/TMCCで共有する構成。**
前段の設計予算は20,452 logic位置（98.63%）、44 BSRAM（95.65%）、38 DSP18（79.17%）。新規DMA・CDC・arbiterを結合した全体占有率は未測定で、この数字を結合RTLの合格値としない。
ただしこれは新しい構成の**実装前予算**であって、合成結果でも保証上限でもない。
現時点で、指定された手順の①「性能余裕を確認済み」を満たして②正式通信割当→③採用まで進められる受信機は**0件**。
Bは実現可能と確定した案ではなく、具体的な容量・期限条件を持つ設計仮説である。
「20Kなら成立する」「全体検算が完了した」「あとは実機だけ」とは結論しない。

このPRは新条件の計算・候補台帳を保存する。受信機RTL完成や成立確定を報告するPRではない。
依頼された「性能余裕内の分担を採用する」という到達点は未達であり、理由と完了条件は§9に記載する。

## 1. 条件と検算範囲

- Tang Nano **20K完成基板1枚**、S3-WROOM-1U **2枚**。S3-Tが地上1周波数、S3-Sが衛星1周波数を同時受信する。
- N8R8とN16R8はCPU、内部SRAM、RF、8 MiB PSRAMが共通。Flash 8/16 MiBの差をDSP性能差にしない。「N16」が文字通りN16（R8なし）ならPSRAMなし。案A/B/CはS3外部PSRAMを処理用に使わないため、その差は本計算を変えない。firmwareの実リンク・起動は各型番で必要。
- Tは全13セグメント、Mode 1/2/3。Sは従来ISDB-S、ISDB-S3ではない。SのTC8PSKに加えBPSK/QPSK、TMCCを省略しない。映像・音声復号、CAS解除は処理対象外。
- 1 bitstreamにT/S両方を置く。別imageへの切替、処理停止中の再構成、`max(T,S)`資源集計は使わない。
- RFは各S3の内蔵RF/private capture。地上波・LNB出力をS3の受信帯へ変換する**独立2系統のRF前段**、帯域フィルタ、必要なLNB給電が別途必要。S3と20Kだけでアンテナへ直結できる意味ではない。
- native T=16 MSa/s、S=40 MSa/s、I10/Q10。32 bit格納の未使用12 bitを削る5 byte/2 sample梱包だけを許す。通信都合のソフトウェア追加間引き、I/Q有効bit削減、LLR精度削減、平均圧縮率依存、欠落許容は不採用。
- Sの40 MSa/sは約38.961 MHzの占有帯域に対し遷移帯域が狭い。公開rate設定から品質合格を推定しない。80 MSa/sが必要になる場合を§7で別計上する。
- 「すべて」は§2の有限処理グラフと§6の通信profileの全組合せを意味する。未知の任意アルゴリズム、任意clock、未定義GPIO符号化まで網羅したという主張はしない。集合外の既知の重要経路も§7で評価する。

### 基準HEADの計算をどう扱ったか

| 元の項目 | 今回の検算・扱い |
|---|---|
| 9Kの8,640 logic /26 BSRAM/20 DSP | 20Kの20,736 /46 /48へ変更。FFは15,552、PLLは2、SDRAMは8 MiB。9KのPSRAM controllerを20K SDRAM controllerと呼ばない |
| T/S排他の資源最大値 | 全16,384 pairを**加算**。共有RS案だけ別にarbiter/contextを加算して共有する |
| 旧Viterbiの高Fmax、旧RS3502 clocks | 旧復号不合格を保持。全受信機のFmax証拠へ転用しない。decoder単体2667 clocks/CWと、今回実装した共有wrapperの2672 clocks/CWを区別 |
| SのTS平均52.17 Mbit/s | 出口帯域とframe平均のみに使用。RS入口の保守期限は28.135828 µs/CW |
| TC8PSKのみのS partial回路 | BPSK/QPSK用K7を別途2,952 logic、1,502 FF、2 BSRAMで予約。TC8PSK距離演算は3 cycles/symbol＝86.58 MHz必要 |
| FFT8192の旧stage費用 | 面積参考値と期限を分離。タイル案は全sample・全binを保持する別アルゴリズム。旧FFT費用の測定済み認定はしない |
| 200 cycles/page | 通信API20 µs＝4,800 cycles/callへ置換する感度計算。旧項を引いてから足す |
| GPIO、pin数 | 9Kの35 pinを使わず、20K Rev1.30回路図のJ6=18信号、J5=16信号、合計34。搭載負荷とBL616の競合は別ゲート |
| 実測と見積もり | 新規全受信topの合成/P&R・実S3 WCETは実施していない。計算値・新規設計予算・既存部分実測を混同しない |

## 2. 全処理分担候補

[ownerships.json.gz](20k-dual-s3/ownerships.json.gz)に全所有者・全境界情報と全pairを保存する。

| 処理列 | 所有者の組合せ |
|---|---:|
| T：FIR/resample → 同期/GI → FFT → 等化/demap → time deinterleave → Viterbi → RS → TS | 2^8＝256 |
| S：FIR → 同期 → trellis/TC8PSK → frame deinterleave → RS → TS | 2^6＝64 |
| T/S同時 | 256×64＝**16,384** |

RFは常に各S3。各行はFPGA/SoC所有者、交差するデータ型と方向別MB/s、CPU低/高モデル、
FPGA各stage資源、加算後占有率、stageの必要MHz、T全mode周期、RS期限、除外理由を持つ。
資源の初期一次検査を通るのは44 pairだが、これは不完全なstage費用の楽観検査である。
不足する全S機能、I/O、SDRAM、制御をゼロとせず、`full_performance_pass=null`を保持する。

実用上の分担群は次のとおり。実装選択の失敗を、同じ分担の全実装の不可能性へ一般化しない。

| 群 | SoCへ置く追加処理 | FPGAとの境界 | 性能検算上の位置付け |
|---|---|---|---|
| RFのみ | 可逆梱包・取得管理のみ | T↑40、S↑100 MB/s；↓制御 | 最優先。全復調のFPGA予算は§3 |
| T FFT | 全bin FFT、reorder | T↑71.522848、↓31.522848 MB/s | 旧低モデルでもAPI後99.31%になる固定配線あり。scalar実装は既存target下限で周期超過。SIMD実WCET未確認 |
| T FFT＋等化/demap | 上記＋復調処理 | T↑68.813853、↓31.522848 | CPUが更に厳しい。全bin inputは捨てない |
| T FIR | 通常復調用filter/resample | ↑32.507937、↓制御 | 低CPU90.01%／高123.77%という旧模型。native取得とのjoint WCET未確認。帯域都合の追加filterは許さない |
| T同期／等化／time deinterleaveとそれらの組合せ | 該当stage | 全256行に記録 | 元の8-bit LLRを保持。CPUが通ってもSDRAM/PSRAM scatterアクセス費用は未確定 |
| T/S全RS | RS復号 | CW204 B↓、TS188 B↑ | 22,060 cycles/CWの既存scalar模型はSだけで784.05 Mcycles/s。S RFと共存不可。TもRF等追加で厳しい |
| S FIR／TC8PSK／frame処理のSoC移管 | 各stageまたは組合せ | 全64行に記録 | 選択したCPU模型では低費用でも不合格。rawデータ精度低下による救済はしない |
| TSだけSoC | packet出力 | T↓2.904337、S↓6.521250 MB/s追加 | S3 USB FSだけではTSを出せない。最終sinkへの別経路も必要。内部SRAM/driver負担が増える |

### RS内部の追加切断（whole-stage集合とは別）

S3-Sは低RF＋APIだけで約90.14% CPU、残り約1,332 cycles/CW程度しかない。
以下は既存部分実装を再利用する検討対象だが、これを満たすsolver WCETは未確認。
全RSを分けない案を優先し、部分案の不明費用を0にして採用しない。

| SoC側RS処理 | FPGA→SoC | SoC→FPGA | 204語batchでの追加wire量／判定 |
|---|---|---|---|
| 全RS | CW＋ID | TS＋ID | 11 page↓＋10 page↑、14.986126 MB/s。scalar CPU不合格 |
| BM＋Chien＋Forney | 19 B syndrome/ID | 20 B位置・値 | 1 page↓＋1 page↑、1.427250 MB/s。旧Chienだけで6,528 cycles/CW、選択実装は不合格 |
| BM＋Omega | 19 B syndrome/ID | 29 B係数/ID | 1 page↓＋2 page↑、2.140875 MB/s。CPU・全体資源未確定 |
| BM＋Omega＋Forney | syndrome19 Bとroots12 B | lambda13 Bとmagnitude12 B | ↓↑↓↑各1 page、2.854500 MB/s。CPU・4段の同一batch期限未確定 |

この4切断も、今回の[通信台帳](20k-dual-s3/routes.json.gz)の`RS_partial_catalog`で再計算した。
各messageを分割せずportへ割り当て、messageごとのpage数・API回数を数える。
RPCが使った半二重時間を引いてからraw100 MB/sとcontrolを置く。
単独経路数はBM/Chien/Forney=3,476、BM/Omega=3,360、BM/Omega/Forney=45,808、全RS=863。
T側のCPU一次条件候補と接続し、34 pinを超える組合せを除いた全**26,238 pair**を`RS_partial_pairs`へ保存した。
9K一系統のpin判定は流用していない。CPU不合格やWCET未確認を通信合格で上書きせず、正式step2割当は0。

## 3. FPGAへ集める4案の全体設計予算

以下の数は「この費用以下に実装する」という設計allocationであり実現を証明する値ではない。
stage見積もりのlogicはLUT4単独とALU/独立FFの配置位置問題を含むため、合成後は合法配置位置で検算する。

| 案 | FPGA内の違い | logic /20,736 | FF /15,552 | BSRAM /46 | DSP18 /48 | 判断 |
|---|---|---:|---:|---:|---:|---|
| A | タイルFFT、T/S独立RS | 22,252（107.31%） | 14,186（91.22%） | 47（102.17%） | 38（79.17%） | 改訂予算ではlogic/RAM超過 |
| **B** | **タイルFFT、T/S/TMCC共有RS** | **20,452（98.63%）** | **13,034（83.81%）** | **44（95.65%）** | **38（79.17%）** | **レジスタ版共有RSを優先。全体性能ゲートは未通過** |
| C | 内蔵RAM常駐FFT、共有RS | 18,952（91.40%） | 13,034（83.81%） | **56（121.74%）** | 34（70.83%） | RAM容量不合格 |
| D | TのFFTをS3-T、共有RS | 18,452（88.99%） | 12,522（80.52%） | 40（86.96%） | 30（62.50%） | SoC期限と通信往復が未確認 |

案Bの内訳は[summary.json](20k-dual-s3/summary.json)の`candidates[].blocks`に保存。
FIR/sync・等化等は基準HEADのarchitecture estimateであり測定値ではない。
新規allocationを導入した箇所は次のとおり。

| 新規allocation | 内容・根拠と限界 |
|---|---|
| Sの追加K7：2,952 logic /1,502 FF/2 BSRAM | T K7見積もりをSの別context用に丸ごと予約。S TC8PSKと同一回路に無料で統合したことにしない。S各符号化率のdepuncture/切替接続は別途必要 |
| 共有RS：3,000 logic /1,408 FF/3 BSRAM | 刺激回路込み部分配置は2,786 logic、1,311 FF、2 BSRAM。staging用1 BSRAMを予約。162 MHz指定は157.431 MHzの表示で不合格、RAM等のSTA網羅性にも欠落 |
| タイルFFT：2,500 logic /1,024 FF/8 BSRAM/8 DSP | 固定小数点tile・cross・係数ROM・burst address mapperを実装し部分配置。更新値は後続報告参照。前段の部分topは6 BSRAM、8 DSP。今回DMA・仲裁・CDCを接続し、並行cross処理用ROMを追加して8 BSRAM相当の構成になった。新規制御を含む合成は未実施で、このallocation内に収まる証拠ではない |
| I/O/SDRAM/TMCC/control：3,000 logic /2,000 FF/13 BSRAM | T受信4 KiB=2 block、S reorder16 KiB=8 block、TS/TMCC/arbiter等3 block。BL616側を受信処理に使ってCPUを増やさない。SDRAM controllerの刺激込み部分配置は1,515 logic。残りのCDC・arbiter・TMCC等を含め3,000 logicに収まる証拠はまだない |

BSRAMは18 Kbit全部をbyte payloadに使えるとはせず、32/8-bit幅の2 KiB/blockでbufferを数える。
共有RS追加bufferとI/O reserveは区別した。PLLはlogic162 MHz、SDRAM135 MHz用の2個を予算化。
外部SPI SCLKは入力clockとして使う。PLL合法設定・clock routing・電気I/O STAは未検証。

### 計算処理のリアルタイム期限

| 処理 | 需要／期限 | 案Bのclock条件と余裕 |
|---|---|---|
| T最大TS | 23.23469994 Mbit/s | 出口27 MHz serial payload能力との差3.76530006 Mbit/s（13.95%） |
| S最大TS | 52.17 Mbit/s | 出口81 MHz serial payload能力との差28.83 Mbit/s（35.59%） |
| T K7、32 ACS | 最大25.212121 Mstep/s×2 clocks | 50.424242/162＝31.13% |
| S TC8PSK metric | 28.86 MSymbol/s×3 | 86.58/162＝53.44% |
| S BPSK/QPSK K7 | QPSK最大7/8を保守計上：28.86×2×7/8 Mstep/s×2 | 101.01/162＝62.35% |
| T RS | 15,448.603684 CW/s、64.73077 µs/CW | 共有wrapperの各slot2672/162＝16.493827 µs |
| S RS | ピーク35,541.871921 CW/s、28.135828 µs/CW | 同上。共有時はTによるblockと待ち行列がある |
| S TMCC RS | 90.332031 CW/s、11.07027 ms/CW | 140バイトzero-extensionと48バイト抽出を実装、独立encoderで規約・訂正を試験。共有slot2672 clocks |
| 共有RS合計 | (T＋Sピーク＋TMCC)×2672 | 約136.488 MHz、162 MHzの約84.252%。空き約15.748% |

共有RSは非preemptive。平均84%だけで「Sの毎CWが28.14 µs以内に完了する」とはしない。
共有wrapperは順序とTS source IDを保持する。追加の有限位相検算ではMode3で18待ち語、S最大完了遅延122.259 µs。
T/S/TMCCの出力FIFOを4096/1024/128 Bとしてcredit待ちは0。全位相証明・DMA結合は未達。
既存RS単体の2667 clocksは出力backpressureなし条件なので、出力FIFOが詰まる設計は再計算する。

### タイルFFTとSDRAM

8192＝64×128、4096＝64×64、2048＝32×64に分解するCooley–Tukey案。
第1群FFT→交差twiddle→転置→第2群FFTとし、全binを自然周波数順で復元する。
固定小数点RTLの全mode・全binを独立整数モデルとbit exact比較し、NumPy FFT/Nとも比較した。追加の結合試験ではpass間もDMA RTLで制御し、SDRAM pin modelで全frameを検証する。**受信BER・全phase到着・STAの保証ではない。**
追加の量子化や信号の間引きによって転送量を下げる設計ではない。

| Mode | 周期（GI1/32） | 2 cycles/butterfly＋4 cycles/交差twiddle | 162 MHz処理時間 | 計算占有率 |
|---|---:|---:|---:|---:|
| 1：2048 | 259.875 µs | 30,720 clocks | 189.630 µs | 72.97% |
| 2：4096 | 519.750 µs | 65,536 clocks | 404.543 µs | 77.83% |
| 3：8192 | 1039.500 µs | 139,264 clocks | 859.654 µs | 82.70% |

GI1/16、1/8、1/4は周期が長い。ただし全modeの制御変更・DMA粒度の実装試験は必要。
2-cycle butterflyが3-cycleになればMode3は162 MHzでも周期超過。125 MHzなら2-cycleでも超過する。
clock目標を達成Fmaxと呼ばない。

データは`n=n1+N1*n2`、出力は`k=k2+N2*k1`として配置する。
8列×128点の4 KiB tileを2面用い、32-byte連続転送で行列を転置する計画。
記録→第1pass read/write→第2pass read/write→復調へのreadを上限6回の4 byte/complexアクセスとして数える。
buffer所有権付き2-buffer scheduleのホスト模型に加え、FFT kernel・burst map・SDRAM controllerを実装した。DMA/arbiter/CDCも接続し、全modeの競合条件をcycle simulationで検証した。結果は最新報告参照。前段のMode3単体traceは333.632 MB/sであり、65%一定モデルを保証しない。今回のRTLはcrossと別bankのFFTも並行するため、前段の直列compute模型とはscheduleが異なる。

| SDRAM項目 | 必要量 |
|---|---:|
| T FFT、6×全complex Q15 | 189.137085 MB/s |
| T 8-bit LLR time deinterleave、write＋read | 57.627706 MB/s |
| S frame/CW、204 B×ピークCW/s×write/read | 14.501084 MB/s |
| その他アクセスの追加予算 | 10 MB/s |
| **合計** | **271.265875 MB/s** |
| 改訂設計目標：135 MHz×32 bit×効率65% | **351 MB/s** |
| 設計上の平均帯域余裕 | **79.734125 MB/s、22.72%** |

初回55%仮定は2-buffer模型でMode1=265.938 µs、Mode3=1063.752 µsとなり期限超過。
65%ならMode1/2/3=237.626/449.968/950.504 µsで条件付き期限内。
135 MHzおよび改訂65%効率は**未検証の設計要求**。34-bit等への丸めを32 bit転送のまま扱わない。
平均帯域のみの最低効率50.235%と、今回のscheduleで必要な約56.674%を区別する。100 MHz・55%なら220 MB/sでこの案は不合格。
32-byte burstのrow切替、read/write turnaround、refresh、最長grant間隔を数えるcontrollerが必要。
FFTとLLRを同じ時刻に扱う最大負荷を、独立benchmarkの帯域の和で合格としない。
raw T/Sを一旦全部SDRAMにwrite/readすると更に280 MB/s増えるので、案BはrawをFIRへ直接streamする。

容量はT interleave 5,690,880 B、S double-frame 155,904 B、FFT複数面131,072 B、
追加staging65,536 B＋管理等262,144 B＝6,305,536 B（8 MiBの75.17%）。
この容量残はSDRAM帯域不足を救わない。sample/LLRの精度は基準を維持する。

## 4. S3の資源と期限

各SoCは240 MHz×2 cores、内部SRAM512 KiBを独立に持つ。
他方のS3の空きCPUを無料で使わない。2台のRF tuningも独立であり、一台内の2 coreで2周波数を受ける構成ではない。

案Bの標準SPI witnessでは、Tの低CPU模型約35.21%、S約90.14%。
Sの高RF費用模型では**106.81%**となる。低模型だけをWCET合格にしない。
Sを6 cycles/sampleから8 cycles/sampleにすると80 Mcycles/s増えることが主因。

RF native40 MSa/sでは64 KiB bankの充填周期409.6 µs、旧12288-sample早期切替なら307.2 µs。
T16 MSa/sではそれぞれ1024/768 µs。取得bankを次に回す期限、core別packing、SPI API20 µsの
CPU-active時間、IRQ/PHY/内部RAM競合、4 KiB page保持を一緒に測定する必要がある。
「両core合計が480 Mcycles/s未満」だけではbank期限は閉じない。

CPUにFFT/RSを置かない案のSRAM容量目標は、RF3 bank192 KiB、packed ring32 KiB、
SDK/IRAM/driver/stack等160 KiBの予算＝384 KiB、raw容量差128 KiB。
160 KiBは目標allocationで、実リンク・ROM予約・起動後heapの保証値ではない。
PR4のT/S切替firmwareのELF空き値を、今回の2種類の専用firmwareの実測としては使わない。
案Dでは更にFFT2面64 KiB、係数等が必要。N16R8のFlash増量は内部SRAM不足を解消しない。

## 5. SoC/FPGAを渡る情報

本資料の↑は**SoC→FPGA**、↓は**FPGA→SoC**。

| 案 | S3-T ↑ / ↓ | S3-S ↑ / ↓ | FPGA外部 |
|---|---|---|---|
| A/B/C | native I10/Q10可逆packed 40 MB/s / status、credit、epoch、fault | native I10/Q10可逆packed 100 MB/s / 同左 | T/Sそれぞれserial TS、clock/valid/dataの3 pin |
| D | raw40＋全FFT bin31.522848 / GI除去後complex Q15 31.522848 MB/s | A/Bと同じ | T/S TS |
| RS部分移管 | T側は選択分担のまま | 上記rawに§2のsyndrome、係数、roots、訂正値を追加 | 元CWはFPGAで保持 |
| TS移管 | 該当TSを↓追加 | 該当TSを↓追加 | S3からの最終出力経路が別途必要 |

各SoCは↑↓それぞれ0.01 MB/sのcontrol予算を予約し、SPI half-duplex時間から引く。
チャンネルID、sample順序、page epoch、長さ、error、tune指示・ackを含める。
全データフロー台帳は`ownerships.json.gz`内に格納。方向を逆にした合算はしない。

## 6. 通常周辺機器の全経路候補と帯域余裕

[routes.json.gz](20k-dual-s3/routes.json.gz)は次の18 profileを組み合わせ、
controller排他・方向・半二重時間・5 GDMA対・各S3端子数を検査した全2,706 subsetから作る。
LCD/CAMは4 KiBごと8 µs gapを計上し、gapなしの楽観値を採用しない。
SPIは80 MHz S3 master、Octalは3 page batch、その他1 page、API20 µs、header80 bit。
SD/eMMCは40 MHz、command/CRC/API20 µsを控除。FPGAはslave/card相当を実装する必要がある。

| profile（controller違いも列挙） | 方向 | 信号pin | 実効MB/s |
|---|---|---:|---:|
| SPI2 Octal80 | 半二重 | 10 | 70.327658 |
| SPI2 Quad80 / SPI3 Quad80 | 半二重 | 各6 | 33.395842 |
| SPI2 Dual80 / SPI3 Dual80 | 半二重 | 各4 | 18.180204 |
| SPI2 Single80 / SPI3 Single80 | 半二重 | 各4 | 9.512308 |
| LCD16 / LCD8、40 MHz | ↑専用 | 19 /11 | 68.956229 /36.967509 |
| CAM16 / CAM8、40 MHz | ↓専用 | 19 /11 | 同上 |
| SDIO4 SDR40 | 半二重 | 6 | 17.651368 |
| eMMC8 SDR40 / eMMC4 DDR40 | 半二重 | 10 /6 | 31.690522 |
| I2S0 TX40 / RX40、I2S1 TX40 / RX40 | 各方向専用 | 各3 | 4.980545 |

同じI2S controllerのTX/RXは同じclock/slotならBCLK/WSを共有して2 pin減。
SDMMCの2 slotは共通driver/DMAを持つため、独立2本分の容量として足さない。
SPIの1本で↑↓をそれぞれ満速とする計算は禁止。

CPU一次検査の候補に対する**必要条件catalog**は全3,736 pair。
この件数を指定手順②の正式割当数とはしない。①の全体性能が未確定のため、正式割当は0。
各pairはT/S経路index、同時pin数、API費用込みCPU感度を持ち、参照先に各portの↑↓負荷・残MB/s・占有率がある。

### raw専用案A/Bの18通りを省略せず表す

S側は次の2通り。T側は次表の9通り。その**直積9×2＝18通りすべて**が34信号pin条件を満たす。
[raw-route-pairs.csv](20k-dual-s3/raw-route-pairs.csv)にも18行を保存した。
control各方向0.01 MB/sを引いた後の余裕である。端子数はT10＋S16＋TS6＋event2＝34で予備0。

| S側 | 実効合計MB/s | 必要↑/↓MB/s | 残MB/s | 容量余裕 |
|---|---:|---:|---:|---:|
| S-P：SPI2 Octal＋SPI3 Quad | 103.723500 | 100.01 /0.01 | 3.703500 | 3.57% |
| S-E：SPI2 Octal＋eMMC4 DDR | 102.018180 | 100.01 /0.01 | 1.998180 | 1.96% |

| T側（全9通り） | 必要↑/↓MB/s | 残MB/s | それぞれ組合せ可能なS側 |
|---|---:|---:|---|
| SPI2 Octal | 40.01 /0.01 | 30.307658 | S-P、S-E |
| SPI2 Quad＋SPI3 Single | 同上 | 2.888150 | S-P、S-E |
| SPI2 Quad＋SPI3 Dual | 同上 | 11.556046 | S-P、S-E |
| SPI3 Quad＋SPI2 Single | 同上 | 2.888150 | S-P、S-E |
| SPI3 Quad＋SPI2 Dual | 同上 | 11.556046 | S-P、S-E |
| SPI2 Single＋eMMC4 DDR | 同上 | 1.182831 | S-P、S-E |
| SPI2 Dual＋eMMC4 DDR | 同上 | 9.850726 | S-P、S-E |
| SPI3 Single＋eMMC4 DDR | 同上 | 1.182831 | S-P、S-E |
| SPI3 Dual＋eMMC4 DDR | 同上 | 9.850726 | S-P、S-E |

優先する通信の仮説は**T SPI2 Octal、S SPI2 Octal＋SPI3 Quad**。
eMMC card endpointより既存SPI endpointを再利用でき、T側に一番余裕が残る。
Sの3.57%は小さく、API/gap増大、clock誤差、control増加に敏感。
全18通りは電気的に実現確認済みの配線ではない。
LCD16＋SPI等は単一SoCでは足りても、T/S同時の34 pin枠に入らない組合せを落とした。

## 7. 通常catalog外の経路も無視しない

### 専用GPIO（eSpDR方式）

upstream `h0m3us3r/eSpDR`を`f279bf823eee41796dfd1ac21f13e1ed9b418c82`で読み直した。
`transmit.S`と`protocol/link.h`は16 sample→40 byteを91 CPU clocks/coreで送る。
2個の8-bit laneを使うpayload loop能力は2×240×40/91＝**210.989011 MB/s**。
これはmarker/header/bank操作を引く前のloop値で、通信路全体の保証帯域ではない。
upstreamのFPGAはArtix-7で、20Kへそのまま移植できる証拠ではない。

| GPIO経路 | payload-loop上限 | raw需要 | 上限からの差 | pin数／追加条件 |
|---|---:|---:|---:|---|
| T 1×8 lane | 105.494505 MB/s | 40 | 65.494505 | data8＋forwarded clock1。単lane bank scheduleは新規設計 |
| S 1×8 lane、40 MSa/s | 105.494505 | 100 | 5.494505 | 同9。bank/marker等を入れると余裕が小さい |
| S 2×8 lane、40 MSa/s | 210.989011 | 100 | 110.989011 | data16＋clock1。S3の両coreを使用 |
| S 2×8 lane、80 MSa/s | 210.989011 | 200 | 10.989011 | raw品質を維持できる帯域上の代案。ただしoverhead後の実効値が必要 |

T単lane9＋S二lane17＋TS6＋event2＝34で本数だけは収まる。
ただし2枚の独立20 MHz referenceからの240 MHz sampler、専用GPIOのcycle固定、
2 PLLと復調/SDRAM clockの同時実現、Gowin側IDDR/phase校正、frame順序を解決していない。
専用GPIOはCPU転送なのでDMA経路と無条件に同時利用して容量を足さない。
この案を「標準SPIに入らないから不可能」と除外することもしない。
**別の有望な入口仮説だが、全体資源・clock・実効帯域は未確定。正式通信割当は0。**

USB FSは12 Mbit/s線速度でT TSにも不足。UART/I2C/TWAIはRF主経路には桁不足で制御用。
Wi-Fiは同じRFをSDR受信に使うので、同時の一般Wi-Fi転送帯域として加算しない。
S3にS31のPARLIOやUSB HSがある前提にしない。SPI0/1はmodule Flash/PSRAM用で、完成moduleの外部リンクに流用しない。
未検証のLCD/CAM高clock、独自DDR GPIO、基板端子の追加取り出しは、既存18 profileとは別設計として再検算が必要。
従って「全ての物理実装を調べた」とはせず、**今回の有限catalogは全列挙し、外部の重要代案は上記のとおり未確定で残す**。

## 8. 完成基板の配線上の条件

Rev1.30回路図の信号集合：

- J6：73,74,75,85,77,15,16,27,28,25,26,29,30,31,17,20,19,18
- J5：76,80,42,41,56,54,51,48,55,49,86,79,72,71,53,52

数はFPGA package pin番号。power/GNDを含まない。全34信号が無負荷・自由なGPIOという意味ではない。
LED、audio、WS2812、microSD、HDMI DDC、BL616 HSPIとの接続がある。
外部SD/HDMI/LCDは接続しない構成が必要で、BL616のHSPI出力はHi-Zにしなければ競合する。
基板の負荷を含む80 MHz setup/hold、SPI SCLKのclock-capable配置、I/O bank電圧、strapを検査してからCSTを確定する。
このPRで34本を無条件に使えるpin mapを完成させたとはしない。

FPGAのTS出力はT/S独立3-wire serial。sync byte0x47とvalidを用い、別のSYNC pinは予約していない。
独立SYNC pinを両方必要とするsinkなら＋2 pinとなり、標準SPI witnessは36>34でそのまま使えない。
S3のGPIO35–37などR8予約pin、GPIO0/3/45/46 strapを通信に勝手に流用しない。
通信容量台帳の1本/eventは通知用、詳しいcredit/statusはhalf-duplex control予算を使う。

## 9. 指定手順の結果と未達の理由・完了条件

| 順序 | 今回行ったこと | 到達状態 |
|---|---|---|
| 1 性能余裕内の分担 | 全16,384 pair、4全体budget案、RS部分切断、全mode FFT期限、T/S/TMCC RS需要、共有SDRAM、S3 API費用を再計算 | Bを優先仮説に絞った。全体資源は設計allocation、CPU/clock/memoryの同時期限は未証明。性能合格0 |
| 2 実現可能な通信路割当 | 別途必要条件catalogを全列挙。方向、半二重、API、GDMA、同時pinを検算 | **正式割当0**。3,736 capacity pair、raw18 pairは探索資料。性能未確認の案を正式割当へ昇格しない |
| 3 非ゼロ経路候補の採用 | 上記ゲートを機械データに反映 | **採用0**。B＋T Octal/S Octal+Quadは検証対象の提案 |

未達の直接理由は、新しいtile FFT/SDRAM/共有RS/全S機能を含む受信topが存在せず、
既存の部分回路測定や旧計算ではそれらの同時占有と期限を導けないため。
新しいallocation値を足すだけで成立したと報告することはできない。
これは20K＋S3×2が不可能と証明された意味ではない。

| 残作業 | この環境で進める部分 | 完了条件 |
|---|---|---|
| tile FFT | DMA・所有権・仲裁・CDCを接続し有限の全mode競合試験を追加済み。実client到着・物理CDC/STAの確認は残る | 全bin一致／精度契約、2-cycle butterfly、162 MHzで全mode周期内、tile8 BSRAM以下 |
| 全体FPGA | FIR・同期・TMCC・depuncture・全interleave・両FEC・共有RS・TS・I/Oを接続、20K合成/P&R | legal placement、logic≤20,736、BSRAM≤46、DSP≤48、PLL≤2、全domain STA。budget超過時は案を修正 |
| SDRAM | FFTとの結合・2-client仲裁・合成背景トラフィックの同時cycle simulationまで追加済み。実LLR等のclient実装と全phase保証は残る | 135 MHzで271.266 MB/s需要を処理、最長待ちがFIFO期限内。raw退避を追加した場合は再計算 |
| shared RS | 仲裁・TMCC短縮・credit予約RTL、2種類の部分合成、有限位相queue検算まで追加 | 外部queue/DMA/FIFO結合、全位相境界、162 MHz STAは未達 |
| S3 dedicated firmware | T用/S用を個別リンク、bank所有権・per-core scheduler・実driver呼出を結合 | N8R8/N16R8のROM/内部SRAM容量内、RF bank再使用より早く回収、API/packing含むWCETに余裕 |
| 実GPIO map | 回路図、BL616 firmware、clock routingと負荷確認 | 配線・CST・衝突回避を具体化。pin本数だけの合格を撤回できる状態にする |
| 実機限定部分 | 上記を準備後に2系統RF、40/80 MSa/s品質、同時転送を測定 | 所要C/N・BER、欠落counter、温度/電源差・位相、S3/SDRAM実効帯域を確認 |

上のソフトウェア／RTL未実装を「実機がないので確認できない」項目へ移してはいない。
このPRには見積もり・検算器に加えて共有RS・FFT・SDRAMの部分RTLがあるが、受信機全体の新規実装は未完成。
この環境で進められる実装作業も残るため、依頼全体を完了としない。

## 10. 再現と根拠

```sh
python experiments/dual_s3_20k_estimate.py --output build/20k-dual-s3
python -m unittest discover -s tests -p test_dual_s3_20k_estimate.py -v
```

生成物：全所有者/pair、全容量route、18 raw組合せCSV、summary/input SHA256。
7件のunittestはhalf-duplexの二重利用禁止、方向制約、frameとCW保存則、全mode期限、
内蔵RAM超過の拒否、RPCとraw batchのAPI時間の違い、factorized FFT順序を検査する。RTL/P&R/WCET合格の代わりではない。

一次資料：

1. [Sipeed 20K仕様](https://wiki.sipeed.com/hardware/en/tang/tang-nano-20k/nano-20k.html)、[Rev1.30回路図](https://dl.sipeed.com/fileList/TANG/Nano_20K/2_Schematic/Tang_Nano_20K_3921_Schematics.pdf)。回路図は取得・J5/J6信号と接続先を照合。
2. [Espressif WROOM-1/1U datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)。N8R8/N16R8/N16の区別。
3. [SPI master IDF5.5.1](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/spi_master.html)、[SDMMC](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/sdmmc_host.html)、[dedicated GPIO](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/dedic_gpio.html)。
4. [ARIB STD-B31](https://www.arib.or.jp/english/html/overview/doc/6-STD-B31v2_2-E1.pdf)、[ITU-R BO.1408-1](https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-1-200204-I!!PDF-E.pdf)。後者はPDF取得・Table3の48 slot、203 B、39936 symbol、TMCC RS64/48を照合。
5. [eSpDR固定commit](https://github.com/h0m3us3r/eSpDR/tree/f279bf823eee41796dfd1ac21f13e1ed9b418c82)、[link.h](https://github.com/h0m3us3r/eSpDR/blob/f279bf823eee41796dfd1ac21f13e1ed9b418c82/protocol/link.h)、[transmit.S](https://github.com/h0m3us3r/eSpDR/blob/f279bf823eee41796dfd1ac21f13e1ed9b418c82/esp32s3/src/transmit.S)。FPGA実証は別deviceである。
6. 基準HEADの[CPU再検算](s3-link-cpu-sensitivity.md)、[全所有者台帳](s3-partition-audit.md)、[S frame検算器](../experiments/s3_isdb_s_frame_budget.py)、[runtime実装の未完了箇所](s3-runtime-endpoint.md)。
