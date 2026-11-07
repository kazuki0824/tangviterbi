# T 残存 FPGA の資源比較

**この診断候補では、S3 に halfband 処理を移しても FPGA の DSP は削減されない。**
同じ 32 tap・2 complex tap/cycle の RTL を使い、baseline を 16 → 512/63 Mcomplex/s、
residual を 8 → 512/63 Mcomplex/s とした比較で、どちらも MULT18X18 は4個である。
FIFOを付けた比較では BSRAM が2個から3個に増える。

| 配置配線後の構成 | MULT18X18 | BSRAM | RAM16SDP4 | 明示的 DFF セル |
|---|---:|---:|---:|---:|
| baseline | 4 | 1 | 18 | 383 |
| residual | 4 | 2 | 24 | 445 |
| baseline + FIFO | 4 | 2 | 18 | 463 |
| residual + FIFO | 4 | 3 | 24 | 549 |

## 証拠の由来と確認方法

`cad/` の合成・配置配線結果は commit
`8e865b0156bfb7ab941c9c25d81a1f58d2e0826b` に保存済みのデータであり、
今回再実行した CAD として扱わない。固定ツールは公式 OSS CAD Suite
2026-10-04、nextpnr `e2fe86b3`、配置配線 seed は1である。
元のソースは同じ commit に残っている。

[resource_audit.py](../../../experiments/t_halfband_fpga/resource_audit.py) を新しく実行し、
4構成それぞれの core mapped、probe mapped、routed の計12個の JSON を独立に読んだ。
Yosys が併記する primitive/ABC9 ライブラリの定義は数えず、指定された design top のセルを数える。
集計結果は [resource-audit.json](resource-audit.json) に保存した。

151条件を fail-fast にせず検査した。7ソースの現在の SHA256 と保存された CAD 入力 hash、
各構成の個別結果と集合結果、12個の gzip と展開後 JSON の hash、
セル種類ごとの独立集計、記録された各段階の終了コード、配置配線完了ログとその hash、
mapped から routed までの DSP/BSRAM 数の保持を確認し、151条件すべて PASS だった。
資源の各数値、圧縮前後のログ hash、DSP と BSRAM の保持はそれぞれ別の条件として列挙する。

```sh
python experiments/t_halfband_fpga/resource_audit.py \
  --output reports/s3-t-preprocess-integration-v2/quality-fpga/resource-audit.json
```

この再集計用コードと JSON は今回新しく作成した。失われた別実装の監査コードや
その出力ファイルを同じ bytes で復旧したものではない。

## 判断の範囲

これは同じ診断用 RTL 構造の資源比較である。元の receiver の係数・丸め規則・
MER/C/N/BER 合否基準との同等性は、この集計だけでは検証されない。
配置配線が完了していても、DSP を含む経路のタイミングモデル網羅性は別途必要である。
headline Fmax を物理タイミング合格として扱わない。
この構成で DSP が減らないという結論から、すべての実装方法や ESP32-S3 全般が不可能とは推論しない。
