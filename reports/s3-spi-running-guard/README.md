# ② 転送中の空振りSDK完了確認を省く

2026-10-28 JST。raw-only構成の `s3_spi_reap` に、固定ESP-IDF 5.5.1の `spi_ll_get_running_cmd` を使った早期TIMEOUTを追加した。専用bus・device・未回収transaction 1個という既存構成に限定する。

動作中のcommandがあれば、SDK結果キューを呼ばずTIMEOUT。idleでも完了とは扱わず、従来の `spi_device_get_trans_result(...,0)` と返却descriptor同一性検査に成功して初めてleaseを解放する。queuedだが未開始、hardware終了だがISR未公開というidle状態ではSDK TIMEOUTのまま所有権を保持する。

[固定SDK HAL](https://github.com/espressif/esp-idf/blob/v5.5.1/components/hal/esp32s3/include/hal/spi_ll.h) の `get_running_cmd` は `cmd.usr` を読む。一方 `usr_is_done` は `dma_int_raw.trans_done` を読むため、ISRが消去する完了フラグをraw割込み経路のguardには使わない。既存の非raw polling方式は変更しない。

実Cのhost試験では動作中のSDK呼出し省略、idleかつ未公開時のlease保持、完了フラグ消去後のSDK完了回収、2portの逆順完了、queue失敗時のpayload保持を確認。既定adapterとraw-onlyの両方を試験した。tests.logは統合見積もり試験も含む。

これは命令経路の改善であり、実CPU時間の削減量は未測定。転送20µs、追加scan1500cycle、管理200cycleの仮定は今回減額しない。したがってS512上端97.48%、S256上端102.41%という前回感度値は維持し、16.05µs/転送という目標を達成したとは言わない。動作中の空振りはscan費用側であり、完了転送1件の費用と混同しない。

[変更後SDK run 40535137322](https://github.com/kazuki0824/tangviterbi/actions/runs/40535137322)、commit `9da570f67607e1278c5e7089a40ff1d0902ea3fc` の成果物を取得・SHA256照合した。T/S各59静的check、各12項目のソース・fill生成命令照合が成功。`sdk-S/`・`sdk-T/` に実ELF・map・設定・provenance・照合結果を保存する。packing CFGも各4checkを通過し、係数45/118/173/223は不変。

実ELFの `s3_spi_reap` は139bytes。`sdk-reap.dis` はbranch先から再開してpaddingを命令と誤読しない逆アセンブルである。Sは0x40378244、Tは0x40378240に配置。両方で相対+0x43のmemw、+0x46のCMD読出し、+0x4bのbit24分岐を確認。動作中なら+0x4eでTIMEOUT=0x107を設定し+0x89でreturn、SDKを呼ばない。idleは+0x56へ進み、+0x5cで `spi_device_get_trans_result` を呼び、SDK成功とdescriptor一致後にのみleaseを解放する。これは生成経路の確認であり、MMIO待ち・割込み・実時間上限の証明ではない。

IRAM末尾0x40388200はT/S共通。Sのheap開始0x3fcad098・既知driver控除後内部空き上限16324bytes、Tは0x3fcad068・16180bytes。guard追加前と変わらない。未計上割当と断片化を除く上限なので実起動可能性の保証にはしない。

再現（Tも同じ引数のSをTへ置換）：
```
python -m ci.s3_fill_unroll_sdk_audit --profile reports/s3-spi-running-guard/sdk-S/image --toolchain build/rs-toolchain/xtensa-esp-elf --commit 9da570f67607e1278c5e7089a40ff1d0902ea3fc --target-dir reports/s3-budgeted-fill/u8 --output reports/s3-spi-running-guard/sdk-S
python -m ci.s3_current_pack_cfg_audit --profile reports/s3-spi-running-guard/sdk-S/image --toolchain build/rs-toolchain/xtensa-esp-elf --output reports/s3-spi-running-guard/cfg-S
```


## 動作中とidleの実命令数比較

`ci/s3_spi_guard_path_audit.py` で、旧S ELFと変更後T/S ELFの宣言した経路を各命令の開始位置から逆アセンブルし、全隣接分岐・call先・returnを照合した。wrapper `s3_pp_spi_reap` を含む。各経路とELF hashはpath-cost/results.jsonに保存する。これは指定条件の命令経路照合であり、任意の状態についての形式証明ではない。

| 経路 | 旧版 | 新版 SPI2 / SPI3 |
|---|---:|---:|
| hardware動作中、結果未公開 | 49＋Q命令 | 38 / 40命令 |
| hardware idle、結果未公開 | 49＋Q命令 | 58＋Q / 60＋Q命令 |

QはSDKの `xQueueReceive(...,0)` 内部で実行する命令数。未計数であり、0と見積もった値ではない。旧版に対し、動作中は11＋Q / 9＋Q命令を削減、idle未公開では9 / 11命令増える。新しいguardの検査費用を無視して、全経路で改善したとは言わない。

上記2経路だけの混合に限り、動作中割合bに対する平均命令差（新版−旧版）はSPI2で `9-b*(20+Q)`、SPI3で `11-b*(20+Q)`。Q≥0だけを使う保守的な境界はb=45% / 55%で、それを上回れば命令数が減る。完了回収・submitや実際の経路頻度はこの比較に含まない。MMIO待ち、割込み、window spill/fill、memory競合があるため、命令削減を同率の実時間改善とは扱わない。

再現：`python -m ci.s3_spi_guard_path_audit --toolchain build/rs-toolchain/xtensa-esp-elf`。
