# 工程2-3: scan除外とK7/SDRAM分散RAMの資源帰属（現時点の部分結果）

## 共存構成の試験用scan回路

[CI #41610591880](https://github.com/kazuki0824/tangviterbi/actions/runs/41610591880) 同一Yosys/Gowin合成条件：

| 項目 | with_scan | no_scan | no_scan−with_scan |
|---|---:|---:|---:|
| LUT＋ALU | 19937 | 19779 | -158 |
| FF | 13191 | 11301 | -1890 |
| BSRAM | 40 | 40 | 0 |
| RAM16SDP4 | 273 | 273 | 0 |
| DSP18 | 36 | 36 | 0 |
| logic+RAM×4位置相当 | 21029 | 20871 | -158 |

no_scan側の `20871>20736` は、容量に対して **135 logic位置相当の超過スクリーニング値**。実装時の位置制約やSTA、FFT/S3接続、T/S両系統の全復調段まで証明したものではない。no_scan topはFFT/K7/SDRAMインターフェースを外部仮想ポートとしており、実端子数の制約に適合するものではない。

## 分散RAM実セルの帰属

[CI #41612359314](https://github.com/kazuki0824/tangviterbi/actions/runs/41612359314) は mapped netlist の各 `RAM16SDP4` をインスタンスパスで帰属させた。

| インスタンス領域 | RAM16SDP4 |
|---|---:|
| `candidate_fft_k7_core.k7`（K7・queue等） | 249 |
| `candidate_fft_k7_core.memory`（SDRAM reader/cache） | 24 |
| **合計** | **273** |

Gowin primitiveのsrc属性は `lutrams_map.v` を指すため、元RTLの帰属を証明しない。階層名による集計はこの部分合成での現物セル所有を示すが、全受信機の唯一の資源ownerを確定しない。

## K7メトリック小バンクのレジスタ化比較：不採用

[CI #41613773341](https://github.com/kazuki0824/tangviterbi/actions/runs/41613773341)：

| 資源 | 分散RAM原案 | メトリックbankのみmem2reg | 差 |
|---|---:|---:|---:|
| LUT＋ALU | 3522 | 5727 | +2205 |
| FF | 1534 | 4862 | +3328 |
| BSRAM | 5 | 5 | 0 |
| RAM16SDP4 | 224 | 32 | -192 |
| logic+RAM×4位置相当 | 4418 | 5855 | **+1437** |

独立4コンテキストK7/TC8整数オラクルで復号値・出力を照合し、試験合格。だが、評価対象の現行RAMをレジスタへ転換するとLUT論理の費用が増えて20K容量に不利。**不採用。** `experiments/shared_tc8_k7_context_regbank.sv` は候補記録のままであり、本RTL `experiments/shared_tc8_k7_context.sv` は変更しない。単体K7 coreの結果を全体の資源差分に直接加減算しない。

## 残作業・帰結

- 全段T/S受信機RTLへの実接続、機能検証、全実装の資源所有、CST/PHY/PLL/SDRAMのP&R/STAは未達。
- 2-3で利用可能な既存回路の資源出所は一部特定したが、他の資源の所有確定と機能ギャップ解消が必要。
- 分散RAMのレジスタ化による容量改善は採用しない。次の改善案は、K7アクセス契約を維持した別のbank構成、またはRTL/物理配置の同時最適化を実測で比較すべきであり、推測だけで資源を減らしたと判断しない。
- 47条件のstage2完了ゲートは依然NG、工程3への移行は禁止。
