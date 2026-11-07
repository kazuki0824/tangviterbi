# ② SDRAM仲裁を合成可能RTLへ置換

追記：[統合SDRAM serviceの面積監査](sdf-sdram-service-budget.md)で本体3357 logic、残予約超過1126、更新全体予算21598/20736を確認。旧予約込み予算を現実装が収まる証拠には使わない。

2026-10-19 JST。これまでtestbench内だった仲裁を、[sdram_client_arbiter.sv](../rtl/sdram_client_arbiter.sv)として実装した。現行FFT＋32 B cache＋実SDRAM controllerに接続し直す。背景のrelease/アドレス/データ保持は依然testbenchモデルで、実K7/deinterleave/S frame回路は未接続。

## 所有権と保持の実装

6 clientのうち5番をFFTとし、新しい要求を選ぶ時だけ優先する。他5源はround robin。選択後はownerを固定し、controllerが要求を受理するまで他clientへ切り替えない。受理後も応答がそのclientに消費されるまでownerを保持する。全体で未完transactionは1個。新たな上限値ではなく、既存controllerへの今回の接続方式である。

requestのaddress/data/DQM/writeをownerのone-hot選択で転送し、ready/response validは該当clientだけへ返す。response dataは共通バスで、validのあるclientだけが消費する。応答側のreadyをcontrollerへ返し、応答先が停止した場合も宛先を変えない。

payloadを仲裁に重複保存しない。**要求元はvalidを上げてからreadyまで全descriptorを保持する契約**であり、FFT側は既存line cacheが保持する。write dataと停止中のread応答は既存controllerに保持される。背景の各producerに実保持回路が不要になったという意味ではない。controllerはrequest受理より後にresponseを返す前提で、同clockの組合せ応答は対象外。

旧testbenchはFFT選択後に背景round robinのcursorを0へ戻していた。今回はFFT処理では背景cursorを変えず、最後に受理した背景源の次から再開する。従って旧時刻を流用せず、接続試験を再実行した。FFT要求が絶えない場合の背景待ち時間上界を、この優先規則だけで保証しない。

## 検証

単体unittestは6 clientの異なるaddress/data/DQM/writeを使い、controller ready待ちの最中にFFT要求が来ても既選択要求が変わらないことを確認。各responseを7 clocks停止し、その間の宛先・valid・dataと、再開時の応答を検査した。FFT優先・背景順序・余分な取引がないことも確認した。

接続試験は従来と同じMode 3・GI 1/32、FFT入力は常時valid/周期入力の2条件。背景は均等154.905243 MB/s、T readはwrite完了後のみ、未読ring overwriteを検査。実controller pin modelによるcommand/data/refreshと、要求側reference memoryによる背景read照合を維持する。背景DQMは0で、仲裁の非零DQM転送は単体試験で確認した。

### 接続測定結果

| 入力条件 | 後続frame間隔 clocks | 最大入力滞留 | 全bin比較 |
|---|---|---|---|
| 常時valid | 145054 / 146523 | 対象外 | 24576 bin一致 |
| symbol周期 | 160381 / 160381 | 5 sample | 24576 bin一致 |

常時validの最大146523 clocksは160380に対し13857 clocks（8.64%）の観測差分。旧testbench仲裁の最大144560より遅く、RTL化の費用を隠さず記録した。両条件とも背景最大未完数はT write/read、TI、S、管理の順に1/1/2/1/1。試験用1 symbol期限超過0、256未完超過なし、到着＝完了＋残件を確認。終了時の未完要求はJSONに残す。

周期入力でのframe完了時刻346957/507338/667719は旧短区間試験と同じだが、最大入力滞留はその旧試験の4ではなく5。前回の16 frame試験で測った5とも一致するが、今回のRTL仲裁を16 frameで再検証したわけではないため、その位相一巡結果を自動的に引き継がない。全refresh位相や実stageのdeadlineも未保証。

単体unittest 1件（0.033秒）、接続unittest 1件・内部2条件（90.325秒）が成功。背景sourceのpayload保持はtestbench配列/カウンタに残るため、「仲裁RTL化」で受信系の全保持を実装したとはしない。

## 合成資源

Yosys `synth_gowin`単体合成でLUT1/2/3/4＝53/35/340/984、計**1412 LUT**、FF12、ALU18、BRAM/DSP0。[全cell数とRTL hash](sdram-client-arbiter-synthesis.json)。wide muxは別cellとして記録される。2712 port bitのIBUF/OBUFは単体topの内部接続端点を数えたもので、基板pin数ではない。

仲裁の状態は小さくても、6本のwide data/address/maskの選択回路には費用がある。先のcache単体807 LUTと合わせると単体合成のLUTだけで2219になるが、**これは残予約2231 logicと同じ占有単位ではなく、合計が予約内に入った判定には使わない**。controller/PHY・背景producerの保持等も残る。各単体topのI/Oや定数を統合すると最適化が変わるため、全体packing/P&Rで予約置換と不足を確認する必要がある。

今回の成果は仲裁のRTL化と接続試験。背景回路/全体資源/PHY/STA/S3 WCETの完了ではない。正式採用は未確定、①は変更なし。

[単体試験](../tests/test_sdram_client_arbiter.py)／[接続試験](../tests/test_sdf_rtl_arbiter.py)／[接続結果・source hash](sdf-rtl-arbiter.json)。Icarus/vvpをPATHへ置き、repo直下で `python -m unittest discover -s tests -p test_sdram_client_arbiter.py -v`、続いて `SDF_RTL_ARBITER_REPORT=reports/sdf-rtl-arbiter.json python -m unittest discover -s tests -p test_sdf_rtl_arbiter.py -v`。
