# SのBM/Omega移管：FPGA Forneyを実装して再合成

2026-10-11。PR4の検算を進めた追加結果。完成見積もり・完成受信機の合格ではない。

## 部品の処理期限と資源

`rtl/s3_rs_forney.sv`はCPUのlambda/Omegaと、Chienの昇順位置から最大8個の訂正値を作る。
GF(256)/0x11d、roots alpha^0..15、51 byte短縮のRS(204,188)を扱う。
Horner評価と逆元計算は1個のGF乗算器を共用する。
根の位置を検証し、位置範囲・昇順・次数/個数・正規化・ゼロ分母の異常を失敗にする。
失敗時の部分訂正値を利用してはならない。符号語保持やTS出力はこの部品に含まない。

| 項目 | 結果 | 判定の範囲 |
| --- | ---: | --- |
| 独立符号化した符号語 | 262件PASS | 無誤り、全204位置の単独誤り、2〜8誤り。既知の誤り値と照合 |
| 不正コマンド | 8件PASS | 不正次数/個数、位置、重複/逆順、根、ゼロ分母 |
| 最悪処理 | 587 clocks | 出力backpressureを除く。試験でも上限に到達 |
| 90 MHzでの処理時間 | 6.522222 µs | **90 MHz達成を仮定**。単体内部STAの合格ではない |
| S到着に対する稼働率 | 23.181199% | 35,541.871921 CW/s。仲裁・通信・保持待ちを除く |
| 単体合成LUT / ALU | 665 / 41 | Yosys 0.69+190、narrow LUT、I/O padなし |
| 単体FF | 651 | BSRAM/DSPは使用しない |

上限の式は203根移動＋8×(1位置検査＋9 locator＋16 Omega＋1平方＋4微分＋1分母＋15逆元＋1訂正値)＝587。
rootを位置ごとに初期化せず、昇順位置間で進めるので根移動は全8誤りで合計203回以内。
reset途中の旧結果破棄、出力stall中の結果保持、次コマンド禁止も検査した。

## 同時合成：このmapped netlistは面積超過

同じSHIFT22精度のPSRAM/SPI受信経路、距離回路、32 ACS TC8PSK、syndrome/Chien、
byte訂正、27 MHz応答検査/FIFOにForneyを加えて合成・packした。
独立部品の数値を足すだけの計算ではない。ただし合成負荷はsyntheticで、BM/Omegaの29 B応答、
credit/descriptor、符号語保持、FIR/同期/frame/TMCC/TSは未接続である。

| packed netlistの必要条件 | 数 |
| --- | ---: |
| LUT | 4858 |
| ALU（blockerを除く） | 2512 |
| fabric FF | 4321 |
| LUT/ALUと共有できるFFの楽観的最大 | 2265 |
| 独立位置を必要とするFFの最小 | 2056 |
| 必要logic位置の下限 | **9426 / 8640＝109.097222%** |
| 下限の超過 | **786位置** |

したがってこのsource・narrow mappingのままでは配置不能。seed探索は行わず、Fmaxも存在しない。
未接続回路を加える前の段階で超過している。PR4の旧S-4部分配置の91.4495 MHzをS-3へ流用しない。
これはS-3の**今回測定したnetlist**の除外であり、別の保持方法・raw直接stream・再合成や
異なる分担を含めた9K＋S3の一般的不可能性ではない。量子化をSHIFT24へ変えて救済した扱いもしない。

CPU GF計数では、正常Forneyと後続の不正位置拒否試験を分離した。
正常経路の観測最大はBM/Omega 421 GF乗算呼出し・16除算、Forney 240乗算呼出し・8除算。
これらは検査ベクトルの観測値であり、Xtensa WCETへの換算値ではない。
IDF5.5.1指定GCC14.2.0のarchive SHA256を照合し、既存CPU objectのOs/O2/O3生成も再現した。

## 再現

```sh
python ci/s3_rs_forney_evidence.py --co-placement
```

PATHに2026-10-04版OSS CAD Suiteを置く。生の合成/pack logと生成top、source SHA、
部品試験・資源下限は[s3-rs-forney-evidence](s3-rs-forney-evidence/results.json)へ保存。
`receiver_adopted=false`、`safe_to_flash=false`、`whole_FPGA_resources_verified=false`。
CPU/RFの同時期限、他の分担、完成T/S回路の見積もりは引き続き未完了である。
