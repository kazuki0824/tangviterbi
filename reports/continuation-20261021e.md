# ②：FF通過用LUTの計上漏れを訂正し、保持共有を追加

**前回の「部分回路の資源超過は解消」は撤回する。**
19353というpack集計自体は正しいが、配置後に追加されるFF入力用LUTが未計上だった。
固定netlistを今のnextpnr backendで配置するための楽観的下限は21634で、容量20736を898超える。
観測回路を除いた値であり、probeだけが原因ではない。

追加した2案は有限競合期限を維持したが、最良でも下限20844、108枠超過。
①停止、完成受信機・正式通信路の採用0。②全方式不可能は証明していない。

## 原因と下限の範囲

測定と同じnextpnr commit `e2fe86b3ce6feaa3f09d8db5c0971c1cda3fc641`を取得して読んだ。

- `slice_valid`はFFのDが同じ場所のLUT FまたはALU SUMと一致することを要求する。
- その出力とFFを同じ場所に置けるのは1組。FF間のシフト、hard block出力、同じDを複数FFへ分岐する場合等は、別の通過用LUTを必要とする。
- `create_passthrough_luts`は配置後に呼ばれる。従来のpack-only集計には、まだ生成されていないLUTが含まれない。
- RAM16SDP4用の実体4 LUTはpack済みnetlistに既に含まれる。残り4 LUTのblockerだけを加算する従来のRAM計数は維持し、RAMを二重加算しない。

[固定commitの配置規則](https://github.com/YosysHQ/nextpnr/blob/e2fe86b3ce6feaa3f09d8db5c0971c1cda3fc641/himbaechel/uarch/gowin/gowin.cc)
／[RAM pack処理](https://github.com/YosysHQ/nextpnr/blob/e2fe86b3ce6feaa3f09d8db5c0971c1cda3fc641/himbaechel/uarch/gowin/pack_luts.cc)
／[該当箇所とsource hash](gowin-ff-site-contract.json)。

計算は、各Dネットについて `max(0, FF数 − 対応する既存LUT/ALU出力数)` を足す。
CE/reset型・信号の一致、ALU隣接、FFを置けないLUT位置、配線・タイミングの制約は緩めている。
したがって固定netlistに対する**楽観的下限**である。

これはこのbackendの配置規則に対する判定であり、別RTL、再合成、別mapping、別toolを含む
全実装の下限ではない。SA異常終了の直接原因まで特定したわけでもない。
一方、現在の固定netlistは下限だけで超過するので、同じ回路のseed探索を続ける必要はない。

## 再計算と検算

| 接続済み部分回路 | 従来pack集計 | 最小追加LUT | 必要枠の楽観的下限 | 容量超過 |
|---|---:|---:|---:|---:|
| 初期固定case | 21358 | 3049 | 24407 | 3671 |
| LOAD/scatter共有 | 21406 | 2329 | 23735 | 2999 |
| 16-bitシフト統一 | 20427 | 2329 | 22756 | 2020 |
| 直接引渡し | 19597 | 2281 | 21878 | 1142 |
| 直接引渡し＋2-cycle grace | 19353 | 2281 | 21634 | 898 |
| 今回：送出用とも保持共有 | 18596 | 2281 | 20877 | 141 |
| 今回：さらに整列条件を明示 | 18576 | 2268 | **20844** | **108** |

全行、観測probeを除外。最後の行でも100.52%であり、未実装stageを追加する前に超過する。
108だけ削れば全受信機が収まるという意味ではない。
最良案の観測probe込み下限は22914で、観測回路の縮小だけでも解消しない。
BSRAM18、DSP6は前回と同じ。最良案のFF位置はblocker込み10426。

配線済みの既存結果2件で検算した。

| 既存回路 | 新計算の下限 | 配線後実測 | 追加通過LUT実測 |
|---|---:|---:|---:|
| 直接引渡しタイル単体 | 8245 | 8245 | 899 |
| 旧FFT/共有K7統合 | 14041 | 14175 | 1538 |

前者は追加899個まで一致。後者は下限が実測を134下回り、下限と実測を同じものとして扱っていない。
配線後netlistでは未対応FF入力が0となることも確認した。
従来の**配線完了後**の数値（単体178.986938 MHz、旧FFT146.220200 MHz等）は、この訂正で無効にはならない。

[検算記録](ff-site-validation/summary.json)／[下限計算](../ci/gowin_ff_site_audit.py)／
[配置前gate](../ci/gowin_ff_site_gate.py)／[4 unittest](ff-site-audit-tests.log)。
新gateはcore下限超過で終了2、probeのみ超過で終了3。終了0でも配置・速度の合格とはしない。
元の計測スクリプトは過去証拠のhashを維持するため書き換えていない。次の配置試行では新gateを先に通す。

## 追加したRTLと期限

`t_time_tile_dma_onebuffer.sv`は、LOAD/bypass保持とSDRAM送出の768-bitレジスタを共有する。
前のbypassがtileへ未受理の間は、次のgather結果による上書きを禁止した。
先読みとtile内部保持は残し、RAMポートを増やしたとは仮定しない。

`t_time_tile_dma_aligned.sv`は、既に要求していたscratch/stride/ringの32-byte整列を
レジスタ入力の定数bitとして明示する。read開始は従来どおり2-byte整列。
最大prefix30 bytes＋payload96 bytes＝126 bytesなので、read bufferの未使用上端16 bitsも除く。
有効なdescriptorのデータ、順序、6個の8-bit soft値は変更しない。

| 条件 | 新2案それぞれの結果 |
|---|---|
| 最大Mode3の312 tiles | 出力119808 words、write29796件のaddress/payloadが全て一致 |
| 時間DI完了 | 2559092 clocks、期限2566080まで6988 clocks余裕 |
| 他5 client | 全宣言期限違反0。全clientのfinish/lateは前回graceと一致 |
| I=1・全96遅延クラス・全偶数byte offset | 各6 tiles、2304 words、573 writesが一致 |
| FPGA資源gate | 新2案ともcore下限超過。配置配線へ進めない |

値の照合は実SDRAM controller/arbiterと独立メモリoracleを使う。
S/FFTの競合は要求proxy、descriptor供給はtestbench。cold-fill、全mode/階層/実到着列の長期保証ではない。
今回の資源gate不合格を、有限期限の不合格へ読み替えない。
新2案の統合Fmaxは測っていない。別案の単体clockを流用しない。

[保持共有の全期間](t-time-tile-dma-onebuffer-full.json)／[全offset](t-time-tile-dma-onebuffer-offsets.json)
／[整列条件明示の全期間](t-time-tile-dma-aligned-full.json)／[全offset](t-time-tile-dma-aligned-offsets.json)。

## 現在残るボトルネック・未確認事項

| 項目 | 現在の状態 |
|---|---|
| FPGA面積・合法配置 | 最良の固定netlistでも使用backendの下限が108枠超過。他stageの追加前。別保持方式・mapping等の変更が必要 |
| 統合clock | 新案は面積gate不合格で未測定。従来実FFT統合の最良146.220200 MHzはK7のstallなし最低152.626638 MHzおよび設計154.285714 MHzへ未達 |
| 時間DI全体 | 実tileと今回有限競合期限は通過。全tile descriptor、3buffer役割交代、cold-fill有効性のRTL接続は未完了 |
| 全受信stage・全体資源 | FIR/同期/TMCC/等化/demap/完全なT・S DI/RS/TSを一貫して接続・検証した完成netlistはない |
| 長期・動的期限 | 全mode/I/rate/最大3階層/位相、実stage到着包絡、RS burst、選局・再同期・停止/reset、最終TS期限が未検証 |
| S3処理能力 | 通常S経路のCPU高費用モデル106.8042%/106.6197%は超過。実無欠落取得・可逆packing・搬出、DMA/IRQ競合、core別WCET、専用GPIO費用は未確認 |
| SoC/FPGA物理経路 | 帯域算術のみでは成立しない。20Kピン割当・搭載負荷・PHY・独立clockの同期とlane整列・保持量が未確認 |
| SDRAM IO | pad/tri-state/PLL位相/min-max制約を含むsetup/hold検証が未完了 |
| RF・実機 | 必要帯域/CN、外部変換/LNB、実S3連続取得、RF→TS誤り率・無欠落が未確認 |

現在の障害へ戻さないもの：共有K7状態回路の不存在、serviceのみのclock未達、3buffer容量と
モデル所有権未検証、実tile回路の不存在、今回の有限競合条件の期限超過。
**資源超過だけは「解消済み」という前回判断を訂正する。**

## 未完了と今回の中断点A/B

Aは、配置失敗につながる資源計上漏れを特定・検算し、新2案を実装して同じ値・期限・資源gateまで
比較し、その結果をPRへ反映した地点。前回のBのうち原因調査は進んだが、合法配置・clock確定には到達していない。

次の合理的なBは、tile内部とDMA間の幅広コピー／保持をさらに減らす構造、または別mappingを作り、
この下限gateを通した上で同一構成の配置配線・clockと値・期限を検証する地点。

Aで返す理由は、現在の固定netlistについて配置探索を続けても必要枠の下限超過を解消できず、
次は回路構造・mappingを変更する別の比較が必要と判定したため。Bへ着手することが禁止されている、
追加のユーザー許可が必要、という理由ではない。今回は不採用理由と修正範囲を確定する境界を選んだ。
これは依頼全体の完了を意味しない。上表の未完了作業は残り、全受信機を成立とする品質には達していない。
①停止を維持し、②全方式不可能へ一般化しない。

[全7固定netlistの再集計・試験記録・hash](continuation-20261021e.json)。
