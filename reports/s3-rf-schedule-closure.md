# RF polling・コア別需要・現行scalar FFTの下限

2026-10-11。平均CPU合計だけでは見えなかった条件を追加した。見積もり全体は未完了。

## 現行C FFTへ500 µsを割り当ててはいけない

IDF5.5.1指定のGCC14.2.0で`experiments/s3_fft_tiles.c`をO3コンパイルし、
実Xtensa命令の各butterfly loopの全分岐を検査した。
分岐の整合性を無視した最小load/store命令数なので、下限は実行より楽観的である。
逆順並べ替え、関数開始/終了、算術/除算の追加latency、同期、RF、memory stallはすべて除外する。

| O3 object | 1 butterflyのscalar load/store下限 | 8192点・13段の下限 | 理想240 MHz×2 coreの下限 |
| --- | ---: | ---: | ---: |
| full twiddle scalar | 32命令 | 1,703,936 memory issues | **3549.866667 µs** |
| quarter twiddle scalar | 35命令 | 1,863,680 memory issues | **3882.666667 µs** |

CPUの一次資料`core-isa.h`はload/store unit＝1、dual load/store FLIX＝0。
各coreが1 cycleで1個のscalar memory命令を出す楽観的な能力を使った。
SIMD命令へ置換する余地はこの下限に含まない。53248 butterflyの仕事は同じobjectを
2 coreで理想的に半分ずつ実行すると仮定し、並列化の費用も0にした。
それでも1039.5 µs/symbolの全CPU容量498960 cyclesを大幅に超える。

従って**このO3 scalar object**はT-A/T-BのFFTに使用不可。
公式高速sc16実装の1024点benchmarkのNlogN外挿は、現行C objectの測定値ではなかった。
500 µsの設計目標や24件の低費用CPU一次条件を、この実装の成立根拠に使わない。
SIMD版・別のobject・別分担の不可能性には一般化しない。
[逆アセンブル、最小経路、ISA設定のSHA256](s3-fft-target-bound/results.json)を保存した。

## 両coreを止めるFFTはnative取得の期限を破る

native pollは12288 sampleでbankを切り替え、追加2000 sampleを超える遅れを拒否する。
Tの16 MS/sでは遅れ限界125 µs。500 µs連続で両coreを占有し、その間pollも割込みも
実行しない方針について、開始位相256通り・最大1024 bankを検査した。
pollの遅れで次bankの閾値も移動するよう模擬した。

| 500 µsのFFT計算の分割 | poll gap仮定 | 256位相での条件合格 | 注意 |
| --- | ---: | ---: | --- |
| 1区間 | 0 | **0** | native切替期限違反 |
| 4区間（各125 µs） | 境界1 µs | 256 | 最大区間が遅れ限界と同じ。余裕の保証ではない |
| 5区間（各100 µs） | 境界1 µs | 256 | 合計elapsed 504 µs。実tile時間・poll費用は未測定 |
| 14区間 | 境界1 µs | 256 | 合計elapsed 513 µs。これだけではjoint scheduleの合格ではない |

位相200 µsでは2番目のbank切替が203.5 µs遅れて失敗。
位相0では一度の遅れを次bankへ伝えると3番目で271.5 µs遅れて失敗する。
ここでのtileは時間モデルであり、既存scalar Cへ付ければ500 µsになるという主張ではない。

## API時間をCPUへも計上し、担当coreを明示

SPI APIの20 µsを全量CPU-activeとする感度条件を追加した。
従来のwire時間への計上は残し、CPUでも負担する。待ち時間を含む実APIを計測した場合は
active部分の値へ置換して再計算する。RFのsingle packing ownerはcore0。
準備は20000 cycles/bank、controlは10 Mcycles/s、pollは8 cycles/256 samplesの設計予算。
T FFTは両coreを使う。S RFはAPI回数が最小になるOctal優先stripeを仮定し、
RSの追加RPC/API/CRC/IRQ/stallやDSP費用は除外するため、ここでの合格は必要条件のみ。

| 条件 | 準備 / API / control core | core0 | core1 | 条件判定 |
| --- | --- | ---: | ---: | --- |
| T pack4、FFT500 µs | 0 / 0 / 1 | **109.444%** | 52.475% | 合計80.959%でもcore0超過 |
| T pack4、FFT500 µs | 0 / 1 / 1 | 85.617% | 76.301% | 需要一次条件のみ合格 |
| T pack6、FFT500 µs | 0 / 1 / 1 | 98.951% | 76.301% | 余裕小。FFT目標自体が未実装 |
| S pack4、RS仮定2000 cycles/CW | 0 / 0 / 1 | **119.728%** | 34.306% | core0超過 |
| 同じS、APIをcore1へ | 0 / 1 / 1 | 93.793% | 60.241% | RPC等追加前の需要条件のみ合格 |
| S pack6、RS仮定2000 | 0 / 1 / 1 | **127.127%** | 60.241% | single ownerのまま不合格 |

core0/1の全144仮定profileを収録し、38件はこの限定需要条件に通った。
これを完成受信機の成立件数へ加算しない。過去のRFモデルの置換値でもない。
FFT elapsedを500→513 µsにした既存bank eventモデルの感度16条件も保存。
API CPU、poll blackout、旧bank eventをそれぞれ通ることから、同時schedule合格を推論してはいけない。

## 再現と次のゲート

```sh
python experiments/s3_rf_schedule_closure.py --output build/s3-rf-schedule-closure/results.json
python ci/s3_fft_target_bound.py --cc xtensa-esp32s3-elf-gcc --core-isa reports/s3-fft-target-bound/core-isa.h
PYTHONPATH=tests python -m unittest -v test_s3_rf_schedule_closure test_s3_fft_target_bound test_s3_bank_schedule test_s3_fft_tiles
```

14 unittest PASS。[全モデル結果](s3-rf-schedule-closure/results.json.gz)・
[scope/source SHA/集計](s3-rf-schedule-closure/summary.json)を参照。
次に必要なのは、scalar比較oracleと区別したtarget SIMD FFT/packer、RF poll機会、
実API active時間、RS/RPC/IRQ費用を結合したschedule、全体資源の検証である。
これらは環境内の実装・見積もり作業であり、実機だけが残ったとは分類しない。
`complete_estimate=false` / `CPU_WCET_verified=false` / `receiver_adopted=false`。
