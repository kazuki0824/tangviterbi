# ② read受信だけのシフト化を部分削減として採用

追記：[観測回路を分割した同条件の再測定](pipelined-observation-results.md)で回転cache版は185.735519 MHz、全体追跡値20999/20736（263 logic超過）。機能検証済みの回転cache/固定maskを部分削減として採用した。旧probeの速度・帰属集計は以下の時点の記録として保持する。

追記：[回転cache・固定maskの比較](rotating-cache-mask-results.md)でさらに小面積の候補を測ったが、面積/測定timingの両方が未達のため採用しなかった。本レポートのread-only版が現行基準。

2026-10-19 JST。前回合成だけだったread-only shift案を機能・配置配線まで検証した。**受信だけの変更は既存の独立検査を通り、今回のprobeでは面積が減ったため採用する。ただし全体予算は依然超過。** write側は元の方式を維持する。

## 変更と検証

SDRAM readの各32 bit wordをresponse保持の上端へ入れ、右へ32 bit送る。8 beat後にはword 0が下位、word 7が上位に揃う。最終beatで返す組合せ応答も同じ順序へ変更する。BL8・mask・request/response・backpressure・refreshの契約は維持し、保持量も256 bitのまま。

- 独立pin memoryによるprotocol/data/mask/refresh/backpressure検査：unittest 1件成功、2.601秒。
- 実仲裁・現行FFT/cache/controller＋均等背景154.905243 MB/s：常時valid/周期入力の2条件、各24576 binが独立整数FFT oracleと一致。unittest 1件・89.342秒。
- frame完了時刻・後続間隔は基準と同じ。常時validは145054/146523 clocks、周期入力は160381/160381。周期入力の最大滞留5 sample。実K7/deinterleave/S frameのburstや長期位相試験は未接続。

## CAD結果と予算

| 測定 | 基準 | readだけシフト | 差 |
|---|---:|---:|---:|
| 本体直接合成 logic | 3325 | 3210 | −115 |
| wrapper込み配置後logic | 5122 | 5018 | −104 |
| 分離したwrapper logic | 1765 | 1960 | ＋195 |
| 本体へ帰属する配置後logic | 3357 | 3058 | −299 |
| 本体FF | 985 | 985 | 0 |
| probe Fmax MHz | 183.924973 | 160.230728 | 低下、目標154.285714は通過 |

基準と同じGW2A `-nowidelut`、GW2AR-18 QN88、seed 1、同じscan/signature境界を使用。wrapperとの合成最適化・配置の変化により、帰属上の299減と直接合成の115減は一致しない。**「実受信機で必ず299 logic節約」とはしない。** 同じ帰属ルールでの予算追跡値として用い、今後の実受信機統合で置換する。scan FF1651＋signature FF1の生存、全体セル数とnextpnr utilizationの一致は前回同様assertしている。

3058 logicを残予約2231へ置換すると、予約超過は827。全体追跡値は20472−2231＋3058＝**21299 / 20736**、**563 logic超過**となる。残る未実装部分の追加費用を0とした追跡値でも収まらない。563だけ削れば完成という意味ではない。FF/BRAMを今回使わなかった予約から無料に戻すこともしない。

速度の余裕は基準より小さい。今回のFmaxは測定wrapperを含むprobe内部clockの結果で、全体STAや外部SDRAM setup/holdの合格ではない。

## 次に残ること

cacheのword選択/保持回路やwide仲裁を含む、追加の具体的削減を測る必要がある。今回の部分削減で受信機全体を採用済みとしない。PHY、背景producer/FIFO、実K7消費とT/S burst、全体P&R/STA、S3 WCETが残る。①は変更なし。

[CAD全結果・source hash](sdf-sdram-read-shift-evidence/summary.json)、[FFT接続結果](sdf-rtl-arbiter-read-shift.json)。CAD再現は `python ci/sdf_sdram_service_evidence.py --output reports/sdf-sdram-read-shift-evidence`。機能再現は `test_common_clock_sdram.py` と `test_sdf_rtl_arbiter.py`。

本turnのpush再試行も承認レビュー用モデルのcapacityエラーで完了できず、GitHub HEADはcd327b4のままと確認した。外部反映とローカル検証結果を混同しない。
