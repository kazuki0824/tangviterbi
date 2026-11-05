# ② SPIの未確定時間を固定SDKの経路へ分解

2026-10-27。ESP-IDF fcae32885b0296b32044cb99ecbdc50d98dddb83のspi_master.c、spi_bus_lock.c、FreeRTOS queue.cを取得し保存。前2ファイルのSHA-256は既存ISR配置監査と一致する。出典URLとhashはsources.jsonに記録。runtimeと①は変更しない。

## 確認結果

**timeout=0はqueueの待機tickを0にする指定で、API全体のelapsed上限ではない。** xQueueGenericSendとxQueueReceiveは、空き/データ不足時のzero-timeout判定より先にqueue専用critical sectionへ入る。別coreのISRが同じqueueを使用する構成では、その競合時間も必要になる。

| 時間条件 | 実経路 | 確定できた範囲 | まだ必要な根拠 |
|---|---|---|---|
| S：両port巡回とqueue | ownerのRF poll/pack/collect → prepare_bulk → check_trans_valid → setup_priv_desc → xQueueSend → bg_request | raw queueはticks=0、1 port同時1転送、SDK descriptorをqueueへコピー | owner全体の通常/例外応答、queue critical待ち、bg_requestのatomicと割込み有効化の実時間 |
| W：return後から完了を回収可能になるまで | bg_request → 開始ISR → queue取得 → spi_new_trans → DMA/線上転送 → 完了ISR → ret_queueへ投入 | 復帰前に開始ISRが走る可能性あり。線上の必要clock数は前報告で確定 | 開始/完了ISRの到達遅延、descriptor設定、DMA競合、割込み優先度・mask区間、ret_queue critical費用 |
| R：回収可能からreap/completeまで | owner再巡回 → xQueueReceive → uninstall_priv_desc → s3_pp_complete | reapはticks=0。先頭から連続したDONEのみretire | owner再巡回遅れ、queue critical待ち、実メモリ遅延 |

ISRは `spi_bus_lock_bg_exit` が終了可能と判定するまでdo/whileで処理する。sourceにretryがあることだけで、実際の無限実行や候補不可能とはしない。単一device・単一owner・1 outstandingという現在の条件で到来回数を制限できるかを、他のIRQ/atomic処理と合わせて評価する必要がある。今回、任意回数でloopを打ち切る修正はしない。

## 通常経路から除外できる仕事

prepare_bulkはtransactionをzero初期化し、内部DMA可能なTX bufferを設定する。RX bufferはNULL。manual alignment flag付きなので、SDKがalignment/DMA条件を満たさないと判断した場合は一時buffer確保に進む前にエラーになる。成功経路ではsend_ptrは元bufferのままなので、setupのpayload memcpy/一時malloc、uninstallのpayload copy/freeは実行されない。

これはSDK全体にallocationがないという意味ではない。初期化のqueue/descriptor等の確保、失敗経路、他の構成を含むメモリ台帳は別に残る。キャッシュ関連の条件付きコードやatomicを、sourceに書かれた命令数だけで一定cycleとはしない。

## IRQ affinityの4候補への影響

API ownerはcore0のまま。SPI2/SPI3 ISRのaffinityには既存の(0,0)/(0,1)/(1,0)/(1,1)がある。

| ISR affinity | この2本のqueueについて、ownerとISRが別coreとなる本数 | 評価上の差 |
|---|---:|---|
| (0,0) | 0 | 同じqueueを別coreから同時に操作する競合を、単一owner/ISR条件では除外できる。両ISRがcore0のRF/packingを妨げる時間は残る |
| (0,1) / (1,0) | 1 | 1本にcross-core queue critical競合。各coreのISR負荷を別途課金 |
| (1,1) | 2 | 両queueにcross-core競合。core1 packingへのISR負荷も別途課金 |

(0,0)でも全spinlock待ちや全IRQ遅延が消えるとは言わない。割込み配置を実際に変更・採用したわけでもなく、4候補の性能合格はまだ0。単にqueue競合を減らすためだけにcore0へ集約すると、RFの観測期限へ悪影響を与え得るため、core別応答時間と同時評価する。

## 再現と判定

`python ci/s3_spi_wait_audit.py --output build/spi-wait-audit.json`

保存hash・既存SDKとの同一性・sourceの経路/順序など14チェック成功（audit.json）。sourceのanchor照合であり、実バイナリCFGやWCETの証明ではない。ソースはSDKライセンス表記を保持して保存した。

今回減らせた未知項は、成功raw経路の一時payload allocation/copyと、(0,0)条件に限ったこのqueueのcross-core競合。一方、数値S/W/Rは確定していない。次に必要なのは、単一outstanding条件下でのISR retry/atomic競合の回数と、各coreの干渉・メモリ待ちの時間根拠。実機elapsed上限や全到着列、SoC全メモリ、全FPGA fit/STAの成立確認は継続する。性能合格・正式割当・採用は0。
