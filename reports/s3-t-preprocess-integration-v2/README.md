# T側結合評価の再構築 v2

2026-11-04 JST。失われた検証一式を再実行できる形に作り直している。
前回の[復旧記録](../s3-t-preprocess-integration/README.md)と、今回の新しい実行結果を区別する。
現在は native 入力と係数表の工程を検証して保存した段階であり、SDK費用・結合モデル・FPGA全評価は続行中である。

## 保存した工程

| 工程 | 確認した条件 | 現在の結果 |
|---|---|---|
| native入力 | 回収したC原本との一致、独立畳み込み、全1,023分割と全1,023折返し、tail・metadata・所有権・異常停止 | [36項目PASS](native/results.json) |
| native回帰検査 | 分割と畳み込み、所有権、異常系に加え、先頭の検査失敗や入力ファイル欠落後も独立項目を検査すること | 7テストPASS |
| FPGA係数 | 保存BRAMからの逆変換、旧原本SHA256との一致、新しい数式生成との一致、全位相のDC和と範囲 | [10項目PASS](quality-fpga/coefficient-recovery.json) |
| 実SDKと対象命令費用 | 新しいELF・map・入力ハッシュを対応させて監査 | 作業中 |
| native/SDK結合モデル | 同一のC制御と対象費用で継続処理と所有権を評価 | 作業中 |
| FPGA接続・資源・品質・timing | 独立oracle、全入力条件、合成・配置配線とtiming coverage | 作業中 |

ホスト検査の成功をS3実機の処理時間の合格に読み替えない。nativeのヘッダーは新しい再構築版であり、対象のレイアウトと費用は新しいSDKビルドから計上する。
係数表2点と `.gitignore` は保存ネットリストなどから旧原本との完全一致を追加確認できた。旧142ファイル全体の原本回収状況は[一覧](recovery-originals.json)に記録する。

## 今回保存した検査の再実行

リポジトリのルートで実行する。Python 3.12、C11対応Cコンパイラー、NumPy 2.3.5を使用した。

```sh
python -m unittest tests.test_t_native_adapter -v
python ci/t_native_adapter_audit.py --output build/t-preprocess-native.json
python experiments/t_halfband_fpga/coefficients.py --output build/t-preprocess-coefficients.json
```

各監査は独立した確認条件を最後まで列挙する。入力が欠けて実行できない条件はBLOCKEDとして残す。元のバイナリやJSONを推測で復元した扱いにはしない。

## 工程の完了条件

再構築工程の完了は、対象ソース、実ビルド、費用、結合結果、FPGA評価をハッシュで対応させ、専用CIで再実行でき、判定をPRへ保存できた時点とする。
これは候補の成立を必ずPASSにする条件ではない。期限やFIFO条件がNGなら、その条件と範囲を示して不採用の判定を保存する。実機のWCET・元方式との品質等価など、証明できていない条件を成功扱いにはしない。
