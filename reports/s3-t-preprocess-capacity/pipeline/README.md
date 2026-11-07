# T側halfbandを2 coreへ分担したCPU候補

**具体的な2 core実装は、明示した外部処理・中断・転送条件の下でCPU容量と有限期限を通過した。現在のS3受信アプリ全体が同品質で成立した、という判定ではない。** 単coreの `hb31_process` が1024入力当たり64µsの供給周期に間に合わないため、入力展開とFIRの一部をcore0へ分ける実コードを作成した。

[結果・命令経路・入力hash](results.json)、[全22条件のイベント検査](events.json)、[target逆アセンブル](halfband_pipeline.dis)。対象は [C実装](../../../experiments/t_preprocess_capacity/halfband_pipeline.c) と [所有権契約](../../../experiments/t_preprocess_capacity/halfband_pipeline.h)。元の [halfband primitive評価](../halfband/README.md) にある受信品質未認定、FPGA側64/63変換未実装・未見積もりは引き続き適用する。

## 実装した分担と所有権

入力はsigned10 I/Qを保持する連続した1024 raw words、出力は512個のcomplex int16である。16 MS/s入力では1 blockの供給時間が64µsとなる。

|担当|実装した処理|
|---|---|
|core0 producer|過去履歴をworkspaceへ移す、1024入力をeven/odd配列へ展開、次block用履歴を更新、先頭32出力を計算、READYをrelease公開|
|core1 worker|READYをacquire取得、残り480出力を計算、DONEをrelease公開|
|core0 reaper|DONEをacquire取得、出力pointerと順序番号を回収、workspaceをFREEへ戻す|

履歴はcore0だけが更新する。workerは自分のworkspaceだけを読み、producerの共有履歴を参照しない。このため、producerが次blockの履歴まで進めても、前blockのFIR入力は変わらない。workerがDONEにするまでworkspaceを再使用せず、同じcore内のAPI再入を禁止する。

出力とworkspaceの寿命は別である。reapが解放するのはworkspaceであり、出力のDMA leaseではない。既存arenaの16KiB frame内へ2048 byteずつ直接書き、8 block全てをreapした後に初めて送信可能とする。frameのDMA完了までは出力領域を次のproducerへ渡さない。raw入力はproduceから戻るまで保持し、その後はこのpipelineから参照しない。

現在のAPIは連続した1024 words専用である。native bankの任意の先頭offset・ring末端・1024未満の端数を次bankと接続するadapterは実装していない。入力を捨てたり埋めたりして境界を合わせる前提は置かない。

## target命令費用と各coreの余裕

Espressif GCC 14.2.0 / `esp-14.2.0_20241119`、`-O2 -fno-tree-slp-vectorize`で実際にコンパイルした。関数の分岐経路、loop回数、history copyの引数、callee費用を検査する。targetのacquire/releaseに生成された `memw` も命令数に含む。

kernelの依存間隔も、TRM §1.7.1・表1.7-2に基づく共通監査を通す。初期orderにあった29cycles/4出力の既知load-use interlockは、同98命令の並べ替えで除去した。旧orderの負例と修正orderを区別し、このgateが失敗した場合はCPU容量・イベント判定をBLOCKEDにする。単に98命令を1cycleずつと数え、既知のinterlockを無視した結果は採用しない。詳細と一次資料は [primitive報告](../halfband/README.md) を参照。

|API・core|1024入力当たり命令数|含まれるもの|
|---|---:|---|
|produce・core0|8837|自身88、history copy196、unpack7691、prefix862|
|work・core1|12890|自身41、suffix12849|
|reap・core0|53|検査、順序確認、pointer回収、FREE公開|
|合計|21780|340.3125 M instructions/s|

FIRは4出力当たり98命令、今回のprefix/suffix caller loopは各9命令。元の単core `hb31_process` の11命令callerを追加していない。calleeのentry/returnも1回だけ課す。外側のtask dispatcher、空poll、APIを呼ぶ命令等は後述の外部予算に含める必要がある。

時間模型は `ceil(α × API命令数)` を各公開APIにつき1回課す。α=1.0は命令数だけの参考値で、既知のcontrol bubbleを含まないため、物理的な時間判定の成立例には使わない。α=1.1は下記の既知費用検査も通した比較条件である。これがcache、memory/MMIO競合、atomic待ち、register-window例外を含む実機上限だとは認定していない。

|α|core0本体＋reap Mcycles/s|core1本体 Mcycles/s|core0外部残余|core1外部残余|
|---|---:|---:|---:|---:|
|1.0|138.906250|201.406250|101.093750|38.593750|
|1.1|152.812500|221.546875|87.187500|18.453125|

TRM §1.7.3のtaken controlに2cycleを課し、call/returnにも同じ2cycleを保守的に課すと、core0/core1の追加は78/726cycles/blockになる。scalar隣接load-useもtarget列から検出し、load→storeにも1cycleを多めに課したcore0の追加50cyclesを点検した。合計の検査値はcore0が9018、core1が13616cycles/blockで、α=1.1の9780/14179以内に収まる。これは既知の依存費用を下回っていないことの検査であり、未知のstall上限の証明ではない。個別opcode・依存register・加算内訳は `scalar_control_hazard_budget` に保存する。

各coreの容量は240 Mcycles/s。α=1.1では、外部残余を64µs当たりで表すとcore0が**23.25µs**、core1が**4.920833µs**である。この残余はRF、bank境界処理、SDK/API/IRQ、task制御、追加memory待ち等が使う共有枠であり、それぞれへ全額を重複して割り当てることはできない。

未中断のproduceは40.504167µs、workは59.079167µs。既存比較の20000cycle＝83.333333µsというslice条件を維持する場合、単一callに重なれる追加中断の残量はそれぞれ42.829167µs、24.254167µsである。通常tick等が同じcallへ重なれば、その分もこの残量から引く。

**固定64µsおきのproducer開始を保証する模型ではない。** workspaceが使用中ならproducerを待たせ、入力bankの保持期限と容量で吸収する。その間もcore0のRFサービスは続ける契約である。平滑入力で同じslotを128µsごとに必ず再使用する契約は、これとは別の制約になる。結果JSONには入力公開からproducer開始までの遅延とreapまでの遅延を別に記録した。

## 有限イベント評価の条件

実Cのproduce/work/reapを、それぞれの完了イベントで呼び出す。READY/DONEを計算開始時に先行公開しない。入力展開・履歴・atomic・slot状態は同じCを使う。イベント評価だけはFIR arithmetic leafをzero-output stubへ置き換え、計算費用はtarget命令数を課す。算術と状態機械を混同しないため、実scalar FIRを使った独立convolution照合も別に実行する。

|条件|設定・意味|
|---|---|
|入力公開|1 blockの平滑公開に加え、11/12 blockの一括公開を検査。11264/12288 rawのburstに対応し、公開周期はそれぞれ704/768µs|
|RF bank|物理3 bankのうち1 bankをRF書込み用に予約。公開済みで未解放のbankは最大2|
|bank期限|native式のswitch起点303280cyclesから、仮定した最大handoff遅延30000cyclesを控除。公開から273280cycles＝1138.666667µs以内のproduce完了を要求。work完了とreapにも同期限を課すのは今回追加した保守的条件|
|外部サービス|64µsごとにcore0/core1へ指定時間を予約。その時間に外側のtask処理、RF、境界adapter、SDK/API等が収まることが成立条件|
|RF監視|core0外部サービスの完了をRF pollと仮定。完了間隔125µs以下を検査。実native準備・sentinel fill状態機械は未接続|
|通常割込み|100Hz tickをcore0 1846cycles、core1 1696cyclesで別課金。WDTは各516cycles、2.5秒周期・観測内に1回到来する位相で別課金|
|追加周期処理|1Hzサービスの10/25/50µs、core0/core1配置、5000/65000µs開始位相を全て検査。実PHY所要時間の認定ではない|
|DMA出力|既存128KiB＝16KiB×8 frame。8 blockのreap後に投入し、40 MB/sのaggregate wire serviceを仮定。投入前・wire完了後に各最大64µsのAPI/IRQ dispatch待ちを置く|
|長さ|各条件4096 block、入力相当262.144ms。失敗条件も途中で他の条件を打ち切らず、各条件の違反と残作業を記録|

tick/WDT単価は既存の [受信費用台帳](../../s3-receiver-cost-ledger/README.md) に由来する。今回は新しい外部予約条件へ加えた感度模型であり、既存SDK全イベントを新pipelineへ接続した結果ではない。40 MB/sのwire serviceも実SPI routeを実装・保証した数値ではない。

125µsはnative切替閾値到達後の2000入力分に対応する幅である。poll間隔だけを通しても、次bankの準備完了、切替時刻、実capture ABIを通したことにはならない。ここでは必要な監視間隔の条件として使う。

## 結果

α=1.0/1.1、batch1/11/12、core0外部16µs・core1外部2µs/64µsの6条件は模型の有限検査を通過した。うちα=1.0の3条件は命令数だけの参考比較である。既知hazard費用検査を通したα=1.1について、次の、より大きいcore0予約を持つ条件も通過した。

|α=1.1、12 block burst、core0外部20µs/core1外部2µs|観測値|
|---|---:|
|produce/work/reap完了|各4096 block|
|最大produce wall time|50.345833µs|
|最大worker wall time|68.295833µs|
|最大RFサービス間隔|108.945833µs|
|最大出力完成遅延（bank公開起点）|800.670833µs|
|最大公開済みraw bank保持|1 bank（RF書込みbankは別予約）|
|出力arena最大保持|49152 / 131072 byte|

core0外部20µs/64µsは75 Mcycles/s、core1外部2µs/64µsは7.5 Mcycles/sである。tick/WDTはこれらとは別に課した。未計上処理が実際にこの予約枠と到来形状へ収まることを確認した結果ではなく、**収まるならこの具体的pipelineには有限CPU・buffer期限の成立例がある**という結果である。

|追加条件|2位相の結果|理由・範囲|
|---|---|---|
|core0へ10µs周期処理|2/2通過|宣言した有限条件|
|core0へ25µs周期処理|2/2通過|宣言した有限条件|
|core0へ50µs周期処理|0/2通過|produceが90.504167µsとなり83.333333µs slice条件違反|
|core1へ10µs周期処理|2/2通過|宣言した有限条件|
|core1へ25µs周期処理|1/2通過|workerへ重なる位相では84.079167µsでslice条件違反|
|core1へ50µs周期処理|1/2通過|workerへ重なる位相では109.079167µsでslice条件違反|

中断がidleや外部サービスへ重なる位相では、同じ50µsでもworker slice条件を破らない場合がある。通過した位相だけを選んで50µs全位相の成功とは扱わない。slice条件による拒否は、この条件下の拒否であり、全ての再分割・scheduler設計を否定する下限証明ではない。

core0外部26µs/64µs、core1外部8µs/64µs、出力wire28 MB/sという3つの過負荷条件も実行し、bank期限／保持容量／drain未完を検出した。各条件の全fault回数は [events.json](events.json)。raw bank容量違反後も論理backlogを記録するが、その後の処理を物理3 bankで実行可能だったとは解釈しない。

## メモリと検証の確度

target ABIの `sizeof` / `offsetof` を別C翻訳単位の `.rodata` から取得した。hostのpointer幅からtarget RAM量を推定していない。

|target配置|byte|
|---|---:|
|hbpipe全体（2 workspace・metadata・履歴を包含）|8528|
|係数vector（別領域）|272|
|追加データの合計|8800|
|出力arena|既存131072を借用。追加output copy領域なし|

slot strideは4208byte、slots開始offsetは112byte、workspaceは各4192byte。両workspaceとvector入出力の16byte整列を維持する。実受信ELFへ8800byteとコード・stack等を配置した最終RAM検査は未実施である。

hostでは4種類のshift、160 block、81920 complex出力を直接convolutionと照合した。前blockのworker開始前に次blockをproduceし、produce後のraw領域を上書きしても結果が一致すること、BUSY/INVALID時の状態不変、先行reap拒否、順序とoutput領域境界を検査した。target kernelは別の命令意味モデルで1600条件を照合しており、target CPU上で実行した結果ではない。

## ここで閉じた判定と残る統合

今回閉じたのは、**単core候補を2 coreへ分ける実装が存在し、その新caller・atomic・historyを計数しても、各coreの240MHz容量と宣言した有限deadlineへ収まる条件を数値で提示できること**である。旧non-FIR 94.646/127.154 Mcycles/sを丸ごと加算してはいない。

受信全体の採用判定には、native bankの端数・wrapから連続1024入力を作る実装とその追加費用、実RF/SDK/外側taskのイベント頻度・配置、最終RAM/stack、実memory競合とPHY busy待ちの上限、元のフィルタと同品質である契約、FPGA64/63変換の品質・資源を接続する必要がある。無上限のPHY busyループを今回の10/25/50µsへ置き換えたとは扱わない。

PIE contextもcaller/runtimeが保持する条件である。割込みとtask切替がQR/QACC/SAR_BYTEを壊さないこと、または完全に保存復元することを実SDK構成で確認し、必要な保存費用を外部予算へ入れる。有限モデルが割込みcycleを足していること自体は、PIE context保存を実装・検証した証拠ではない。

新pipelineの条件付きCPU比較はここで再現可能になった。追加の受信全体実装を行わずに、これを「S3がT側全処理を必ず捌ける」と確定することはできない。

## 再現

repository ROOT以外からの実行でも、相対 `--toolchain` / `--output` はROOT基準で解決する。binaryは一時directoryに作り、報告には残さない。

```sh
python -m ci.t_halfband_pipeline_audit \
  --toolchain /path/to/xtensa-esp-elf \
  --output reports/s3-t-preprocess-capacity/pipeline
```

`results.json` の `check_summary` と全check行が監査結果である。意図的な過負荷の検出は監査成功と区別して各scenarioの `scenario_pass` に残す。ソースと逆アセンブルのSHA-256も同じJSONに保存する。
