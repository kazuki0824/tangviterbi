# ② core割当てと、受信中のSYSTIMER待ちを除く共通時計候補

2026-10-26。前回の手順2と、それに必要な手順3の条件整理。①は変更しない。

## 時計候補の実装

`experiments/s3_cycle_clock.c` は受信前にSDK時刻と各coreのCCOUNTを対応付け、受信中はCCOUNTだけを読む。固定SDKの `esp_cpu_get_cycle_count` はCPU毎のcycle counterを読む。同期のための共有spinlock、SYSTIMER UPDATE/VALID待ち、整合性retryを受信中に追加しない。旧SYSTIMER adapterを置換・採用済みとはしない。link probeには比較用の関数と2core分のstateを保持するが、RFもtaskも開始しない。

校正の順序は `timer_before, c0, timer_sample, c1, timer_after`。前後のSDK時刻の区間幅が2^32 cycles未満であることを確認してから `d=(uint32_t)(c1-c0)` とする。sampleの整数µsをqとすると、c1時点の上端は `(q+1)*240+d`、誤差幅は `E=240+d`。採時がc0とc1の間なら、実時刻は必ず `[U-E,U]` に入る。その後はCCOUNT差分をUに加算する。受信中に再校正してepochを飛ばしてはいけない。

校正が長引くとEも大きくなり、worker boundやnative期限の余裕を使う。校正に成功しただけで性能合格にはしない。前後SDK時刻の逆行・負値・長すぎる区間・差分の矛盾・overflowは拒否する。

前提は両coreが校正から停止まで240 MHzで連続動作し、CCOUNTを再設定しないこと。stateはcore固定の単一caller専有とし、そのcoreのRF/worker呼出しでは同じstateを使う。ISRや他coreとstateを共有しない。各読取り間隔は2^32 cycles未満（約17.8957秒）とする。CCOUNTだけでは丸一周以上の見落としを検出できないため、これは明記した実行条件でありfail-safe保証ではない。CPU周波数変更、sleep、debug haltを許す設計にはそのまま使えない。

SYSTIMERの起動前校正の所要時間は未確定だが、RFは校正終了・誤差幅の受入れまで起動しない。受信中の関数にloopがないことと、割込み・メモリ待ち込みのWCETが確定することは異なる。

## core/IRQの割当て候補

|担当|core0 coordinator|core1 worker|
|---|---|---|
|RF|native poll、bank準備、accept/collect/reclaim、選局制御|なし|
|packing|worker ID0、有限pair slice|worker ID1、有限pair slice|
|SPI|2 portのsubmit/reap、queue_size=1、期限内にpollへ戻る|なし|
|時計|専有state0をRF/worker0が順次使用|専有state1をworker1だけが使用|
|割込み|SPIを初期化したcoreの割込み、tick等を費用計上|tick、IPC等を費用計上|

現行packingは等分。core1が単独でSPI APIを操作するとcoordinator専有のtake/completeと競合するため、所有権設計を変えずにSPIだけcore1へ移す候補は使わない。IRQのaffinity・最大実行時間は実起動設定で確定させる必要がある。IRQを無効化して負荷を無料にはしない。

coordinatorではRF pollを優先し、packingを有限sliceに区切る。collect、SPI reap/submitはpollの間へ分散する。SDK queue/reapの待ちtick=0は、API全体のCPU/critical-section時間が0または既知の上限という意味ではない。起動時bus acquireはRF開始前に行う。worker1の空job pollingもCPU・memory trafficに含める。

## 前回CI失敗の確認と修正

production/audit commit d454dbdではSDK配置、raw startup、actual linker-map、RF共存、host FFTの5 workflowは成功。receiver functional closureのnew-componentsだけ失敗。218 testは `OK (skipped=1)` で終了し、成果物生成の `log.rstrip().endswith('OK')` が拒否していた。skipはunicorn不足によるTLSF32 replay。加えてPython stdoutのbufferingにより試験中のprintが最終summaryより後に出力されていた。

workflowに固定 `unicorn==2.1.4` を追加し、unittestを `python3 -u` で実行する。skipや失敗を許容するよう監査を緩めず、全試験を実行し、stdout/stderrを発生順に記録する。該当TLSF32の6試験はローカルで成功。

## 検証

新adapterは実CをSDK readだけmockして検証。240位相×81校正delay×3採時位置×2counter位置の116640ケースで誤差区間を検査し、独立core offset、32-bit wrap、64-bit overflow、異常校正を確認。実wrapperの受信中読取りでesp_timer_get_timeが呼ばれないことも確認。host合成時刻であり、実機WCETではない。

SDK CIの結果とsource/ELF照合は後続の節に記録する。校正誤差幅の実機値、固定周波数/IRQ条件、RF polling/packing/SPIを合わせた期限保証、FPGA全体のfit/STAは未完。採用件数は増やさない。
