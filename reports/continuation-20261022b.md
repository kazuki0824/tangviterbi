# ②：互換FFの二組クラスタによる配置改善

**②の部分統合fixtureで、互換FFの二組制約により配置・配線まで到達した。配線後99.088387 MHzで目標154.285714 MHzに未達のため、この候補は速度で不採用。**
①は停止を維持。②の正式受信機・通信路採用は0。全方式不可能の証明ではない。

## 今回の変更と検証範囲

固定nextpnr e2fe86b3の通常LUT→FF制約の後に、孤立したLUT/FFクラスタ二組をまとめる実験を行った。
FF型が完全一致し、CLK/CE/SET/RESET/PRESET/CLEARの各接続が一致する組だけを対象とする。
同じ群をLUT名順に並べ、二組の相対Zを0/1/2/3にする。既存のALU・RAM・広幅LUTクラスタは対象外。
根の絶対位置は固定しない。最終的に配置器が通常の全合法性条件を判定する。
これは配置探索を制約するheuristicであり、全合法配置を網羅する方法ではない。

二組制約を追加するpacker変更ではセル・net・パラメータを変えない。RTL、soft値幅、SoC転送量も変更していない。通常backendが配置後に追加する恒等LUTは後述の通り別に集計する。
前回の対象選択式診断以外、gowin.ccの合法性判定は変更していないことをdiffの完全一致で確認した。
公式の同じGW2A-18C chipdbを使用。目標154.285714 MHz、seed1、heap、cell探索上限10000を維持した。

二つのmapped入力それぞれについて、無変更source buildと変更buildでpackを行った。
pack済みcells・ports・netnamesは完全一致。prebuffer版は33,154セルで、packed JSON自体も同一hashだった。
クラスタ制約はこのJSONには保存されないため、この照合は論理graphの保存の証拠であり、物理配置の合法性証明ではない。

prebuffer版は4,058組、同期制御をLUTへ移したfolded版は4,077組の二組クラスタを生成した。
pack時の資源は前回から不変：必要LUT位置下限19,404/20,736、FF8,662、BSRAM29/46。
prebuffer版を配置完了まで進めると恒等LUTが48個追加され、実使用位置は19,452/20,736（93.8079%）となった。
FF実体8,662とRAM blocker1,638を合わせたFF位置は10,300/15,552。追加48個のINITはすべて0xff00で、I3の恒等関数になることを全16入力組合せで検算した。
[配置後の資源監査](placement-compatible-pairs-checkpoint/audit.json)。
DSPは受信回路6 MULT18、probe21 ALU54D（42 MULT18相当）。probe込み48/48換算である。
未実装stageを追加した全受信機の資源数ではない。

## 配置・配線結果

| 入力／配線器 | 上限 | 結果 | 配線後MHz |
|---|---:|---|---:|
| prebuffer／router1 |600秒|配置通過、一般配線途中の時間切れ|未取得|
| 同期制御移動／router1 |600秒|配置通過、一般配線途中の時間切れ|未取得|
| prebuffer／router1 |1800秒|配置通過、一般配線途中の時間切れ|未取得|
| **同期制御移動／router1** |1800秒|**1759.65秒で配線完了、timing不合格のexit1**|**99.088387**|
| 同期制御移動／router2 |当初1800秒|205反復で優先順位変更により中断（exec exit130）|未取得|

router1完了版は、K7の追加stallゼロでの最低152.626638 MHzにも届かない。
最長経路はtile.op名のFF→仲裁器→SDRAM controller.stateで、12段のLUTを通る。
CLK→Q 0.231 ns、logic 5.599 ns、routing 4.227 ns、setup 0.035 ns、合計10.092 ns。
目標6.481481 nsに対し3.610519 nsの短縮が必要。配線後解析であり、実機測定ではない。

配線後のLUT欄は15411となるが、postRouteでblockerセルを除去した表示である。
ALU位置2920とRAMの追加占有1092を加えた物理位置は19423のまま。
4012枠の回路削減と誤認しない。独立auditでFF8662、追加通過LUT19、全位置19423を確認した。
このpartial fixtureの収容確認を、未実装stageを含む全受信機の収容確認へ一般化しない。

router2は34反復時の重複使用266が最良、205反復時832で、171反復にわたり最良値を更新しなかった。
router1の完了・速度未達が確定したため、残る時間を同じ配置の非収束探索へ使うより、測定された組合せ経路の変更を優先すると判断して中止した。
これは自動timeoutでも、router2で全配置不可能の証明でもない。中断後のchild return codeは取得できず、exec sessionのexit130を記録した。
最初のPID直接signalはProcessLookupErrorで届かず、所有exec sessionへのCtrl-Cで停止した。結果・ログhashは固定済み。

[配線後の検算](placement-compatible-pairs-folded-extended/audit.json)
／[router2中止理由](placement-compatible-pairs-router2/intentional-stop.json)
／[全結果の集計](continuation-20261022b.json)。

## 配置後の推定経路の診断

配置だけでは固定版nextpnrのJSONレポートにfmax/critical_pathsが保存されなかった。
別の診断binaryで、通常pack・配置の後に既存timing_analysisの結果保存を呼び出した。
activeな配線用binary・source・objectを変更せず、command.ccのコピーと別object/binaryを作った。
診断追加前後のprebuffer配置済みcells・ports・netnamesは完全一致。ハードウェア合法性判定も変更していない。
保存済み配置をno-pack/no-placeで再読込みする初案はbackend初期化assertion（exit−6）で失敗したため、通常pack・配置を通す方法へ修正した。失敗ログも保存。

| 条件 | 配置後の使用位置 | 追加恒等LUT | 推定MHz | 最長推定経路のLUT段数 | CLK→Q＋logic＋setup | 推定配線 | 推定clock skew |
|---|---:|---:|---:|---:|---:|---:|---:|
| prebuffer |19452|48|63.395462|11|5.174 ns|7.0 ns|3.6 ns|
| 同期制御移動 |19423|19|88.920502|12|5.646 ns|4.6 ns|1.0 ns|

目標周期は6.481481 ns。各行の遅延合計の逆数とfmaxを検算した。
**いずれも配線前の予測であり、専用clock配線前のskew予測を実際のclock skewとは呼ばない。**
またセル内遅延は「推定最長経路」の内訳であり、全経路の配線遅延をゼロにしたときの最長経路を探索した結果ではない。
この表から全経路の論理遅延合格や配線後Fmaxを主張しない。

prebufferの経路はtile.aligningから仲裁器を経てcontroller.stateまで。
始点sourceはt_time_tile_dma_onehot.sv、終点sourceはdual_sdram_refresh_predecode.svに対応する。
同期制御移動版の推定経路はtile.phase名のFFから同じcontroller.stateまで。
次のRTL/mapping検討対象として、DMA要求→仲裁→controllerの組合せ経路が具体化した。
単純なレジスタ追加は有限期限の余裕3082 clocksを損ね得るため、遅延を増やさない組合せ再構成、または処理待ちに隠せるbuffer化を値・全client期限で再評価する必要がある。

[経路・遅延・資源の検算](placement-compatible-pairs-timing/comparison.json)。
診断collectorの初版には、実入力mappedではなく未使用checkpoint参照をinput_sha256として記録する誤りがあった。
元metadataと使用runnerを保存し、保存commandから実入力hashを訂正した。配置・経路・数値は変更していない。

## 現在残る障害・検証不足

| 対象 | 現在の状態 |
|---|---|
| 物理実装・全体資源 |同期制御移動＋二組制約で部分fixtureの配置配線と19423位置への収容を確認。旧「配置不能」はこの候補の現障害から除く。未実装stage込み全体資源は未確定 |
| 統合速度 |配線後99.088387 MHz。設計154.285714 MHz、K7追加stallゼロの最低152.626638 MHzとも未達。DMA→仲裁→SDRAM制御の最長経路10.092 nsが今回の測定上の律速 |
| 時間DI全体 |設計クロック前提のonehot 312 tiles有限cycle期限は通過済み。99.09 MHzでの実時間期限合格を示さない。descriptor供給、3buffer交代、cold-fill有効値管理の全体RTL接続は未完成 |
| 全受信stage |FIR／同期／TMCC／等化／demap／完全なT・S DI／RS／TSの一貫した接続・精度・資源が未確認 |
| 長期・動的期限 |全mode／I／rate／最大3階層／位相／実到着包絡／RS burst／選局・再同期・停止・reset／最終TS期限が未検証 |
| S3処理 |高費用CPUモデル106.8042/106.6197%は超過。実無欠落取得、可逆packing、DMA/IRQ、core別WCETは未確認 |
| SoC/FPGA物理経路 |帯域算術の18組は未認定。通常S経路余裕3.7135/2.00818 MB/sに対するpin、搭載負荷、PHY、独立clock同期、lane整列、保持量が未確認 |
| SDRAM IO |pad、tri-state、PLL位相、min-max setup/holdが未検証。周期とaccessの差はsetup余裕ではない |
| RF・実機 |帯域/CN、外部変換、LNB、実S3連続取得、RF→TS誤り率・無欠落が未確認 |

既に通過した共有K7の状態保持、service部分のclock、三つのscratch容量・モデル所有権、onehotの有限期限を、現時点の失敗原因に戻さない。
FPGA→SoCは指令のみ。追加のソフトウェア間引き・再量子化は行わない。


## 未完了と今回の区切りA/B

今回Aは、前回Bだった互換FFの割当変更を実装し、二netlistのgraph保存、配置後の追加LUT、通常配線器の完了・timing不合格、別配線器の非収束中断、推定値と配線後値の差まで検算し、PRへ保存する地点である。
前回の「合法配置未達」を、この候補について「配置配線成立・速度不足」に更新できた。

次の合理的なBは、DMA要求→優先選択/lease/grace→controllerアドレス判定の組合せ段数、または同制御群内の配置近接性を変更し、同じ有限データ・全client期限・全位置・配線後clockを再検証する地点。
今回のpairingはLUT名順であり配線近接性は最適化していない。
参考として、異なるFF名prefix同士の組はprebuffer106、同期制御移動237だった。ただし名前の違いは実機能の帰属や混雑原因の証明ではない。
[組数・名称上の近接性の監査](placement-compatible-pairs-timing/locality.json)。

Aで返すのは、配置制約だけの変更について結果を確定し、次に直す対象が配置拒否ではなく組合せ経路の速度へ変わったことを、検証済みの状態で共有する判断による。
Bまで続ける選択も可能だが、単なる配置再試行と異なり、制御経路の変更は有限期限の余裕3082 clocksや所有権に影響し得るため、機能・期限・面積・clockを一組にした次の検証が必要になる。
この因果関係を混ぜずに今回の比較を確定する境界で返す。外的な必須停止理由や追加許可待ちがあるという意味ではない。

全依頼は未完了。上の表の全体実装・期限・S3・物理経路・SDRAM IO・RF実機確認が残る。
router2の最終収束/速度も未確認だが、理由を記録して探索対象から一旦外した。
今回の数値・graph・出典・中断理由の品質は監査済みであり、受信機全体の完成品質を満たしたとはしない。
