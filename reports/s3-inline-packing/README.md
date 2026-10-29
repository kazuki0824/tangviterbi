# ② 可逆packingのinline候補

`experiments/s3_inline_pack.c` は既存packing実装の代替translation unit。8word処理だけをalways_inlineへ変更し、bank所有権・時計・slice制限・端数・折返し・品質を維持する。baselineと同時にlinkしてはならない。既定実装は変更していない。

Xtensa GCC 14.2.0_20241119、ESP32-S3設定で比較：

|設定|baseline定常命令/8sample|inline候補|step関数text|stepスタック枠|
|---|---:|---:|---:|---:|
|O2|45|39|770→890byte|96→112byte|
|Os|50|47|694→814byte|96→96byte|

O2の定常ループは13.33%の命令削減。これは実時間削減率ではない。run入口・spill/reload・slow経路・slice全体の費用再計数は未完了なので、送信queueの期限模型にこの削減を流用していない。SDK全体のstack高水位も別に確認が必要。

3分担/転送長×O2/Osの6条件で、実Cを2workerで実行。各2000bank・全出力の一致、carry、source/arena折返し、順不同DMA完了、stale lease、期限・backpressureを確認した。8wordのビット対応式はbaselineと同一であることも検査した。

[命令計数](instructions.json)、[検算](tests.log)。再現：`python -m ci.s3_inline_pack_audit --toolchain ../toolchain/xtensa-esp-elf`、`python -m unittest tests.test_s3_inline_pack`。
