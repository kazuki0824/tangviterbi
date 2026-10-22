# ②：受信DMAの更新回路を変更し997枠削減、統合配置は未達

**onehot更新版は値・有限期限を保ったまま、probe込み必要LUT位置下限を20401から19404へ減らした。ただし2条件とも合法配置に到達せず、統合Fmaxは未取得。**
①停止、正式受信機・通信路の採用0を維持する。②全方式不可能の証明ではない。

## 今回の比較

全行は同じcompact BRAM probeを含む集計。capacityは20736。
FFの入力に必要な通過LUTとRAM blockerを加えた楽観的下限であり、実配置の占有率ではない。

| 受信DMA | 全fixture FF | pack＋RAM blocker | 最小追加LUT | 必要枠下限 | 容量までの余裕 | 時間DI完了 | 期限余裕 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 前回heldearly |8662|17501|2900|20401|335|2562998|3082 |
| 保持共有sharedhold |8150|18730|2388|21118|−382|2596936|−30856 |
| **排他的更新onehot** |8662|16504|2900|19404|1332|2562998|3082 |

sharedholdは読出し1008-bit保持の下位512 bitsを送出保持にも使う。
前の読出しの整列・scatter完了を待ってから次の送出データを捕捉する。
FFは512減ったが選択回路を含むpack値は1229増え、総下限は717増えた。
値は全一致するものの期限も30856 clocks超過するため棄却。配置探索は実施しない。

onehotはheldearlyの保持量と処理順序を変えず、read_bufferの更新を4区間へ分けた。
各区間の更新元を「16-bit位置合わせシフト」または「該当BL8応答」として明示し、
マスクしたデータのORで更新する。双方0なら保持する。6個の8-bit soft値はそのまま。
読み応答はoutstanding要求に対応し、整列中には次のreadを発行しないという既存契約を使う。
無関係なrsp_validを外から注入するなど、契約違反時の全状態等価性を主張しない。

probe179 FF、11 BSRAM、21 ALU54Dは変更していない。
onehotの全fixtureはBSRAM29/46、MULT18位置換算48/48（うちprobe42、receiver6）。
FF位置はFF8662＋RAM blocker1638＝10300/15552で前回と同じ。
純粋なreceiver資源をprobe込み値と混同しない。

## 値・期限・更新条件の確認

- 両新案とも最大Mode3/I4、312 tiles、出力119808 wordsと29796 writesが独立byte oracleと一致。
- sharedholdは他5 clientの期限違反0、時間DIだけ1回違反。unittest exit0でも採用しない。
- onehotは6 client全て期限違反0。各clientのfinish/late記録もheldearlyと完全一致。
- onehotのI1全96遅延クラス、全偶数byte offset 0..30では、2304 words／573 writesが一致。
- 同じI1条件で、シフトと応答捕捉が同時に成立しないassertionも通過。有限試験であり全状態形式証明ではない。
- source hashを照合し、比較JSONを生成。競合S/FFTは負荷proxyであり、全受信stageの機能試験ではない。

[最大条件のログ](t-time-tile-dma-onehot-tests.log)／[更新条件assertion](t-time-tile-dma-onehot-contract.log)
／[棄却案ログ](t-time-tile-dma-sharedhold-full.log)／[集計・hash](continuation-20261021h.json)。

初回の生成用PythonにSyntaxErrorがあり、RTL作成前に停止した。その直後の試験・collector呼出しは
未作成ファイルで失敗した。setup-failureログを残し、生成スクリプト修正後に上記全測定を実施した。
未作成ファイルの失敗をRTL機能不合格として数えない。

## 統合配置

固定tool、seed1、154.285714 MHz目標、heap、cell探索上限10001回、壁時間上限300秒。
LUT・FF・DSP・RAMの合法性規則とtiming条件は変更していない。

| 条件 | 必要枠下限 | 結果 |
|---|---:|---|
| onehot通常配置 |19404|exit125、dut.fft.in_valid_DFFRE_Qの配置10001回で失敗 |
| 同じonehot＋恒等LUT事前挿入 |19404|exit125、ff_input_identity_127の配置10001回で失敗 |

後者は2900個の恒等LUTを事前に入れ、最小追加LUT=0、pack=19404となる。
既存の変換器で逆変換が元netlistへ戻ることを確認している。
両方とも配線未完了・Fmaxなし。壁時間上限・自動承認・ホスト容量不足ではない。
失敗セル名は探索終了地点であり、根本原因がそのセルだという証明ではない。
1332枠の楽観余裕があっても、FF制御共有・隣接・carry・配線制約を通せる保証はない。
未実装stage追加前の部分receiverであるため、この余裕を完成受信機の余裕とも呼ばない。

[通常配置](shared-receiver-fft-tile-onehot-route/summary.json)
／[事前挿入配置](shared-receiver-fft-tile-onehot-prebuffer-route/summary.json)。

## 現在残るボトルネック・未完了


| 項目 | 現在の状態 |
|---|---|
| 統合合法配置・全体資源 | probe込みの下限超過は回避できたが、実配置は未達。今回fixtureはLUT下限93.58%、DSP全使用。receiverだけの配置、残stageを含む全体資源は未確定 |
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
今回onehot版は受信回路を変更したため、値・有限期限を再試験した。SoC側の処理や通信方向、soft値精度は変えていない。

## 未完了と今回の区切りA/B

Aは、受信側の保持共有案と更新選択回路変更案を比較し、値・期限・資源・2条件の統合配置を確定してPRへ反映した地点。
前回Bの「受信側の追加削減」は997枠の削減まで進んだが、合法配置・統合clockの達成は未完了。

次の合理的なBは、固定netlistのFF制御共有・隣接制約と配置探索の失敗を具体的に切り分け、
その結果に基づくRTL/mapping変更で合法配置・統合clockを再確認する地点。
Aで返す理由は、今回の2変更について採否と根拠を確定でき、次は面積総数の削減だけではない配置制約の診断へ作業対象が移るため。
同じnetlistでseedだけを増やす試行はここでは選ばない。追加許可待ちでも、全残作業が実機待ちでもない。
Bまで継続する選択も可能だが、未診断の配置制約を原因と断定して場当たり的なRTL変更を追加せず、検証済み差分を固定する区切りを選んだ。
今回の比較の値・期限・出典hash・失敗結果の保存は完了しているが、全依頼と受信機の完成品質は未達。
