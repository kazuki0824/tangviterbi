# ② 通常owner反復：collect・feed・制御を加えた費用

2026-10-28 JST。固定S候補SDK ELFから指定経路を計数した。runtimeは変更していない。全分岐選択・call数・source/ELF hashを照合し、pathsをresults.jsonへ保存する。任意状態の形式証明、WCET、実平均ではない。

条件はRF準備済み・非settling・閾値未満、両SPI転送中、watchdog更新時刻より前、時計上位word=0、fault/stopなし。collectは(1)所有bankなし、(2)bank0の両jobが未完了で期限内、の2例。状態遷移・他経路の頻度は未評価。

| 命令数の内訳 | 所有bankなし | 1bank未完了 |
|---|---:|---:|
| ownerループ制御（call命令を含む） | 108 | 108 |
| RF監視callee群 | 1295 | 1295 |
| SPI確認callee群 | 78 | 78 |
| collect用時計 | 20 | 20 |
| feed確認＋時計（実WDT更新なし） | 40 | 40 |
| collect | 31 | 66 |
| **packing本体を除く合計** | **1572** | **1607** |
| α=1.1のcycle相当 | **1729.2** | **1767.7** |
| 240MHzでの時間模型 | 7.205µs | 7.3654µs |

実ELFの最初の2回のRF監視はpoll_rf wrapperがinline化されている。前回の「7×189命令」をそのままowner制御に加えると2×14命令の重複になるため、RF callee群は1323−28＝1295とした。残り5回のpoll_rf wrapperは実call先として計数する。ownerループにはnative直接call2回、poll_rf5回、packing1回、collect時計1回、collect1回、SPI reap2回、feed1回があることを検査。

packingはpack_slice wrapperと時計を含めbody全体が別費用。fill、RF切替・settling・accept、SPI完了/submit、実watchdog更新、その他collect状態、並行worker遷移、stall/IRQ/window exceptionも今回の合計に含まない。従ってscan全体の上限ではない。

## CPU感度への接続

次表は上記2経路のcycle相当を**平均追加scan費用と仮定した場合**。その平均を達成・測定したという意味ではない。管理200cycle/反復、SPI20µs、U0/U1=20/10Mcycles/s等は維持する。

| 追加scan費用の仮定 | S512 core0上端 | S256 core0上端 |
|---|---:|---:|
| 従来1500cycle | 97.4807% | 102.4113% |
| 1729.2cycle | 98.2766% | 103.2071% |
| 1767.7cycle | 98.4103% | 103.3408% |

式はケースごとに `P200+(C−1500)*(owner_frequency−25000)/2400000`、全ケースの最大値。従来Uに25000反復/s側の未分類費用を残しているので、今回分を全反復へ追加しない。管理200cycleは準備管理の別感度点として維持する。Uの実内訳と状態頻度が未確定であることは変わらない。

S512のscan予算2225.546cycleから引いた残額は496.346 / 457.846cycle。その他経路・待ちをこの残額に収められるとの確認はない。512を推進候補として維持し、256への変更は行わない。性能合格・通信路正式割当・採用は0。

次は、collect完了公開・RF切替/settling/準備・SPI完了/submit・実watchdog更新を含む経路頻度と総費用。通常経路だけを平均上限に昇格させない。

再現：`python -m ci.s3_owner_iteration_path_audit --toolchain ../toolchain/xtensa-esp-elf`。
