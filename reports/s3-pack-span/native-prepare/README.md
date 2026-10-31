# ② RF coordinator: sentinel preparation

2026-10-25。production af66386 の保存済み SDK ELF を再利用し SHA256 を照合。FPGA/SoC の分担・信号品質・通信方向は変更していない。

`s3_native_poll` は reclaim 成功後、次 bank の START=3072、END=4096 words を一度の poll で書く。SDK の2個の hardware-loop body はそれぞれ `extui, addx4, memw, s32i.n, addi.n` の5命令。合計 **35,840命令/bank**。volatile store ごとの memw も含まれる。setup、callback、その他poll、バス待ち、割込みは含まない。命令数から実時間の上限は得られない。

| 条件 | T | S |
|---|---:|---:|
| 公称12288 samples/bankでのfill命令/s | 46.667 M | 116.667 M |
| 理想1命令/cycle、240MHzでのbody時間 | 149.333 µs | 149.333 µs |
| 同じbody中に進む入力数（切上げ） | 2390 | 5974 |
| bodyのみを引いた最遅開始written | 11898 | 8314 |
| LATE=2000 samples相当時間 | 125 µs | 50 µs |

公称bank頻度を使う。実際のcount、初回bank、late、sentinelの境界は変動する。毎秒値を任意の実行traceの保証値として使わない。

## poll間隔と開始位相

149µs > 50µs だけでS不可とはしない。準備は次の切替より十分早く開始できる。INDEXを読んだ時点のwrittenに対して、次回INDEX観測までの条件は

`written + ceil((prepare_tail_cycles + external_gap_cycles + next_poll_to_INDEX_cycles) / cpp) <= 14288`

である（cpp=T15/S6、THRESHOLD+LATE=14288）。上表の最遅開始はbody以外を全て無料とした参考値で、許可時刻の保証ではない。入力位相・INDEX/MMIO同期も実機確認が必要。次回INDEX観測後のSELECT書込み時間と境界guardは別途必要。

現行コードはavailableなら直ちに全fillを実行する。unavailable時の早期停止条件、前回poll時刻、reclaim可能時刻もあるため、任意の遅いwrittenを選んで「到達可能な失敗」と断定もしない。実taskの時系列で、準備開始位相と各bankのlease期限を一緒に確認する必要がある。既存host模型は各sentinel storeの実時間を進めないので、その成功でこの条件は証明できない。

## coordinator費用への反映

前回のpacking CFG値（12288 samples、first=0、slice=512pairs、等分）に、今回のfillを1命令/cycleとして加算。さらに旧模型のAPI active 20µs/32KiB（payload+0.01MB/s）を**仮定**として加えると:

| 条件 | T Mcycles/s | S Mcycles/s |
|---|---:|---:|
| packing（保守的命令訪問数、理想cycle換算） | 47.959 | 119.899 |
| sentinel body（同じ理想換算） | 46.667 | 116.667 |
| API（旧仮定、未測定） | 5.861 | 14.650 |
| 合計 | 100.487 | **251.215** |

Sはこの**条件付き模型**で240を超える。packingには排他的経路を両方数える上振れがあり、APIも未測定なので、これを実機不成立の下限証明にはしない。一方、この模型のまま「現在の等分実装に性能余裕あり」とはできない。旧RF未分類残額128.4375をさらに加えると二重計上の可能性があるため加算しない。他のRF制御、共通clock、IRQ、SPI競合等は依然未分類。

次の実装判断は、fillの短縮/分割又はpackingのcore配分変更を、準備開始位相・bank消費期限と合わせて評価すること。まだ変更・採用していない。共通clockのepoch/単位統一とwait上限も未完。①は対象外。

## 再現と検証

`python -m ci.s3_native_prepare_audit --toolchain build/fir-target/xtensa-esp-elf --output reports/s3-pack-span/native-prepare`

ELF一致と2ループ命令列の3チェック成功。新規3 unittest、およびnative capture/parallel packing既存5件の合計8件成功。UBSanを含む既存host試験は機能検証でありtarget時間測定ではない。結果は results.json、命令列は fill.dis、試験出力は tests.log。production/firmware変更なし。
