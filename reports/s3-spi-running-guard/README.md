# ② 転送中の空振りSDK完了確認を省く

2026-10-28 JST。raw-only構成の `s3_spi_reap` に、固定ESP-IDF 5.5.1の `spi_ll_get_running_cmd` を使った早期TIMEOUTを追加した。専用bus・device・未回収transaction 1個という既存構成に限定する。

動作中のcommandがあれば、SDK結果キューを呼ばずTIMEOUT。idleでも完了とは扱わず、従来の `spi_device_get_trans_result(...,0)` と返却descriptor同一性検査に成功して初めてleaseを解放する。queuedだが未開始、hardware終了だがISR未公開というidle状態ではSDK TIMEOUTのまま所有権を保持する。

[固定SDK HAL](https://github.com/espressif/esp-idf/blob/v5.5.1/components/hal/esp32s3/include/hal/spi_ll.h) の `get_running_cmd` は `cmd.usr` を読む。一方 `usr_is_done` は `dma_int_raw.trans_done` を読むため、ISRが消去する完了フラグをraw割込み経路のguardには使わない。既存の非raw polling方式は変更しない。

実Cのhost試験では動作中のSDK呼出し省略、idleかつ未公開時のlease保持、完了フラグ消去後のSDK完了回収、2portの逆順完了、queue失敗時のpayload保持を確認。既定adapterとraw-onlyの両方を試験した。tests.logは統合見積もり試験も含む。

これは命令経路の改善であり、実CPU時間の削減量は未測定。転送20µs、追加scan1500cycle、管理200cycleの仮定は今回減額しない。したがってS512上端97.48%、S256上端102.41%という前回感度値は維持し、16.05µs/転送という目標を達成したとは言わない。動作中の空振りはscan費用側であり、完了転送1件の費用と混同しない。

SDKリンク・IRAM配置は変更後のCIで再確認する。既存1d954f4のELFをこのguardの検証済み成果物としては扱わない。
