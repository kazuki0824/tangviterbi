# ② settling後の初回INDEX、準備開始、packing期限の接続

2026-10-26。実nativeの分岐と実packingの処理量を検算。runtime sourceは変更せず、①にも変更なし。性能合格・正式通信路割当・採用は0。

## 初回INDEXまでの条件付き予算

Bはswitch_earliestからsettling完了後の最初のINDEX読取り完了までのelapsed上限。SELECT/clock末尾、settling待ちと次pollまでの遅れ、境界探索、accept、taskの間の処理、INDEX MMIO遅延を全て含める。

RF indexが一定rateで進み、不連続やunwrapの曖昧さがなく、最初の観測が受理済み終端e以降であるという条件の下では、writtenの上限はceil(B/cpp)。ここでcppはT15/S6 cycles/sample。RFの未公開ABIでこの条件を実証できたという意味ではない。

| 条件 | T | S |
|---|---:|---:|
| 次bankがbusyのとき許される初回written | ≤7930 | ≤5930 |
| 上記を保証する保守的B予算 | 495.625 µs | 148.250 µs |
| 次bankがavailableのとき準備開始可能な初回written | ≤12287 | ≤12287 |
| 上記を保証する保守的B予算 | 767.9375 µs | 307.175 µs |
| switch_earliestからpacking deadlineまで | 1263.6667 µs | 455.4667 µs |
| busy用B予算の端での残時間（下記費用控除前） | 768.0417 µs | 307.2167 µs |

busyのgateはTHRESHOLD−floor(20000/cpp)−1024−LATE。最初の観測がgate以上ならnativeはfault7で止まる。availableならそのgate以降でも準備できるが、THRESHOLD到達時に未準備ならfault5になる。この違いをT/Sの実native C試験で確認した。小さいbusy用予算を全条件共通の絶対限界とは扱わない。

準備開始できることだけでは十分ではない。初回written上限w、準備の追加費用P、通常観測間隔Dに対し、さらに w+ceil((P+D)/cpp)≤14288 が必要な局所条件となる。limits.jsonはB/P未測定をnullのまま保存し、上限超過を候補の不可能性とは判定しない。

## packingの期限はaccept時刻から始まらない

期限はswitch_earliest＋(2×12288−1024−2000)×cpp−20000。settlingと公開が遅いほど残時間は減る。busy用B予算を差し引くと、12288×cpp＋cpp−(20000 mod cpp)となり、ほぼ1 bank周期である。

表の残時間はworkerの校正誤差E、DONE公開末尾、他の仕事、既存job backlog等を引く前の値。workerは物理時刻そのものではなく上側時刻Uで期限を判定するため、実行可能なworker応答時間にはEも計上する。accept時点ではまだB全部が経過していない場合があるので、Bの端を使う計算は保守的な条件である。

## nominal 6 sliceを最大bankへ流用しない

nativeが受理し得る最大countは12288＋2000＋64＝14352 sample。512 pair/slice・現行均等分割の場合、各workerはnominal bankなら6回だが最大bankでは8回必要になる。carry有無とsource wrapを含めた実packing C試験で、回数と全出力byteの一致を確認した。

この8回は有効なpacking slice回数であり、空job反復・poll・collect・SPI・watchdog費用は別。既存のnominal平均予算を6回で割った値を、最大bankの期限判定へそのまま適用してはいけない。以前のnominal表はその限定を明記しており、その数値を誤りとして消してはいない。

## 検証と未完了

14 unittest成功（tests.log）。初回busy gate−1/gate、available THRESHOLD−1/THRESHOLDを実nativeで確認。整数丸め境界と準備費用の合成、既存位相/7gap条件、実packing・並行所有権/SPI試験も成功。試験の人工時刻は実機の時間測定ではない。

B/P、各task経路とIRQ・メモリ干渉の数値上限、およびbank到着から両worker完了・reclaimまでの全体応答時間は未確定。今回閉じたのは「通常poll以外のどの時間を、どの期限に計上するか」と初回分岐/最大slice数の検算である。

再現:
```sh
python -m experiments.s3_settling_limits --output build/settling-limits.json
PYTHONPATH=tests python -m unittest test_s3_native_clock test_s3_settling_limits test_s3_task_gap_limits test_s3_raw_schedule_limits test_s3_parallel_pack -v
```
