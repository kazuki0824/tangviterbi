# ② 全SoC計上範囲と受信アプリの処理一覧

2026-10-29。`experiments/s3_raw_tasks.c`、`experiments/s3_raw_probe/main/raw_probe.c`、最新保存SDK設定を照合した。これは実装されている処理と見積もりの構成仮定の対応表であり、最終受信アプリが完成したという認定ではない。

## RF動作中：同じ時刻模型へ接続済みの処理

|処理|発生頻度の定義|計上先|
|---|---|---|
|owner反復・停止フラグ判定・通常WDT期限判定|実行反復ごと1回|OWNER_SHELL。通常判定をWDT追加費用に重ねない|
|worker反復・停止フラグ判定・通常WDT期限判定|実行反復ごと1回|WORKER_SHELL|
|RF状態監視・時計・MMIO読出し|成功owner反復ごと7回。拒否した反復はそこまでの実回数|RF_BASE|
|次bank準備の判定と実書込み|未prepared pollごと、実fill span/語数ごと|RF_PREPARE差分＋FILL|
|RF bank切替・受渡し・境界探索|実状態遷移ごと|RF_SWITCH/RF_ACCEPT差分|
|可逆packing・empty走査|各coreの実slice、run、block、slow pair数|PACK_*。pairごとにslice費用を重ねない|
|bank完了回収と送信可能prefix公開|owner反復ごと1回、owned数別|COLLECT|
|各SPIの完了確認・prefix退役|active時だけ1回/port訪問|REAP_RUNNINGまたはREAP_DONE|
|各SPIのtake・queue登録|inactive時だけ1回/port訪問|SUBMIT_EMPTYまたはSUBMIT_DONE|
|SPI開始/完了IRQ|開始、線上完了ごと。初回開始は別単価|SPI_IRQ。線上DMA時間はCPUへ加算しない|
|tick・IWDT callback・USB hook仮定・同task再選択|各core100Hz、通常1tick/IRQの仮定|TICK_IRQ。IRQ入口復帰と通常peer lock待ちを包含|
|受信task WDT更新|各core、更新前の読取時刻＋2.5秒を初めて越える反復|WDT追加費用。peer reset待ち込み|

回数・回/s・費用は [最新費用台帳](../s3-receiver-cost-ledger/runtime.json) と [順序比較](../s3-owner-order-estimate/results.json) の同じ実行から得る。S側の失敗までの短い実行から、2.5秒WDTの定常発生を0回/sとは認定しない。

## RF停止中・境界：呼出し数を整理した処理

次の処理はRF動作中の反復費用へ一律に足す対象ではない。ただし、選局完了時間・起動時間・停止時間を見積もる場合は別途必要である。

|phase|実装で確認した処理|発生回数／頻度|数値費用の状態|
|---|---|---|---|
|起動前|PHY/SPI初期化、storage/pack準備、task runtime init|起動／再初期化ごと。PHY/SPIの呼出し側は未完成|未確定。link-only app_mainは実行しない|
|task生成|worker→ownerのstatic pinned task生成|成功起動ごと各1回。失敗時ownerなしの場合あり|受信中台帳の対象外|
|task起動|core/priority検査、時計初期化、WDT status/add、force feed、ready公開|taskごと。owner/workerとも時計再初期化あり|受信中台帳の対象外|
|peer起動待ち|force feed＋vTaskDelay(1)|whileの実反復数。peer準備到着時刻で決まり固定回数ではない|回数上限未確定。RFはOFF|
|RF開始境界|WDT idle監視解除、native開始、run公開|成功起動ごと1回|受信中の通常WDT resetとは別|
|worker開始gate|run確認＋通常feed判定|ready=2以後、run公開までの反復数|RF開始境界の差分が必要。受信定常反復と混同しない|
|停止要求・故障|stop/fault公開、RF停止|停止事象ごと|停止指令の受信経路は未実装。故障正常化費用も未確定|
|peer停止待ち|force feed＋vTaskDelay(1)|workerのstopped公開までの反復数|無限待ちを打ち切る実装はない。根拠なく有限上限を置かない|
|送信終了処理|active portのreap、idle WDT設定復元、WDT delete、stopped公開、task delete|各port最大1回のreap、taskごとdelete。TIMEOUT時lease保持|DMA drain/resetはsupervisorの責任で、呼出し側は未完成|

これらを「起動時1回」にまとめるとpeer待ちの反復とforce feedを落とす。逆に、RF停止中の待ちを受信中CPU%へ常時加算すると二重計上／phase混同になる。再選局には旧epochの停止・lease排出・新epochの初期化順序が必要で、現在のコードにはその全supervisorはない。

## SDK／指令側：構成仮定のまま残る処理

最新保存 `reports/s3-spi-running-guard/sdk-S/image/sdkconfig.json.gz` の設定は、100Hz tick、5秒TWDT、PM無効、USB Serial/JTAG secondary console有効、Wi-Fiコンポーネント有効である。**コンポーネント有効は受信中のWi-Fi task活動を意味しないし、link-only probeは活動がない証明にもならない。**

- `s3_raw_tasks_launch` は `priority[2]` をそのまま受け取る。同優先度は今回の模型条件で、launcherが固定している事実ではない。
- idle、IPC、esp_timer／FreeRTOS timer、USB／console、PHY／Wi-Fi関連のtask・IRQは、生成済みか、blockedか、受信中に起床するかを分けて確定する必要がある。現在のprobeでは最終登録・到来制約を確認できない。通常tickに含めたhookをもう一度加算してはいけない。
- FPGAからの選局・停止・電源等の指令は許可された通信であるが、受信／解釈／supervisorの実装と到来上限がない。帯域予約0.01 MB/sをCPU費用・指令回数に読み替えてはいけない。1指令の長さ・burst上限・処理単価が別に必要。
- window例外、ハードウェア待ち、メモリ競合は追加taskではなく上表の各処理内の追加時間である。既に課した命令費用と通常lock待ちを除いた差分だけを足す。

## 指定2点の完了判定

受信中の宣言構成について、イベント台帳と期限模型は接続済み。今回、順序24通りの比較も追加した。一方、全SoCの未計上解消は未完了である。未実装の制御経路と最終SDK活動を「0」と置いて全費用確定とは報告しない。実機がないことだけが未完了理由ではなく、最終受信アプリの構成・実装自体も不足している。
