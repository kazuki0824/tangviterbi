# ② S側：先行queueを接続した受信taskの費用・期限

2026-10-30 JST。S5/16、可逆inline packing、16KiB、SPI2 Octal＋SPI3 Quad、準備2048語/反復・1024語/poll。①は対象外。

## 実コードの接続

既存task lifecycleから [変換器](../../experiments/s3_queue_tasks_source.py) で候補C/headerを生成する。SDKとhost検査は同じ生成物を使い、SDK成果物中のソースと現在の生成物の完全一致も検査する。元の単一転送taskは変更しない。

起動検査をqueueのdevice・pack・host・未使用状態へ変更し、ownerはcount>0で回収、count<2で投入する。停止時は各port最大2件を回収するが、TIMEOUT/faultでは所有権を保持する。実装には1poll最大1024語の制限を追加し、反復合計2048語という模型の配分と揃えた。未消費語数を次のpollへ持ち越す。単に旧定数1024を2048へ変更するだけの実装は採用しない。

[SDK run 40915522463](https://github.com/kazuki0824/tangviterbi/actions/runs/40915522463) は成功。入力commit・artifact hashは [provenance](sdk/provenance.json)。これは受信taskを保持したlink probeであり、app_mainはRFを開始しない。

## 単価と重複の整理

|項目|生成コードの包絡|使用単価|範囲|
|---|---:|---:|---|
|owner制御|333命令/反復|367 cycle|7pollの制御、collect前の時計、通常feed判定、port順序・条件分岐を包含|
|うちpoll制御|23命令×7|owner内に包含|1024語上限・消費語数の差引き・stop/fault判定。native本体は別|
|worker制御|56命令/反復|62 cycle|通常feed・stop判定。packingは別|
|RF基本処理|既存179命令/poll|197 cycle|従来213cycleに含めたpollラッパ14命令を除き、ownerとの重複を解消|
|期限到来時のWDT追加|通常feedとの差分＋peer reset待ち|516 cycle|通常判定はowner/workerに含むため再加算しない|

命令数×1.1を切上げる費用模型。[命令・CFG経路・加算先](instructions.json)。SDK投入/回収・割込み、inline slice、native各状態、collect、tickの既存単価は維持し、owner追加0/100/300cycleという仮置きは使用しない。実ownerの2port forループを模型へ接続し、並べ替えた擬似ownerを使わない。

## 同じ費用での期限評価

[全条件・頻度・費用台帳](runtime.json)。追加stallなしの20000bank（6.164秒）で出力byte照合と費用保存が成立した。

|観測項目|結果|
|---|---:|
|arena最大使用|123328 / 131072 byte|
|arena最小残量|7744 byte|
|RF監視最大間隔|68.208 µs|
|job期限余裕の最小値|187.808 µs|
|owner反復 / RF poll|180215 / 1261505（7倍）|
|worker反復|1889725|
|tick|各core616回|
|WDT更新|各core2回|
|SPI IRQ：初回 / 開始 / 完了 / 連続|2 / 14447 / 14447 / 23171回|

20000bankは以前の比較と同じ観測長で、2.5秒周期のWDT更新を複数回含める。観測した最大値・最小値であり、無期限の境界値を保証するものではない。

追加stall感度は `joint_charge` の課金に0/1/2/5/10/15/20/30%を追加する。非同期IRQ/tickの直接加算部分は増やさないため、「すべての未計上処理を15%以内と確認した」という意味ではない。0〜15%の評価点は4000bank通過、20%は67bankで次の受入れ148731byteが128KiBを超過、30%は5bankでpacking期限違反。実機stall率の範囲を推定した結果ではない。

## 未確定範囲

今回閉じたのはqueue接続後の正常受信ループ制御費用と同じ費用による有限期限評価。RF-off起動/peer待ち/再選局/停止の時間、指令入力とsupervisor、register-window例外、メモリ/MMIO待ち・競合、最終task/IRQ構成は残る。生成taskの存在を完成した受信アプリとは扱わない。全SoC費用確定・実機成立認定は未完了。

再現：`python -m ci.s3_queue_owner_audit --toolchain <xtensa-esp-elf>`、`python -m experiments.s3_queue_owner_runtime`、`python -m unittest tests.test_s3_queue_tasks`。

## task・queue・RF領域をまとめたメモリ検査

[SDK run 40917626944](https://github.com/kazuki0824/tangviterbi/actions/runs/40917626944) でN16R8構成をlinkし、[配置・割当検算](memory.json)を実施した。128KiB転送領域、RF領域、2taskのstack/TCBを同じELFに保持し、ROMとの非重複と配置条件を通過。費用probeとこのELFの8関数について、再配置アドレスを除いた命令・分岐の完全一致を確認した。

queue深さ2で、既知SPI割当の下限は2port合計1584byte。その差引き後の内部メモリ容量の**上限は16820byte**。GDMA channel/group/pair、lock、interrupt handle、allocator header/alignment、PHY/calibration等は未計上なので、実際の空き容量・起動保証ではない。固定task stackは各4096byteを配置したが最大stack使用量は未確定。構成定数はCMakeと生成header、stack引数は実際のcreate_tasks命令から確認した。

再現：`python -m ci.s3_queue_memory_audit --rom <esp32s3_rev0_rom.elf> --toolchain <xtensa-esp-elf>`。保存したELFと入力commitは [provenance](memory-sdk/provenance.json)。回帰検査結果は [tests.log](tests.log)。

検証結果：73 tests成功。全イベントの回数・各core課金時刻を分母とした回/sは [統合JSON](../receiver-integrated-estimate/estimate.json) の `queue_connected_owner_candidate.event_rates_per_core_accounted_horizon` に収録。最後の課金が観測停止時刻を越える場合を混同しないため、core別の課金終端を分母にする。

## 2026-10-30：GDMA・lock・IRQの未計上常駐割当を追加

[再計算](allocations.json)、[SDKソースとSHA-256](allocation-sdk/sources.json)、[検査ログ](allocations-tests.log)。SDK v5.5.1の割当箇所と、保存済みN16R8 ELFのDWARF型サイズを照合した。次は2port全体の常駐要求量であり、allocator overheadを含まない。

|追加対象|target sizeof|個数|合計byte|
|---|---:|---:|---:|
|GDMA TX channel|52|2|104|
|GDMA RX channel|56|2|112|
|GDMA pair|28|2|56|
|GDMA group|136|1|136|
|SPI bus lock|64|2|128|
|SPI device lock|12|2|24|
|device lock semaphore|84|2|168|
|SPI interrupt handle|8|2|16|
|非共有interrupt vector descriptor|12|2|24|
|追加合計|||768|

既知SPI/GDMA常駐割当の下限は1584→**2352byte**、差引き後の内部メモリ容量上限は16820→**16052byte**。これは未計上分を足した見積もりの訂正であり、実装の使用量が増える変更ではない。GDMA groupは共有の1個だけを計上する。別subsystemが先に生成した場合も、同じgroup/vectorをそちらで重ねて課金してはならない。

発生phaseはRF停止中の初期化で、受信中は保持し終了時に解放する。bank/transferごとのmalloc費用に読み替えない。2portを空のGDMA状態から順次初期化する場合、TX/RX確保各2回、group確保2回（1回は既存確認後解放）、pair確保3回（1回は既存確認後解放）。group136byteとpair28byteの一時確保は別の時点に発生する。最終常駐量に両方を足して起動peakとはしない。

正常送信でのDMA用一時payload割当は0回/transfer。adapterはMANUAL alignment flagを付け、DMA領域を検査し、rx_bufferをNULLに保つ。SDKは不適合TX bufferを発見してもこのflagでerrorを返し、代替bufferを確保しない。この分岐の費用は既存submit費用に含み、今回さらに加算しない。

適用条件はSPI IRQが非共有・trace wrapperなし、2bus各1device、同じSDK設定である。**現adapterは呼出し側のintr_flags/isr_cpu_idを引き継ぐため、受信候補専用の `s3_queue_receiver_open` は非共有・level1・IRAM・core0を固定する。最終launcherはこの入口を使う必要がある。** 本検算だけでその設定を実装済みとはしない。PHY/calibration、allocator overhead/fragmentation、制御処理の資源、初期化のCPU費用・所要時間は未確定。旧16820byteは今回以前の上限として残す。

再現：`python -m ci.s3_queue_allocation_audit`、`python -m unittest tests.test_s3_queue_allocations`。pyelftoolsが必要。SDKソースはCIのimage tagと対応する公開版で、target ABIサイズは実際の保存ELFから抽出した。

## PHY・allocator・TWDTを含めた寿命別再検算

[寿命別台帳](lifetime-memory.json)は過去の `ci/s3_runtime_memory_audit.py` を再利用し、転送長32768→16384、queue長1→2だけを変更した。同じ保存ELFの型サイズを再抽出し、今回の2352byteと一致することを照合した。再取得したSDKソースは過去の固定commitのSHA-256にも一致する。

|phase（fresh vector）|SPI/PHY要求量|最小割当header|TWDT前の残量上限|既知TWDTが全て内部RAMの場合の残量上限|
|---|---:|---:|---:|---:|
|SPI初期化後|2352|132|15520|15432|
|PHY校正中|4340|140|13524|13436|
|校正後・定常|2468|140|15396|15308|

単位byte。残量はDMA pool管理領域400byteも控除する。4096byteのpool本体は再利用可能なので二重控除しない。PHY mutex84byte、校正一時1904byte、校正後PLL timer32byteは寿命を分ける。TWDT16byte object/entryとIRQの最小管理費を再計上し、startupのidle登録と受信task登録が重なるphaseも別表に保存した。TWDT callocは内部優先だがPSRAM fallback可能なため、常に内部RAMと断定しない。強制internalなTWDT IRQだけを引く定常残量上限は15368byte。登録追加M件、PHY binary内部、断片化・追加allocator費用等は未確定。

## 費用模型とIRQ設定の接続

[受信専用初期化](../../experiments/s3_queue_receiver_open.c)はpin設定をコピーし、SPI IRQのcore0・level1・非共有・IRAMを強制して既存queueを開く。RF停止中の呼出しであり、通常submit/reapへ追加費用はない。callerのpin設定を変更せず、エラーをそのまま返すことをhost検査した。[SDK run 40979624053](https://github.com/kazuki0824/tangviterbi/actions/runs/40979624053)も成功。コンパイルは [保存build log](irq-sdk/build.log.gz)で確認できる。objectの保存指定は当該runでは一致しなかったため、objectを確認済みとは扱わない。最終board launcherはまだ未完成である。

## 受信中のPHY追従処理

[SDK設定・実バイナリの監査](phy-periodic.json)、[逆アセンブル](phy-periodic.dis)。PLL timerは有効、1000ms周期、esp_timer taskはcore0。`phy_track_pll_timer_callback → phy_param_track_tot → rfpll_cap_track → wait_hw_freq_busy` という条件付き経路を確認した。最後は0x6000e168のbit31が落ちるまで戻るループで、ソフトウェアの回数上限はない。一度busyを観測すると解除後50µs待つ。これは毎回その経路を通る証明ではなく、有限WCETにするには経路条件とhardware解除時間の根拠が必要という結果である。

1Hzはrelease頻度であり、遅延callbackのまとめ実行まで1秒1回に制限するものではない。旧20000bank通過にはこの費用が未計上だった。「全SoC処理の通過」とは扱えない。PLL無効化は行っていない。

[追加周期処理の35条件](periodic-runtime.json)では、timer dispatch/切替/PHY全体をcore0のサービス時間とする仮定で、1秒周期・開始位相5点を20000bankまで評価した。0µsは旧結果と完全一致、10µsは5/5通過、50/100/200/500/1000µsは各0/5。50µsでは2条件がRF切替期限、3条件がpacking slice上限で停止した。未計上処理を平均CPU%に均すだけでは、この単発中断の影響を表せない。サービス時間は感度点で、実PHY費用を測定したものではない。

## 周期処理の配置・packing分担比較

[core1だけへ移動](timer-core1-runtime.json)は、S5/16・slice512・準備2048語で50/100/200/500µs、slice許容20000/40000cycleを各5位相評価したが、全位相を通過する組合せはなかった。

[18設定の探索](periodic-candidates.json)はshare5/6、slice128/256/512、準備2048/3072/4096語を対象にした。core1・50µsから開始し、5位相4000bankを通過した設定のみ代表位相20000bankへ延長、さらに100µsを評価する。1件の失敗が出た設定はそこで棄却した（未実施位相を合格としない）。slice許容40000cycleは、未計測の上限を確定した値ではなく、周期中断を許容する比較条件である。

50µsで残ったのはS6/16・slice512の3設定。代表位相20000bankは次の結果。

|準備語/反復|arena最小残byte|RF監視最大µs|job余裕最小µs|
|---|---:|---:|---:|
|2048|6848|68.208|154.929|
|3072|6900|68.208|157.604|
|4096|7215|68.792|161.458|

3設定とも100µsでは失敗。元のS5/16を単に遅延の少ない例で評価し直したのではなく、同じ周期費用で分担を変更して比較した。ただしtarget命令単価はS5/16・準備2048のものを継承するため、S6/16等の正式採用にはtarget再計数が必要。timer IRQとtaskを丸ごとcore1サービスとする仮定、task優先度、RFへの影響も未解消。実機費用を50µs以下と認定した結果ではない。

S6/16・準備2048語を[さらに62.5/75/87.5µsで比較](periodic-headroom.json)した。62.5µsは5位相4000bankと代表位相20000bankを通過、75/87.5µsは最初の位相で失敗。これは実PHYの所要時間でも全位相の境界値でもない。busyを観測したPLL経路の50µs待ち以外の処理・IRQ・dispatch・busy解除待ちまで合計62.5µs以内に収まるかは未確定である。

今回の追加後は [78 tests成功](allocations-tests.log)。対象は新しい割当台帳・寿命別照合・周期処理の費用保存/発生回数/旧結果一致に加え、既存queue・task・packing・期限の回帰検査。受信全体の実機成功を示す検査ではない。
