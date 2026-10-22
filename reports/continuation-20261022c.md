# ②：仲裁・行判定の4案比較（2026-10-23 JST）

基準commitは33f93d04f5e733b1cacfe24b2885d09f48d16e41。①とPR8は停止を維持。
FPGA→SoCは指令のみ、品質を落とす追加ソフトウェアdecimation/requantizationなし。
今回の変更はFPGA内部の仲裁判定またはSDRAM row判定だけで、soft値幅、保持量、SoCとの情報種別・転送量・経路候補は変更しない。
正式受信機・通信路の採用は0。全方式不可能の証明ではない。

## 変更と値・期限

- parallel：マスク付き／通常優先encoderを並列に計算し、lease、2-cycle grace、FFT優先の上書きを論理式でまとめた。
- matrix：各要求元に先行する要求元のmaskをrrから生成し、5個の選択判定を並列に計算した。lease等はparallelと同じ。
- bank-parallel：仲裁器は基準のまま、4 bankのrow一致を並列に計算してから選択。open-page/refreshの挙動は変更しない。
- 元のSELECT直接発行、stall時の所有権固定、応答消費までのowner保持、最大128要求lease、FFT優先を維持。レジスタ・要求サイクルを追加しない。
- 通常module名とmetadata module名の両方を、元RTLとのYosys equiv_make/equiv_simple/equiv_induct/equiv_status -assertで確認。各655個のequivが証明済み、未証明0。実機・vendor gate model検証ではない。
- bank-parallelはREFRESH_CYCLES/OPEN_PAGE=(64,0),(64,1),(1203,1),(65535,1)の4条件で元controllerとの形式等価性を確認。
- parallel＋旧版の9 unittest、matrixの5 unittestが通過。所有権、stall、全要求subset/cursor、quota、grace、FFT優先を含む。
- 既存subsetテストはresetを実行しておらず、lease/remaining/graceがXのままだった。手続きifと論理式のX伝搬差を検出したため、resetを実行するよう修正し、旧版・新版とも再試験した。既知値での動作を変更して隠したものではない。最初の宣言順エラーとX検出ログも保存。

各案の312 tiles試験では、119808出力words、29796 writesが独立oracleと一致。
以下の全client結果は基準版と完全一致する。S/FFT背景は負荷proxyであり全受信経路ではない。

|client|完了cycle|期限違反件数|
|---|---:|---:|
|0|2483896|0|
|1|2484525|0|
|時間DI 2|2562998|0|
|3|2514327|0|
|4|2489406|0|
|FFT proxy 5|2566013|0|

時間DI期限2566080に対する余裕3082 clocks。設計クロックで動作する場合の有限cycle試験であり、新版の実時間合格とは独立に判断する。

## 要求元ごとの先読み（追加の構造変更）

上の3案で合成後の段数短縮を実証できなかったため、その先の変更も実施した。
仲裁器のselectedをcontrollerへ渡し、6要求元の生アドレスそれぞれについてbank open/row hitを先に計算してからselectedで選ぶ。
要求・応答のサイクルは追加しない。SoCとの境界・soft幅も不変。

- 元arbiterへselected出力と形式検証専用assertを足しただけであり、逆変換すると通常版・metadata版とも元ソースと完全一致。
- owner/lease/chosen/selectedのone-hot-or-zeroと、req_validならselected非zeroを、reset後と同じ全ゼロ状態からSAT帰納法で証明した。resetや入力要求の並びは以後任意。
- one-hot selectedを条件として、任意の6アドレス・4 bankのopen/row値に対し、選択後の従来lookupと今回の選択前lookupが一致することをSATで証明。
- controllerの次状態選択以外は、変更を戻すと元ソースと完全一致。上記の前提はarbiterの証明と元のアドレスOR muxに対応する。単なる無条件assumeではない。
- メタデータserviceの実配線に接続して合成。別の実メモリ・タイルDMA試験で312 tiles、119808 words／29796 writes、全6 clientのfinish/lateが基準と一致。
- pack下限19604/20736、FF8672。RTLにレジスタを追加していなくても、実合成のFFは基準8662から10増えたため、その数で計上する。増分の厳密な機能別帰属は未確定で、名前だけから分類しない。
- 同一始終点間の構造最大段数は14。経路全体の段数改善を証明したわけではない。配置配線・推定経路は別途保存する。

[構成的な証明テスト](../tests/test_sdram_client_lookahead.py)／[証明ログ](controller-client-lookahead/proof.log)／[有限値・期限](controller-client-lookahead/finite.json)。

## 要求経路の1-cycle性の確認

別の有限traceで、DMAのopをクロック直前／NBA更新後に比較し、その次クロックでtile要求とSDRAM要求がともにhandshakeする例を確認した。
6 tilesの2304 words／573 writesを照合し、op変化→次edge受理184件、phase変化→次edge受理5件。
[試験結果](control-path-witness.json)／[ログ](control-path-witness.log)。
要求経路全体に一律のmulticycle exceptionを設定できない反例である。
特定の配線後12段経路の全arcが同時に活性化することや、remaining counter起点の個別multicycle条件を証明したものではない。
今回タイミング制約は緩めていない。個別例外を使うなら、launch/capture/enable/reset/holdの条件ごとの証明が必要。
初回のmonitor宣言順によるcompile失敗も保存し、修正後の成功と区別する。

## 面積・物理実装

固定OSS CAD Suite 2026-10-04、nextpnr source e2fe86b3、前回と同じ互換FF二組制約・診断のみの変更。
復元binary SHA256はd72d2903f4ccf7c569deec4e205356cb661cffdfcd82408dde414ba0b90790adで前回と一致。
公式GW2A-18C chipdbのhashも前回と一致。合法性条件を緩めていない。
各mapped netlistに恒等LUT事前挿入と同期制御移動を適用し、元graphへの逆変換一致を確認した。

|候補|pack時の位置下限 / 20736|FF|前回の最長経路と同じ始終点間の構造上の最大段数|
|---|---:|---:|---:|
|基準|19404|8662|13|
|parallel|19417|8662|14|
|matrix|19421|8662|13|
|bank-parallel|19443|8662|14|
|client-lookahead|19604|8672|14|

段数はLUT/ALU graphの最長段数で、routing/pin delay、経路の活性化条件を含めない。配線後timingの最長経路やFmaxではない。
基準の実STA経路が12 LUTだったことと、この異なる診断値13段を混同しない。
RTLの表記を並列化しただけでは、合成後に段数が減ったとは言えなかった。

配線器とは別binaryで通常pack/placeを実行し、配線前の推定経路を保存した。
診断binaryも前回のSHA e47bcc30…と一致。元command.cc、配線中のbinary/object/RTLは変更していない。
no-route＋timing-allow-failの終了0は速度合格ではない。

|候補|配置後位置 / 20736|配置後追加恒等LUT|推定MHz（配線前）|推定最長経路の段数|その経路のCLK→Q＋logic＋setup|
|---|---:|---:|---:|---:|---:|
|parallel|19451 (93.80%)|34|81.712700|13|5.638 ns|
|matrix|19439 (93.75%)|18|62.414185|7|3.622 ns|
|bank-parallel|19469 (93.89%)|26|76.598999|13|6.255 ns|
|client-lookahead|19623 (94.63%)|19|89.734383|7|3.744 ns|

最初の3案はFF8662、client-lookaheadは8672。新規cellが恒等LUTのみであること、位置増加数、timing遅延和の逆数を独立auditで確認した。
推定最長経路はparallelがtile.phase→controller.state、matrixがarb.remaining→controller.write_data、bank-parallelがarb.remaining→controller.state。
matrixには配線6.6 ns・clock skew5.8 nsの予測が含まれる。これを実配線や実clock skewとは扱わない。
各行のセル内遅延は「推定最長経路」の内訳であり、全経路のzero-wire最長遅延を求めたものではない。
[配置後の独立監査](arbiter-placement-timing/audit.json)。

### 配線完了後の判定

client-lookaheadは1697.62秒で配線完了。**142.694061 MHz**で設計154.285714 MHz・K7最低152.626638 MHzに未達。
基準99.088387 MHzから改善したが、速度合格・受信機採用にはしない。実機測定ではなく同一toolchainの配線後STA。
実位置19623/20736（94.63%）、FF8672。基準より位置200、FF10増。
最長経路はarbiterのrr[1]→controller.state、7 LUT。CLK→Q 0.231＋logic3.279＋routing3.463＋setup0.035＝7.008 ns。
目標周期6.481481 nsまで**0.526519 ns**の短縮が必要（周波数では約8.12%増）。
経路途中の(40,8)→(14,7)配線が1.272 ns。局所配置やcursor decode短縮を調べる具体的根拠だが、そこだけ直せば全経路が合格する保証はない。
[配線結果](controller-client-lookahead/route-result.json)／[経路内訳](controller-client-lookahead/critical-path-audit.json)。

parallel/matrix/bank-parallelの1800秒試行は配線未完了。速度は未確認で、速度不足とは判定しない。
matrixの延長試行は**3418.95秒で配線完了、84.480865 MHz**。今回は3600秒で打ち切っていない。
位置19439、FF8662、最長13 LUT、tile.aligning→controller.state。
CLK→Q 0.231＋logic5.484＋routing6.087＋setup0.035＝11.837 ns。
1800秒では未完了だった同じnetlistが延長で完了した。したがって1800秒を収束限界と扱えないことを、今回の結果自体が示す。
元1800秒記録は保存。配線完了後は速度未達として今回の固定条件で不採用だが、別配置・RTL全般の不可能性は示さない。

|案|上限秒|終了までの実秒|配線完了|配線後MHz|判定|
|---|---:|---:|---|---:|---|
|parallel|1800|1800.09|なし|未確認|予算による中断、速度判定保留|
|matrix 初回|1800|1800.06|なし|未確認|予算による中断|
|bank-parallel|1800|1800.09|なし|未確認|予算による中断、速度判定保留|
|matrix 延長|3600|3418.95|あり|84.480865|速度未達|
|client-lookahead|1800|1697.62|あり|142.694061|速度未達|

[進行記録の集計](arbiter-route-progress.json)／[matrix延長の結果](arbiter-matrix-extended/route-result.json)。
初回の最後の未配線数はparallel7057、matrix4075、bank6258。これらは千反復ごとの記録で、終了瞬間の未配線数そのものではない。
matrix延長では最後に260069反復・未配線0へ到達。parallel/bankの延長価値を否定する測定はしていない。
今回は実STAで改善量と残経路が分かったclient-lookaheadを次の改善対象とし、未測定2案の追加長時間再実行より優先する。
これは探索資源の配分判断であって、未測定2案を不可能として棄却する判断ではない。

### 秒数上限の由来と打切りの意味

1800秒は、基準回路の配線完了1759.65秒を参考に30分へ丸めた探索予算。規格・回路期限・環境の強制上限ではない。
余裕は約2.3%しかなく、回路差・host負荷・複数seedを校正した値ではない。十分な上限という根拠は弱い。
3600秒は、未配線数が減っていたmatrixで実配線後STAを得るため倍にした暫定予算。収束上限の導出ではない。
checkpointの再読込みはbackend初期化assertに阻まれたため、延長試行は途中再開でなく同じ入力・seedからの再実行。
診断の600秒は既存collectorの実行上限を継承したもの。配線前診断を有限時間に区切る実務上の値で、回路成立条件ではない。

各試行を有限時間で止める意図は、一条件に無期限に計算を使わず他の回路変更・検証へ配分すること。
ただし時間到達だけでは、探索候補の棄却や②の打止めを正当化できない。同じ秒数でも同じ探索量・公平な順位付けは保証しない。
この3つの時間切れは「当該条件・予算内で未完了」であり、今後の延長価値がないと実証したものではない。
client-lookaheadは上限前に完了しており、打切りではなく実STAによる速度未達である。


## 現在残る障害・検証不足

- 部分統合の速度不足。今回の先読み版142.694061 MHzも設計154.285714 MHzとK7最低152.626638 MHzに未達。旧基準99.088387 MHzを現最良値として扱わない。
- 未実装stageを含む全受信機の面積・配置・速度。部分fixtureの収容確認を全体へ一般化しない。
- 時間DIの全体descriptor供給、3buffer役割交代、cold-fill有効値管理のRTL接続。
- FIR、同期、TMCC、等化、demap、完全なT/S DI、RS、TSの一貫した接続・精度・資源。
- 全mode/I/rate、最大3階層、位相、実到着包絡、RS burst、選局・再同期・停止/reset、最終TSの長期・動的期限。
- S3の高費用CPUモデル106.8042/106.6197%超過と、実無欠落取得、可逆packing、DMA/IRQ、core別WCETの未確認。
- 帯域算術の18経路組合せに対するpin、搭載負荷、PHY、独立clock同期、lane整列、保持量の未確認。算術帯域合格は正式経路の認定ではない。
- SDRAM pad/tri-state/PLL/min-max setup/hold。access時間と周期の差をsetup余裕とは扱わない。
- RF帯域/CN、外部変換、LNB、実S3連続取得、RF→TS誤り率・無欠落の実機確認。

共有K7の状態保持、service部分のclock、3scratchの容量・モデル所有権、onehot有限cycle期限、基準部分fixtureの合法配置は、既に確認した範囲について現在の失敗原因へ戻さない。
内部common clockにCDCは不可避ではない。独立S3 PHYとの同期未検証とは別問題。
分担・経路の全候補台帳は既存のcontrol-only-20kとfolded-t-evidenceを継承する。今回の4案は内部実装候補であり新しいSoC/FPGA分担・通信方式ではない。

## レビュー指摘との照合

[PR9のレビュー](https://github.com/kazuki0824/tangviterbi/pull/9#pullrequestreview-5558614170)を再確認した。今回の範囲で完了扱いにできない条件は以下。

|ゲート|今回までに確認した範囲|なお未確認の範囲|
|---|---|---|
|全体収容・STA|部分fixtureの合成、基準版の配置配線、今回3案の形式等価性・先読み版の構成的証明と配線後142.69 MHz|全復調段/TMCC/RS/TS×2/PHY/追加queue/PLLを含む実top、全clock・DSP/dual-port RAM等のtiming arcを含むSTA。旧置換予算の残55 logic/0 BSRAMを今回の実測余白と混同しない|
|実SDRAM・保持|実controller/arbiterとタイルDMAの有限試験、3scratch容量・モデル所有権|全Mode/GI/入力位相・実FFT＋T DI＋S frame＋両I/Q＋TSの最大grant待ち、CRC保留、credit、入力保持、reorder/出力・全queueの最大滞留とbank/address配置。平均帯域・容量合格だけでは満たさない|
|FEC/RS|共有K7状態保持と限定スケジュール検証|T/S全変調・最大3階層・depuncture・休止burstを含む全条件期限、204/188＋TMCC短縮RS、最悪訂正cycle・非preemptive仲裁と階層別到着の有限FIFO・最終TSまでの統合|
|S3二系統|hostモデル・可逆packer/取得制御の限定検証|各S3の2core別RF poll/packing/DMA/IRQ/RTOS/checksum/epoch/credit/sendの実active時間、bank lease/送信完了/skew、内部SRAM/PSRAM/Flash起動・stack高水位のモジュール型番別測定。2枚の空きCPUは無条件に共有しない|
|物理接続・RF/TS|方向別帯域・34信号の算術必要条件|J5/J6の実pin、搭載負荷、BL616側Hi-Z、clock-capable pin、bank電圧、2 PLL、独立S3参照の同期、80/240 MHz外部setup/hold、TS sinkのSYNC専用pin要否、2独立RFの同時受信・C/N/MER/BER・TS連続性|

Sの40 MSa/s・約38.96 MHz占有帯域に対するRFフィルタと周波数変換も未確認。
もし必要取得レートが80 MSa/sなら無損失転送量200 MB/sで再評価が必要になるが、今回80 MSa/sが必要と測定したわけではない。
この条件付きリスクを、現行40 MSa/sモデルの測定済み帯域違反と混同しない。

## 未完了と区切り

今回Aは、4変更案の値・有限期限・資源を照合し、先読み版の配線完了と速度未達、他案の探索経過を保存してPRへ反映した地点。
次のBは、先読み版のrr→selected→controller.state経路を対象に、cursor decodeの事前計算または局所配置を変更し、同じ機能・有限期限・資源・配線後速度を再検証する地点。
単なる優先encoderの書換え3案の結果を、先読み版との組合せ結果に流用しない。変更の組合せは別のnetlistとして検証が必要。

Bまで続ける選択は可能であり、実行環境の強制制限・承認拒否・実機不足がこのRTL探索を阻んだわけではない。
Aで返すのは、99.09→142.69 MHzという検証済みの改善と、次の対象経路を確定した一組の比較を共有するためという作業配分上の判断。
新たなRTLや配置制約を入れるBには、所有権・同周期発行の証明と配置配線を含む別の検証一式が必要で、その途中の推定値を今回の確定結果へ混ぜない。
この境界は今回の比較結果の品質には妥当だが、全残タスク完了を意味せず、ここで探索全体を終了してよい根拠でもない。
現在の未完了項目は上記。①の探索は再開せず、②の採用0・全方式不可能未証明を維持する。
