# T 候補 C：S3 halfband 16→8 MS/s の条件付き CPU 評価

**結論：この具体的な 31 tap primitive は、入力展開・履歴・呼出し命令・I16/Q16 出力変換まで含め、1024 raw 複素 sample/block で 342.484375 M命令/s。旧 RF/調整・API 予算を足す参考式は 404.548340、独立 payload copy を 1/2 cycle/byte で足す参考式は 436.548340 / 468.548340 Mcycles/s となる。ただし、これらは FIR 部分の命令数下界に旧仮定予算を足した値であり、call/return/taken branch の既知 control bubble を含まない。480 Mcycles/s 未満という数字から、物理的な実行可能性を確認したとは判断しない。**

本 primitive を単 core に置くと、命令数下界だけで 91.329 µs に対して入力周期 64 µs となり不適合。実際の 2 core 分担候補の条件付き判定は、[新 pipeline の費用・期限監査](../pipeline/README.md) を参照する。この単体の参考式は CPU 合格条件として採用しない。

同品質、FPGA の 64/63 resampler、実際の RF/管理費用も未確認。この未確認を、halfband を用いる全実装の不可能証明に置き換えない。保存済み full 32 tap rational FIR の準備処理の不適合とも別の判定である。

## 比較の対象

経路は RF → T 側 S3 → FPGA → T TS。RF 入力は 16 M複素 sample/s、S3 が halfband FIR で 8 M複素 sample/s、FPGA が 64/63 補間して 512/63 = 8.126984 M複素 sample/s にする候補である。S3→FPGA の I16/Q16 は 32 MB/s。FPGA→S3 の payload 追加はない。

これは受信機 DSP の同品質な分担変更を探す比較用実装であり、品質低下を受け入れる追加間引きとして採用するものではない。係数や丸め契約をまだ満たしたと主張しない。既存 FIR の FPGA 資源が全て削減できるとも主張しない。64/63 段の必要係数・tap 数・資源・期限は別途必要である。

## 実装した内容

- [halfband31.c](../../../experiments/t_preprocess_capacity/halfband31.c)：32 bit raw の bits 0..9 / 10..19 を signed I10/Q10 として可逆展開し、偶数・奇数系列の履歴を保持する。上位 12 bit は無視する。入力 block は 8 の正の倍数、最大 1024。出力は入力の半数。
- [halfband31.S](../../../experiments/t_preprocess_capacity/halfband31.S)：4 連続複素出力を QACC の 8 lane で同時に計算する。tap-major 展開配列は作らない。16 個の非零偶数 tap と中心 tap を計算し、`EE.SRCMB.S16.QACC` と vector store で I16/Q16 出力を生成する。入力の位相が定数なので、各出力の有理数位相更新はない。
- 同 asm の `hb31_copy_words`：4 回、合計 184 byte/block の履歴 copy を明示し、未価格の libc `memcpy` 依存を除いた。
- [halfband31_host.c](../../../experiments/t_preprocess_capacity/halfband31_host.c) と [t_halfband_capacity_audit.py](../../../ci/t_halfband_capacity_audit.py)：独立直接畳み込み、host C streaming、実際の target 逆 assembly を読む TRM 意味モデルで算術と境界を検証する。

S3 向け GCC 14.2.0（`esp-14.2.0_20241119`）、`-O2 -fno-tree-slp-vectorize` で生成した。通常の `-O2` は 2 個の halfword store を結合する際に sign 拡張後の再 pack を生成し、unpack が 19命令/2 raw になる。この候補は明示した flag で 15命令/2 raw を使用する。生成コードが変わる場合は再監査が必要。

最初の 82 命令案は成立しなかった。PIE vector load の即値増分は 16 byte 単位であり、複素 1 sample = 4 byte の進行には独立 `addi` が必要だった。保存した実コードはその 16 命令を含む **98命令/4出力**。仮の 82 を性能値へ流用しない。

### operand interlock の見落としと修正

その後、最初の 98 命令配置にも **29 cycle/call の必須 operand interlock** があったことを独立監査で確認した。内訳は係数 load 直後の MAC 17 箇所と、上側入力 load 直後の `SRC.Q` 12 箇所。算術意味モデルだけではこの待ちを検出できず、旧順序を 98 cycle と扱った費用は不十分だった。旧順序の issue 費用は、他の待ちを除いても 98+29=127 cycle/call、2M call/s では未計上が 58 Mcycles/s に相当する。

現在の asm は命令を追加せず、次のように並べ替えた。

- 整列 tap：入力 load →係数 load →独立 pointer `addi` → MAC。
- 非整列 tap：下側入力 load →上側入力 load →係数 load → `SRC.Q` → pointer `addi` → MAC。
- 中心 tap と出力：入力 load →係数 load → NOP → MAC → NOP → `SRCMB` → store。

根拠は [Espressif TRM v1.8](https://documentation.espressif.com/esp32-s3_technical_reference_manual_en.pdf) §1.7.1 と表 1.7-2。producer の出力が stage SA の末尾に準備され、consumer が stage SB の先頭で読む場合、issue 間隔は `D=max(SA−SB+1,0)` 以上必要である。

|依存|def / use stage|必要な issue 間隔|現配置|
|---|---:|---:|---|
|vector load → MAC / SRC|2 / 1|2 cycle|独立命令を 1 個以上挟む|
|MAC の QACC → SRCMB|2 / 1|2 cycle|NOP を 1 個挟む|
|SRCMB の QR → store|1 / 1|1 cycle|隣接可|
|load の AR postincrement →次 load address|1 / 1|1 cycle|隣接可|
|USAR の SAR_BYTE → SRC|1 / 1|1 cycle|入力 QR の load 依存も別に検査|

`check_kernel_hazards` は実際の target 逆 assembly の **166 本の register 依存**を追跡し、現順序の必須 operand interlock **0**、旧順序 regression fixture の **29** を再現する。ADDI の AR 読込みも、decode stage 0 / ALU 結果 stage 1 という保守的条件で検査する。load→MAC、QACC→SRCMB の隣接負例等 5 条件も照合する。これらを通らなければ CPU 計算を `BLOCKED` とする。

再配置後も 98 命令と係数・丸め・入出力を維持し、1600 条件の target 意味モデルと全 host oracle を再実行した。**0 はこの register 依存検査の追加待ちであり、全 CPU stall が 0 という意味ではない。** entry/return/caller の制御費用、他の hardware resource 競合、fetch/cache/memory 待ち、window spill、割込み、core 間競合は別で、命令数を実測 WCET にはしない。

## 係数と数値契約

係数は Q15、長さ 31、対称、中心が 16384、中心以外の奇数 tap は 0：

```text
[-18, 0, 68, 0, -182, 0, 404, 0, -803, 0, 1533, 0, -3116, 0,
 10305, 16384, 10305, 0, -3116, 0, 1533, 0, -803, 0, 404, 0,
 -182, 0, 68, 0, -18]
```

作成方法は SciPy 1.17.0 `remez(31, [0, 39/14+0.1, 8-(39/14+0.1), 8], [1,0], fs=16)` の結果について、奇数 tap を 0、中心を 0.5 とした後の Q15 整数丸め。この band と +0.1 MHz は診断用の設計仮定で、合意済みの CFO・隣接妨害波条件ではない。再現評価は固定整数表を使い、SciPy を要求しない。

出力は各 accumulator の arithmetic right shift と signed16 saturation。round-to-nearest ではない。係数分母を含む gain は raw 整数に対し `2^(15-shift)` で、診断の `shift=10` は 32 倍。これは既存受信機のスケール・丸めと同等だと認定した規則ではない。

`sum(abs(coef))=49242`、signed10 入力の絶対値は最大 512 なので、どの入力に対しても accumulator の絶対値は 25,211,904 以下。40 bit QACC は飽和しない。shift=10 の出力絶対値は 24,621 以下で、出力も飽和しない。入力の有効 bit を捨てる unpack は実施しない。

65,537 点の周波数 grid では、通過域 0〜2.885714 MHz の ripple 0.003296 dB p-p、阻止域 5.114286〜8 MHz の最小減衰 73.591324 dB。これは continuum 全域の厳密 bound、旧 FIR との同等性、受信 BER/C/N、隣接波耐性の証明ではない。halfband の group delay は 0.9375 µs。64/63 段も含む振幅・位相・alias・image・CFO・量子化の品質契約を満たす必要がある。

## 生成命令と費用

|処理|頻度・命令数|理想 Mcycles/s|
|---|---:|---:|
|I10/Q10 unpack と偶数/奇数 workspace への store|15 命令 × 8M pair/s|120.000000|
|QACC kernel、shift/saturate、出力 store|98 命令 × 2M call/s|196.000000|
|kernel 呼出し・引数・pointer・loop|11 命令 × 2M call/s|22.000000|
|履歴 copy|196 命令 × 15,625 block/s|3.062500|
|入力検査、固定管理、padding 等|91 命令 × 15,625 block/s|1.421875|
|**合計（1024 raw/block）**||**342.484375**|

raw block 長を N とすると、`338 + 4592/N` M命令/s。範囲はこの実装の N=8,16,...,1024。既知の kernel operand interlock を除去した命令1個1cycleの基準であり、entry/return/caller の制御費用、他の hardware resource 競合、I-cache/D-cache、内部メモリ競合、register window spill、割込み・context save、core 間同期、scheduler を含む WCET ではない。kernel 内の明示 2 NOP は計上している。

同じ旧感度予算を使うため、RF/調整 57.375 Mcycles/s と API `(32+0.01)*4800/32768 = 4.688964844` Mcycles/s を残した。後者は 32 KiB/API・20 µs CPU-active・240 MHz という旧仮定で、endpoint の実測ではない。

|raw/block|halfband 命令数下界|旧 RF/調整＋API を加えた参考式|さらに独立 copy 1cycle/B|さらに独立 copy 2cycle/B|
|---:|---:|---:|---:|---:|
|128|373.875|435.938965|467.938965|499.938965|
|256|355.9375|418.001465|450.001465|482.001465|
|512|346.96875|409.032715|441.032715|473.032715|
|1024|342.484375|404.548340|436.548340|468.548340|

単位は命令 1 個＝1 cycle とした参考上の Mcycles/s、比較枠は 240 MHz × 2 = 480 Mcycles/s。**call/return/taken branch の control bubble を加えていないので、表の 404/436/468 を新 S3 pipeline の実行可能な総費用とは扱わない。** 旧 RF/調整予算自体も実機上限や全処理の下界ではない。旧転送費用 1/2cycle/byte は、今回の出力 store とは別の payload copy が存在するときだけ追加する。kernel が既に出力形式と store を生成するので、同じ作業の重複加算はしない。raw packing を再加算もしない。一方、新しい DMA endpoint・handoff が無償だと認定した値でもない。

1024 block の 2cycle/B 参考式と 480 の差は 11.451660 Mcycles/s、約 2.39%。**この差は call/return/taken branch の既知 control 費用を追加するだけでも消え得るため、実装に残る余裕とは認定しない。** 半帯域部分の命令数基準に対して約 3.34% の追加費用に相当する小さな差であり、未知の全費用を収めた結果でもない。新 pipeline の肯定的な条件付き結果は、その新 caller・core 分担について TRM 依存・control 等を別に照合した α=1.1 予算と有限イベント条件に限定される。

## core、memory、継続入力について残る条件

**単 core では、この具体実装は入力速度に届かない。** 全処理を 1 core に置くと 342.484375 > 240 Mcycles/s。1024 raw を処理する 21,919 命令は理想 91.329 µs、到着間隔は 64 µs。現在の逐次 `hb31_process` を置くだけでは合格しない。

2 core の期限を判定するには、実際の分担と全費用を使う必要がある。偶数/奇数履歴の producer/consumer、FIR の前に次 block 用履歴を公開するか、block ごとの独立履歴を用意するか、workspace の所有権、RF/API の担当、PIE の保存、同期費用を実装し、有限 buffer で連続入力・期限を評価する。本 primitive はそれらの並行処理を実装していない。別 adapter の実装・期限監査を併せて判断する。RF 管理の旧予算も最終値ではない。

理想的に準備を core0、kernel と caller を core1 に分離すると、前処理だけの分担は **124.484375 / 218 Mcycles/s**。これはこの逐次関数の費用を分類しただけで、並行処理を実装した結果ではない。命令費用係数を α=1.1 にすると core1 は **239.8 Mcycles/s** に達する。さらに既存模型の tick 100 Hz × 1696 cycle を残すだけで **239.9696 Mcycles/s**、残余は **30,400 cycles/s**。handoff、同期、割込み、window spill、競合等をこの残余内に保証できていないため、この単純分担を性能合格としない。分担を変えた adapter は別に費用と期限を確認する必要がある。

|領域|bytes|範囲|
|---|---:|---|
|履歴 state|92|偶数15複素、奇数8複素|
|workspace|4192|最大1024 raw、vector read padding 込み|
|係数 vector 表|272|17×8×s16|
|raw block|4096|別に必要|
|I16/Q16 出力 block|2048|別に必要|

これは 1 workspace 分。2 core 分、queue、DMA descriptor、driver/RTOS、stack 等を含む全 RAM 見積もりではない。kernel は 4 出力につき 46 回の 16 byte vector load、論理読出し 1.472 GB/s を行う。小さい係数表や重なる入力窓を繰り返し読む値で、外部 PSRAM の物理通信量と同一視しない。配置と競合の検証は必要。

## 検証と再現

```sh
python ci/t_halfband_capacity_audit.py --toolchain /path/to/xtensa-esp-elf
```

script が target compile と逆 assembly を行い、S3 構成を設定して PIE instruction を decode する。作業ディレクトリに依存せず repo ROOT を基準とし、`.o` / `.so` は `build/t-halfband-capacity/` に置く。`--output` の既定はこの report directory、相対指定も ROOT 基準。命令列 [halfband31.dis](halfband31.dis) と数値・check 一覧 [halfband_results.json](halfband_results.json) を生成し、source と disassembly の SHA256 は repo 相対パスを key に保存する。

**audit は group 単位で non-fail-fast。** target C build、target asm build、host build を独立に試み、失敗した build に依存する decode/意味モデル/依存待ち/命令数だけを理由付き `BLOCKED` とする。独立した host oracle、係数、スペクトル等は継続する。最後に全 group の `PASS` / `FAIL` / `BLOCKED` 一覧を JSON に保存し、FAIL または BLOCKED があれば exit 1。以前の build が残っていても、今回失敗した build の代わりに流用しない。監査全体の PASS は以下の静的・意味モデル検証の完了を指し、受信機性能合格を意味しない。

- 実 target 逆 assembly の TRM 意味モデル：1600 条件、12,800 s16 lane が独立式と一致。shift 0/10/15/31、signed10 の上下端、random input、lane ごとに異なる random 係数も検証し、係数対称性に依存した照合を避けた。vector read は許可領域内で、偶数系列の 80 byte（padding込み）を確認。
- host C streaming：8〜1024 raw の変動 block、block 境界の履歴、metadata 上位 bit、上下端を含め 108 call、12,384 複素出力が独立した直接畳み込みと一致。出力後の canary を保持。
- invalid count、shift、alignment、null の 36 条件で state/workspace/output を変えず return 0。
- target 上での実行、周期計測、RF 同時取得、FPGA 接続は未実施。意味モデルは命令 encoding emulator や cycle simulator ではない。

命令の一次仕様は [Espressif ESP32-S3 TRM](https://documentation.espressif.com/esp32-s3_technical_reference_manual_en.pdf) の PIE の USAR/SRC、QACC MAC、§1.8.54 `EE.SRCMB.S16.QACC`。同命令の公式利用例は [esp-dl tie728 s16 実装](https://github.com/espressif/esp-dl/blob/5989f4a38f553235daf4da8a3de33a1acefe2196/esp-dl/dl/base/isa/tie728/dl_tie728_s16.S)。CPU 費用の比較元は既存 `reports/s3-preprocess-break-even/results.json` の感度仮定。具体費用の再分類は PR 本文の統合台帳と整合させること。
