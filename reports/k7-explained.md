# このPRでいう「K7」と、共有する回路

**K7は、拘束長 K＝7 の畳み込み符号を復号するViterbi回路の略称**として使っている。7千個の回路やFPGA製品名を意味しない。これまでREADMEに`K=7`という表記はあったが、意味と今回の共有範囲を説明していなかった。

畳み込み符号は、現在の1 bitと過去のbitから冗長な符号bitを作る。K＝7では現在を含む7 bitを使い、過去6 bitの組合せに対応する **2⁶＝64状態**がある。Viterbi復号は、受信した値との食い違いを累積し、もっともありそうなbit列を求める。

この実装では符号器の多項式を8進数171/133としている。入力は受信bitの確からしさを表す8-bit軟判定値2個と、punctureで送信されなかったbitを示すerasure情報。出力は誤り訂正したbit列であり、これだけでTS完成ではない。後段のRS復号等は別に必要である。

| 用語 | この回路での意味 |
|---|---|
| ACS | Add・Compare・Select。候補経路の誤差を加算・比較し、小さい方を選ぶ処理 |
| 32並列／2 clocks | 32状態分のACSを2回実行して64状態を更新。1 trellis stepにつき復号対象1 bitが進む |
| metric | 各状態へ至る経路の累積誤差。この実装では順序を保つ13-bit modulo表現 |
| survivor | 各状態でどちらの前駆経路を選んだか。64 bit/stepを256行保持 |
| traceback | 保存した経路を逆向きにたどり、復号bit列を確定する処理 |
| context（復号状態） | metric、survivor、読書き位置、traceback途中状態、出力途中状態など、独立したbit列ごとに保持する情報 |

## ②で共有するもの

Tは最大3階層の独立した畳み込み符号列を扱うため、最大3 context。SのBPSK/QPSK系の畳み込み符号列を加えて、今回の実験は4 contextを持つ。

**共有するのはACSとtracebackの演算回路であり、4系統の復号状態は混ぜない。** 2クロック単位で処理対象を切り替え、入力と出力にcontext番号を対応させる。T/SのRF受信は同時のまま。①で許可されたT/S別bitstream切替とは別の仕組みである。

SのTC8PSK回路、TのFFT、T/SのFIR・同期、RS、TMCC、外部メモリ制御は、このK7共有だけで消えるものではない。depunctureの位相管理と入力FIFO/スケジューラも別に接続する必要がある。

## 実装と証拠の場所

- [既存単一contextの生成器](../experiments/s3_viterbi_traceback.py)：124-step tracebackとmetricの説明。
- [erasure対応](../experiments/s3_viterbi_erasure.py)：送られなかったbitを誤差0で扱う。
- [4 context共有RTL](../rtl/shared_k7_context.sv)／[生成器](../experiments/shared_k7_context.py)：2-clock slotで演算回路を共有する今回の実験。
- [機能試験](../tests/test_shared_k7_context.py)：独立した無限精度metric計算、全5符号率の符号化列、context交互処理、停止、途中resetとの照合。
- [資源監査](recovery-resource-audit.md)：共有によって許容される追加費用と、不採用にする条件。

回路の機能試験、FPGAに収まるかの合成・配置配線、実受信の期限保証は別の判定。K7単体が復号できても、指定したT/S同時受信機が成立したという意味にはならない。
