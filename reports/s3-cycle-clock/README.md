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
|割込み|SPI ISRの明示割当て候補、tick等を費用計上|tick、IPC等を費用計上|

現行packingは等分。core1が単独でSPI APIを操作するとcoordinator専有のtake/completeと競合するため、所有権設計を変えずにSPIだけcore1へ移す候補は使わない。IRQのaffinity・最大実行時間は実起動設定で確定させる必要がある。IRQを無効化して負荷を無料にはしない。

coordinatorではRF pollを優先し、packingを有限sliceに区切る。collect、SPI reap/submitはpollの間へ分散する。SDK queue/reapの待ちtick=0は、API全体のCPU/critical-section時間が0または既知の上限という意味ではない。raw bulkはpolling-start経路を使わない。SPI等のblocking初期化はRF開始前に完了させる。worker1の空job pollingもCPU・memory trafficに含める。

## 前回CI失敗の確認と修正

production/audit commit d454dbdではSDK配置、raw startup、actual linker-map、RF共存、host FFTの5 workflowは成功。receiver functional closureのnew-componentsだけ失敗。218 testは `OK (skipped=1)` で終了し、成果物生成の `log.rstrip().endswith('OK')` が拒否していた。skipはunicorn不足によるTLSF32 replay。加えてPython stdoutのbufferingにより試験中のprintが最終summaryより後に出力されていた。

workflowに固定 `unicorn==2.1.4` を追加し、unittestを `python3 -u` で実行する。skipや失敗を許容するよう監査を緩めず、全試験を実行し、stdout/stderrを発生順に記録する。該当TLSF32の6試験はローカルで成功。

## 検証

新adapterは実CをSDK readだけmockして検証。240位相×81校正delay×3採時位置×2counter位置の116640ケースで誤差区間を検査し、独立core offset、32-bit wrap、64-bit overflow、異常校正を確認。実wrapperの受信中読取りでesp_timer_get_timeが呼ばれないことも確認。host合成時刻であり、実機WCETではない。

SDK CIの結果とsource/ELF照合は後続の節に記録する。校正誤差幅の実機値、固定周波数/IRQ条件、RF polling/packing/SPIを合わせた期限保証、FPGA全体のfit/STAは未完。採用件数は増やさない。

## 開始位相とcore別の必要条件を数値化

再現scriptは `experiments/s3_raw_schedule_limits.py`、結果はschedule-limits.json。nativeの定数を実sourceから読む。次の式は、連続RF/index模型と、通常INDEX観測間隔Dの上限が成立するときの**条件付き位相計算**である。通常gapはclock、worker slice、API、IRQ、MMIOを含む実経過時間。prep追加時間Pは通常gapへ追加されるreclaim/fill等の時間。

次bankがまだ利用不能だった最後の観測は `written <= G-1`。`G=12288-floor(20000/cpp)-1024-2000`。次の準備開始側の観測までD、準備後の次INDEXまでP+Dとすると:

`G-1 + ceil(D/cpp) + ceil((P+D)/cpp) <= 14288`

初回準備側にも同じ開始位相上限が必要。最初のaccept/settlingが長引く場合をこの式だけで証明したことにはしない。INDEX→SELECTの遅延とRF境界検出の妥当性も別条件。

|項目|T|S|
|---|---:|---:|
|通常INDEX gapの必要上限 D|125 µs|50 µs|
|unavailableで停止するwritten G|7931|5931|
|上記Dで許される準備追加時間Pの上限|147.375 µs|108.950 µs|
|旧SDK fill 21574命令を1命令/cycleと仮定した参考値|89.892 µs|89.892 µs|
|その参考値を引いた残額（未測定費用に使えると保証しない）|57.483 µs|19.058 µs|

これにより「Sのfillが50µsを超えるので即不可」とは言えず、開始位相を制御すれば許容範囲があることが分かる。一方、19.058µsに収まると確認できていないbus待ち等を0にはしない。整数丸め込みの境界と、1cycle超過で上限を破ることを3 unittest内で検査。

公称12288sample/bank、512pair/sliceの等分なら1workerあたり6slice/bank。bank周期はT768µs、S307.2µs。旧fill理想費用とAPI仮定20µs/32KiBだけをcore0へ計上した場合、その他費用控除**前**の1slice平均上限はT109.893µs/S33.093µs。core1はT128µs/S51.2µs。これらはclockを含むslice全体の必要上限で、保証された余裕・実WCET・全位相のresponse-time boundではない。core0では平均条件と通常gap条件の両方を満たす必要がある。非公称bank長・初回bank・burst・SPI回収遅延は別途時系列へ含める。

## SDK設定から分かった追加の実行条件

保存済みd454dbdのsdkconfigはCPU240MHz、PM無効、2core、tick100Hz。これだけでCPUの停止/CCOUNT再設定がないとは保証しない。また両idle taskのwatchdog監視が有効、timeout5秒。高priorityの2taskを常時readyにするとidleを実行できず、`taskYIELD`だけでも低priority idleへの時間は保証しない。一方、単純な1tickのblockは10msでRFの50/125µs上限を超える。

従って、実task化にはidleを動かせる短い待機/再開方式とその最悪遅延を設計するか、専用coreの監視対象を実receiver taskへ移すwatchdog設計が必要。今回はwatchdogを無効化したり、未検証のwake-up timerを導入して成立扱いにしていない。IRQ/IPC/driver critical-sectionの時間、source/payload SRAMとDMAの競合も残る。

## 実native/packingへの接続試験

既存capture harnessへ4番目のclock modeとして追加した。nativeとworker0は専有state0、worker1は異なるoffset/誤差幅のstate1を使う。T/S、正常/worker停止の4追加条件で、正常80banksずつの全送信byteが独立期待値と一致し、worker停止は2banksでRF停止となった。SDK時計とCCOUNTは合成で、fill/packingの実時間は加算しない。したがってepoch・誤差幅・所有権の接続試験であり実スケジュール成立の試験ではない（native-tests.log）。

### SPI割込みの4通りの割当て

固定SDKのspi_bus_config_tには `isr_cpu_id` があり、現adapterのopen_portはcallerからの値を保持してspi_bus_initializeへ渡す。したがってAPI所有者core0を維持したまま、SPI2/SPI3 ISRを `(0,0), (0,1), (1,0), (1,1)` の4通りで評価できる。初期化coreだけで固定される、と限定しない。一般にcore1へISRを寄せる案はcore0のRF pollを妨げにくいが、worker1遅延とcross-core wakeup/IPI等が増える可能性があるため、両ISRをcore1へ置けば必ず有利とはしていない。

core別の式では、各portのtransaction頻度×ISR費用を割当て先へ加え、cross-core起床/共有bus-lock費用も別計上する。必要なISR費用と最大到来頻度が未確定のため、4候補のうち性能合格を出したものはまだない。比較元ヘッダとSHA256を保存した。

## 新SDK binaryの確認

[raw-only SPI CI 40239861135](https://github.com/kazuki0824/tangviterbi/actions/runs/40239861135)はcommit32777e444e60856906344902f3cc36f2a7a17db3で成功。共通47/raw専用52のstatic checkが全て成功。artifact12616276633のZIP SHA256は `a3eb3fec5fc2775d2e22b08bd774882856a3c6843ba8ad5c86f48bc0192edd2f`。sdk以下へELF/map/config/build logを保存。

`ci/s3_cycle_clock_sdk_audit.py`でELF/source hash、240MHz/PM無効/2core、state配置、実到達CFGを再検算した。**受信中readは63bytes、到達26命令、最長経路21命令、CCOUNT読取り1回、callなし、CFG cycleなし、hardware loopなし**。advanceはcompilerがinline化しており、消えたsymbolを無理に要求せず、実際の保持entryとその命令列を監査する。初期化側はliteralの実値も照合し、SDK時刻→CCOUNT→SDK時刻→CCOUNT→SDK時刻の観測順を確認した。14check成功。線形objdumpのpadding誤decodeを避けるため分岐先から再decodeしている。

この結果で、受信中SYSTIMER待ち/retryという未確定要因を含まない具体案が得られた。21命令を21cyclesとは置かない。memory/pipeline/IRQ/window exception費用は含めていない。clockの校正/連続動作前提も実機確認が必要で、receiver採用判定は変えない。

2stateは内部RAM48bytes。両時計方式を保持した比較probeではIRAM末尾0x40387a00、heap開始0x3fcac780となり、前版からheap開始が304bytes進んだ。state48bytesだけの増分とは扱わない。メモリ台帳19checkと限定ISR配置26checkが成功。fresh vectorsでの残量**上限**はSPI17160 B、PHY校正15164 B、定常17036 B。断片化を含む実機空きheapの保証ではない。

## まだ必要な実task化

校正は各stateを使用するcore自身で、RF停止中に行う。両coreの校正完了をrelease/acquire等で確認し、観測したEが採用scheduleのboundに収まることを確認してからRF開始する。この起動handshakeと実task loopは今回のlink probeには実装していない。現probeの2taskは引き続き休眠用で、今回のclock candidateを実受信で使ったとは報告しない。

残作業は、(1) IRQの4候補とidle/watchdogを含む実task起動/停止条件の確定、(2) 有限sliceとRF/APIを交互実行したときの全経路費用・応答時間、(3) RF ABIとDMA競合下の実機連続受信。clock readの構造的な無制限retryは候補側で除去できたが、これらを代替する証拠ではない。
