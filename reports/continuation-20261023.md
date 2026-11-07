# ②：巡回順マスクの登録と停止判断の訂正（2026-10-23 JST）

①/PR8は停止維持。②のFPGA→SoCは指令のみ、品質を落とす追加software decimation/requantizationなし。
前回の部分fixture最良はclient-lookaheadの142.694061 MHz。正式受信機・経路の採用0。

## 秒数を置く合理性への回答

[訂正の全文](exploration-stop-policy.md)。以前の「他へ時間を配分する」は一般論であり、
この環境で経過秒数だけの自動killを必要とする根拠にはならなかった。
1800秒は前回1759.65秒を参考に丸め、3600秒は倍に延長しただけで、収束保証や利用者の予算から導いた値ではない。
環境の実在する強制上限、承認拒否、資源逼迫を確認したわけでもない。
今回の配置配線runnerから経過時間による自動killを除いた。30秒は状態観測間隔であり終了条件ではない。
停止する場合は、実際の進行・資源・優先する検証と比較して理由を保存する。
有限試験に継承された480秒のhost watchdogは受信期限ではなく、時間切れなら未完了と扱う。
過去のcollectorは再現性のためそのまま保存し、過去の時間切れを不可能判定へ読み替えない。

## 今回の変更と検証

前回の実最長経路がrr[1]→controller.stateだったため、rrを組合せ回路で優先maskへ復号する部分を取り除いた。
代わりに、同じ要求受理edgeで次の優先maskを保存する。resetでは11111。
要求元0/1/2/3/4を受理したら11110/11100/11000/10000/11111へ更新し、FFT受理では保持する。
lease、grace、FFT優先、stall時のowner固定、応答所有権、client別row先読みは維持。
レジスタ表現を変更したが、要求にpipeline cycleを追加していない。

- 通常module/metadata moduleとも、前回lookahead版とYosys sequential equivalenceを確認。各663 equivが証明済み、未証明0。
- 312 tiles・競合ありの実controller/タイルDMA試験を実行。119808出力words・29796 writesが独立oracleと一致。
- 6 clientのfinish/lateが前回と完全一致。時間DI完了2562998、宣言期限2566080、余裕3082 clocks。
- S/FFT背景は負荷proxyであり、全stageや実到着列を再現した試験ではない。
- 合成/pack位置下限19614/20736、FF8673。先読み版の19604/8672に対し位置10・FF1増。
- 同じtoolchain/binary/chipdb/seed1、恒等LUTと同期制御移動、互換FF二組制約を使用。ハードウェア合法性・目標周波数は緩めない。
- 新合成collectorもtimeout=None。実行後に未使用の秒数引数だけを整理し、実行時sourceとhashを保存した。

[形式等価性](controller-cursor-mask/equivalence.log)／[有限試験](controller-cursor-mask/finite.json)／[合成資源](controller-cursor-mask/mapped-result.json)。

## 配線完了後の結果

時間上限なしで1174.40秒後に配線完了。終了1は**速度不合格**によるもので、timeoutや配線未完了ではない。

|項目|前回client-lookahead|今回cursor-mask|
|---|---:|---:|
|配線後MHz|142.694061|**152.091263**|
|物理位置 /20736|19623 (94.63%)|19627 (94.65%)|
|FF|8672|8673|
|設計154.285714 MHz|未達|未達|
|K7最低152.626638 MHz|未達|未達|

pack下限は10位置増だったが、配置後の追加恒等LUTが19→13に減ったため、物理位置の実増分は4。
配線後の最長経路は、K7のmetric RAM read→ALU chain→survivor_hi入力FFへ移った。
名前の長いlaunch FFだけから機能を推定せず、実際のRAD/DO/ALU/FFのarc列で分類した。
11個のlogic arcにはRAM readとALUが含まれ、11 LUTという意味ではない。
CLK→Q 0.231＋logic2.815＋routing3.494＋setup0.035＝**6.575 ns**。
設計周期6.481481 nsまで**0.093519 ns**不足。K7最低にも0.535375 MHz不足している。
最長の単独配線はmetric RAM出力→ALU入力の1.509 ns、launch→RAM addressも1.344 ns。
次はこの配置近接性・アドレスfanout・演算経路と近接する未達経路を調べる根拠になるが、そこだけ直せば必ず合格するとは言えない。

前回の仲裁経路は今回の最長ではない。ただし最長経路一本のレポートだけで、仲裁器を含む他の全経路が154.285714 MHzを満たしたとは断定しない。
過去の別構成のK7比較式書換え失敗を遡って合格にせず、今回の新しい配置・接続条件と区別する。
対象はprobeを含む部分fixture。同一seedで得た配線後STAであり、実基板/全受信機/全clock・IOの合格ではない。

[配線結果](controller-cursor-mask/route-result.json)／[独立検算とhash](controller-cursor-mask/audit.json)／[生ログ](controller-cursor-mask/route.log)。

## 今回の停止・区切り

配置配線はツールが完了したため終了した。こちらが秒数や未配線数を理由に途中停止した実行は今回ない。
開始時のメモリ・ディスクに逼迫を観測していない。一度ps監視コマンドが失敗したが、配線進行は継続し、計算失敗や資源不足へ読み替えていない。
[観測記録](controller-cursor-mask/monitor-observations.json)。

今回Aは、前回Bとして挙げたcursor decode変更について、形式等価性・有限期限・資源・配線後速度・新しい最長経路の検算とPR保存まで終えた地点。
次のBはK7のRAM read→ALU→survivor書込み経路について、近接する他の未達経路も確認し、配置または回路を変えて同じ統合構成の配線後速度と機能/期限を再検証する地点。
Aで返す理由は、対象の仲裁経路変更が検証済みになり、次の変更対象がK7のmemory/ACS側へ移ったため。
この先はcontext状態、metric更新、survivor生成の契約を再確認する別の検証単位で、前回の仲裁等価性証明をそのまま流用できない。
Bまで続けることは可能であり、実行時間上限や環境障害に阻まれたわけではない。今回は検証済みの変更境界で結果を保存して共有する判断。
気分による実行中断ではないが、全残タスクの完了、探索終了、②全方式不可能を示すものでもない。未完了範囲は以下に残す。

## 現在の未完了範囲

|対象|現在残るもの|
|---|---|
|部分統合の実時間速度|今回152.091263 MHz。最長はK7 metric RAM→ALU→survivor FF。154.285714 MHzとK7最低152.626638 MHzへの到達。有限cycle試験だけでは実時間通過にならない|
|全FPGA回路|FIR/同期/GI/TMCC/等化/demap/完全なT・S DI/RS/独立TS×2の接続・精度・全体資源と全clock STA|
|時間DI|全体descriptor供給、3buffer役割交代、cold-fill有効値管理のRTL接続|
|全条件の期限・保持|全mode/I/rate/最大3階層/到着位相/RS burst/停止・選局・再同期・reset/最終TSの長期・動的期限とqueue最大滞留|
|ESP32-S3×2|高費用CPUモデル106.8042/106.6197%超過。実無欠落RF取得、可逆packing、DMA/IRQ/RTOS、core別WCET、内部RAM等の実測不足|
|通信PHY|算術18経路組合せのpin・搭載負荷・lane skew・独立clock同期・保持/creditの実装と実性能。今回の内部変更で帯域算術は変わらない|
|SDRAM IO|pad/tri-state/PLL/jitter/min-max setup/holdを含む基板条件STA|
|RF→TS実機|外部変換/LNB/フィルタ/CN/MER/BER、S3連続取得、2系統同時の無欠落TS|

確認済みの共有K7状態保持、scratch容量・限定所有権、onehot有限cycle期限、基準部分fixtureの合法配置を再び未達として列挙しない。
内部common clockではCDCは不可避ではないが、独立S3 PHYとの同期は別に未確認。
全分担・境界・経路の台帳とレビューゲートは[前回報告](continuation-20261022c.md)を継承する。
