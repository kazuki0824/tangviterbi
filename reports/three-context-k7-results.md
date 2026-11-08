# ① 3階層・16 ACS・4 clocks K7の実装比較

2026-10-18。**この試作系列は不採用。** 3 contextを機能的には共有できたが、最初のRAM構成は分散RAM上限超過。分割版も速度とK7単独の資源上限を満たさない。9K全方式の不可能性ではなく、この実装構成の結果である。

前回ローカルで未Pushだった試作はworkspaceの自動整理で失われたため、PR8の既存4-context coreから再構成して検証し直した。以前の未保存ログを今回の証拠として流用しない。

## 実装と検証

[generator](../experiments/three_context_k7.py)、[RTL](../rtl/three_context_k7.sv)、[unittest](../tests/test_three_context_k7.py)、[CAD harness](../ci/three_context_k7_evidence.py)。Tの3階層のみ。S用回路やT/S同時共有ではない。

16 ACSで64状態を4 clocksで更新し、contextをslot内で固定する。13-bit modulo metricの旧/新世代をping-pong保存し、前半の更新が後半の旧metricを破壊することを防ぐ。8-bit soft値・zero-weight erasure・全幅tracebackを維持し、hard化・再量子化していない。context 3は受付不可、idle slotはtraceback/outputを進める。入力scheduler/FIFO/depunctureは含まず、出力backpressureには未対応。

2構成について各18432 step（6 epochs×3 contexts×1024）を検査した。独立無限精度oracleと全64 metric・survivor decisionを照合。ランダムsoft/erasure、全5符号率のclean stream、順序切替、idle、停止、slot途中の外部context=3/dirty input、途中resetを検証。既存unknown-state acquisitionと同様、最初の64 bitを除いて出力bitを照合する。ローカル試験でありGitHub CIの合格とは別。

## 測定

GW1NR-LV9QN88PC6/I5、family GW1N-9C、108 MHz目標、seed 1。入力端子は固定、6出力は基板LED端子の1.8 V設定。受信機配線や外部I/O STAを保証するprobeではない。PLLも未実装。

| 構成 | RAM16SDP4 | BSRAM | 配置配線と速度 |
|---|---:|---:|---|
| 32語・2読出しのmetric bank | 288/270 = 106.67% | 4/26 | RAM BEL不足で配置不能。Fmaxなし |
| 上位/下位を16語bankへ分割 | 160/270 = 59.26% | 4/26 = 15.38% | 配線完了、51.926476 MHz。108 MHz未達 |

分割版のroute後JSONはLUT4=2541、ALU=776、実DFF=757、DSP=0。**LUT4+ALU=3317（38.39%）はRAM周辺の使用制限を加算しない下限集計**で、完成回路の資源占有率ではない。FFも757/6480=11.68%は実セルのみ。配置前logにはRAMの予約を含むLUT4=3724、ALU=776、DFF=1717が現れるが、route後JSONと異なる集計段階なので混在させない。20Kの補正式を無検証に適用しない。

K7単独の合格線2096−Iに対して、下限3317だけで1221＋I超過。したがって未確定の周辺補正を楽観的に0としても、この版をK7だけの縮小で採用できない。旧K7 3706との差389を完成受信機の確定削減とは扱わない。

4 clocks/stepの算術必要clockは100.848485 MHz。実測51.926476 MHzなら最大12.981619 Mstep/sで、T要求25.212121 Mstep/sに不足（保守/仲裁をまだ引く前）。クリティカルパスはsoft/erasure選択から枝メトリック・ACSへの組合せ経路を含み、logic 8.72 ns＋routing 10.54 ns。CDCはこのcore内に存在しないので、内部CDC削減ではこの失敗を救えない。

[2読出し版の証拠](three-context-k7-dual-read/summary.json)／[分割版の証拠](three-context-k7-split/summary.json)。生成RTL、constraints、CADログ・netlistを同directoryへ保存（大きいファイルはgzip）。`generate(False)`と`generate(True)`で各dutを再生成可能。

## 次の判断

- この版への単純なFIFO追加やclock変更を中止する。1段追加して5 clocks/stepにすれば必要126.060606 MHzへ上がるため、pipeline追加だけを救済としない。
- 次の比較対象は、枝メトリック生成を先行/重畳して4-clock実効間隔を維持する構成と、metric/traceback保存の複合再設計。K7だけで2096−Iを満たさないなら、FFT/RSとの複合削減を同時に測る。実装前に満たしたと扱わない。
- ①の外付NOR内T/S別bitstream、S用image全変調/TMCC/有限queueの未達は維持。②の同時T/S共有による削減を①へ二重転用しない。
- native I10/Q10、FPGA→SoC指令のみを維持。FPGA入力はsoft pair＋erasure＋context、出力はFPGA内の後段へdecoded bit＋context。SoCへ戻さない。この候補は性能段階で落ちるため、外部通信路の正式割当は0。既存全候補/全通信路の台帳を変更して成立扱いにしない。
