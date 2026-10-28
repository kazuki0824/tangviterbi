# ② 全費用計上・同一費用による期限評価の接続状況

2026-10-28 JST。**依頼された手順1・2は未完了。** 本変更は転送構成の接続不一致の修正と、費用区分/発生頻度の台帳化である。全費用の数値確定や共同スケジュールの完了と報告しない。

## 修正した構成不一致

現在のS候補は16KiB転送だが、保存済みarena/順序付きprefix/IRQ到来包絡の関数は32KiB固定だった。短転送専用の周期scan試験は別途16KiBを扱っており、その結果まで誤っていたという意味ではない。これらの結果を一つに接続する際に構成を混在させてはいけない。

`capacity`、`connect`、`wire_floor`、`evaluate`、`worker_event`へ転送長を伝播する。既定32KiBの過去試験は維持し、Sでは16384を明示する。4×32KiBの物理arenaは変更しない。

| 入力/必要頻度 | T | S |
|---|---:|---:|
| payload | 40MB/s | 100MB/s |
| 転送長 | 32768bytes | 16384bytes |
| 定常成功転送頻度の合計 | 1220.703125/s | 6103.515625/s |
| 公称12288samples/bankのbank頻度 | 1302.083333/s | 3255.208333/s |
| Octal線上時間下限 | 98334cycle | 49182cycle |
| Quad線上時間下限 | 196668cycle | 98364cycle |

線上時間はqueue復帰後の残時間の下限でも、送信完了上限でもない。header80bit、80MHz、multilineから算出。IRQ式の周期Lへ同じ転送長を接続した。有限burst/carry-inを含むIRQ式の適用前提・実行費用Cの未確認は残る。

16KiB/32KiBで同じbyte数を解放した場合に同じ残量になること、128KiB容量の不変、必要prefix数、公開chunk数、IRQ周期境界、設定伝播、無効転送長拒否を追加試験。既存試験込み16件成功。

## 費用台帳

results.jsonのcomponentsに13区分を保存した。owner制御、worker制御、packing、RF poll、fill、collect、SPI submit、SPI reap、SPI IRQ、WDT更新、その他IRQ、stall/block、起動停止faultである。包含するcalleeと除外する別費用を明示した。これは費用境界の定義であり、全経路の漏れなしを証明したものではない。

継続受信の完全なowner反復をN0、worker反復をN1とすると、native pollは7N0、collectはN0、packing試行は各coreでN0/N1。nativeのquiet/wait/switch/accept/prepare回数の合計は7N0。SPI試行は各方向で2N0以下、成功転送/回収は定常payloadと転送長から制約される。watchdogは5000ms設定なら更新間隔2500msで、長さR cyclesの区間の更新回数は各coreで1+floor(R/600000000)以下という条件付き包絡になる。

N0/N1と各状態の比率は、実行時間を無視したhost試験からは決まらない。短縮した経路の時間だけを独立に平均へ代入しても全費用計上にはならない。旧U0/U1をこの台帳の代わりには使わない。

## 未完了項目

1. 通常以外のnative/collect/packing空振り/driver/IRQ/WDT費用、各状態の発生頻度、競合待ちを含む入力範囲。記号を数値ゼロで代用しない。
2. その同じ入力による非一様なowner/worker/DMA順序の評価。RF switch/prepare/reclaim、送信、順序付きprefix解放、128KiB容量を同じ実行について確認する。従来の一定scan30µs・固定公開320µsの別模型は代替にならない。

再現：`python -m experiments.s3_joint_accounting`、`python -m unittest tests.test_s3_schedule_transfer_size tests.test_s3_arena_limits tests.test_s3_spi_prefix_response tests.test_s3_native_spi_windows tests.test_s3_spi_irq_envelope`。
