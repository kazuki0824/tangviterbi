# ② 有限line cacheと現行FFT・実SDRAM controllerの初接続

追記：[現行cacheへ背景負荷を加えた仲裁比較](sdf-cache-contention.md)。以下は他clientなしの測定記録。

2026-10-19 JST。理想外部RAMを、[sdf_delay_cache.sv](../rtl/sdf_delay_cache.sv)＋既存`dual_sdram_burst.sv`に置換した。**他clientなしのMode 3連続入力で3 complete frameの全24576 binが整数参照モデルと一致した。競合・物理接続・受信機全体の合格ではない。**

## 実装した予約と容量

保持するlineは32 B（8×32 bit）1個。次のlineを全部readしてからexternal_readyを立て、8 sampleまで受理を許す。各sampleのreadは入力受理の1 clock後に同期readし、2 clock後のFFT演算に供給する。writeは受理の6 clocks後に格納する。8番目の受理時にreadyを下げ、最後のwriteが来るまで待つ。その後lineをBL8 writebackし、その応答後に次lineのBL8 readを発行する。512 lineで折り返す。

これは**必要なlineを受理前に取得する最小の有限cache**。次lineの先読みを現在lineの演算と重ねるdouble bufferではない。writebackとrefill中は入力が止まる。外部delayの全4096 wordをFPGA内に複製せず、未完writeの領域も再利用しない。予約違反・アドレスline不一致にはfaultを立てる。reset時は要求元とcontrollerを一緒にresetする契約で、単独cache reset中に残存responseを受ける運用は対象外。

## 検証と測定

[unittest](../tests/test_sdf_delay_cache.py)では非零乱数4 frameを投入し、先頭3 frameを独立整数DIF参照モデルと比較する。SDRAM pin側は既存の独立モデルを再利用し、初期メモリを非零値で埋める。実controllerの初期化・ACT/read/write/precharge/refresh・DQとアドレスを検査する。各column commandは受理済み要求アドレスとも照合する。要求側oracleとpin memoryを同一モデルにしない。

154.285714 MHz想定、初期wait30858、refresh1203、tRP/tRCD/tWR/tMRD=4、tRFC=12、CL3。これらは既存の未認定デジタル条件であり実機timing保証ではない。入力は常時validの最速条件、出力は常時ready。他clientは未接続。

| 観測項目 | 結果 |
|---|---:|
| 入力sample数 | 32768 |
| 比較bin数 | 24576、全一致 |
| frame完了clock（reset解除基準） | 298870 / 432796 / 566709 |
| 後続frame完了間隔 | 133926 / 133913 clocks |
| GI 1/32のsymbol間隔との比較 | 160380 clocksに対し最大133926、差26454（16.4946%） |
| 最大入力受理間隔 | 65 clocks |
| 最大出力間隔 | 52 clocks |

最初の完了にはSDRAM初期化とSDFのpipeline充填が含まれる。最初のframeが1 symbol内に完了したとは主張しない。後続2間隔の余裕は他clientへ配れる保証時間ではなく、この有限試験での観測差分。実際のpaced入力の滞留・許容初期遅延・全Mode/GI・共有K7/T/S負荷の最悪期限は別途必要。

## 資源と採否

Yosys `synth_gowin`の単体合成は成功。[合成結果](sdf-delay-cache-synthesis.json)はLUT1/2/3/4＝304/16/298/189（計807）、FF＝308、ALU＝13、BRAM/DSP＝0。wide muxと入出力bufferも別に出力される。これは**配置後のlogic占有率ではない**。632 port bitを単体topとして扱ったIBUF/OBUFは統合時の内部配線であり、実基板のpin要求ではない。

従来の全体見積もり20472/20736 logic・46/46 BRAMに、この数を異なる集計基準のまま加算・置換しない。32 Bというpayload容量だけでは小面積の証明にならず、今回もread mux、write enable、refill選択、制御の費用がある。未実装予約の内訳と統合し、GW2ARでのpacking/P&R・Fmaxが必要。今回の結果から「全体資源が足りた」とは判定できない。

次はこの実cache経由の要求をT spill・deinterleave・S frameと競合させ、実際の入力滞留とframe期限を測る。1 lineが不足するなら、その失敗原因に応じてline追加/先読み並行化を比較し、実資源も計上する。先の旧6転送・128要求方式の結果を本回路の保証へ流用しない。

**現在は接続単体試験まで通過。通信路割当・全体採用は0。PHY、全体P&R、S3 WCETは未達。①は変更なし。**

再現：Icarus/vvpをPATHへ置き、repo直下で `SDF_CACHE_REPORT=reports/sdf-delay-cache.json python -m unittest discover -s tests -p test_sdf_delay_cache.py -v`。[機械可読結果・source hash](sdf-delay-cache.json)。
