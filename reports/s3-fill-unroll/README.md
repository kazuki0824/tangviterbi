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
| T raw 8/16・32KiB | 41.96〜43.94% | 26.18〜28.05% |
| S raw 5/16・16KiB | 83.22〜86.71% | 80.07〜87.86% |
| **S raw 6/16・16KiB** | **90.17〜94.40%** | **73.27〜79.94%** |

S6/16の追加scan費用の平均CPU予算は旧465.90→現在3113.63cycle/回に増える。3000cycleという感度点でもcore0上端99.61%。これは実測費用・信頼区間ではない。

6/16のpacking-only平均service上端は現SDK係数で271.73µs。fillの命令削減が、公開320µsまでの実スケジュール全体を自動的に保証するものではない。通信容量・有限buffer条件・FPGA全体資源の未確定差分も不変。実装改善は平均CPU予算の問題を緩和するが、受信機成立の確認はまだ終えていない。

## 検証

host試験は実production fillを呼び、全16384開始位置×17長さと非正規化開始位置を1/4/8word全てで確認する。長さはunroll境界、ring全周、複数周回を含む。独立した距離式で全wordとguard、callback回数を検査、UBSan有効。native capture・共通時計・parallel deadline・raw task試験も併せて実行し、結果をtests.logに保存する。テストの時刻は実write時間ではない。

再現：`python -m ci.s3_native_fill_target --toolchain build/rs-toolchain/xtensa-esp-elf --unroll 8 --output reports/s3-fill-unroll/u8`、`python -m experiments.s3_integrated_estimate`。

## 同じS構成のSDK確認を追加

raw-only SPI CIにS6/16・16KiB・8word fillのprofileを追加。CMake定義を全関連翻訳単位へ一括適用し、実ELFに残した3設定値を要求値と照合する。DMA descriptorの既知量も実転送長で計算する。既定T相当8/16・32KiB構成とのメモリ差を混同しない。これはlink診断であり受信task実行ではない。CI結果は取得後に別途記録する。

### 既定構成のSDK結果

[run 40507751547](https://github.com/kazuki0824/tangviterbi/actions/runs/40507751547)、commit `2ecb729`の共通/raw-only構成は成功。raw-only ELFを取得し、source identity・ELF hash・実生成命令（literal relocationのみ除外）・sentinel定数等9確認が成功。fillは165bytes・61命令でobjectと一致し、15362命令/bank包絡を適用できる。SDK配置監査54項目成功。IRAM末尾0x40388100、heap開始0x3fcacf60、既知driver控除後の内部空き**上限**16444bytes。未計上割当・断片化・実起動を含む保証値ではない。S6/16・16KiBのprofile結果とは区別する。証拠と再検算はsdk-defaultおよび `ci/s3_fill_unroll_sdk_audit.py`。

### S候補構成もSDK link・配置確認が成功

[run 40508948605](https://github.com/kazuki0824/tangviterbi/actions/runs/40508948605)、commit `ca8c06e`で共通・raw-only既定・S候補の3profileが成功。S候補はELF内の設定が6/16・16384bytes・8wordであることを含む57静的check成功。fillの実命令列・sentinel・source identity等9再確認も成功。

同じcommitのraw-only既定との比較：pack構造体392→440bytes、heap開始0x3fcacf60→0x3fcacf90（+48bytes）。DMA descriptorの既知量は1port216→120bytes、2portでは192bytes減少。差引で既知driver控除後の内部空き上限16444→**16588bytes**（+144bytes）。IRAM末尾0x40388100は共通。メモリの実起動・断片化・未計上割当の解消を意味しない。

### 残るスケジュール上の具体的な問題

現在のownerは `poll_rf → s3_native_poll → fill(3072)＋fill(4096)` を同期実行し、その間は同じownerのSPI reap/submit・collectへ戻らない。今回の同じα=1.1模型でもfillは約70.41µs/bank（bodyだけ約69.81µs）を見込む。従って、平均CPU94.40%に下がったことから「scanが常に30µs間隔」を導けない。一定30µsの有限buffer検証を、現runtimeの成立根拠として昇格させない。

次のSoC改善はfillを途中再開可能な小単位へ分割し、owner1反復当たりのfill仕事量を制限すること。その場合は次bankの全消去完了前にpreparedへ遷移しないこと、reclaim順序、RF切替期限、追加管理費用、非一様なSPI service間隔を同時に評価する必要がある。これは単なる測定不足ではなく、現runtimeと一定scan模型の対応が取れていないという残課題である。

### packing係数も現SDKで再計数

S候補と同じcommitのT相当profile双方を逆アセンブルし、到達可能CFGと4つのloop backedgeを検査した。regular118・bulk6・byte11・候補scan17は旧値と一致。量子化時計対応を含む現implは293nodes（旧285）、wrapper31（旧29）で、slice係数は213→**223**。block45/run118/slow_pair173は不変。`cfg-S`と`cfg-T`にELF hash・設定・4確認・CFGを保存。S5/16についてはshareがaccept時の分割位置だけに使われる同じpacking本体の係数を適用する比較模型で、5/16専用SDKを新規buildした結果ではない。

統合見積もりをこの係数で再計算したため、直前のS6 core0上端94.32%は**94.40%**、core1上端79.83%は**79.94%**へ更新。clock callback本体・実メモリ待ちはこのCFG計数に含まず、既存の別費用・感度仮定を保持する。
