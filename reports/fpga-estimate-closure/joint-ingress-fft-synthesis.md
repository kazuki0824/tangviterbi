# 工程2：T/S SPI入力2系統とFFT・K7・SDRAM部分回路を同時合成

CI [41213704449](https://github.com/kazuki0824/tangviterbi/actions/runs/41213704449) で、`experiments/dual_s3_ingress_joint_fft_area_top.sv` をGowin GW2A用Yosys `synth_gowin -nowidelut` に投入し、`hierarchy -check` および `check -assert` を含め成功した。ソースmanifestと各SHA256はCI artifact内 `result.json`。

| 測定量 | 同一ネットリスト実測（mapped） |
|---|---:|
| LUT＋ALU | 13591 |
| FF | 9189 |
| BSRAM primitive | 35/46 |
| RAM16SDP4 | 273 |
| MULT18X18 | 6 |
| 暫定logic換算（LUT＋ALU＋4×RAM16SDP4） | **14683 / 20736** |

**注意:** 暫定logic換算は合成時点の比較量で、nextpnr合法配置を保証しない。残りlogic 6053やBSRAM11を完成回路の余りとして使えない。実際のFPGA端子・PLL・SDRAM PHY・全段実装は追加費用が必要。

## 同一ネットリストで実装した範囲

- 既存 `s3_spi_runtime_endpoint` から返送経路を未使用にしたT用・S用SPI入力endpoint 2個。
- 既存 `shared_receiver_fft_metadata_probe`：FFT、SDRAM controller、TC8PSK/BPSK/QPSK用K7・T soft readerの部分統合。
- 両者は同じ合成topの**独立した兄弟インスタンス**であり、`RF_data`とFFT入力などを接続していない。K7側はCADスキャンfixtureで駆動。
- したがって「T/Sが同一FPGAで資源を消費する」ことを合成値で示すが、**実入力に対する連続処理、所有権、期限、物理配置、TS出力は未検証**。

## 工程2で引き続き必須

実接続すべき機能はT/SのRF→FIR・同期、FFT→等化・demap、T時間DI・S frame DI、TMCC/slot、K7→共有RS→T/S TS、実producer有限保持とready/credit、PLL/外部I/Oである。これらをダミーに置換して合成した結果を全段値には昇格しない。既存旧予算20472/20736 logic/46 BSRAMとの加算は、重複と抜けを精算しない限り禁止。

## 失敗経緯

初回CI [41213408875](https://github.com/kazuki0824/tangviterbi/actions/runs/41213408875) はPython import path不足、次回 [41213476022](https://github.com/kazuki0824/tangviterbi/actions/runs/41213476022) はFFTアーカイブの `readmemh` 作業ディレクトリ相違で失敗した。いずれもFPGA容量の不合格ではない。修正後同一実験が成功した。

**工程2未完了、工程3未着手。**
