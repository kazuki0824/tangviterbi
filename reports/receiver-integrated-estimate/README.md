# ② Tang Nano20K＋N16R8×2：現在の統合見積もり

2026-10-30 JST。①は変更しない。**S5/16の正常受信だけの模型は通過したが、未計上だった1HzのPHY追従処理を追加すると50µsの中断条件で失敗した。S6/16＋周期処理core1の比較候補は50µsの条件で通過。実際のPHY処理時間とRFへの影響は未確定で、全受信機の成立認定には至っていない。**

SoCはRF取得・可逆I10/Q10 packing・FPGAへの送信、FPGAは全復調とT/S独立TS出力を担当。N16R8×2限定で検討する。追加software間引き・有効bit削減は行わず、FPGA→SoCは選局・電源等の指令のみ。

## 最新：周期PHY処理の追加と分担の再比較

[設定・実バイナリ](../s3-queue-owner/phy-periodic.json)で、PLL追従timerが1秒周期・core0で有効なことを確認。条件付きでbusy-bit待ちループと、その解除後50µs待ちを通る。ソフトウェアの待ち回数上限はないため、この処理のWCETを命令数だけで確定できない。PLL追従を無効化する変更は行っていない。

[core0の35条件](../s3-queue-owner/periodic-runtime.json)では、追加サービス時間10µs/秒は5位相とも20000bank通過、50µs以上の評価点は5位相とも失敗。0µsは前回の出力・費用・期限結果と一致する。[core1移動だけの40条件](../s3-queue-owner/timer-core1-runtime.json)も、S5/16では5位相すべてを通過する条件なし。

そこで[18設定の比較](../s3-queue-owner/periodic-candidates.json)を実施。S6/16、512sample/slice、準備2048/3072/4096語、slice許容40000cycleで、core1追加50µs/秒の5位相4000bankと代表位相20000bankを通過した。準備2048語の代表結果はarena残6848byte、RF監視最大68.208µs、job余裕最小154.929µs。100µsは失敗条件が出る。未通過の設定は最初の失敗で棄却し、残り位相を通過扱いにしない。

[追加の余裕評価](../s3-queue-owner/periodic-headroom.json)では、S6/16・準備2048語が62.5µsでも5位相4000bank＋代表位相20000bank通過、75/87.5µsは最初の位相で失敗。全位相の許容上限を確定した結果ではない。

**追加時間は実測費用でなく感度条件。** 実際のtimer IRQ/task配置・優先度、PHYのbusy解除とRF影響、変更分担のtarget命令再計数が残る。これに加えて指令/supervisor、window例外・メモリ競合も未確定。以前の正常受信20000bank通過を全SoC成立とは扱わない。

追加後の[回帰検査78件](../s3-queue-owner/allocations-tests.log)は成功。

受信専用のSPI初期化関数はcore0・level1・非共有・IRAMを固定するよう実装し、[SDK CI](https://github.com/kazuki0824/tangviterbi/actions/runs/40979624053)成功。最終board launcherの完成や、timerのcore1移動を実装済みとするものではない。

メモリは[寿命別に再計算](../s3-queue-owner/lifetime-memory.json)。PHY・最小allocator管理費・既知TWDTを内部RAMへ配置する条件で、校正中残量上限13436byte、定常15308byte。TWDTのPSRAM fallbackを許し、強制internal分だけを差し引く定常上限は15368byte。未計上のPHY内部・断片化等を含む実際の空き容量ではない。以下の16820/16052byteは控除項目の少ない旧段階の上限。

## 最新：未計上だった常駐割当を追加

[GDMA・lock・IRQの内訳](../s3-queue-owner/README.md)、[再計算JSON](../s3-queue-owner/allocations.json)。SDKソースの割当箇所と同じN16R8 ELFの型サイズから、2portで**768byte**を追加計上した。既知割当下限は**2352byte**、内部メモリ容量上限は**16052byte**へ訂正。受信中のバッファ期限結果は変更なし。GDMA共有groupの二重計上を避け、一時確保と常駐量を分離した。これは見積もり漏れの是正で、使用メモリを増やす実装変更ではない。

これらは初期化時の割当であり、毎転送の費用ではない。MANUAL alignmentを使う正常送信では一時DMA payload割当0回/transferを確認した。初期化CPU費用、PHY/calibration、allocator overhead、制御・supervisorは未確定。IRQの非共有設定とcore割当は最終launcherで固定する必要があり、現adapterが強制しているとは扱わない。

## 最新：実owner接続後の費用・期限とメモリ

[詳細・再現手順](../s3-queue-owner/README.md)、[費用台帳と全15条件](../s3-queue-owner/runtime.json)、[命令監査](../s3-queue-owner/instructions.json)、[メモリ検算](../s3-queue-owner/memory.json)。正常受信ownerを実装し、準備2048語/反復・1024語/pollを実コードと模型で一致させた。owner追加0/100/300cycleの仮置きは除去。実生成コードのowner制御367、worker62、RF基本197cycleを使用し、poll wrapperの二重計上も除いた。

S5/16、PCAB、16KiB、深さ2queue＋可逆inline packingで20000bank（6.164秒）通過。arena最大123328/131072byte（**最小残7744byte**）、RF監視最大**68.208µs**、観測job期限余裕最小**187.808µs**。費用と発生回数の積、各core総課金・経過時間、出力byteを照合した。追加stall感度の0〜15%評価点は4000bank通過、20%は容量超過。ただし非同期IRQ/tickは増加対象外で、実機の未計上費用を15%以内と確認した結果ではない。

同じtask/queue/RF領域を保持したN16R8ビルドはlink・配置検査を通過し、費用probeと8関数の命令・分岐一致を確認。既知SPI割当1584byteを差し引いた内部メモリ容量上限は**16820byte**。PHY/GDMA等の未計上割当が残り、実際の空き容量・起動成功は未確認。

未確定なのはRF-off/再選局/停止、指令・supervisor、window例外、メモリ/MMIO待ちと競合、最大stack、全受信機FPGA資源・期限。**正常受信の条件付き見積もりは通過、全SoC費用確定・全受信機成立認定は未完了。** 以下は旧結果の履歴であり、「owner未実装」「owner追加300」「SDK未監査」等の記載は当時の状態を示す。

## 2026-10-30：inlineの周辺費用も含めた最新結果

[packing全費用比較](../s3-inline-packing/README.md)、[全65条件](../s3-queue-study/inline-runtime.json)。定常blockの50→43cycleだけでなく、run130→140、端数191→201、slice319→323、空処理143→148cycleも計上した。同じSDK単価でのS5/16・PCAB・準備2048語・owner追加300cycle、20000bank比較は以下。

|観測値|queue単独|queue＋inline|
|---|---:|---:|
|arena最小残量|6760 byte|7724 byte|
|RF監視最大間隔|71.754 µs|68.275 µs|
|job期限余裕最小|159.488 µs|184.867 µs|

**周辺費用増を含む条件付き模型でも改善を確認した。実機性能・全SoC費用の確定ではない。** inline併用はS5/16・S6/16、PCAB/BCPA、準備2048/3072語、owner追加0/100/300cycleの24条件すべてで4000bank通過。S5/16の代表条件は20000bankも通過。準備1024語は失敗条件が残る。新SDKの指定経路費用とメモリ増分は次節、旧結果はその下に履歴として保持する。

## 2026-10-30：先行queueのSDK費用・メモリ増分を再計上

[新しい費用・期限結果](../s3-queue-study/README.md)、[全58条件](../s3-queue-study/audited-runtime.json)、[SDK費用根拠](../s3-queue-study/sdk-n16r8/costs.json)。前回のAPI/link probeはPSRAM未設定だったため、N16R8のPSRAM/atomic設定を揃えた [SDKビルド](https://github.com/kazuki0824/tangviterbi/actions/runs/40903267320)で再確認した。

- 投入822、完了回収458、空照会200cycle。完了＋次開始は同一IRQの2511cycleとし、旧1037＋2287cycleの共通処理二重計上を解消した。値は命令数×1.1の模型。
- owner追加300cycle、S5/16・PCAB・準備2048語で20000bank（6.176秒）通過。arena最大124312/131072byte（残6760byte）、RF監視最大71.754µs、観測job期限余裕最小159.488µs。
- SDKの送信/完了queue確保要求は2portで+80byte。adapter静的+32byteと合わせて+112byte。allocator差分と全受信機メモリ収容は未確定。
- 全58条件で費用保存と出力byte照合を検査し、IRQ4経路の単価×回数を総IRQ費用へ照合した。inline packingの節約は未計上。

**新queueの指定通常SDK経路の費用は確認したが、全SoC費用確定ではない。** owner最終実装、window例外・メモリ/MMIO競合、制御指令・supervisor、全アプリ資源が残る。下記の「SDK未監査」「6.187秒/残6660byte」は前回結果の履歴であり、今回の値を優先する。

## 2026-10-29：改善案1・2を実装した結果

[送信停止原因の計測](../s3-tx-idle-study/README.md)、[深さ2のqueue候補](../s3-queue-study/README.md)、[可逆packingのinline候補](../s3-inline-packing/README.md)を追加した。旧S6/16・609bank条件で、公開データがあるのに未送信の時間はSPI2で11.645%、SPI3で9.366%だったため、先行投入を優先した。

|改善|実施内容|確認できた結果|未確定部分|
|---|---|---|---|
|先行queue投入|専用queue_size=2、固定descriptor、後続転送中の先行結果回収、失敗時lease保持|S5/16・準備2048語・各管理費用+300cycleの模型で20000bank（6.187秒）通過。arena最大124412/131072byte、RF監視最大79.071µs、WDT各2回を含む|SDKの新経路費用、追加queueメモリ、最終受信task接続、実機競合|
|可逆packing inline化|品質・境界・所有権を維持した代替translation unit|O2定常ループ45→39命令/8sample。3分担/転送長×O2/Os・各2000bankの実C並行検算成功|step text+120byte、O2 stack枠+16byte。slice全費用の再計上が必要（SDKのIRAM配置は確認済み）|

queue模型は新adapterの実Cを使うが、SDK自動開始は模型で、旧SDK費用へowner/submit/reap各0/100/300cycleを足した感度評価である。**実測性能や、未計上費用も含めた成立保証ではない。** inline化の削減はqueue通過の計算へ加えていない。既定受信実装の準備1024語・単一転送APIも変更せず、比較可能な候補として保持する。

ESP-IDF v5.5.1での [API/link確認](https://github.com/kazuki0824/tangviterbi/actions/runs/40894324461)も成功した。実ELFでqueue/packingのIRAM配置と39命令を確認。adapter静的metadataは2portで224→256byte（+32byte）だが、SDK queue動的割当と全受信機fitは別途確認が必要。

本番1024語のままの条件は不成立。2048語への変更とqueue接続の両方を確認する必要がある。改善案3〜7は未実施で、まず今回のqueue候補をSDKへ照合する。以下は、単一転送APIを用いた旧模型の履歴として読む。

## 2026-10-29：カウンタ・ハードウェア待ち費用の追加監査

[64bitカウンタ監査](../s3-counter-envelope/README.md)では上位word一致という従来の制限を外した。takeは55命令のまま、completeは144→153命令の保守的包絡となり、REAP_DONEを469→479cycleに置換した。実Cで桁上がり前後の完了順序370128例を検算し、同じ費用で216条件と通過条件の長期評価を再実行した。

**最新の追加待ち0条件では、S側の最長到達は5/16が344bank、6/16が609bankで、いずれも容量超過により停止。** どちらもSPI3→collect→packing→SPI2、準備2048語の条件である。T現行順序は準備1024/2048/3072語の各4000bankを通過。費用を増やすと到達bankが増える場合があるが、処理位相が変わるためであり、性能改善とは解釈しない。

[ハードウェア待ちの単価・期限感度](../s3-wait-cost/README.md)も追加した。SPI UPDATEとcounter readyは追加1反復3命令、snapshot再試行は6命令。既計上の初回checkを再加算せず、開始IRQとtickへ追加費用を接続した。追加反復各0/16回という感度点の20条件では、Tは4000bank通過、Sは容量超過。16回は実測値でも上限でもない。

**全SoC費用・頻度の確定は未完了。** window例外頻度、追加競合・メモリ遅延、最終アプリの指令/supervisor/SDK活動、待ち回数の推定範囲が未確定である。これらを0費用とは扱わない。

## 2026-10-29：同じ費用で処理順序24通りを比較

[順序比較の結果](../s3-owner-order-estimate/README.md)、[全イベント台帳](../s3-owner-order-estimate/results.json)、[全SoC処理と未計上範囲の対応表](../s3-receiver-application-inventory/README.md)を追加した。packing、collect、SPI2処理、SPI3処理の24順序×3分担×3準備予算＝216条件を、同じ単価・反復7回のRF監視で比較した。各100bankを要求し、S側で通過した4条件は4000bankでも評価した。

**比較したS側の順序変更だけでは継続受信は成立しない。** S5/16・準備2048語の最長到達はSPI3→collect→SPI2→packingの348bankで、次の受入れ132214byteが128KiBを1142byte超過。S6/16ではSPI3→collect→packing→SPI2の121bankで、5432byte超過した。両条件のRF監視最大間隔は51.779µs。T側は全72条件が100bank通過し、並べ替えたT側の4000bank評価は今回未実施。

owner制御単価190cycleを共通に置いた順序比較であり、並べ替え後のXtensa命令列の再計数ではない。全スケジュールの不可能性証明でもない。現行順序の元台帳との完全一致、単価一致、費用保存則、byte oracleを検算する。実装の処理順序は変更していない。

全SoC対応表では、RF停止中の起動・peer待ち・停止処理も列挙した。peer待ちのforce feedを「起動時1回」と省略せず、受信中の通常feedとも混同しない。未実装の指令経路／supervisorとSDK活動の未固定部分が残るため、指定2点の全SoCとしての完了はまだ報告しない。

## 2026-10-29：受信ループ・tick・IRQを命令計数へ置換した結果

[最新の費用・発生頻度・期限評価](../s3-receiver-cost-ledger/README.md)、[全45条件](../s3-receiver-cost-ledger/runtime.json)。RF準備・切替・受渡し、collect、空packing、owner/worker、tick本体、level-1 IRQ入口復帰をSDKバイナリから追加計数した。前回のSDK/ROM監査に接続し、同じ単価を台帳と仮想時刻へ一度ずつ使用する。

**今回の条件でもS側の継続受信は成立していない。** S5/16・512pair・準備2048語・追加stall0%は49bank後、次の受入れ132666bytesが必要となり128KiBを1594bytes超過。S6/16・同条件は58bank後に9741bytes超過。本番1024語では準備未完で停止。T側8/16・512pair・1024語は4000bankを通過し、RF監視最大間隔54.346µs、arena最大94455/131072bytes。いずれも実機上限ではない。

監査した通常IRQ入口復帰は249命令、同優先度taskの再選択を含む場合は642命令。launcherの優先度は呼出し側が選ぶ。今回の同優先度という構成仮定ではcoreを分けてもtickで再選択を要求しうるため、その経路を加算した。peer kernel lock待ち包絡も含めたtick費用1846/1696cycle、WDT更新＋peer待ち516cycle、S開始ISR2287cycle、完了ISR1037cycleという命令数×1.1模型で評価した。WDT更新時刻も実ソースと同じ更新前の時計読取値から計算するよう模型を訂正した。準備予算2048/3072語は模型比較であり、本番1024語を変更していない。

**指定2点の全SoCとしての完了には未到達。** 受信ループ＋宣言した通常SDK/IRQ構成は数値台帳と実行順序を接続した。残るwindow例外、lock競合、ハードウェア反映待ち、cache/メモリ待ち、最終アプリ差分は明示した費用式へ置き、0とは認定していない。保存ELFはapp_mainが受信を開始しないlink-only probeであり、最終アプリの全task/IRQ/制御指令頻度を証明しない。詳細な確定／未確定の境界は最新結果に記載。正式採用0。

前回の[SDK費用台帳](../s3-sdk-cost-ledger/README.md)と[旧費用模型](../s3-joint-runtime/README.md)は比較履歴として保持する。最新判定には上の受信ループ台帳を用いる。

## 2026-10-28：費用収支の訂正と確定条件

**従来のS core0上端98.28〜98.41%は、全費用込みの見積もりとして確定できない。** U0=20Mcycle/sに基礎25000反復/sのscan費用を含める前提は未検証で、全額をscanへ使っても800cycle/反復。通常経路1729.2/1767.7cycleを平均と仮定する場合には不足する。

[全反復分を明示した収支と確定条件](../s3-cost-reconciliation/README.md)では、旧U0と差分scanを除去して全scanを計上した。同じ通常経路費用を平均と仮定し、その他残余をゼロとした場合でも、**S512 core0上端107.96〜108.49%、S256は112.89〜113.42%**。これは実平均ではなく、旧感度計算の費用収支を整合させた結果である。S512が100%以内になる平均scan予算は、その他残余ゼロでも**1156.386cycle/反復以下**。成立認定はしない。

確定に必要なのは、(1)全経路費用と状態頻度の一意な計上、(2)同じ費用による非一様スケジュール・期限・buffer検証、(3)同一FPGA全段topの資源/タイミング、(4)候補と通信路の最終採否。実機成立確認とは区別する。下の既存表は旧Uを含む感度条件の履歴として残し、上記訂正と合わせて読む。

## 見積もり結果の要約

以下は旧U0=20Mcycle/sを維持した従来模型の数値で、全費用の整合確認前である。当時の推進案はT raw 8/16・32KiBとS raw 6/16・16KiB、N16R8を各1枚。現在のS候補は冒頭の5/16・深さ2 queueである。下表のSoCは管理200cycle/反復も含めた同一感度条件で示す。実測値や成立確率ではない。

| 項目 | T側 | S側 | 判定・条件 |
|---|---:|---:|---|
| SoC core0占有率 | 44.86〜46.84% | 93.25〜97.48% | 管理200cycle・30µs反復の感度値 |
| SoC core1占有率 | 26.18〜28.05% | 73.27〜79.94% | packing命令模型＋未分類費用 |
| 必要payload帯域 | 40 MB/s | 100 MB/s | 同精度I10/Q10 |
| 仮割当通信路の容量 | 74.519 MB/s | 106.990 MB/s | G=30µsを仮定 |
| payloadとの差 | 34.519 MB/s | 6.990 MB/s | 制御予約0.01 MB/sは別控除 |

共有FPGAのraw＋slotaddrは**20472/20736 logic（98.73%）、46/46 BSRAM（100%）**という旧全段台帳からの条件付き値。部分回路の配置配線は**166.22MHz**で目標154.29MHzを達成したが、全段統合の速度・資源とは別である。

**この表の2.52ポイントという余裕は旧費用模型の履歴であり、現在の全費用込み余裕ではない。上記の同一費用・順序評価ではS側が停止する。正式採用0。**

数値の全桁・根拠hashは [estimate.json](estimate.json)。実装改善の履歴より先に結果を確認したい場合はこの節を参照する。

## 1. SoC：実装した改善と最新の数値

[fill実装・実生成命令・SDK成果物](../s3-fill-unroll/README.md)。各volatile storeのbarrierと順序を残し、アドレス更新を8wordで共有した。折返し・端数・付帯費用まで含む命令数包絡は旧21574→**15362命令/bank**。削減率28.79%は命令数についての値で、実時間の測定結果ではない。

packingも最新SDKからCFGを再計数した。block45/run118/slow_pair173は維持、slice係数は213→223へ更新。実Cの11264/12288/12289/14288/14352 samples、開始位置0/16380、slice64/128/512/1024、各64bankの40条件×3構成で出力・経路保存則を確認。下表は1024word/反復への分割後（追加準備管理ΔEは直下に別計上）。512pair/slice、定常4長さを用いる。初回短bankを定常rateへ流用しない。

条件：240MHz×2、命令cycle係数α=1.1、SPI CPU active20µs/転送、未分類U0/U1=20/10 Mcycles/s。Sには40→30µs scanの追加費用1500cycle/回という**未測定の感度点**を含む。

| 構成 | core0 | core1 |
|---|---:|---:|
| T raw・8/16・32KiB・分割fill | 42.08〜44.06% | 26.18〜28.05% |
| S raw・5/16・16KiB・分割fill | 83.52〜87.02% | 80.07〜87.86% |
| **S raw・6/16・16KiB・分割fill** | **90.48〜94.70%** | **73.27〜79.94%** |

分割前はS6上端94.40%だった。分割後・ΔE未計上での追加scan費用予算は3025.55cycle/回。追加3000cycleという感度点ではcore0上端99.91%。追加scan費用と準備管理ΔEは別費用であり、同じ残余予算を二重使用しない。追加scan費用0・500・1500・3000とΔE=0・100・200・300をestimate.jsonへ保存する。いずれも実値が入る信頼区間や成立確率ではない。

### 平均CPUとは別に残る、ownerの処理間隔

| Sの分担 | core1 packing-only平均service上端/bank | 公開320µsから30µs collect待ちを引いた残り |
|---|---:|---:|
| 5/16 | 300.30µs | −10.30µs |
| 6/16 | 271.73µs | 18.27µs |

これは平均serviceからの設計予算であり、IRQ・古いjob待ち等を含む最悪応答ではない。5/16を平均CPUだけで第一案にしない。

[予算付き準備の実装と検算](../s3-budgeted-fill/README.md)で、owner内の7回のRF pollに**1反復合計1024word**の予算を共有させた。reclaimは1回、全7168wordが完了するまでprepared禁止、予算0でもRF監視を継続する。実Cで全16384開始位置・途中状態・期限失敗を検証した。

| 分割の影響 | 同期8word | 1024word/反復 |
|---|---:|---:|
| 1bankのfill命令数包絡 | 15362 | 15567 |
| 1反復のfill命令数包絡 | 15362 | 2265 |
| α=1.1のfill単独時間模型 | 70.41µs | 10.38µs |

呼出し増分を含めるとS6のcore0上端は**94.70%**。追加準備管理をΔE cycle/owner反復、毎秒33333.33反復と仮定すると、ΔE=100/200/300で**96.09/97.48/98.87%**。追加管理の残予算は約381cycle/反復。これは未測定費用の感度で、ΔE=0を実際の無償性とはしない。core1上端79.94%は不変。

**分割で連続fill量は減ったが、一定30µs scanを達成したとは認定しない。** 7反復の準備完了とbank解放・RF切替期限、SPI API/packing等を含む非一様なowner反復と有限bufferの整合が残る。1反復のfill単独10.38µsはowner全体の実時間上限ではない。

[packing細分化の比較](../s3-owner-slice-tradeoff/README.md)では、256pairへ減らすと非空slice平均のケース上端は28.10→17.29µsになる一方、追加管理200cycle/反復込みのcore0上端は97.48→102.41%。64/128もCPU超過、1024は連続packingが長くなる。細分化だけで解決せず、512を維持して処理本体・SPI費用・スケジュールを改善する。平均slice時間を最悪時間とは扱わない。256pair案を管理200cycleの感度条件で平均CPU100%以内へ戻すには、他条件固定ならSPI CPU使用時間20→16.05µs/転送以下が必要。達成値ではなく改善目標の逆算である。

[SPI空振り確認の改善](../s3-spi-running-guard/README.md)：raw-onlyの転送中はSDK結果キュー確認を省くguardを実装。idleだけでは完了認定せず、従来のSDK完了結果でleaseを解放する。関連host試験と変更後SDKのT/S各59静的check・各12ソース/生成命令照合が成功。実ELFでも動作中のSDK呼出し省略とidle時のSDK回収経路を確認。削減時間は未測定で、上記CPU感度値を減額していない。 実命令比較ではwrapper込みで動作中49＋SDKキュー内部命令→38/40命令。idle未公開では逆に9/11命令増えるため、全経路の改善とはしない。256pair案は転送API20µs・管理200cycleを固定すると、追加scan費用805.544cycle/回以下が平均CPU100%境界。scan全体の達成値ではなく、残る改善目標である。

[通常RF監視の費用内訳](../s3-owner-quiet-path/README.md)：準備済み・非settlingの指定経路はRF監視1回189命令。7回＋2本の転送中SPI確認で1401命令、α=1.1なら1541.1cycle相当。collect・feed・owner制御等は別なので、追加scan1500cycleを保証上限とは扱えない。これは特定反復の部分費用であり、平均費用への置換には状態頻度と既存Uの重複整理が必要。CPU数値は今回据え置く。

[通常owner反復の追加集計](../s3-owner-iteration-path/README.md)：collect・feed・時計・制御を加え、inline化した2pollのwrapper重複28命令を除くと、指定2経路はpacking本体を除いて1572/1607命令。α=1.1では1729.2/1767.7cycle相当。この値を平均追加scan費用と**仮定**した感度計算ではS512 core0上端は**98.28/98.41%**、S256は**103.21/103.34%**。実平均の確認ではなく、上表の1500cycle条件を置換した成立認定もしない。その他経路・待ちと状態頻度の確認が残る。

### 同じS候補構成のSDKメモリ確認

[SDK run 40535137322](https://github.com/kazuki0824/tangviterbi/actions/runs/40535137322)、commit `9da570f`の共通・raw-only既定・S候補が成功。Sの実ELFが6/16・16384bytes・8word・1024word準備予算であることと新入口のIRAM配置を含む**59静的check**、fill命令列・literal・8 source identity等**12再確認**が成功。3構成の静的check合計は172。SPI guard追加後もS/Tのpacking係数45/118/173/223は変わらず、各4項目のCFG照合が成功。

SPI guard追加前後で下記メモリ値は不変。Sのpack構造体440bytes、captureは準備分割により160→168bytes。分割前と比べIRAM末尾は0x40388100→0x40388200、heap開始は0x3fcacf90→0x3fcad098。既知driver控除後の内部空き**上限**は16588→**16324bytes**（264bytes減）。準備管理の追加はメモリ上も無償ではない。未計上割当・断片化・実起動までの保証ではなく、128KiBの物理payload arenaを維持したlink結果である。

## 2. 通信と有限buffer

T raw40 MB/sはOctal、S raw100 MB/sはOctal＋Quad。T32KiB・S16KiBで、対応FPGA endpointのWRITE_BYTESを合わせる。通信内容は同精度の可逆I10/Q10 packing。

| 非直列化時間G=30µsという条件 | payload容量 | payloadとの差 |
|---|---:|---:|
| T・Octal | 74.519 MB/s | 34.519 MB/s |
| S・Octal＋Quad | 106.990 MB/s | 6.990 MB/s |

制御予約0.01 MB/sを使う場合は差から0.01を控除。G、CPU active、scan周期は別の量で、実測G=30µsを確認した値ではない。

[全scan位相検証](../s3-short-transfer-audit/README.md)では公開320µs・一定scan30µsの指定3列×全7200位相が128KiBに入り、最小残7872bytes。scan40µsでは交互列が9600位相中2772で超過、最大2040bytes。これらは指定列・一定間隔の模型であり、分割fillと非一様な処理間隔を持つ現runtimeへそのまま適用できない。位相件数を失敗確率とは扱わない。

## 3. FPGA：全段予算と速度

旧全段配分から共有K7を置換した条件付き台帳。現在のtransportを含む全top合成・配置配線値ではなく、統合差分Δが残る。全8kernel×T FIR移管有無の16候補はestimate.json。

| 構成 | logic /20736 | FF /15552 | BSRAM /46 | DSP18 /48 | K7単体Fmax |
|---|---:|---:|---:|---:|---:|
| raw＋slotaddr | 20472 | 13189 | 46 | 34 | 156.764MHz |
| raw＋localshift | 21425 | 13364 | 46 | 34 | 224.266MHz |
| T FIR移管＋slotaddr | 19720 | 11653 | 44 | 26 | 156.764MHz |
| T FIR移管＋localshift | 20673 | 11828 | 44 | 26 | 224.266MHz |

raw＋高速localshiftはlogic689超過のため単純置換しない。slotaddrの台帳上の純増許容量はlogic264・BSRAM0。pairedはslotaddrよりlogic7多く、単体151.378MHzで劣る。他の保存trialも資源と速度の組合せで上回らない。未知の実装まで排除した結論ではない。

[配置配線の完了結果と検算](../cursor-mask-route-comparison/README.md)：保存部分構成は**166.2234MHz**へ改善し、最低152.6266MHz・目標154.2857MHzの両方を達成した。目標に対する周波数余裕は7.737%。logic site計数19658（基準比+31）、FF8673、BSRAM29。もう一方のweight20試行は152.9520MHzで、最低を超えたが目標には未達。入力netlist・backend source・chipdb一致と出力再計数等18checkが成功した。

この部分構成の速度不足は解消した。ただしRF endpoint・equalizer・interleaver・RS/TS・PHY等の全接続構成ではなく、scan/観測fixtureを含む。**166.22MHzを全受信機のFmaxとは扱わない。** 旧全段台帳の資源数・未接続段・現在のtransportとの差分を統合して再合成/配置配線する課題は残る。詳細成果物は [Actions run 40524351929](https://github.com/kazuki0824/tangviterbi/actions/runs/40524351929)。

[固定配置からの再配線2試行](../cursor-mask-fixed-router2/README.md)はcheckpoint復元エラーで終了。続くローカル通常配置配線も完了結果を取得できなくなり、停止原因は不明。その途中ログを成果とせず、Actionsへ移した完了結果を今回採用した。合法性検査は緩和していない。

T FIR移管は752logic・1536FF・2BSRAM・8DSP18を空ける代替。ただし保存QACC kernel＋準備書込みのみ＋旧非FIR/API予算で370.964〜403.472 Mcycles/s。準備書込み約2.081GB/s、gather読込み・展開・競合・core偏在・同品質係数契約が未確認。rawよりCPUを軽くする案として選ばず、FPGA容量を空ける代替として保持する。

## 4. 必須根拠の所在と採否

| 必須項目 | 所在・範囲 |
|---|---|
| 処理分担候補すべて | [全分担台帳](../partition-recheck-20261023/README.md)。宣言したT8段/S6段の16384組・320所有者、方向制約適合63組。未知の全アルゴリズムの網羅ではない |
| 資源占有率・期限 | 本文・estimate.json、[worker応答](../s3-worker-response/README.md)、[reclaim期限](../s3-reclaim-deadline/README.md)。平均占有率と最悪応答を区別 |
| 交換情報の種類 | 台帳の各境界に型・方向・速度。raw T40/S100 MB/s、T FIR代替はQ15複素32.507937 MB/s。FPGA→SoC payload禁止 |
| 全通信路候補と余裕 | 元台帳の18 profile・555有効集合と63分担の比較を維持。今回の転送長・費用を反映した経路は性能評価用の仮割当 |

性能・資源・期限の評価→合格分担への通信路割当→経路が非空のものを採用、という順序を維持する。正式な性能合格・通信路割当・受信機採用は0。

**現在の改善結果は「先行queueとinline packingの候補を実装し、N16R8設定で指定SDK経路費用を照合、同じ費用による有限期限模型でS5/16を通過した」。未完了はownerの時間配分と有限bufferの整合、FPGAの全段統合、実メモリ/RF連続取得・品質、T/S同時TSの確認。** 未測定項目を理由に条件付き数値を出さないことも、仮定を達成済みとすることもしない。

再現：`python -m experiments.s3_integrated_estimate`。現SDK CFG、実C経路計数、fill包絡、FPGA16候補、保存STA、FIR算術を再計算し、根拠hashをestimate.jsonに保存。値の幅は入力ケース・感度仮定によるもので、統計的信頼区間ではない。

検算：既存66件＋今回4件、合計70件。結果は [技術検算ログ](../s3-queue-study/audited-tests.log) に保存。
