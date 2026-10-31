# ② 可逆packingのinline候補

## 2026-10-30：slice全体の費用を含めた比較

N16R8設定の新ELFでCFG全336命令を分割し、scan最大3回・端数byte loop最大5回・8sample hardware loopを明示して再計数した。通常clock21命令×2とraw wrapper25命令は既存の確認値を別加算する。従来の45→39命令だけを差し引かず、周辺コードの増加も計上した。[係数・CFG領域・根拠hash](slice-costs.json)。

|費用項目|従来の命令数|inlineの命令数|従来→inline cycle（×1.1切上げ）|
|---|---:|---:|---:|
|8sample block|45|39|50→43|
|run|118|127|130→140|
|端数pair|173|182|191→201|
|非空slice管理（clock/wrapper込み）|290|293|319→323|
|空処理（clock/wrapper込み）|130|134|143→148|

実Cもinline primitiveへ置換した [期限評価65条件](../s3-queue-study/inline-runtime.json)を、[queue単独58条件](../s3-queue-study/audited-runtime.json)と同じRF条件・SDK単価・owner追加費用で比較した。出力全byteと費用保存を確認した。

S5/16・PCAB・準備2048語・owner追加300cycleの20000bank比較：

|観測値|queue単独|queue＋inline|
|---|---:|---:|
|arena最大使用 byte|124312|123348|
|arena最小残量 byte|6760|7724|
|RF監視最大間隔 µs|71.754|68.275|
|job期限余裕最小 µs|159.488|184.867|
|模型時間 秒|6.176|6.167|

**この条件付き模型では、周辺費用増を含めてもinline化で余裕が改善する。実機性能の確認ではない。** bank長はRF監視・切替位相にも依存するため、模型時間の差をそのまま処理速度の改善率と解釈しない。S5/16とS6/16のPCAB/BCPA・準備2048/3072語・owner追加0/100/300cycleの24条件はすべて4000bank通過。準備1024語はS5/16・BCPA・追加0だけ4000bank通過し、他条件は停止するため、既定値1024語を維持してよいという結果ではない。S6/16の20000bank評価は未実施。

再現：`python -m ci.s3_inline_slice_audit --toolchain <xtensa-esp-elf>`、`python -m experiments.s3_queue_audited_runtime --inline`。既定実装へはまだ組み込んでいない。window例外・メモリ待ち・競合、最終ownerと指令/supervisor、全受信機fitの未確定部分は残る。

以下は初回の定常ループ比較。


`experiments/s3_inline_pack.c` は既存packing実装の代替translation unit。8word処理だけをalways_inlineへ変更し、bank所有権・時計・slice制限・端数・折返し・品質を維持する。baselineと同時にlinkしてはならない。既定実装は変更していない。

Xtensa GCC 14.2.0_20241119、ESP32-S3設定で比較：

|設定|baseline定常命令/8sample|inline候補|step関数text|stepスタック枠|
|---|---:|---:|---:|---:|
|O2|45|39|770→890byte|96→112byte|
|Os|50|47|694→814byte|96→96byte|

O2の定常ループは13.33%の命令削減。これは実時間削減率ではない。run入口・spill/reload・slow経路・slice全体の費用再計数は未完了なので、送信queueの期限模型にこの削減を流用していない。SDK全体のstack高水位も別に確認が必要。

3分担/転送長×O2/Osの6条件で、実Cを2workerで実行。各2000bank・全出力の一致、carry、source/arena折返し、順不同DMA完了、stale lease、期限・backpressureを確認した。8wordのビット対応式はbaselineと同一であることも検査した。

[命令計数](instructions.json)、[検算](tests.log)。再現：`python -m ci.s3_inline_pack_audit --toolchain ../toolchain/xtensa-esp-elf`、`python -m unittest tests.test_s3_inline_pack`。

ESP-IDF v5.5.1のlink probe実ELFでも、定常ループ39命令・8load/5store、IRAM配置、step text890byte・stack枠112byteを確認した。[SDK監査](../s3-queue-study/sdk/audit.json)。全slice費用の監査は別であり、queue期限模型へpacking削減を加えてはいない。
