# S3-N16R8：API CPU費用とT全mode期限の追加検算

2026-10-12。元資料はPR4 HEAD `8bd08d21f5a1af77be5e518650e5d51860b0708b`。
対象はTang Nano 9K＋ESP32-S3-WROOM-1U-N16R8、ISDB-T全13セグメントと
従来ISDB-Sの排他的実行。T/S別imageを基板外付けSPI NORからreloadする。
通信都合の追加software間引き・再量子化は採用しない。

**完成見積もり・性能ゲート・採用は未達。** 今回の値は旧kernel費用を保持した
感度条件であり、WCETや全体配置結果ではない。帯域に入る案を性能確認済みに昇格しない。

## 比較集合と既存資料への対応

[320所有者分担・全境界情報・全通信台帳](s3-partition-audit.md)はT256＋S64。
各8段／6段のFPGA/SoC所有者を全列挙する。[4 SoC台帳](four-soc-comparison.md)の
S3部分は全16384 T/S pairを保持する。SのRS内部は全RS、BM/Chien/Forney、BM/Omega、
BM/Omega/Forneyの4切断。任意microarchitecture、全RS切断、独自GPIO・任意clockまで
網羅したものではない。旧資源値はselected-stage費用であり完成回路の占有率ではない。

今回の[結果](s3-link-cpu-sensitivity/results.json.gz)は全320所有者、既存18 rate組の
gap0/8全fluid通信割当、RS内部4切断の全message割当についてCPU API費用を追加した。
RFとRPCで同じport時間を二重利用せず、方向・page数・半二重占有を保持する。
各行の全体資源・per-core WCET・performance_passは未確定、採用はfalseのまま。

比較する設計仮説はTのFFT移管、FFT＋等化移管、全復調FPGAと、SのBM/Omega移管、
BM/Omega/Forney移管。これは優先比較対象であり、最良確定又は他分担の不可能性ではない。

## 200 cycles/pageと20 µs/APIを同じ費用にしない

旧S3台帳の境界CPU項は `(↑MB/s + ↓MB/s) × 200 / 4096` Mcycles/s。
20 µsをCPU-active時間として全量計上する場合は240 MHz×20 µs＝4800 cycles/APIである。
新感度条件では旧境界項を一度引き、宣言したpage/batchサイズのAPI回数×active時間を加える。
旧項と新項の両方を加算したり、API1回をOctalのpage数だけ繰り返し課金したりしない。

wire capacityに含めた20 µsのAPI時間はそのまま保持する。CPU稼働を同時に課金することは
同じ資源への二重課金ではない。実APIに待機が含まれる場合は実active時間へ置換する。
0/20 µsは感度条件であり、未公開SCT APIや実driverの保証下限／上限ではない。
追加IRQ/CRC/RTOS、memory stall、batch端の切上げを省くため、回数・CPU値は平均必要条件。

T-A Mode3固定割当ではRFのOctal3page batchが40e6/(3×4096) API/s、
FFT返送1 API/symbol、Quad FFT入力8 API/symbol。計11913.216991 API/s。
低CPU模型の424.549097 Mcycles/sから旧境界項を引き、57.183442 Mcycles/sを加えると
**476.701010 Mcycles/s＝99.312710%**。従来88.447728%の余裕を同条件へ転用しない。
現行scalar FFTが速くなったという意味ではなく、SIMD/tile/barrierの実時間は依然未確認。

## TのMode1/2へMode3の固定経路合格を転用しない

GI1/32の短周期を独立に計算した。全bin complex Q15の各方向平均は31.522848 MB/sで共通だが、
小FFTではAPI回数／秒が増える。下表はraw＋FFT結果をOctalだけへ、FFT入力をQuadへ置く
固定割当。symbolごとにFFT返送を1 API、RFを3page APIとする。

| Mode | FFT点 | period µs | Octal時間占有 | API20 µsならCPU費用 Mcycles/s |
|---|---:|---:|---:|---:|
| 1 | 2048 | 259.875 | **104.264795%** | 71.036255 |
| 2 | 4096 | 519.750 | **100.416791%** | 61.801046 |
| 3 | 8192 | 1039.500 | 98.492789% | 57.183442 |

この固定割当はMode1/2の平均wire必要条件を通らない。RFの一部をQuadへstripeする、
複数symbolをまとめる、LCD経路を使う等は別案。保持容量、buffer寿命、release期限と
各core CPUを改めて評価する。固定割当の失敗を全T経路の不可能性へ一般化しない。

## SのRPC後に残るCPU予算

RS保守到着率は28.86e6×2/(203×8)＝35541.871921 CW/s、28.135828 µs/CW。
204 CW batch＝5739.708940 µs。TS平均によってこの期限を緩めない。
RF既存低/高費用368.4375/448.4375 Mcycles/sは旧境界API項を含まない値を使う。
各RPCが使用したport時間を控除し、残時間にRF100 MB/sを置く。
Octal3page RF batchを優先して平均API回数を最小化する。これはwireのminimax余裕を
求めた元stripeと異なるwitnessであり、同じ配分を実装済みとはしない。

| SoCのRS段 | O/Q全message割当 | RF＋APIだけの低CPU占有 | solverと未計上処理の低残予算 cycles/CW |
|---|---:|---:|---:|
| BM/Omega | 4 | 90.247991–90.462101% | **1288.112088–1317.028115** |
| BM/Omega/Forney | 16 | 90.422216–90.993177% | **1216.389297–1293.498704** |

いずれもAPI20 µs全量CPU-activeという感度条件。高RF費用条件はAPI後に残予算が負となる。
旧約3002 cycles/CWをそのままsolverへ渡さない。core0 packing/poll、core1 API/solver等の
実schedulerを結合していないため、この低条件でも性能余裕の確認済み候補にはしない。
LCD等のAPIも同じactive時間を仮定した全通信感度結果を保存するが、実driver測定ではない。

## 資源・memory・通信・切替の判定は維持

- [S Forney同時合成](s3-rs-forney.md)：選択partialの最低9426/8640位置は超過。
- [T FEC＋実memory](s3-t-fec-resource.md)：通常9001位置は超過。compact8605位置は全復調未接続、合法配置/Fmax不明。
- [最新worker SDK容量](s3-fft-simd-evidence/worker-sdk-ci.json)：allocator/startup後内部空き上限7512 B、4 KiB pool後上限3416 B。旧台帳の19312 Bは最新workerの余裕ではない。
- 18 peripheral profileのpin/GDMA必要条件2169集合を実GPIO/電気STAの合格にしない。SDMMC2 slotの帯域も単純合算しない。IDF5.5.1の共通`s_request_mutex`と共通DMA状態で取引は直列化される。
- 基板外付けNOR4 MiBのT/S image保存だけを許可範囲とする。参照基板のMSPI strap変更、1.8 V RECONFIG接続、実image/CRC、停止/drain/epoch/relockは別確認。内部Flashや部分再構成へ拡張しない。

API感度・固定経路の追加不合格を、全SoC＋FPGA構成の実現不能又は成立済み最良案へ
読み替えない。全体top、各core期限、memory競合、endpoint/credit、RF連続性と品質、
NOR切替に未知が残る。[完了条件](pr4-estimate-completion.md)は未達である。

## 再現・根拠

```sh
python experiments/s3_link_cpu_sensitivity.py
python -m unittest discover -s tests -p test_s3_link_cpu_sensitivity.py -v
```

通常出力はbuild。固定結果を更新する場合のみ`--output reports/s3-link-cpu-sensitivity`。
[summaryと入力・結果hash](s3-link-cpu-sensitivity/summary.json)を保存する。
unittestは短mode、旧項の二重加算、port別RPC API回数、RPC後RF配置、全所有者と未知保持、
固定出力の再現を検査する。合成・STA・実S3実行を今回行ったとは扱わない。

一次資料：
[Espressif module datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)、
[SPI](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/spi_master.html)、
[SDMMC](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/sdmmc_host.html)、
[SDMMC取引実装](https://github.com/espressif/esp-idf/blob/v5.5.1/components/esp_driver_sdmmc/src/sdmmc_transaction.c)、
[ITU BO.1408-1](https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-1-200204-I!!PDF-E.pdf)。

`performance_stage_completed=false` / `complete_estimate=false` / `receiver_adopted=false`。
