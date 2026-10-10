# 実PSRAMプロトコルとIQ返送の追加実装

2026-10-10。Tang Nano 9K＋ESP32-S3-WROOM-1U-N16R8、T/S実行時切替。
`receiver_adopted=false`。ここで合格したのは部分回路であり、T/S受信機の成立ではない。
過去の `rtl/psram_ctrl.sv` はDDR・初期化を持たない面積用モデルとして残す。
今回の新回路を旧FEC+mem合成結果へ自動的に含めたとは扱わない。

## 追加した処理と試験

| 不足していた機能 | 実装・確認した内容 | この結果に含まないもの |
|---|---|---|
| PSRAMの初期化・実DDR出力 | `s3_psram_burst` と `s3_psram_phy`。2個のx8を32-bit/core-clockへstriping。電源待ち、RESET、CR0設定/読戻し、ID0/1確認、ODDR/IDDR、CK/CS、固定2×4 latency | 実デバイスのsampling eye、IODELAY校正、外部IO/位相STA |
| 高速連続転送 | 各die 128 B wrapped burst、合計256 Bを64 wordで終了。4 clockのCS high、CS lowの上限、応答停止でRAM reset | 他のburst長、byte mask、任意散在アクセスの効率 |
| 書込みbufferと確定ack | 2 port×2面のburst bufferと独立read buffer。burst完了後に元portへ64 ack。ack中に次burstを実行 | RF/FFT別ring、interleaver用arbitration/cache |
| 読戻し | dieごとにRWDS high/lowのbyteを復元し、4-word FIFOで時差を吸収。頁readerは1024 word消費後にslotを解放 | RF同期・復調、TのGI除去・S3向けIQ生成 |
| 未ackの期限 | SPI頁commit後も監視し、既定32768 core cyclesで進捗のないportを停止 | 実PSRAMの最大遅延測定 |
| 通信からメモリまでの結合 | Octal/Quad各80 MHz→CDC→頁管理→PSRAM DDR端子モデル→頁reader。96頁393216 Bが一致。出力stall、16-slot ring周回を含む | CPU、API、status処理時間、実端子の電気的誤り |
| 地上波IQの同時生成/送信 | `s3_spi_iq_pingpong`。4 KiB×2面を独立に公開・解放。16頁65536 Bが一致。active 512/63 MSps、8頁ごと256 GI sample、129.9375 µs/頁で試験 | 理想化したIQ producerを使う。実filter/同期/PSRAMとの接続、S3 ready driver |
| 独立timeout | 片面のSPI転送を切断し、他面だけ正常に完了しても、切断側のtimeoutと保持を解除しない | S3による停止・再初期化処理 |

入力RFはnative I10/Q10の可逆packingのままメモリへ保存する。
SoCで帯域を合わせる追加デシメート・再量子化は導入していない。

## 合成・配置配線

固定OSS CAD suite 2026-10-04、GW1NR-LV9QN88PC6/I5、family GW1N-9C。
clock制約はIBUF/BUFG/PLLの実netへ設定し、失敗seedもJSONへ保存する。

| 部分回路 | LUT4 / 8640 | FF / 6480 | BSRAM / 26 | PLL | core Fmax / 目標 | SPI Fmax / 目標 |
|---|---:|---:|---:|---:|---:|---|
| PSRAM BIST、PLL、queue、DDR PHY | 1320（15.28%） | 685（10.57%） | 2（7.69%） | 1 | 99.48 /99 MHz、seed1 | — |
| 2 SPI RX＋頁管理＋PSRAM＋頁読出し＋PLL | 2461（28.48%） | 1391（21.47%） | 4（15.38%） | 1 | 99.91 /99 MHz、seed2 | Octal226.40、Quad160.93 /80 MHz |
| 2 SPI RX＋頁管理＋2面IQ TX（メモリはモデル） | 1627（18.83%） | 963（14.86%） | 6（23.08%） | 0 | 99.59 /99 MHz、seed2 | Octal191.28、Quad93.48 /80 MHz |
| S距離/TC8PSK/RSと実PSRAM受信経路の同時配置用top | 配置前8022（92.85%） | 配置前4758（73.43%） | 10（38.46%） | 1 | 配置未完、Fmaxなし | 配置未完 |

2行目と3行目は重複する機能を持つ別topであり、合計して全体面積にしない。
4行目は独立した合成用FEC負荷とRF transportを同居させたもの。復調器として接続していない。
heap/seed1は180秒で打切り、sa/seed1はsignal11でツール異常終了、
heap/seed2のcell探索上限10000ではDFFCEの合法配置を得られず終了した。
これは当該試行の不合格であり、全配置または全処理分担が不可能という証明ではない。
面積表の差618 LUTを、自由に追加可能な余裕として扱わない。
外部IO遅延、位相を持つclock間の制約、CDCのGray skew/bundled-data制約は未完。
99 MHzに対するcore余裕はそれぞれ0.48%、0.92%、0.60%で、小さい。
未実装の全復調器を足してもこの周波数を維持できるという証拠にはならない。

Sについて、既存の距離回路＋TC8PSK＋RS＋抽象memの5602 LUT4と今回の
PSRAM受信経路2461 LUT4を参考加算すると8063（93.32%）となり、差は577 LUT4。
抽象mem等の重複と統合後の配置変化があるため全体値ではないが、同期・復調・TMCC・
TS整形・メモリ校正を追加できる余裕が確認済み、とは扱えない。

物理PSRAMのBIST用 `.fs` は生成したが、T/S受信imageではない。
実機未確認で `safe_to_flash=false`。再構成やflash書込みは実行していない。

## 帯域の検算と適用範囲

99 MHz、256 B burstの独立pinモデルで、command受理からdoneまでwrite82 cycles、read87 cycles。

| 項目 | 検算値 | 意味 |
|---|---:|---|
| 単独write | 256×99/82＝309.07 MB/s | queue仲裁を除いた当該burst |
| 単独read | 256×99/87＝291.31 MB/s | 同上。sinkは全burstを受け入れる必要がある |
| write/readを同数実行 | 512×99/169＝299.93 MB/s | readとwriteを合算したbyte数。片方向299.93 MB/sではない |
| SPI→DDR→出力の結合試験 | 約117 MB/s | 最終値とelapsed_nsは `s3-psram-evidence/results.json` に保存。Sの100 MB/sに約17 MB/sの差 |
| TのIQ返送 | 4096/129.9375＝31.522848 MB/s | 2面buffer試験で満たした理想producerの周期 |

結合試験のSPIにはpage間250 nsだけを入れており、S3のAPIやstatus費用を含まない。
従来のS3通信予算であるS合算103.7235 MB/sの方が最終経路の厳しい上限である。
RF sequential ringの合格を、散在する全interleaverアクセスの合格へ読み替えない。
PSRAM readとwriteは同じバスを共有する。

最初の結合試験では32-token FIFOが次頁でoverflowした。128 tokenへ増やし、
同じBSRAM数のままDDR完了/ack待ちを吸収した。
合成ではasync-reset process内のRAM書込みがFF化したため、RAM processを分離した。
また、componentのfault出力を互いのupstreamへ直接接続すると組合せloopになるため、
registered sticky停止と即時の出力valid maskに分けた。これらは単体試験では現れなかった問題である。

## 未完の環境内作業

全S3機能検査は `unittest discover` の45件が142.443秒で全合格。
デジタルモデルの機能試験であり、アナログIO、実CPUのWCET、完成受信機の照合は含まない。

今回の変更で「今の環境でできる全作業が完了」したとは報告しない。
次は、IODELAY校正と位相/IO/CDC制約、RF/FFT別ring、実IQ producer/2面TX接続、
S3 status/credit/RTOS/SIMD統合、T/S全復調器、NOR切替driver/recovery image、
RF前段の回路図/BOM、各完成bitstreamの全体合成が必要。
これらは実機だけを理由に止めてよい項目ではない。
環境内作業と実機が必要な作業の全表は `s3-receiver-blockers.md` の第6/7節を参照。

## 再現と一次資料

```sh
python -m unittest discover -s tests -p 'test_s3_*.py' -v
python ci/s3_psram_benchmark.py
python ci/s3_psram_benchmark.py --bridge
python ci/s3_psram_benchmark.py --fec --seeds 2 --heap-cell-timeout 50000
python ci/s3_comm_endpoint_benchmark.py --pingpong
gowin_pack -d GW1N-9C -o build/s3-psram-pnr/psram-bist.fs build/s3-psram-pnr/routed.json
python ci/s3_psram_evidence.py --test-log build/s3-complete-tests.log
```

- [Winbond W955D8MBYA A01-001, 2019-06-05](https://www.mouser.com/datasheet/2/949/W955D8MBYA_85C_PKG_datasheet_A01-001_20190605-1760391.pdf)：CA、CR0、wrapped burst、latency、reset/CS timing。
- [Gowin UG289 GPIO](https://cdn.gowinsemi.com.cn/UG289E.pdf)：IDDR/ODDRとIODELAY。独立edgeモデルはアナログ特性モデルではない。
- [Gowin UG286 Clock](https://cdn.gowinsemi.com.cn/UG286E.pdf)：27 MHz→99 MHz、VCO792 MHz、CLKOUTP90度。
- [zf3/psram-tang-nano-9k](https://github.com/zf3/psram-tang-nano-9k/tree/394ae14a68f112729f79f78cbfc62a95d874d632)：構成参照。今回のcontroller/PHYはデータシート契約から新規実装。参照sourceのCA45をそのまま採用していない。

raw P&R log、失敗trial、source SHA256、tool version、試験結果は
`s3-psram-evidence/` と各JSONに保存する。
