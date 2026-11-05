# T halfband移管後の残存 FPGA 評価

**この診断用の移管候補は採用しない。** 同じRTL構造の資源比較ではDSPが4個から4個のままで、
FIFOを含むBSRAMは2個から3個に増える。宣言した間隔なしの入力stressではFIFOがあふれ、
改善版タイミングモデルに含まれる経路でも目標clockを満たさない。
これは、この係数・RTL・FIFO・clock条件に対する評価である。別の回路構造やESP32-S3全般の不可能性は主張しない。

| 評価対象 | 得られた結果 | 証拠・方法 |
|---|---|---|
| 同じ構造のFPGA資源 | DSP4→4、FIFO込みBSRAM2→3 | [資源比較](RESOURCE-COMPARISON.md)：保存済み12 netlistを独立再集計、151条件PASS |
| 整数演算とhandshake | 9条件の全出力がoracle一致 | [RTL検証](STREAM-VALIDATION.md)：再実行、最大整数誤差0 |
| 512µs周期・8フレーム | 32768入力を受理、損失0、FIFO最大438 | [stream結果](stream/stream-results.json) |
| 間隔なし・2/8フレーム | 宣言した論理入力列では4798番目から損失 | post-parser入力stressであり、統合SDKの正確なwire波形の観測値ではない |
| 診断係数の周波数・固定小数点 | 全phase/image計算と整数誤差上限を検証 | [品質評価](QUALITY.md)：70条件PASS、契約資料の8条件PASS |
| 旧・新ツールのmodel coverage | 両方ともDSP modelなし | [タイミング](TIMING-COVERAGE.md)：旧43、新25条件を検査 |
| 新ツールの既知model経路 | 約7.635ns、130.975769MHz < 154.285706MHz | 同じmapped netlistを新しくroute、9条件PASS、clock条件REJECT |
| 元receiverと同品質 | UNVERIFIED | 係数・出力契約・MER/C/N/BERの受入基準が未確定 |
| 完全な物理STA | UNVERIFIED | DSPを含む全経路のmodelと実機/ベンダSTAが未検証 |

## 保存済み証拠と今回の新しい計算

RTL、復元済み係数HEX、4構成のCAD結果は既存commitに残っていた。
今回そのCADを再実行したことにはせず、ソースとpayloadのhashを確認して再集計した。
ストリーム、品質、契約資料、timing coverage、2026-11-03固定版での補足routeは今回実行した。
新しく書いた解析コード・JSONを、失われた過去のファイルの同一bytes復旧とは扱わない。

## 静的条件の統合監査

[t_halfband_fpga_audit.py](../../../ci/t_halfband_fpga_audit.py) は657条件を明示的に列挙する。
各報告の条件名と判定、期待されるソースhashのキーと現在の内容、保存CADの入力hash、
12 netlistの資源数、36個の全ストリーム記録の圧縮前後hash、品質の全phase/image/入力profile、
CSVの圧縮前後hash、公開timing sourceのcommit付きURL、実際のrouteとtiming報告の対応を確認した。
1項目が欠けても後続を省略しない。[audit.json](audit.json) は **657 PASS**、
`evaluation_completed=true`、候補判定`REJECT`、`receiver_adoption=false`である。
このPASSは証拠の整合性に対するもので、表のREJECTやUNVERIFIEDを合格へ変えるものではない。

[verify_non_fail_fast.py](../../../experiments/t_halfband_fpga/verify_non_fail_fast.py) は、
一つのnetlist欠落、全証拠欠落、独立する3報告の欠落、residual係数の全零化、RTL tool欠落を
別々のコピーで試験した。[audit-robustness.json](audit-robustness.json) には5シナリオ・27条件のPASSを保存した。
元のファイルを削除して試験してはいない。
零係数で非有限値が生じても、全70品質条件を含む厳密JSONを出し、該当値はnullと理由で表す。
tool欠落時は4 compile profile・9条件群・72検査を残し、容量を`UNVERIFIED`とする。

```sh
python ci/t_halfband_fpga_audit.py \
  --evidence reports/s3-t-preprocess-integration-v2/quality-fpga \
  --retained-cad reports/s3-t-preprocess-integration-v2/quality-fpga/cad
python experiments/t_halfband_fpga/verify_non_fail_fast.py \
  --evidence reports/s3-t-preprocess-integration-v2/quality-fpga \
  --retained-cad reports/s3-t-preprocess-integration-v2/quality-fpga/cad \
  --output reports/s3-t-preprocess-integration-v2/quality-fpga/audit-robustness.json
```

`--evidence`は新しい出力ディレクトリにもでき、統合監査はその直下へ`audit.json`を書く。
`--retained-cad`は保存済みCADを独立して指定する。CIでは各generatorを新しい出力先で実行し、
途中のコマンドが失敗しても残る独立した検査を実行する。
必要なPython依存はnumpy2.3.5、msgpack1.2.1で、CAD suiteは両版ともarchive SHA256を固定する。
