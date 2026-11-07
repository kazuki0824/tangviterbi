# T側のFIR移管をESP32-S3で捌けるか

**2026-11-05 続報：** [T側のnative／SDK／残存FPGAを結び付けた新しい検証](../s3-t-preprocess-integration-v2/README.md)に、現在のソースから作ったELF、実命令費用、有限実行モデル、独立RTL oracle、資源再集計とtiming coverageを保存した。最新のhalfband候補の判定は、この続報を参照する。

以下は先行するQACC・ACCX・halfband単体の評価である。過去に失われた成果物のbyte一致復元を、新しい再生成結果とは扱わない。旧版の外部処理予算と有限モデルの通過を、最新SDK経路の成立判定に流用しない。

2026-11-03。対象は②の **T担当ESP32-S3 N16R8 1個、2 core × 240 MHz**。入力は16 M複素sample/sのI10/Q10。調査開始時のPR #10 headは `1fe8e006a33e146b358d244f0bade5908a4b258d`。

## 判定

**既存のtap-major QACC＋基準prepare Cは捌けない。今回のmirrored-history C callerを接続したACCXも捌けない。** いずれも、RF・通信・RTOSを無料としても、実命令列の必要処理量が2 coreの理想上限を超える。以前の「Tは未計上費用を確認するまで未判定」を、この2つの具体実装について解消した。

別に、**16→8 M複素sample/sのhalfbandをS3、8→512/63 M複素sample/sの64/63変換をFPGAとする案**も実装して評価した。31tapの試作halfbandは、元の単core関数では入力速度に届かなかった。そこで2 coreへ分担するCを作成し、**指定した外部処理予算・入力burst・転送条件の下で、各coreと有限bufferの期限を通過する候補**を確認した。従って「Tを減らす方式はS3では全て捌けない」とは結論しない。ただし、元フィルタとの同品質、実RF/SDK経路、FPGA後段を含む受信性能合格は未認定。

| 対象 | 必要処理量または具体的条件 | 判定の範囲 |
|---|---:|---|
| 既存QACC＋scalar prepare | prepare書込みだけで **520.127 Mcycles/s以上**。実際のhalfword storesでは1040.254 | **NG**。O2/Os/O3の全3条件。読み出し・FIR・RFを無料にしても不可 |
| 既存ACCX＋今回のmirrored-history C caller | 最良Osでも入力処理＋call＋kernelだけで **483.810 Mcycles/s以上** | **NG**。Q15変換・RF・転送を無料にしても不可 |
| 既存AR経由register gather | 保存命令列627.810、履歴load等を無料にした部分だけでも585.143 Mcycles/s | 既存の**NG**を維持。[前回の評価](../s3-preprocess-break-even/README.md#中間iq配列を使わないregister履歴配置) |
| 今回の31tap halfband単core関数 | 1024入力当たり21,919命令。理想91.329 µsに対し入力周期64 µs | **単core運用はNG**。2 core合計342.484 Mcycles/sは必要条件の検討値 |
| halfbandの2 core分担 | 入力側32出力、worker側480出力。α=1.1で前処理 **152.813 / 221.547 Mcycles/s**。外部20 / 2 µs・64 µs周期などの宣言条件で有限期限通過 | **条件付きCPU候補**。同品質・実RF/SDK・FPGA後段を含む受信合格は未認定 |

これは**評価した実装の判定**である。異なるvector shuffle、融合assembly、特殊係数、別のFIR構成の全てが不可能という証明ではない。T raw経路の全受信成立や、S側の採否も今回の結果だけでは変更しない。

## 1. 判定基準と費用の読み方

公式[ESP32-S3 TRM](https://documentation.espressif.com/esp32-s3_technical_reference_manual_en.pdf) §1.7は、理想的な1命令/cycleのpipelineと、依存・資源・分岐によるstallを説明する。ここでは240 MHz × 2 coreを完全に均等利用でき、各命令が1 cycleで発行されるという**速い側の条件**をまず置く。SIMDのload＋MAC等は複合命令のまま1回と数え、内部演算を別命令として加算しない。

この条件で必要命令数が480 M/sを超えれば、その実装は不合格にできる。480未満の場合は、各coreの240 Mcycles/s、短時間期限、割込み、待ち、メモリ競合、品質等を追加確認しなければ合格にできない。命令数やhost試験をtarget実行時間・WCETの測定値とは扱わない。

### 旧「FIR以外」の予算は最新実装の全費用ではない

旧94.646306 / 127.154243 Mcycles/sの内訳は次の通り。原典は[旧費用模型](../../experiments/control_only_estimate.py)と[保存QACC監査](../s3-preprocess-break-even/qacc/qacc-audit.json)。

| 旧項目 | low / high Mcycles/s | 性質 |
|---|---:|---|
| RF・調整 | 57.375 / 57.375 | 36.5416667＋20.8333333という継承予算。実測・WCETではない |
| FIR出力転送 | 32.507937 / 65.015873 | 32.507937 MB/s × 1/2 cycles/byte |
| API | 4.763370 / 4.763370 | 32 KiB、20 µs/APIの仮定 |

新しい入力展開・FIRへ置換するときは、旧FIR内に含まれていた展開費用を残さない。FIR出力を送る経路へraw20 packingを再加算しない。出力の変換・格納をkernelへ入れたなら、旧転送課金との重複を調べる。SDKのSUBMIT/REAP/IRQを具体的に数える場合は旧API費用を置き換える。

最新[queue-owner](../s3-queue-owner/README.md)の16 KiB・深さ2の検証を、旧32 KiB/API予算と混在させてはいけない。[保存runtime](../s3-queue-owner/runtime.json)の15行はS・40 MS/s・share 5/16であり、新T FIRの統合結果ではない。また、raw側のbusy polling費用を実作業の固定負担とみなし、単純にFIRを足す方法も採らない。

## 2. QACC：未計上だったprepare Cだけで上限を超える

対象は既存の [prepare C](../../experiments/s3_fir_qacc_prepare.c) と [QACC assembly](../../experiments/s3_fir_qacc.S)。T条件は32tap、L/M=32/63、4出力/batch。

出力rateは `16,000,000 × 32/63 = 8,126,984.126984` 複素sample/s、batch rateは `2,031,746.031746 /s`。prepareは各batchで、samples 512 Bと係数512 B、計1024 Bの別配列を実体化する。

O2/Os/O3の逆assemblyでPIE vector storeはなく、最大のscalar store幅は4 B。payload本体は4個の `s16i` を32tap×4laneで繰り返す。監査ではさらに速い側へ緩めて、**全1024 Bを4 B/storeで書ける**と仮定した。

```text
最低store数 = 1024 / 4 = 256 / batch
最低費用 = 256 × 2,031,746.031746
         = 520.126984 Mcycles/s > 480 Mcycles/s
```

実際の4 halfword store/tap/laneを使えば512 store/batch、1040.253968 Mcycles/sになる。必要な読み出し、符号展開、除算、gather、QACC kernel、出力変換、RFはまだ足していない。2 coreに完全分割できても救えない。

以前のprepare 130.031746 Mcycles/sは、**16 Bのvector storeだけで全書込みを済ませる仮定**だった。既存scalar Cをコンパイルした費用ではない。従って「QACC＋prepare＋旧予算＝370.964～403.472 Mcycles/s」を、このCの実装可能な処理量として使わない。その旧算式は別のvector化実装に対する楽観的な比較値としてのみ残る。

証拠は[生成JSON](qacc-preparation-capacity.json)と[O2](prepare-O2.dis)・[Os](prepare-Os.dis)・[O3](prepare-O3.dis)の実命令列。監査はsource/header/ISA headerをhashで固定し、3命令列も独立再compileとの一致を確認したhashへ固定する。保存disassemblyを欠損させても、再監査によって容量不合格の根拠を誤生成しない。

## 3. ACCX：kernelだけでなくcallerを接続して判定

[今回のcaller](../../experiments/t_preprocess_capacity/accx_wrapper.c)は、I10/Q10符号展開、I/Q各64 halfwordの逆向きmirrored history、除算のない32/63位相更新、既存 `s3_fir_accx_32` 呼出し、仮のQ15変換を接続した。

| 最適化 | 入力処理＋call＋kernelのみ | 仮Q15変換の必須命令も含む | 63入力・32出力のloop全経路 |
|---|---:|---:|---:|
| O2 | 563.809524 | 661.333333 | 830.476190 |
| Os | **483.809524** | **581.333333** | **807.365079** |
| O3 | 563.809524 | 661.333333 | 814.222222 |

単位は理想Mcycles/s。全経路欄もblock入口・出口、初期化、RF、転送、RTOS、stall等を除く。

Osで入力ごとに必ず通る15命令と、出力ごとのcall 1命令＋kernel 29命令だけで、

```text
15 × 16 + (1 + 29) × (512 / 63)
= 483.809524 Mcycles/s > 480 Mcycles/s
```

となる。最も弱い証明は、出力変換を無料にしても成立する。仮Q15契約が元receiverと未照合であることは、この実装のCPU不合格判定を変えない。

仮変換は `(acc + 256) >> 9`、signed16飽和。正方向tieの丸めであり、実受信機の契約を採用したという意味ではない。全精度の和を独立oracleと比較した上で、この仮変換も別に検査した。phase×headの1024組、chunk継続、極値、tie、mirror一致、vector read範囲を確認した。[再現結果](accx/accx-audit.json)。

## 4. halfband：具体的な別候補を評価する

### 処理量・品質・残るFPGA処理

[31tap C/assembly](../../experiments/t_preprocess_capacity/halfband31.c)は17個の非零係数を使い、4複素出力をQACCで計算する。tap-major中間配列を毎回作る方式ではない。PIEのload増分制約を反映した実kernelは98命令/4出力。Cは `-O2 -fno-tree-slp-vectorize` で15命令/2 raw入力となる。

**命令数だけでは見つからない依存待ちも修正した。** 初回の98命令配置には、係数load直後のMACが17か所、非整列load直後のSRCが12か所あり、TRM §1.7.1・表1.7-2による最低29 stall/kernelがあった。そのままでは2 core版workerも255.78125 Mcycles/s以上となり、1.1倍の命令模型は不足する。この初回配置を成立候補として採用していない。

最終assemblyでは、独立したloadやpointer更新を間へ移し、最後の2 NOPもload→MACとMAC→SRCMBへ分けた。同じ98命令で、QR・QACC・SAR_BYTE・ARの**166依存関係について追加operand interlockが0**となることを逆assemblyから監査した。旧順序の29 stallと、5つの依存関係の回帰例も検出する。算術の意味モデルとhost oracleは再実行して一致。これは既知operand待ちの解消であり、callerの制御費用、cache/MMIO、memory競合、context保存を0にする主張ではない。

| 1024 raw/blockでの処理 | 理想Mcycles/s |
|---|---:|
| 可逆I10/Q10展開・workspace格納 | 120.000000 |
| FIR、shift/飽和、I16/Q16出力store | 196.000000 |
| kernel引数・call・loop | 22.000000 |
| 履歴copy | 3.062500 |
| 検査・padding等の固定費 | 1.421875 |
| **単core関数の総仕事量** | **342.484375** |

出力は8 M複素sample/s × 4 B = 32 MB/s。変換とstoreは上表へ算入済み。旧RF57.375と、32 MB/s用の旧API4.688964844だけを残した比較値は404.548340 Mcycles/s。**別の**payload copyが1/2 cycles/byteで残る算式なら436.548340 / 468.548340となる。これは1命令/cycleの最低側の算数に旧予算を足した参考値で、call/return/taken branchの制御費用もまだ含まない。468.548340が480未満であることを、その条件のCPU合格とはしない。実際の2 core候補は次節で別に評価する。

試作係数・算術の一致は確認したが、**元32tapとの同品質は未確認**。元の[保存FIR模型](../s3-preprocess-break-even/original-fir-model.json)にはrate/tap数とcycle仮定はあるが、品質合否を決める係数・passband/stopband・スケール・丸め契約がない。

試作halfbandの周波数gridでは、宣言したpassband端 `39/14 + 0.1 MHz` に対してripple 0.003296 dB p-p、対応stopbandで73.591324 dBの減衰。これは追加100 kHzを含む**診断条件**であり、受信仕様の同品質認証ではない。出力はarithmetic shift＋飽和で、round-to-nearestではない。shift=10ではsigned10全域に対する整数boundから飽和なしを確認したが、この出力契約を無断で製品経路へ適用しない。

rateの積 `(1/2) × (64/63) = 32/63` が一致しても、cascade全体の品質が一致した証明にはならない。FPGAへ残す64/63変換の実装・資源・期限も必要。**FIR全移管の旧削減値（752logic、1536FF、2BSRAM、8DSP18）を、このhalfband案の削減量へ流用しない。**

詳細・全係数・整数oracle・memory内訳は[halfband報告](halfband/README.md)と[数値JSON](halfband/halfband_results.json)。

### 各coreと有限buffer

2 core分担の[具体的C](../../experiments/t_preprocess_capacity/halfband_pipeline.c)では、core0が履歴を単独所有し、1024 rawを展開して先頭32出力を計算する。core1は残り480出力を計算。2個のworkspaceをrelease/acquireで `FREE → READY → DONE → FREE` と受け渡す。先のblockをworkerが読んでいても、producerは別workspaceで次の履歴へ進める。出力は16 KiB DMA frameの2048 B区画へ直接書き、**workspaceの解放と送信中の出力領域の解放を分ける**。

新callerのloopは9命令/4出力となったため、旧単core関数のcaller費用22 Mcycles/sは再加算しない。target命令列を入口・callee・return・原子操作まで再計数した。

| 新操作 | 命令/block | α=1.1、操作単位切上げのcycles/block |
|---|---:|---:|
| core0 produce | 8837 | 9721 |
| core1 work | 12890 | 14179 |
| core0 reap | 53 | 59 |

前処理はα=1.0で合計340.3125 M命令/s、α=1.1でcore0 **152.8125**・core1 **221.546875 Mcycles/s**。外部作業に残る容量はそれぞれ87.1875 / 18.453125 Mcycles/s、64 µs当たり23.25 / 4.920833 µs。α=1.1は10%を加えた**感度条件**であり、stallやmemory競合の上界を保証した係数ではない。

修正済みkernelを使い、既知のtaken branch/call/returnとscalar load依存も別に検算した。core1は12890命令＋制御726 cycle＝13616 cycle/blockで、1.1倍模型の14179以内。core0も制御78 cycleと、copyのload→storeまで含めて保守的に50 cycleを加えた9018 cycle/blockが、produce＋reapの9780以内となる。従って既知依存だけで1.1倍模型が不可能となる問題は解消した。残りをmemory競合・memw・ABI例外等の上限として保証した結果ではない。α=1.0の行は制御bubbleを含まない命令発行数の比較値である。

有限event模型は、hostで実Cの所有権関数を実行し、READY/DONEを各操作の完了イベントで公開する。4096 block、宣言した外部作業・tick/WDT・転送を加え、source bank、slot、DMA frameの寿命を確認した。入力を1 / 11 / 12 blockずつ公開するケースを含み、64 µsごとに1 blockが滑らかに到着する仮定だけでは評価を終えなかった。

| 具体的通過条件 | 値 |
|---|---|
| 入力公開 | 12 block＝12288 rawを768 µsごとに一括公開 |
| 前処理命令の課金 | α=1.1 |
| RF/API/外側制御等の外部予算 | core0に20 µs、core1に2 µs、各64 µs周期。tick/WDTは別計上 |
| 外部予算を含む平均、tick/WDTを加える前 | core0 227.8125 / core1 229.046875 Mcycles/s |
| 転送 | 40 MB/sの宣言drain、16 KiB × 8 frame、API dispatch・完了回収の有界待ち |
| switch→公開の仮定 | 最大125 µs。その分をjob期限303280 cycleから控除 |
| 最大処理slice、core0 / core1 | **50.345833 / 68.295833 µs**、上限83.333333 µs以内 |
| 最大RF service完了間隔 | **108.945833 µs**、宣言した125 µs以内 |
| 最大出力完了、bank公開から | **800.670833 µs**、控除後1138.666667 µs以内 |
| 最大保持領域 | 公開済みraw bank 1個、出力frame 3個＝49152 B |
| 完了数 | produce / work / reapが全て4096。faultなし |

この模型ではslotを待てないときに入力を勝手に捨てず、公開済みraw bankの待ち行列で吸収してその保持期限を検査する。**各slotを必ず128 µs間隔で再使用できる保証ではない。** また、実native captureの可変長span、ring端、端数を1024個へ組み立てるadapterと、実SDK eventの全費用は未接続。上表の外部予算へ収められると確認した事実はない。転送も既存SPI経路の性能認定ではなく、明示した容量・待ち契約である。

平均だけで判定しないことを確認するため、core別の過負荷、転送28 MB/s、周期的な一時停止も評価した。例えばcore1の処理に25 µsの中断が重なる指定位相ではslice **84.079167 µs**となりNG。50 µsなら **109.079167 µs**。同じ50 µsでも処理中に重ならない位相は別結果になる。全割込み位相・無限時間についての証明ではない。

新pipeline本体はtargetの `sizeof` で8528 B、共有係数272 B。raw bank、128 KiB arena、SDK、stack、PIE保存等は別。hostの64bit pointerを含むsizeofをS3のRAM値へ流用しない。[専用報告](pipeline/README.md)・[命令/host検査結果](pipeline/results.json)・[全event結果](pipeline/events.json)に条件と失敗ケースを保存した。

Tの既存capture条件は、[capture実装](../../experiments/s3_native_capture.c)において、12288入力で通常切替、閾値到達後2000入力（125 µs）までの遅延許容、slice 20000 cycle（83.333 µs）、bank age 16256入力（1016 µs）、switchからjob deadline 303280 cycle（1263.667 µs）。125 µsは閾値からの余裕であり、任意時点から常に125 µs停止してよいという意味ではない。

既存の[PHY周期処理監査](../s3-queue-owner/phy-periodic.json)では、busy bit解除待ちのソフトウェア上限がなく、観測したbusy経路には解除後50 µs待ちもある。肯定判定では、配置するcore・頻度・最大中断時間を具体化する必要がある。平均CPU%だけで無視しない。

## 5. 静的完了条件確認

判定は最初のNGで打ち切らず、対象ごとの条件を一覧化する。証拠生成のPASSと、処理能力のNGを区別する。必要処理量でNGの実装に対して、後続の未知値を0としても救えないことを確認する。

| 条件 | 確認方法・合否基準 | 結果 |
|---|---|---|
| 対象・入力rate・revisionの固定 | input SHA、L/M、tap数、signed10入力、compiler/flags/source hashを保存 | OK |
| QACC準備処理の実命令化 | O2/Os/O3 compile・逆assembly・hash照合、store幅とcalleeを監査 | OK。CPU必要条件は3条件ともNG |
| ACCXの入力・履歴・caller接続 | target compile、全phase/head、chunk境界、独立整数oracle | OK。CPU必要条件は3条件ともNG |
| QACC/ACCXの出力品質 | 元品質契約との照合 | 未確定。CPU NGは出力変換等を無料にしても成立 |
| halfbandの入力・履歴・丸め・store | 実C/assembly、独立直接畳み込みとTRM意味モデル | 算術モデルはOK。単core連続処理はNG |
| halfbandの既知命令依存・制御費用 | TRMのstage、逆assemblyの依存166本、旧29stall負例、Cのcontrol/load-useを確認 | 修正後の追加operand待ち0。既知制御等を含む確認値はα=1.1予算以内。未知WCETは未認定 |
| halfbandの2 core分担・所有権・有限期限 | 分担C、独立整数oracle、target CFG計数、1/11/12 block公開・過負荷・周期中断の有限模型 | 宣言条件でOK、過負荷と指定中断でNGを確認。native span組立・全割込み位相・最終receiver統合は未完 |
| RF・API・IRQ・周期処理の全費用 | 実配置・イベント頻度・待ち上界まで含め各coreを確認 | receiver全体は未認定。旧予算のみでOKにしない |
| 全メモリ・PIE context・DMA寿命 | 最終SDK link、実確保、stack、競合、所有権を確認 | 試作領域と模型の確認まで。起動後全体の成立は未確認 |
| 元FIRと同品質 | 係数・応答・出力契約とcascade全体を照合 | 未確定。原典契約なし。試作係数の診断で代替しない |
| FPGA資源削減 | 残置64/63段を含むtopで比較 | 未確定。FIR全移管の削減量を流用しない |
| SoC→FPGA出力型・rate | 32/63 FIR案の仮Q15出力契約なら32.507937 MB/s、halfbandの仮I16/Q16契約なら32 MB/s。rate積を検算 | 算術OK。品質契約・正式通信路割当は未確定 |
| FPGA→SoC payload禁止 | 今回の候補はSoCで入力を処理しFPGAへ出力。逆向きpayloadを必要としない | 方針適合。配線・実transportの採用確認とは別 |
| 最終受信・T/S同時TS | 実機の連続取得、無欠落、品質・TSを確認 | 未実施。host算術試験や有限模型で代替しない |

## 6. 再現

使用toolchainはEspressif `xtensa-esp-elf`、GCC 14.2.0、`esp-14.2.0_20241119`。公式[release archive](https://github.com/espressif/crosstool-NG/releases/download/esp-14.2.0_20241119/xtensa-esp-elf-14.2.0_20241119-x86_64-linux-gnu.tar.xz)を次のSHA256で検証して使用した。

```text
e3e6dcf3d275c3c9ab0e4c8a9d93fd10e7efc035d435460576c9d95b4140c676
```

展開したtoolchain rootを各 `--toolchain` に指定する。script内で `XTENSA_GNU_CONFIG=.../lib/xtensa_esp32s3.so` を設定する。host試験はGCCとPython標準ライブラリを使用する。

```sh
python ci/t_fir_capacity_audit.py --toolchain /path/to/xtensa-esp-elf
python ci/t_accx_capacity_audit.py --toolchain /path/to/xtensa-esp-elf
python ci/t_halfband_capacity_audit.py --toolchain /path/to/xtensa-esp-elf
python ci/t_halfband_pipeline_audit.py --toolchain /path/to/xtensa-esp-elf
python -m unittest discover -s tests -p 'test_t_fir_capacity_audit.py' -v
python -m unittest discover -s tests -p 'test_s3_fir_qacc.py' -v
python -m unittest discover -s tests -p 'test_s3_fir_accx.py' -v
```

QACC監査はtoolchain指定を省略して保存disassemblyを照合できる。保存hashが合わない命令列は再評価済みの証拠とみなさずFAILにする。新しいcompiler/コードを試す場合は必要条件を再監査する。旧checkを通すためにhashだけを付け替えない。

実行結果は各JSONと[検証ログ](validation.log)へ保存する。target compile、逆assemblyの意味モデル、host C実行、静的容量判定、有限期限模型を区別し、ESP32-S3実機で実行したという記録は作らない。

| 最終検証 | 結果 |
|---|---|
| QACC prepare容量監査 | 16項目PASS。容量判定NGの証拠が有効 |
| ACCX caller容量監査 | 16項目PASS。容量判定NGの証拠が有効 |
| halfband primitive監査 | 20項目PASS。旧29stall検出・新順序0・算術一致を含む |
| halfband 2 core監査 | 20項目PASS。known dependency/control gateと22有限scenarioを含む |
| 新しい監査回帰unittest | 7件PASS。保存命令列の欠損、vector方式との適用範囲の区別等 |
| 既存QACC / ACCX unittest | 5 / 4件PASS |

合計72監査項目・16 unittestを完了した。22有限scenarioは模型上15通過・7拒否で、拒否は過負荷等の検出結果である。α=1.0の3通過は命令数のみの参考条件であり、物理的timing成立の認定へ使わない。失敗ケースを除外して成功件数だけを数えた評価ではない。

## 7. 今回の区切りと次の条件

QACC/ACCXの具体実装については、未計上だった準備・callerを実命令へ落とし、不成立の必要条件まで閉じた。既に必要処理量が上限を超える実装へRF/SDK統合を追加しても結果は改善しないため、これらを性能合格候補へ進めない。

halfbandについては、単core関数のNGだけで評価を終えず、2 coreへ分担する具体的C、独立算術照合、burst入力を含む有限bufferの確認まで進めた。次の実装工程はnative span/ring端/端数を処理するadapterと実SDK schedulerへの接続であり、机上で進められる作業として残る。今回の条件付きCPU候補を、既にその接続まで完了した実装とはしない。

次工程へ進む採用判断には、元FIRとの同品質契約と、FPGAへ残す64/63段を含め本当に容量を削減できる根拠も必要。元契約を新しい試作係数で置き換えて品質合格にしたり、未実装の残置段を無料として削減量を確定したりすれば、今回のユーザー条件を破る。**既存方式のNGと新方式の条件付きCPU境界を確定したこの地点を、判定報告の区切りとする。次の実装・品質・FPGA統合は未完であり、②の完成として終了した扱いにはしない。**

**今回のコミットはT側の実装別判定と再現根拠を確定するもの。②全受信機の完成、T前処理全方式の不可能性、halfbandの性能合格を宣言するものではない。**
