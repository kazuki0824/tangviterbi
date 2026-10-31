# 工程2：既存資源見積もりの厳密な精算（未完了）

基準PR #10のHEAD `1fe8e006a33e146b358d244f0bade5908a4b258d`、対象は工程1 scope.json に固定した②である。

## 既存測定値を同一値へ混ぜない

| 分類 | logic位置 | FF位置 | BSRAM | Fmax | 注記 |
|---|---:|---:|---:|---:|---|
| 旧全段予算 | 20472/20736 | 13189/15552 | 46/46 | 未取得 | 実接続の合成値ではない |
| SDRAM service本体を実装値に置換、producer保持未加算 | 20726/20736 | 未確定 | 旧46を維持 | service probe 155.982 MHz | 残10 logicだが未実装回路は追加0とした**診断値** |
| 5系統1件保持を追加した代替試行 | 22002/20736 | 13791/15552 | 旧46を維持 | service probe 181.488 MHz | 1266 logic超過。単独保持試行であり不採用 |
| T soft reader/cache単独の追加費用を評価した別の診断 | 22977/20736 | 未確定 | 未確定 | - | 別候補。5系統保持と重ねて二重計上してはならない |
| cursor mask部分fixture | 19658/20736 | 8673/15552 | 29/46 | **166.223 MHz** | 統合受信機ではない。fixtureのscan資源を含む |
| Mode3 T input holding部分top | 13036/20736 logic換算 | 5537 | 42/46 | 未取得 | 全体ではない。上流保持を含む |

出典: `reports/receiver-integrated-estimate/README.md`、`reports/read-only-spill-budget-results.md`、`reports/background-holding-budget.md`、`reports/cursor-mask-route-comparison/README.md`、`reports/20k-dual-s3-t-buffer.md`。

## 算術

- 旧全段仮定 20472 − service予約2231 + 実service本体2485 = **20726**（未計上部分を0と仮置きした追跡値）。
- 旧全段仮定 20472 − service予約2231 + producer slot付きservice本体3761 = **22002**（容量20736を**1266超過**）。
- service本体の実配置差 = 3761 − 2485 = **1276** logic。mapped差53だけではplacement差を表せない。
- 特に旧46/46 BSRAMを勝手に解放しない。bufferをどのinstanceが所有するか照合しない限り別見積もりから加算・控除しない。

## 旧stage費用を全段確定値へ昇格できない理由

1. T FIR・同期・等化／demap、S FIR・同期／全変調、TMCC/slot、実RF入力、T/S TS、外部CDCの全受信topが未接続。
2. 共用K7、共有RS、全メモリproducerの有限保持・descriptor・下流backpressureが同一ネットリストで資源計上されていない。
3. 既存のFFT・SDRAM service probe値を、全top合成における合成最適化・legal placementの結果へ読み替えられない。
4. 旧見積もりのlogic、FF、BSRAM、DSP、PLLとI/Oの割当項目に対応するRTL instance（含む/除外）を一対一に対応付けられていない。
5. 周辺のscan/刺激/観測fixtureを全受信機から除外し、制御・PHYに必要な回路を含む必要がある。

## 工程2を閉じるための実施項目

- scope.jsonのT8・S6・共用15項目を、選定した単一topのRTL instanceへ一対一に対応させる。
- 未実装部を品質・機能を維持したRTLで接続し、Yosys/nextpnrの実資源報告を採取する。
- FPGA上の全消費資源（logic位置、FF、BSRAM、分散RAM、DSP、PLL、I/O）を数え、共用部と旧台帳の重複がないことを確認する。
- 必要機能欠落・配置不能なら、直ちにその構成を不合格と記録し、単に旧予算の未計上欄へ0を入力しない。
- その後だけ工程3の全期限見積もりに進む。

**工程2完了=false。工程3以降へ進んではならない。** 既知の「別々の試行が容量超過」は有効な反例だが、「最良の全実装が収容不能」の証明にはならない。部分結果と全体結果を混同しない。
