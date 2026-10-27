# ② native fillの8word展開と統合見積もりへの反映

2026-10-27。production `s3_native_capture.c` の既定を8word展開へ変更した。比較用に `S3_NATIVE_FILL_UNROLL=1/4/8` を指定できる。各volatile store、store順序、compilerが挿入する各memw、末尾memw、ring境界、bank callback1回、reclaim-before-fillを維持する。入力精度・rate・転送形式は変えない。

## 実生成命令からの比較

GCC14.2 esp-14.2.0_20241119、ESP32-S3、O2、実production C全体を最小SDK宣言stubでcompile。SDK全体linkとは別。各variantのtarget.jsonにsource hash、flags、検査、命令数、fill.disに逆アセンブルを保存。

| variant | 主loop | 端数loop | 静的命令数 | 7168word/bankの命令数包絡 |
|---|---|---|---:|---:|
| 旧相当1word | memw/store/update、3命令/word | なし | 25 | 21570 |
| 4word | memw/store×4＋update、9命令/4word | 分岐を含む4命令/word | 50 | 16246 |
| **8word（既定）** | memw/store×8＋update、17命令/8word | hardware loopで3命令/word | 61 | **15362** |

旧台帳21574命令に対して28.794%削減。旧相当を同じ新包絡で比較すると21570→15362、28.781%削減。旧包絡との差4命令を改善による削減と混同しない。4wordより8wordが884命令/bank少ないため8wordを選ぶ。静的コード増加とSDK配置差分は別途確認が必要。

計数方法：各spanで、主loopをfloor(span/u)回、端数loopをspan mod u回計上。さらに**全ての非loop-body静的命令をspanごとに1回ずつ**計上する。排他的な分岐、入口・出口まで繰り返し計上する保守的な包絡。productionの3072wordと4096wordのfill（開始位置差12288）について全16384開始位置を列挙した最大値。任意nのWCETや、MMIO待ち・callback内部・caller・割込みまでの上限ではない。命令列とcompilerのloop回数の対応を前提とする。4wordの端数は実際に分岐loopになったので、理想式の3命令/wordから修正した。

## 同じ受信構成の見積もり

[統合見積もり](../receiver-integrated-estimate/README.md)の既知命令係数α=1.1、API active20µs、U0/U1=20/10 Mcycles/sを保持。Sの追加scan1500cycle/回という感度条件で：

| 構成 | core0 | core1 |
|---|---:|---:|
| T raw 8/16・32KiB | 41.92〜43.90% | 26.15〜28.01% |
| S raw 5/16・16KiB | 83.16〜86.65% | 79.94〜87.74% |
| **S raw 6/16・16KiB** | **90.09〜94.32%** | **73.15〜79.83%** |

S6/16の追加scan費用の平均CPU予算は465.90→3135.11cycle/回に増える。3000cycleという感度点でもcore0上端99.53%。これは実測費用・信頼区間ではない。

6/16のpacking-only平均service上端271.32µsは不変。fillの命令削減が、公開320µsまでの実スケジュール全体を自動的に保証するものではない。通信容量・有限buffer条件・FPGA全体資源の未確定差分も不変。実装改善は平均CPU予算の問題を緩和するが、受信機成立の確認はまだ終えていない。

## 検証

host試験は実production fillを呼び、全16384開始位置×17長さと非正規化開始位置を1/4/8word全てで確認する。長さはunroll境界、ring全周、複数周回を含む。独立した距離式で全wordとguard、callback回数を検査、UBSan有効。native capture・共通時計・parallel deadline・raw task試験も併せて実行し、結果をtests.logに保存する。テストの時刻は実write時間ではない。

再現：`python -m ci.s3_native_fill_target --toolchain build/rs-toolchain/xtensa-esp-elf --unroll 8 --output reports/s3-fill-unroll/u8`、`python -m experiments.s3_integrated_estimate`。
