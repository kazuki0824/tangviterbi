# ②：観測回路の容量超過を減らし、統合配置を6条件で確認

**probe込みの必要枠下限を容量内へ収めたが、統合配置・配線・clockには到達していない。**
受信回路を削除した結果ではない。①停止、完成受信機・正式通信路の採用0を維持する。
今回の失敗は②全方式不可能の証明ではない。

## 実施したことと結果

前回の早期解放DMA、FFT、SDRAM service、T最大3階層＋S共有K7は変更していない。
新3種probeで、probeを外して合成したreceiver coreのJSONが前回と完全一致することを検証した。
scan入力の独立性を保つ測定回路を作り、通常の配置規則を使って試した。

| 測定回路／配置条件 | 全回路の必要枠下限 | 20736枠までの余裕 | 結果 |
|---|---:|---:|---|
| DSP保持probe／heap |20671|65|FF配置を10001回試行して失敗、exit125 |
| 未使用scan位置除去／heap |20556|180|FF配置を10001回試行して失敗、exit125 |
| 同上／SA |20556|180|初期配置中に異常終了、exit−11 |
| さらに観測保持をBRAM化／heap |20401|335|FF配置を10001回試行して失敗、exit125 |
| 同上＋通過LUT事前挿入／heap |20401|335|LUT/FF組の配置を10001回試行して失敗、exit125 |
| 同上＋通過LUT事前挿入／SA |20401|335|初期配置中に異常終了、exit−11 |

heap失敗cellは順に `dut.fft.mode_DFFRE_Q_1`、`dut.fft.output_pipe_DFFR_Q_1`、
`dut.fft.in_data_DFFRE_Q_7`、`ff_input_identity_57`。
これらは探索が最後に失敗したcell名であり、そのセル単体を回路全体の根本原因と断定しない。
SAの直接原因も未特定。自動承認レビューやホスト容量不足という結果ではない。
全試行で配置配線未完了、統合Fmaxなし。seedは1、壁時間上限300秒。
heapの失敗はこの壁時間上限ではなく、cellごとの10001回の探索上限によるもの。

面積下限が容量内でも、FF制御の共有、隣接、carry chain、配線などを満たせる保証はない。
今回、そこを実配置で通せなかった。配置器の有限試行失敗を全配置不可能へ一般化しない。

## probeをどう変更したか

1. 入力1632 bitsのうち1134 bitsを21個のALU54Dの出力レジスタへ移した。
   残る498 bitsはfabric FF。入力を同一値に束ねたり、有効な入力を定数化したりしていない。
   出力の384-bit captureを一旦省き、checksumへ直接渡す版を最初に測った。
2. 旧scan列の未接続23 bitsと、実tileが置き換えたBG client 2の312 bitsを除いた。
   後者はcore-mapped netlistでIBUF出力の内部consumerが全て0であると検算した。
   保持対象1297 bitsへの対応は一対一。残る1297 bitsは独立に設定可能。
3. 観測出力の保持をBRAMへ移す版では、384 bitsを11 BSRAMで保持した。
   書込みアドレスを0/1で交代し、反対側から読むため同一アドレス衝突を避ける。
   初期2回分の有効性を管理し、未初期化データをchecksumへ入れない。
   checksumの遅延は旧probeと異なるが、receiver coreへはフィードバックしていない。

ALU54Dはmode2のA＋B＋CASIでB/CASIを0、入力registerをbypass、出力registerを有効とする。
[Gowin UG287-1.4J §4.1](https://cdn.gowinsemi.com.cn/UG287J.pdf)と、使用Yosysのprimitive宣言を照合した。
7000 clocksのscan/hold/resetを独自の限定primitiveモデルで照合し、1632-bit版・1297-bit版とも通過。
これはvendor simulation modelや実機によるDSP検証ではない。
1297-bit版の最初の30秒上限は超過したためログを保存し、120秒上限で再実行して約30.2秒で通過した。
BRAM観測は全384 bitsのwalking-oneと途中resetを照合し通過。
BRAM版のscan回路部分は、試験済み1297-bit版とのソース一致も確認した。

[入力未使用の検算・core同一性・primitive条件](dsp-probe-contract.json)
／[scan試験](dsp-scan-probe-tests.log)／[圧縮scan試験](compact-dsp-scan-probe-tests.log)
／[BRAM観測試験](bram-observation-probe-tests.log)。

## 資源の帰属と集計上の注意

| 資源 | receiver部分／観測回路 | 容量・意味 |
|---|---|---|
| LUT位置 | BRAM観測版の全回路下限20401 |20736の98.38%。実配置の使用率ではない |
| FF位置 | receiver FF8483＋RAM blocker1638＝10121。probe179を加えて10300 |15552の66.23%（probe込み） |
| BSRAM | receiver18＋probe11＝29 |46。probe11を受信処理の必要量へ加算しない |
| DSP | receiver MULT18X18×6＋probe ALU54D×21（MULT18位置42相当） |fixture全体は48/48。receiver自体は6/48 |

probeを付けた配置はDSPを全使用し、観測側の配線・配置制約も加わる。
従って今回の失敗からreceiver部分だけが配置不可能とはいえない。
逆にprobeを除いた下限が容量内でも、receiverの合法配置を確認したことにはならない。

出力captureを省いた版では、合成器がreceiverの5 FFを`digest`で始まる名前へ変更した。
旧collectorの「digest名ならprobe」という分類はassertionで止まり、誤ったcore集計の保存はしていない。
pack自体は成功。失敗段階を[記録](shared-receiver-fft-tile-dsp-probe-pack/collector-failure.json)した。
新集計は**全fixtureをそのまま配置判定**し、参考のcore値もsourceで特定したprobe FFだけを除く。
checksum等のLUTは保守的に残すため、`core_plus_probe_logic`は純粋なcore値ではない。
旧20049というcore下限と、この保守的な値を同じ範囲の値として比較しない。

## 通過LUT事前挿入の検証

nextpnrの`constrain_lutffs`は既存LUTとFFを組にする一方、必要な通過LUTの追加は通常配置後となる。
そこでmapped netlistへ、同一のD値を出すLUT1（INIT=2）を2900個追加した。
元のcell・制御・portを一切削除せず、FFのDだけを恒等LUT出力へ接続した。

- 追加内容を逆変換すると元JSONと完全一致することを検証。
- LUTの真理値表0→0、1→1を確認。
- shared driver、ALU SUMとcarryの区別、制御改変を拒否する3 unittestを通過。
- pack後の最小追加LUTが2900から0へ変化し、全必要枠20401は変わらないことを確認。
- backendの合法性規則・容量・timing条件は緩めていない。

それでもheap／SAのどちらでも配置完了に至らなかった。
この事前挿入を配置問題の解決策として採用したとはしない。
[変換器](../ci/gowin_materialize_ff_inputs.py)／[試験](gowin-materialize-ff-inputs-tests.log)
／[逆変換照合の記録](shared-receiver-fft-tile-compact-bram-probe-prebuffer-route/mapped.identity-proof.json)。

## 現在残るボトルネック・未完了

| 項目 | 現在の状態 |
|---|---|
| 統合合法配置・全体資源 | probe込みの下限超過は回避できたが、実配置は未達。今回fixtureはLUT下限98.38%、DSP全使用。receiverだけの配置、残stageを含む全体資源は未確定 |
| 統合速度 | 今回Fmaxなし。旧FFT統合146.220200 MHzはK7のstallなし最低152.626638 MHz、設計154.285714 MHzに未達。単体164.690384 MHzを統合へ流用しない |
| 時間DI全体 | 早期解放版の312 tiles有限期限は通過済み。全tile descriptor／3buffer交代／cold-fillのRTL接続は未完了 |
| 全受信stage | FIR／同期／TMCC／等化／demap／完全なT・S DI／RS／TSの一貫した接続・精度・全体資源が未確認 |
| 長期・動的期限 | 全mode／I／rate／最大3階層／位相、実到着包絡、RS burst、選局・再同期・停止・reset、最終TS期限が未検証 |
| S3処理 | CPU高費用モデル106.8042%／106.6197%は超過。実無欠落取得、可逆packing、DMA／IRQ、core別WCETは未確認 |
| SoC/FPGA物理経路 | 帯域算術の18組は未認定。通常S経路の余裕3.7135／2.00818 MB/sに対して、ピン・搭載負荷・PHY・独立clock同期・lane整列・保持量が未確認 |
| SDRAM IO | pad／tri-state／PLL位相／min-max setup・holdが未検証。周期とaccessの差はsetup余裕ではない |
| RF・実機 | 必要帯域／CN／外部変換／LNB／実S3連続取得／RF→TS誤り率・無欠落が未確認 |

現在の障害へ戻さない項目：共有K7状態回路の不存在、service単独clock、3buffer容量とモデル所有権、
実tileの不存在、早期解放版の今回有限期限違反、旧候補のcore下限108枠超過。
**旧probe込み1383枠超過も、新probeに対する現在の障害としては書かない。実配置未達は残る。**
受信回路は未変更なので、前回の値・有限期限試験を再利用した。SoC側の処理や通信方向、soft値精度は変えていない。

## 未完了と今回の区切りA/B

Aは、probeを3方式で変更し、省略がないことを検証し、恒等LUTの事前挿入も含め6条件の配置結果を確定してPRへ反映する地点。
前回のBのうち、測定境界の変更と配置試行までは実施したが、合法配置・統合clockの確定には届いていない。

次のBは、receiver側の保持・mappingの追加削減、または観測資源と独立した適切な統合測定方法を用意し、
合法配置と統合clockまで確認する地点。
Aで返す理由は、同じ高占有netlistへseedを追加し続けるより、資源余裕か測定方法を変える検討が必要と判断したため。
Bへ進む許可がない、全作業が実機待ち、という理由ではない。残るRTL・ソフトウェア作業もある。
今回の比較では、不成立・異常終了を含む全結果と適用範囲を確定するところまで進めた。
この比較単位の品質は確認したが、受信機の完成品質には到達していない。全依頼は未完了。

[6条件の機械集計・hash](continuation-20261021g.json)。
