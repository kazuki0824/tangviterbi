# ② 深さ2の送信queue候補と同費用の期限評価

**候補実装を追加し、条件付き模型ではS5/16・準備2048語で20000bankを通過した。実機成立や全SoC費用確定ではない。**

## 実装

`experiments/s3_raw_queue.c/.h` に、専用SPI device・queue_size=2・固定transaction 2個を実装した。固定header/flagsを初期化時に準備し、送信時はoffsetとpayload pointerを更新する。2本のportを同じownerが操作し、SPI IRQ affinityは起動側が設定する。FPGA→SoC payloadは追加しない。

後続転送が動いていても先行結果を回収するため、既存の「running command中は結果queueを見ない」guardは使わない。SDKから正しいtransactionが返るまでdescriptorもpayloadも保持し、packの連続prefixだけを退役させる。queue失敗や異なる完了pointerはfaultを固定してleaseを保持する。自動retry・無断再利用はしない。旧API・既定受信taskは変更せず、独立した候補として追加した。

実Cの所有権検算で、2個投入、満杯時のtake抑止、先行完了時の後続保持、2port間の順不同完了、失敗時lease保持、誤完了pointerを確認した。

## 同じ費用での評価

host模型は新queue adapter本体と既存packing/native Cを実行する。SDKの次転送自動開始はモデル化し、旧SDK開始/完了費用を各転送へ課す。完了IRQ内の次転送開始費用が終わるまで線上時間を開始しない。空の結果queue照会は従来のrunning guard42/44cycleではなく230cycleを課す。照会費用の進行中に完了した場合は成功単価との差分も加える。

旧単価を新queueの実SDK監査済み費用とは扱わない。新しい管理費用の感度として、owner反復・成功submit・成功reapへ、それぞれ0/100/300cycleを追加した。追加0は費用増がないという仮定である。通常IRQ・tick・WDTの旧費用は保持。inline packingの削減はまだ加えない。

- S5/16、現行順序PCABとBCPA、準備2048/3072語は、追加0/100/300cycleの12条件すべて4000bank通過。
- S6/16では不成立条件が残る。S5/16へCPU分担を寄せる候補を優先する。
- 本番準備1024語のままでは不成立。2048/3072語は候補条件であり、既定値を無検証で変更していない。
- S5/16・PCAB・準備2048語・各追加300cycleは20000bank、6.187秒を通過。arena最大124600/131072byte（残6472byte）、RF監視最大78.717µs、両coreでWDT更新各2回を含む。

有限通過は無期限保証ではない。追加window例外、ハード/メモリ待ち、指令受信、最終アプリ差分は残る。queueを増やした場合の実SDK全経路・queueメモリ・割込み競合と全受信機のfitを別途確認する。API/link確認用のSDK probeも追加したが、RF起動・128KiB arena・受信taskを含む完成アプリではない。

[通常条件](runtime.json)、[20000bank](extended.json)、[検算](tests.log)。再現：`python -m experiments.s3_queue_runtime`、`python -m experiments.s3_queue_runtime --extended`。元模型との比較は [送信停止原因](../s3-tx-idle-study/README.md)。

## 改善案の扱い

優先度1の先行queue投入と優先度2のinline packingを候補実装・検算まで進めた。優先度3以降（sentinel削減、動的スケジュール、転送単位変更、arena増量、復調分担変更）は未実施。現時点では、先行queueの実SDK費用と全体メモリを確かめる前に、境界検出や通信仕様まで同時に変えると改善要因を切り分けられないため、先行queueを先に検証する。
