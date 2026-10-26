# ② DONE後のbank解放期限

2026-10-26。前回の応答時間モデルへ、nativeのbank再使用条件から導いた**条件付きの十分条件**を接続した。性能合格・正式割当・採用は0。runtime sourceと①は変更しない。

## 導出

A→B切替時のINDEX観測をt0、nativeのswitch_earliestをs0≤t0とする。連続した整数cycle/sampleのRFモデルで、受理終端end(A)がこのINDEX以上なら、次のBは少なくともTHRESHOLD=12288 sampleを含む。Cの取得中にAが未解放としてfault 7になるには、Cのwrittenがgate以上でなければならない。

したがって、その観測までにt0から少なくとも12288+gate sample進む。1 sample当たりcpp cycle、任意の整数位相でn sample進む最短時間は `(n−1)×cpp+1` cycle。s0基準でこの値より前にAを解放すれば、このbusy判定より先に解放できる。

| 条件 | T | S |
|---|---:|---:|
| sample rate (MSa/s) | 16 | 40 |
| cpp (240 MHz) | 15 | 6 |
| gate (sample) | 7931 | 5931 |
| 最小sample進行量 | 20219 | 18219 |
| reclaim厳密上限 R（release < R、cycle） | 303271 | 109309 |
| この式で保証できる最後の整数cycle | 303270 | 109308 |
| 同値の時間 (µs) | 1263.625 | 455.450 |
| packing厳密上限 (cycle) | 303280 | 109312 |
| packing上限 − reclaim上限 (cycle) | 9 | 3 |

これは実機での最終許容時刻を特定する計算ではない。実際のpollはもっと後でもよく、この保守値を越えただけで候補が不可能とは言えない。INDEXの連続性・unwrap・受理終端との順序、Bの最小count、native以外がbankを公開しないことが前提。通常INDEX間隔、settling、準備完了期限、出力arena容量とSPI回収は別に満たす必要がある。

## 応答時間への接続

`bank_response(..., native_reclaim_model=True)` またはCLI入力の `"native_reclaim_model": true` を指定した時だけ、この予算を使う。明示的reclaim_budgetとの同時指定、およびnativeでは発生しない古いbank2個のAPI stress条件との併用を拒否する。従来通り予算未指定ならunproved。

Jと各応答Rはswitch_earliestからの物理elapsed上限として与え、両DONE上限を `max(J0+R0, J1+R1)` とする。その後のcollect待ちはcore0の通常反復2回＋追加干渉包絡で覆う。合計が上記reclaim上限**未満**であることを要求する。時計誤差はworkerのsampled deadline/admissionにも別途課金する。数値入力が物理elapsed上限である根拠は、この式やhost試験からは得られない。

packing期限をreclaimへ流用すると、workerが期限内にDONEでもcollectによる解放が遅いケースを見逃す。T/S両方について、DONEは期限内、解放はreclaim上限ちょうどで不合格、1 cycle早ければ余裕0で条件付き合格、という境界を試験した。条件付き合格もreceiver_adopted=false、hardware_RF_model_verified=falseのまま。

## 検証と残る項目

独立の整数sample counterでTの15位相/Sの6位相、受理終端の遅れ5条件、次bankの追加sample4条件を列挙した。実native Cでも同じgate観測時に、bankがbusyならfault 7、既に解放済みなら準備へ進むことを確認した。人工時計による分岐試験であり、RF実機やWCETの証明ではない。

関連21 unittest成功（tests.log）。条件付き数値はreclaim-limits.jsonに保存。前commit a3e513dのCIは確認時点で5 workflow成功、receiver functional closureは実行中。今回のCI成功とは区別する。

未取得の実elapsed上限C/A/J/Eと追加処理包絡、RF ABIの前提検証は残る。次にこのbank解放条件と独立な4出力arena/SPI回収条件を接続する。さらに起動全体のメモリ、RF設定/指令、全FPGA fit/STAが必要であり、この局所計算で全体成立とはしない。

再現:
```sh
python -m experiments.s3_reclaim_limits --output build/reclaim-limits.json
PYTHONPATH=tests python -m unittest test_s3_reclaim_limits test_s3_worker_response test_s3_settling_limits test_s3_task_gap_limits test_s3_raw_schedule_limits test_s3_parallel_pack -v
```
