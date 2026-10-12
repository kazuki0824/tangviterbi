# S3-N8R8とN16R8のSDK検証を分ける

2026-10-12。元の4 SoC比較のS3型番はN8R8。実SDK成功を保存したHEAD e8cc725の
native-direct-phy-simdは16 MB flash設定であり、N8R8設定の合格へ転用しない。

`native-direct-phy-simd-n8` profileを追加した。固定IDF5.5.1、同じbounded SIMD worker／
native RF lower-bound probeに対して8 MB Quad flash、Octal PSRAM 80 MHzを要求する。
build後の実sdkconfigを読んでflash容量設定とPSRAM設定の双方を検査する。
指定がeffectiveでない場合は成功にしない。既存16 MB profileにもflash容量の検査を追加。
CI matrixで8 MB設定専用job、独立ELF/map/configとstartup容量検算を保存する。

Flash容量を減らした分を内部SRAMの増加に数えない。N8 profileもdirect PHYなので
省いたevent taskを架空に加算しないことを回帰検査する。startup必要容量の検算は、
fragmentation／driver／追加worker stackの十分性や実起動の成功を証明しない。

追加後のSDK job結果回収までは**N8R8 link未確認**。実機RF dump、SIMD WCET、
memory同時占有、実受信機完成も未確認。CI入口を追加しただけで合格としない。

```sh
RF_PROFILE=native-direct-phy-simd-n8 python ci/s3_rf_coexist_probe.py
python -m unittest discover -s tests -p test_s3_startup_memory_bound.py -v
```

第1コマンドは固定upstream checkoutとIDF環境を必要とする。
新旧moduleの容量・GPIO根拠は[4 SoC比較台帳](four-soc-comparison.md)を参照。
