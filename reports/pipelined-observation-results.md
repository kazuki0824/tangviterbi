# ② 観測回路を分割して再測定：回転cache版の速度通過、面積263超過

2026-10-19 JST。前回の回転cache＋固定mask仲裁は、signatureを含む最悪pathで133.58 MHzとなり、部分回路の速度を判定できていなかった。本体の出力をレジスタで受けてからsignatureを計算するprobeへ変更し、read-only controller版と回転cache版を同じ条件で比較した。

**回転cache＋固定mask仲裁のprobe Fmaxは185.735519 MHzで、154.285714 MHz目標を通過した。機能照合済みのRTLとsource hashが一致することも確認し、部分削減として現行RTLへ採用した。全体追跡値は20999/20736、依然263 logic超過のため、受信機全体の採用には到達していない。**

## 観測境界と集計の変更

旧probeは355本の出力を1本のXOR treeでsignature FFへ集約していた。新probeは355 bitをまずcapture FFへ入れ、32 bitごとの12 groupのparity FFを経て、最後にdigest FFへ入れる。本体出力→capture FFと、capture→signatureのpathを分ける。測定回路の保持はscan 1651＋capture 355＋group 12＋digest 1＝2019 FFで、両条件とも全2019が残ったことをsourceから確認した。

[観測試験](../tests/test_sdram_probe_observation.py)は355本の各出力を1本ずつ立て、3段の所定遅延でsignatureへ届くことを独立した遅延parity計算と照合する。最後の3 bit groupも含め全laneが成功した。RF/SDRAMの機能を試す試験ではなく、CAD観測境界の検査である。

**capture FFに入る組合せ論理は本体の費用に残す。** captureというセル名だけでその入力driverを測定回路へ除外すると、本体の出力論理まで差し引いてしまう。測定回路として分離するのは、srcで特定したprobe由来FF、そのFF用のpassthrough LUT、capture後のdigest reduction論理だけとした。全体のLUT＋ALUとFFがnextpnr utilizationに一致する検算も維持している。

新probeの初回集計ではobserved_capture名の論理も除外してしまい、基準2633／候補2169という過小値を出した。これは誤りとして訂正した。初期のsummaryとcollectorを各evidenceの `summary-initial-classification.json` / `collector-initial.py` に保存するが、**それらは無効な集計であり採否へ使用しない**。修正後の `summary.json` が有効値。

## 同一条件での比較

GW2A `-nowidelut`、GW2AR-LV18QN88C8/I7、seed 1、目標154.285714 MHz。baselineは9a038f8のread-only controller＋旧cache/仲裁、candidateは前回の機能照合済み回転cache＋固定mask（binary cursor維持）である。

| 測定 | 基準read-only版 | 回転cache版 |
|---|---:|---:|
| 本体直接合成logic | 3210 | 2733 |
| wrapper込み配置後logic | 5072 | 4572 |
| 分離したwrapper logic | 1814 | 1814 |
| 配置後本体帰属logic | **3258** | **2758** |
| 本体FF | 985 | 986 |
| BRAM / DSP | 0 / 0 | 0 / 0 |
| probe Fmax MHz | **258.464722** | **185.735519** |
| 予約置換後の全体追跡値 | 21499 / 20736 | **20999 / 20736** |
| 容量超過 | 763 | **263** |

この同一probeでは本体帰属で500 logic減、直接合成では477減。旧probeの563／99超過と直接差分を取らず、今回の763→263の対比較を使う。観測回路・packing・集計境界の変更があるため、実受信機で常に500節約できる保証ではない。

候補の最悪pathはcontrollerのrefresh_age→stateとなり、旧signatureを通る経路ではなくなった。今回のprobe内部clockの通過は確認できたが、外部SDRAMのsetup/hold、PLL/PHY、全受信機の同時STAは別途必要である。

## 採用範囲と機能証拠

`experiments/rotation_sdf_delay_cache.sv` / `rotation_sdram_client_arbiter.sv` を現行の対応RTLへ採用した。元の旧方式と各失敗版はgit履歴・snapshotで保存済み。

回転版の実仲裁＋FFT/cache/controller接続は[前回の最終候補の機能結果](sdf-rtl-arbiter-rotation-binary-mask.json)を使う。2条件で各24576 bin一致、常時validのframe間隔145054/146523 clocks、周期入力160381/160381、最大入力滞留5 sample。今回採用したRTLを含む全source hashがこの完了済み試験とbyte一致することを検算した。回路本体を変えない観測変更のため同じ長時間FFT照合は重複実行していない。

観測lane試験1件、現行/候補仲裁の4件（全320要求集合/5 cursor、要求/応答停止、DQM、折返し）、回転cacheの1件（順序・予約・停止writeback・違反検出）を確認した。実K7消費や背景burstは引き続き未接続で、この成功を受信機全体の性能合格にしない。

## 残予算と次のゲート

候補の本体2758は残予約2231より527多い。従来全体20472から置換すると20472−2231＋2758＝20999で、20K容量20736より263多い。**他の未実装費用を0としても超過する追跡値**であり、263だけ減らせば完成という意味ではない。背景producer/FIFO・PHY・RF端点・管理等の実費がさらに必要になる。

次は共通の測定境界を維持し、controller/仲裁のwide保持・選択回路の追加削減を検証する。実K7/T/Sメモリ要求と保持容量、全体P&R/STA、S3同時WCET、RF→TS連続受信も残る。①の探索は再開していない。

## 証拠と再現

- [基準版CAD・有効集計](sdf-sdram-pipeline-current-evidence/summary.json)。対応するcache/arbiter snapshotも同ディレクトリ。
- [回転版CAD・有効集計](sdf-sdram-pipeline-rotation-evidence/summary.json)。source hashは実験用RTLを指し、採用RTLも同一内容。
- [実行スクリプト](../ci/sdf_sdram_service_evidence.py)。現行版は `python ci/sdf_sdram_service_evidence.py --output <new-dir>`。実験用コピーからの同等版は `--rotation` を付ける。
- 基準版の再現は一時checkoutへ基準snapshotのcache/arbiterを置き、新probe/collectorを維持して実行する。今の現行RTLを旧baselineと読み替えない。

各測定の合成JSON、routed JSON、log、source hashを保存。`--rotation` により、比較のために正規worktreeのRTLを途中で書き換える必要はない。
