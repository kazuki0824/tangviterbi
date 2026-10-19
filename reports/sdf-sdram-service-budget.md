# ② 統合SDRAM serviceの面積監査：現実装は残予約を超過

追記：[観測回路を分割した同条件の再測定](pipelined-observation-results.md)で回転cache版は185.735519 MHz、全体追跡値20999/20736（263 logic超過）。機能検証済みの回転cache/固定maskを部分削減として採用した。旧probeの速度・帰属集計は以下の時点の記録として保持する。

追記：[readだけのシフト化を単独検証](sdram-read-shift-results.md)し、機能/配置配線が通過。部分削減を採用したが、更新全体追跡値21299/20736で563 logic超過。以下は基準/旧試行の記録。

2026-10-19 JST。cache・仲裁・controllerを[sdf_sdram_service.sv](../rtl/sdf_sdram_service.sv)で接続し、従来と同じGW2A向け`-nowidelut`とGW2AR-18 QN88配置配線で数え直した。**現実装の費用を従来予算へ置換すると20K容量を超える。時間試験が通っただけでは採用できない。**

## 境界と測定方法

含むものは32 B FFT outer-delay cache、6 client仲裁、既存SDRAM controller。FFT演算本体、背景producerの保持/FIFO/descriptor、RF端点、PHY、K7/deinterleave/S frame本体、TS出力は含まない。backgroundの5 portは各21 bit address・256 bit payload・32 bit DQM等の内部接続であり、基板pinではない。

直接本体を合成した結果と、[CAD用scan/signature wrapper](../experiments/sdf_sdram_service_probe.sv)付き配置配線の両方を保存した。wrapperは1651独立scan入力bitと1 signature FF。全出力bitを観測し、上流からの入力を定数にして本体を小さくしない。scan入力は機能試験の合法要求列ではなくCAD専用であり、物理SDRAMを駆動するものでもない。

配置後は合成JSONのsrcからwrapperの1652 FFを特定し、signatureのdigest名の論理と、それらFFにnextpnrが付加したpassthrough LUTを測定回路として分離する。名前にdutが付いていてもscan由来なら本体へ誤計上しない。その他のlogicはすべて本体側へ計上した。セル別内訳と集計コードを同梱し、全体のLUT＋ALU/FFがnextpnr utilizationと一致することをassertしている。

## 結果

| 対象 | logic（LUT＋ALU） | FF | BRAM / DSP |
|---|---:|---:|---|
| 本体直接合成 | 3325 | 985 | 0 / 0 |
| 測定wrapperを含む配置後全体 | 5122 | 2637 | 0 / 0 |
| 分離した測定wrapper | 1765 | 1652 | 0 / 0 |
| 配置後・本体へ帰属 | **3357** | **985** | **0 / 0** |

直接合成と配置後帰属の32 logic差も記録する。過去の単体合成807 LUT＋1412 LUTの単純和とは違い、controllerも含み、Gowin family、wide LUT設定、packingの費用も揃えた。ただし実受信機へ統合した最終資源量ではなく、境界を固定した今回のprobeの帰属集計である。

配置配線はseed 1、154.285714 MHz目標で完了し、報告Fmaxは183.924973 MHz。最悪pathはsignature側を含む。これはprobe内部clockの通過であって、受信機全体STAやSDRAM pinのsetup/hold合格ではない。PHY/外部I/O遅延制約は含まない。

## 既存予算への置換

直前の[depuncture込み予算](shared-k7-depuncture-results.md)は全体20472 logic、うち残未実装予約2231 logicだった。その予約の所有者に今回のcache・仲裁・controllerが含まれるため、二重加算せず予約と置換する。

- 予約超過：3357 − 2231 ＝ **1126 logic**。
- 他の未実装部分の追加費用を仮に0にした更新値：20472 − 2231 ＋ 3357 ＝ **21598 logic**。
- 20K容量20736に対する超過：21598 − 20736 ＝ **862 logic**（約4.16%）。

つまり、ほかの未実装費用を無料としても、**現在のブロック実装とこの集計方法では収まらない**。PHY・受信端点・背景保持・管理等を実装すれば、それらの実費も必要になる。FFは985だから残1646以内、BRAM消費0だからよい、という理由でlogic超過を無視しない。残り予約のFF/BRAMを削減できたとは扱わない。

これは全方式の不可能証明ではない。実受信機統合で定数化/共通化される箇所や別回路を含む全実装空間を探索した結果ではなく、今の案が従来面積見積もりを満たさなかった結果である。背景portを意味なく削る、DQMを根拠なく固定する、機能の省略を削減として扱うこともしない。

## 次の方針

このままの資源量を採用候補の成立根拠にはしない。次はcontrollerの256 bit保持/選択回路とcache、6源のwide選択回路を分解し、同じ機能・保持契約を維持する具体的削減を測る。最低でも862 logicに残未実装部分の実費を足した分の改善が必要。実費が未確定なので「862だけ削れば完成」とはしない。削減案は既存の独立FFT oracle・controller pinモデル・応答停止試験で再検証する。

PHYを含む全体P&R、実K7/背景burst、S3 WCETは依然未達。今回新たに判明した面積超過を先に解消する。①は探索停止のまま変更なし。

## 再現と証拠

[summary・cell帰属・source hash](sdf-sdram-service-evidence/summary.json)、同ディレクトリの合成/P&Rログ・JSON、[実行スクリプト](../ci/sdf_sdram_service_evidence.py)。OSS CAD Suite 2026-10-04をPATHへ置き、repo直下で `python ci/sdf_sdram_service_evidence.py --output reports/sdf-sdram-service-evidence`。大きなnetlist/logはgzipで保存し、`--collect-only`は保存済み結果の再集計だけを行う。

本turnでは既存の部品間接続を合成用wrapperへ集約し、Yosys checkと配置配線を確認した。新wrapperを用いたRF/TSの機能試験を実行したという主張はしない。既存仲裁/FFT接続の機能検証は[前回レポート](sdf-rtl-arbiter.md)の範囲に限る。
