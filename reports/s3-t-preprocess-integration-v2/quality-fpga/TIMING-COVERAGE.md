# T 残存 FPGA のタイミングモデルと配置配線

**旧ツールの headline Fmax から実機動作の合格を出すことはできない。**
旧ツールには MULT18X18 と LUT1/2/3 のモデルがなく、積のregister入力も積算器のdata入力も
タイミング報告に現れない。LUT1/2/3モデルが追加された固定版で同じnetlistを再配置配線すると、
既知モデルの経路だけでも目標154.285714 MHzに届かなかった。

| 項目 | 固定2026-10-04版 | 固定2026-11-03版 |
|---|---:|---:|
| nextpnr commit | `e2fe86b3ce6feaa3f09d8db5c0971c1cda3fc641` | `a2c6479977d64d312686d853a93941744fdbeacf` |
| GW2A-18Cの8 speed grade各々のcell model数 | 37 | 40 |
| LUT1/2/3モデル | なし | あり |
| MULT18X18モデル | なし | なし |
| residual + FIFO: 積registerのD endpoint | 0 / 128 | 0 / 128 |
| residual + FIFO: 積算器registerのD endpoint | 0 / 160 | 160 / 160 |

旧版は保存済み4構成のrouteを新しく監査し、新版は保存済みresidual + FIFOの
`probe-mapped.json.gz` と `pins.cst` をそのまま使って2026-11-05に再配置配線した。
元の4構成の合成・配置配線を今回やり直したという主張はしない。
新版でも DSP4個、BSRAM3個である。

## 新版で見える経路

積算器 `aq1` のQからoutput memoryのdata入力までのモデル上の経路は約 **7.635000 ns**。
nextpnrが報告した Fmax は **130.975769 MHz**、内部の目標値は154.285706 MHzだった。
この固定model・固定配置条件では、目標clock判定は `REJECT` になる。
不足するDSPモデルを推測で埋めたり、算出Fmaxを完全な物理タイミング保証へ読み替えたりしない。

## どこを確認したか

[timing_coverage.py](../../../experiments/t_halfband_fpga/timing_coverage.py) は、実際に配布された
chipdb binaryのv6 packed structureとRelPtr/RelSliceを読み、全8 speed gradeの
cell type、pin、combinational入力arc、register clock arcを列挙する。
magic/version、constid数、pointer範囲、対象speed grade、固定suiteのchipdb SHA256を確認した。
単にnextpnrのログで警告を検索した判定ではない。

同じcommitの公開ソース7ファイルも確認した。
[旧版arch.cc](https://github.com/YosysHQ/nextpnr/blob/e2fe86b3ce6feaa3f09d8db5c0971c1cda3fc641/himbaechel/arch.cc) と
[新版arch.cc](https://github.com/YosysHQ/nextpnr/blob/a2c6479977d64d312686d853a93941744fdbeacf/himbaechel/arch.cc) には、
cell typeからtiming modelを引き、モデルがない場合に `TMG_IGNORE` とdelay無しを返す分岐がある。
Gowinのheaderにその標準cell timingを置換するoverrideがないことも確認した。
Apiculaの元データでも、8 speed gradeにDSP timing groupは含まれていない。

route後の全セルと実際の詳細タイミングJSONを突き合わせ、積registerと積算器registerの
各D/CE endpointを区別した。CEが報告されてもDの網羅性を意味しない。
endpointが存在するだけで全arcを網羅した証明になるとも扱わない。

- 旧版の監査：[timing-coverage.json.gz](timing/timing-coverage.json.gz)。43条件PASS、model coverageはFAIL。
- 新版の監査：[timing-coverage.json.gz](cad-20261103/timing/timing-coverage.json.gz)。25条件PASS、model coverageはFAIL。
- 新版のroute：[supplement-results.json](cad-20261103/supplement-results.json)。9条件PASS、model上のclock条件はREJECT。

上記のPASSは読出し・hash・source対応・register列挙など、検証手順に対するもの。
coverageのFAILやclock条件のREJECTとは分けて記録する。失敗があっても後続条件を省略しない。
使用したソースURLとhash、chipdb hash、route入出力hashは各JSONに保存した。
これらの監査コードと結果は今回新しく作成したもので、失われた過去のファイルの同一bytes復旧ではない。

## 再現

依存はPython3.12、msgpack1.2.1と、SHA256を固定した公式OSS CAD Suiteの2版。
archive SHA256は旧版
`8a4708629b0f0afd5a1835aca8b44d224fec5f6e544c5fd22a060ea5514f83c9`、新版
`f991f2b5a8204028100cf3ad2d14d97c005ce14b903b50edf71399da99b417ed`。

```sh
python experiments/t_halfband_fpga/timing_coverage.py \
  --suite "$pinned" --source-cache "$cache/pinned" \
  --cad reports/s3-t-preprocess-integration-v2/quality-fpga/cad \
  --output "$out/timing"
python experiments/t_halfband_fpga/supplement_timing.py \
  --suite "$current" --source-cache "$cache/current" \
  --input reports/s3-t-preprocess-integration-v2/quality-fpga/cad/residual-fifo \
  --output "$out/cad-20261103"
```

ベンダSTAや実機でのタイミング検証は、この評価では実行していない。
full physical STAは `UNVERIFIED` のままである。この候補の判定から、別のFPGA回路構造や
すべてのESP32-S3構成が不可能だとは推論しない。
