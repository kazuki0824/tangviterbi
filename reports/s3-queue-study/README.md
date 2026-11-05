# ② 深さ2の送信queue候補と同費用の期限評価

**候補実装とN16R8 SDK費用を照合し、S5/16・準備2048語で20000bankを通過した。inline併用の最新比較は [packing全費用比較](../s3-inline-packing/README.md)。実機成立や全SoC費用確定ではない。**

## 2026-10-30：N16R8設定のSDK経路費用へ置換

前回のAPI/link probeはPSRAM未設定で、N16R8のatomic workaroundと生成コードが異なっていた。前回のリンク成功はAPI確認として維持するが、そのELFをN16R8のSDK費用として使用しない。PSRAM Octal/80MHz・内部予約4096byte・外部task stack許可を合わせた [Actions 40903267320](https://github.com/kazuki0824/tangviterbi/actions/runs/40903267320) が成功した。[入力commit・成果物hash](sdk-n16r8/provenance.json)、[SDK経路監査](sdk-n16r8/costs.json)。

既存SDKの56経路について、実行命令・literal・分岐先・calleeを新ELFと照合した。ROM費用は固定ROM入口アドレスを照合して既存の検算結果を再利用。新adapterは全分岐包絡、take/completeは64bit桁上がりを許容する包絡を使用する。待ちtaskなし、内部DMA整列buffer、単一device/port、callbackなし、競合なしの指定経路であり、全ハードウェアWCETではない。

|処理|旧queue模型 cycle|新SDK経路模型 cycle|計上単位|
|---|---:|---:|---|
|データなし投入|63|53|未公開データへの投入試行|
|投入成功|939＋追加0/100/300|822|1 transaction|
|空の完了照会|230|200|1照会|
|完了回収|479＋追加0/100/300|458|1 transaction（照会中の完了は差額のみ追加）|
|初回開始IRQ|2550|2550|1 IRQ|
|開始のみIRQ|2287|2287|1 IRQ|
|完了のみIRQ|1037|1037|1 IRQ|
|完了＋次転送開始IRQ|1037＋2287＝3324|2511|同一IRQとして入口・復帰を1回|

命令数×1.1を切り上げる模型。新SDK投入時のbus requestは、active/idleの両経路を含む包絡へ置換し、特定旧経路に対して7命令を追加した。owner制御の未確定差分だけは0/100/300cycle/反復の感度を残す。inline packingの削減はまだ使わない。

[再評価58条件](audited-runtime.json)：S5/16のPCAB/BCPA、準備2048/3072語、owner追加0/100/300cycleの12条件はすべて4000bank通過。S6/16は不成立条件が残り、準備1024語も不成立。

S5/16・PCAB・準備2048語・owner追加300cycleでは20000bank、**6.176秒**を通過。arena最大**124312/131072byte（残6760byte）**、RF監視最大**71.754µs**、観測job期限余裕最小**159.488µs**。出力617545728byteをoracleと照合。tick各617回、WDT各2回。これらは有限模型の観測値で、最悪値の保証や成立確率ではない。

同じ単価を実行順序と台帳の双方へ一度だけ適用し、IRQは初回開始・開始・完了・連続の4経路別の回数も保存する。回収台帳のeventsは費用加算の回数であり、照会途中で完了した場合の差額加算を含む。論理完了件数はtransfers_doneで確認する。

新ELFのQueueDefinition=84byte、spi_trans_priv_t=20byteをDWARFで確認。2port×送信/完了の4queueについて確保要求は416→496byte（**+80byte**）、adapter静的増分+32byteと合わせて**+112byte**。allocatorの管理領域・丸め・断片化と全受信機のfitは別。従来の+32byteだけを全メモリ増分としない。

再現：`python -m ci.s3_queue_cost_audit --toolchain <xtensa-esp-elf>`、`python -m experiments.s3_queue_audited_runtime`。検査：`python -m unittest tests.test_s3_queue_costs`。SDK費用と頻度の未計上範囲は、owner最終実装、window例外、MMIO/メモリ待ち・競合、指令/supervisor等の最終受信アプリ。全SoC費用確定・全FPGA統合・実機成立は未完了。

以下は前回の感度模型と実装の説明。

## 実装

`experiments/s3_raw_queue.c/.h` に、専用SPI device・queue_size=2・固定transaction 2個を実装した。固定header/flagsを初期化時に準備し、送信時はoffsetとpayload pointerを更新する。2本のportを同じownerが操作し、SPI IRQ affinityは起動側が設定する。FPGA→SoC payloadは追加しない。

後続転送が動いていても先行結果を回収するため、既存の「running command中は結果queueを見ない」guardは使わない。SDKから正しいtransactionが返るまでdescriptorもpayloadも保持し、packの連続prefixだけを退役させる。queue失敗や異なる完了pointerはfaultを固定してleaseを保持する。自動retry・無断再利用はしない。旧API・既定受信taskは変更せず、独立した候補として追加した。

実Cの所有権検算で、2個投入、満杯時のtake抑止、先行完了時の後続保持、2port間の順不同完了、失敗時lease保持、誤完了pointerを確認した。

## 同じ費用での評価

host模型は新queue adapter本体と既存packing/native Cを実行する。SDKの次転送自動開始はモデル化し、旧SDK開始/完了費用を各転送へ課す。完了IRQ内の次転送開始費用が終わるまで線上時間を開始しない。両SPIのIRQとcore0 tickのservice期間も直列化し、同一core上で同時に開始処理できるとは仮定しない。空の結果queue照会は従来のrunning guard42/44cycleではなく230cycleを課す。照会費用の進行中に完了した場合は成功単価との差分も加える。

旧単価を新queueの実SDK監査済み費用とは扱わない。新しい管理費用の感度として、owner反復・成功submit・成功reapへ、それぞれ0/100/300cycleを追加した。追加0は費用増がないという仮定である。通常IRQ・tick・WDTの旧費用は保持。inline packingの削減はまだ加えない。

- S5/16、現行順序PCABとBCPA、準備2048/3072語は、追加0/100/300cycleの12条件すべて4000bank通過。
- S6/16では不成立条件が残る。S5/16へCPU分担を寄せる候補を優先する。
- 本番準備1024語のままでは不成立。2048/3072語は候補条件であり、既定値を無検証で変更していない。
- S5/16・PCAB・準備2048語・各追加300cycleは20000bank、6.187秒を通過。arena最大124412/131072byte（残6660byte）、RF監視最大79.071µs、両coreでWDT更新各2回を含む。

有限通過は無期限保証ではない。追加window例外、ハード/メモリ待ち、指令受信、最終アプリ差分は残る。queueを増やした場合の実SDK全経路・queueメモリ・割込み競合と全受信機のfitを別途確認する。API/link確認用のSDK probeも追加したが、RF起動・128KiB arena・受信taskを含む完成アプリではない。

[通常条件](runtime.json)、[20000bank](extended.json)、[検算](tests.log)。再現：`python -m experiments.s3_queue_runtime`、`python -m experiments.s3_queue_runtime --extended`。元模型との比較は [送信停止原因](../s3-tx-idle-study/README.md)。

## 改善案の扱い

優先度1の先行queue投入と優先度2のinline packingを候補実装・検算まで進めた。優先度3以降（sentinel削減、動的スケジュール、転送単位変更、arena増量、復調分担変更）は未実施。現時点では、先行queueの実SDK費用と全体メモリを確かめる前に、境界検出や通信仕様まで同時に変えると改善要因を切り分けられないため、先行queueを先に検証する。

## SDKでの追加確認

[Actions 40894324461](https://github.com/kazuki0824/tangviterbi/actions/runs/40894324461)のESP-IDF v5.5.1 API/link probeが成功した。成果物のSHAと入力commitを [provenance.json](sdk/provenance.json) に保存。実ELFでsubmit/reap/packing本体のIRAM配置を確認し、inline定常ループ39命令（8load/5store）も一致した。submit/reapのcalleeを除く命令包絡は101/40命令で、SDK込みの費用ではない。

新queue metadataは2port合計256byte。旧port＋descriptor＋transferの224byteに対し+32byte。ただしSDKが動的確保する送受信queue等の増分は含まず、全受信機のメモリ収容を証明した値ではない。[ELF監査](sdk/audit.json)。
