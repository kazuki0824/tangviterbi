# ② raw task起動・停止の実装と、時間保証との境界

2026-10-26。前回ec7a8a2の6 workflowはすべて成功。receiver functional closure（40240765473）も成功し、unicorn不足とbuffered stdoutによる成果物生成エラーは解消した。①は変更しない。

## 実装した担当と起動順序

`experiments/s3_raw_tasks.c`に実FreeRTOS task entryを追加した。外側のboard launcherがPHY/SPI・新規pack/bufferを初期化し、2個の静的taskをcore0/1へ固定して起動する契約。rate、epoch、slice長、各workerの時間bound、現在のTWDT設定をcallerが与える。未測定のboundをdefault値として埋めていない。SDK link probeはentry/state/初期化関数を保持するが、app_mainは実行しない。

- core0: RF poll、worker0、collect、2 portのreap/submit。各処理の間へRF pollを置く。有限sliceを使い、受信中にtick-sized delayを入れない。
- core1: worker1。payload所有権のtake/completeはcore0だけが操作する。
- 両taskが校正・watchdog登録を終え、core1が全tick待機を抜けたready=2をrelease公開する。core0はacquire確認後にだけRF開始へ進む。
- 起動待機でidleが動いた後のCCOUNT連続性を仮定しないよう、両coreとも最後のtick待機後に再校正する。その後は停止までtick待機をしない。実行coreの一致と、校正誤差幅E < worker boundも確認する。
- core0のRF開始成功をrun flagで公開する。core1はready=2以降、このflagをtick睡眠せず待つ。ready=1だけでは起動しない。

起動中はRF停止状態でtick待機できるが、core1がその待機から戻る前にRFを開始すると最大1tick=10ms遅れる。Sのbank期限に収まらないため、上記ready=2 handshakeは必要。強制的にpeerをその待機へ留める試験で、RFが先に始まらないことを確認した。

## watchdogの扱い

固定SDKのtask_wdt.cではSMP時のidle監視がuser entryであり、idle task handleをesp_task_wdt_deleteする方法では解除できない。公開 `esp_task_wdt_reconfigure` によりidle_core_maskを0にする。両receiver taskを先にTWDT登録し、timeout_ms/trigger_panicと他の登録task/userは維持する。受信中のwatchdog監視を無効化しない（reconfigure内部のtimer停止・再開はRF開始前/停止後に行う）。設定変更はcore0だけが行う。

callerがTWDT設定の唯一の管理者であり、渡す設定が現在の実設定と一致することが前提。公開getterは使っておらず、SDK defaultを実設定と推定しない。他コードによる並行reconfigureを許す実装ではない。

受信中のfeed間隔は渡されたtimeoutの半分。これはTWDT期限から導いた間隔でありRF処理の時間保証ではない。feed自身のSDK lock/entry走査費用もRF gapへ計上する必要がある。起動・停止待機では毎回feedする。WDTが発報してもDMA所有権が解消するとは扱わない。

## 停止・異常

各coreが自分の処理失敗をstopへ公開する。core0はRFを止めてからpeerのstoppedを待つ。worker1はpackingを抜けた後にのみstoppedを公開する。peerが止まらなければ任意timeoutで安全なreuseへ進まず、監視された待機のままとする。

peer停止後、SPIは各portを1回nonblocking reapする。未完了/異常ならactive/leaseを保持する。idle監視を元の設定へ戻し、各task自身のTWDT登録を解除してtaskを削除する。stopped flagだけではDMA完了やtask stack回収完了ではない。外側supervisorはtask削除とDMAのdrain/resetを確認するまでstorageを再初期化してはいけない。正常停止時に未送信IQを最後までTSへ流す機能も、この停止処理の保証には含まない。

## 試験と限界

host-tests.log。実task entryを2 pthreadで走らせ、SDK/RF/packing/SPI calleeをmockしたlifecycle試験を追加した。通常停止、最後のtick待機にいるpeer、校正失敗、TWDT登録失敗、SPI失敗とDMA未完了保持を確認。既存の実native/packing出力一致試験も実行した。lifecycle試験を実RF/SDKの時間検証とはしない。

実task entryができたことと、すべての処理が期限内に終わることは別。IRQ affinity4候補、task priority、各slice/API/clock/watchdog/IRQ/memory競合のWCETと連続入力response timeは未確定。起動前のcallerによるboard設定と、停止後のsupervisorも別途必要。静的task生成は下記の起動処理で追加した。SDK placement、増分state/コード、TWDT entryの動的確保は新ELFで確認する。全受信機の採用は依然0。

## 新SDKでの配置・容量検算

[675025c SDK CI 40248353257](https://github.com/kazuki0824/tangviterbi/actions/runs/40248353257)成功。共通49/raw専用54 static check、成果物のELF/source/配置/型情報13checkが成功。artifact12619727361のZIP SHA256は `d5c15a0dbee861fcd25ee6c4f3db67b785199c9832efeb59d716e61665cb07b7`。sdk以下にELF/map/config/logを保存。

runtime state184 B、2task引数16 B、entry code1302 B（IRAM）。raw専用heap開始は0x3fcac780→0x3fcace58、整列込み1752 B増。比較用の旧時計state/entryも保持したprobeであり、state200 Bだけを増分として扱わない。

SPI/PHY台帳19checkを新ELFで再実行。fresh vectorsで既知費用控除後の残量上限はSPI15408 B、PHY校正13412 B、定常15284 B。この台帳はTWDT全費用を含まず、利用可能heapの保証ではない。

TWDTのDWARF実サイズはentry16 B、object16 B。4 B/割当ての最小header込みで、receiver2taskのentryは最低40 B、idle2＋receiver2の起動切替時は最低80 B、watchdog objectは最低20 B。既存watchdog IRQ handle/vector、他の登録entry、allocator丸め・断片化は別。callocが全て内部RAMへ配置される保証もないため、これを無条件に内部残量から引いた値を全構成共通の上限としては示さない（sdk-evidence.json）。

停止前cancel、校正誤差幅がbound以上、idle priority、既存TWDT登録のtask終了時解除を追加し、lifecycleは合計9条件。extended-tests.logに保存した。未送信データの完走・実機時間・cache-off実行を保証する試験ではない。

## CPU費用へ追加すべき実呼出し

正常なowner_iterationはworker0 slice1回、collect1回、最大reap2回/submit2回、RF poll7回、feed判定1回。feed判定は毎回CCOUNTを読むが、SDK TWDT resetはtimeout/2到達時だけ呼ぶ。worker1はslice1回＋feed判定1回。空jobの場合の反復回数はslice成功数だけでは求まらず、busy pollingのCPU/共有メモリ負荷を除外してはいけない。

通常native pollを2clock readの経路とした場合、owner反復はnative14＋worker2＋collect1＋feed1=18 clock read、worker1反復はworker2＋feed1=3。native経路により回数は変わる。旧集計のworker2readだけを新task全体の時計費用として使わない。7回のpollを挟んだこと自体も、各gapがS50µs/T125µs以下であるという証拠ではない。

TWDT resetには共有spinlockと登録entryの走査がある。割込み/critical-section/他coreの到来条件・entry数と費用を含めた上限はまだ得ていない。taskの呼出し順序は実装できたが、その数値上限を創作して性能合格にはしない。現在の固定SDK構成と実core割当てを用いた応答時間評価へ引き継ぐ。

## 静的task生成と部分失敗（今回の追加）

`s3_raw_tasks_launch` はcallerが初期化したruntimeと、永続する起動state、stack/TCB、priorityを受け取る。worker1を先に生成し、その後owner0を生成する。ownerを先に生成してpeer生成に失敗すると、停止時に存在しないpeerを待つため、この順序には停止手順上の意味がある。

- worker生成失敗：ownerは作らずstop/faultを記録する。
- owner生成失敗：生成済みworkerへstopを公開する。workerはRF開始前に自分でTWDT登録を解除して終了する。返値falseでもworkerの削除完了までは起動state/stack/TCBを保持する。
- 両方成功：trueは2task生成成功だけを表す。RF開始・期限達成・受信成立の成功ではない。
- 一度試行した起動stateによる再起動を拒否する。停止済みflagを未生成taskに偽装せず、handlesで生成の有無を区別する。

callerは単独のsupervisorであること、storageが有効な重ならない内部RAMでありstartup用途から回収済みであること、runtime初期化とPHY/SPI設定が済んでいることが前提。stackの4096 Bは従来probeの予約量であり、実測済みstack boundではない。priorityもcaller指定で、上限内・idleより大きいことを確認するだけで時間保証はしない。

link probeの休眠ダミーtask生成をこの実起動処理の保持に置き換えた。app_mainからは呼ばない。新レイアウトのSDK検証はCI結果で確認する必要があり、上記675025cの容量値を新変更の値として流用しない。

`launcher-tests.log`：実launcher＋実task entryのhost試験で最初/2個目の生成失敗、生成成功、生成順序、重複起動拒否、priority範囲を確認。既存の時計・native/packing試験を含む7 unittest成功。SDK APIはmockであり、実機task生成・メモリ空き・WCETの証明ではない。

前実装675025cの6 workflowはすべて成功を確認した。今回の変更のCI結果とは区別する。
