# ② SPI queueのcritical section内で必要な処理

2026-10-27。前回のowner/ISR status CASとは別の、FreeRTOS queue lockを調べた。runtimeと①は変更しない。

## 除外できた経路

現在のraw構成は各hostにdevice 1個、queue_size=1、owner 1個、ownerのsend/receiveはtimeout=0、ISRはFromISR API、queue setへの登録なし。初期化後に他のtaskがこのqueueへアクセスせず、lifecycle操作もしない条件では、待機taskのevent listは初期の空のまま。timeout=0はtaskをevent listへ追加する分岐に達する前にreturnし、FromISRもtaskを待機状態にしないため、この不変条件は維持される。

従ってqueue内の `xTaskRemoveFromEventList`、queue set通知、それに伴うyieldの経路を除外できる。item sizeは非ゼロでmutexでもないので、priority disinherit経路も通らない。これはqueue操作に起因する経路の話で、割込み・critical exit後のスケジューリング等が全て消えるという意味ではない。trace hookが有効ならその費用は別途必要。

保存SDK ELFのDWARFによる `spi_trans_priv_t` は**20 byte**。メンバー位置はtrans=0、buffer_to_send=4、buffer_to_rcv=8、reserved=12。SDK設定でSOC_SPI_SCT_SUPPORTED=trueなので、通常raw SPIでも予約領域2 wordを含む。同設定はSCT転送を使用しているという意味ではない。3 pointerだけから12 byteと推測しない。

| 呼出し | 保護対象 | 成功時のコピー | 空/満杯時 | 待機task操作 |
|---|---|---:|---|---|
| owner xQueueSend | trans_queue | 記述子20 byteをqueueへ | 満杯なら即return* | なし |
| ISR xQueueReceiveFromISR | trans_queue | 記述子20 byteを取り出す | 空ならreturn* | なし |
| ISR xQueueSendFromISR | ret_queue | 記述子20 byteをqueueへ | 満杯ならreturn* | なし |
| owner xQueueReceive | ret_queue | 記述子20 byteを取り出す | 空なら即return* | なし |

*return判断の前にqueue spinlockを取得する。ここでの「即」は空/満杯待ちのtask blockがないという意味で、時間上限ではない。

各API invocationでcritical sectionは1回、コピーは成功時1回・失敗時0回。正常な完了転送1件は4回の記述子コピー、計80 byte。空のreap poll等は別のAPI invocationとして数える。32 KiBのIQ payloadはこのqueue内ではコピーしない。DMA読出しやpackingのメモリアクセス費用は残る。

## 検証方法

固定SDKのqueue.cから4 APIと2 copy helperの**関数本体をそのまま抽出**してhostでコンパイル。queue set/mutex機能を有効にしたshimで、queue setなし・非mutex・待機list空を設定する。event list操作、queue set通知、task block、yieldへ達したらabortする。4 API×空/満杯の8条件でcritical entry/exitが各1回、コピー回数・20 byte・全byte一致・待機list不変・ISR woken=0を確認した。critical操作そのものは逐次shimであり、spinlock競合を再現していない。host時間は測らない。

ELFのSHA-256を前回の実バイナリ監査と一致確認し、DWARFのsize/offsetと保存configを `layout.json` へ出力。既存owner/ISR CASとSDK primitive試験を含め8 unittest成功。8条件を8 unittestと数えてはいない。これらはSDK全体の形式的同値や実XtensaのWCET証明ではない。

保存SDK source hash・API経路の既存14チェックも再実行し、`source-audit.json` に保存した。

## まだ必要な時間根拠

queue critical内から到達するtask起床処理を、この正常経路へ無条件に課金する必要はなくなった。一方、20 byte memcpy、queue bookkeeping、lock acquire/releaseのメモリ待ちと高優先度割込みの上限は未確定。

API ownerはcore0。ISR affinity (0,0)ではこの2 hostのqueueに対するcross-core競合を除外できる。SPI ISRが同じcoreへ集中する干渉は課金する。(0,1)/(1,0)/(1,1)ではcore1に置いたhostのqueueでcross-core競合が残る。配置を採用・変更した結果ではない。

特に「相手のcritical本体が短い」だけでspinlock待ちをその1回分に抑えられるとは限らない。ret_queueが空の間、ownerはreapを繰り返せるため、別coreのISRがret_queueを取得するまでの再取得競合を考慮する必要がある。lockの公平性、相手の再取得間隔、メモリアクセス仲裁等の根拠なしに有限待ち時間へ置き換えない。実機で飢餓が起きる、または別core候補が不可能だという判定でもない。status CASの最大4失敗/最大1失敗は、このqueue spinlockへ流用できない。

次に閉じる対象は、同一core配置でのIRQ干渉を含む時間上限と、別core配置での上記lock取得待ち。H/S/W/Rは依然として数値未確定。RF ABI・全到着列・全FPGA fit/STAも未証明で、性能合格・正式割当・採用は0。

再現:

```sh
python -m ci.s3_spi_queue_layout --output reports/s3-spi-queue-paths/layout.json
PYTHONPATH=tests python -m unittest test_s3_spi_queue_paths test_s3_spi_owner_atomic test_s3_spi_atomic_interference test_s3_spi_isr_rounds test_s3_spi_lock_primitives -v
```
