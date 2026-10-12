# RF/FFT/IQ/statusの未実装接続を追加

2026-10-12。Tang Nano 9K完成基板とS3-WROOM-1U-N16R8、T/S排他切替。
`e6d9797` のlink-only保存証拠の後続。全受信機の完成を示すものではない。

| 以前の未実装 | 今回の実装 | 確認した範囲 |
|---|---|---|
| FPGA FFT戻り入口、RFとの保持・競合 | 4×4 KiBの共有BSRAM、RF/FFT独立順序cursor・独立held出力、2 port token parser | RFを17語で停止してもFFT16ページが完了。32ページの全語、同じoffsetの異なるstream、20-bit sequence wrap、stall中不変性 |
| 実identity／epoch／enable／IQ-ready | SPI3 D71C/D71D/D71EのRTLと実SPI driver C。core request/ACKによるcoherent snapshot、nonceとchecksum、実CSR ACK | SPI波形とC境界試験。core停止中の繰返しqueryは古いsnapshotを新しいACKと誤認しない。request DMA終了をCSR ACKとみなさない |
| RF/FFT/IQ/controlを一つのendpointへ接続 | `s3_spi_runtime_endpoint`：共有pool、RF retirement、IQ ping-pong、status、epoch resetを結合。TはQuad書込みguardを、SはFFT管理回路を除去 | TはRF5ページ＋FFT2ページ＋IQ2ページ。Sは両portのRF40ページとGray wrap。全byte、identity/epoch/enable、mute/drain/resetを80 MHz SPI/90 MHz coreの実RTLで検証。DSPは未接続 |
| 毎IQページのready問い合わせ | 2-bit Grayの公開ページ数と` s3_iq_credit `。2不変pageの制限を利用しoffset/epochを照合して一度だけ消費 | 10,000ページ、modulo4 wrap、2ページ同時公開、unstable retry、epoch/offset/過剰公開fault |
| RF creditとFFT用空きの両立 | RF creditを3-bit modulo8へ拡張。S最大4、T最大2未消費RFページ。Tは共有4ページのうち2ページをFFT返送用に確保 | 400ページの実pump/ring/driver境界試験。GPIOをDMA完了の代用にしない |
| Quadのpolling終了待ちによるRF処理停止 | RF開始前にSPI3を専有取得。固定IDF 5.5.1のHALと同じdone predicateを先に確認し、未完了ならpolling_endを呼ばず戻る | actual CをSDK境界shimで検証。polling_end(0)はSDKの厳密`>`判定で次tickまでspinし得るため、0だけを非blockingの根拠にしない |
| native packerの不要なmask | low20-bitと同じ結果になる狭いbitfield抽出へ変更 | native payloadのbit一致。固定S3 GCC14.2 O2/O3でhelper43→39命令、8読出し5書込み。WCETではない |
| NOR切替pulseの実GPIO driver | `s3_reconfig_esp`：GPIO40のoutput latchをreleaseにしてからopen-drain設定、quiescent確認後5µs low、release | actual CのGPIO境界試験とSDKリンク。直接3.3 VでFPGA pin9を駆動しない。外付けopen-drain level shifterとMSPI strap、NOR imageは別途必要 |
| enable要求と実enable ACKの混同 | `s3_control_apply_epoch/enable`：DMA終了後にfresh CSRを照会、違う旧値なら継続待機。C switchにENABLE待ち状態 | delayed CSR ACK試験とcallback-event試験。RUNNINGは実FPGA enable ACK後。cold queryのnonce wrapもfresh ACK fenceに従う |

信号の追加software間引き・再量子化はない。SPI silicon、実FreeRTOS、GPIO電気的CDCはhost shimでは確認できない。

## 配線と上下メッセージ

従来のOctal SPI2／Quad SPI3の18本を維持する。追加線は以下。

| 方向・意味 | ESP GPIO | FPGA package pin | レベル |
|---|---|---|---|
| FPGA→SoC RF consumer retire Gray[0:2] | 38,39,41 | 55,56,57（J5 20,21,22） | 3.3 V |
| FPGA→SoC IQ page publication Gray[0:1] | 42,47 | 37,38（J5 2,1） | 3.3 V |

GPIOは同じIN1 register一回のreadで各counterを採取する。連続2回安定性確認は電気的CDCの証明ではない。
GPIO42/47はこのN16R8 moduleで使用できる線。FPGA37/38のmicroSD機能と共用できない。
新CSTのpackage pin割当と3.3 V bankは前提、実配線と外部IO setup/holdは未検証。
旧SDA/SCL55/56をstream中に併用しない。

TのSoC→FPGAはOctal native RF（40 MB/s）と全FFT bin返送、FPGA→SoCはQuadの全IQページ。
SのSoC→FPGAは両port native RF（合計100 MB/s）、RS split案では別途RPC request/replyと符号語保持が必要。
共通controlはQuadで10-byte request header、queryだけ32-byte reply。wire時間はquery1.05 µs、command0.25 µs。
1 kHz queryならQuad使用率0.105%／42 kB/sで、API/CS gap/IRQ費用は別。
現pipelineはcontrol clientを保持するが受信中の周期queryを自動実行しない。IQ公開はGPIOを使う。
帯域に収まる必要条件でも、全core期限・buffer期限を満たした正式割当とはしない。

## 資源の証拠

`ci/s3_runtime_endpoint_evidence.py`を追加。上記のconnected endpointと既存FECを同時合成する。
FECは独立synthetic input、IQはsynthetic producerであり、FIR/sync/equalizer/interleaver/TSは含まない。
生成top、実CST、clock constraint、source hash、synth/pack/P&R logを保存する。
最小サイト数はpack済みnetlistについての下限、routingの実使用数ではない。

| 部分構成 seed1 | 最小サイト / 8640 | 配置配線の結果 |
|---|---:|---|
| T endpoint＋Viterbi＋RS | 8216（95.09%） | 180秒limit。fit/timing不明 |
| S endpoint＋TC8PSK＋split RS演算 | 8322（96.32%） | 180秒limit。fit/timing不明 |
| S endpoint＋TC8PSK＋全RS | 8857（102.51%） | 217サイト超過。今回のmapped netlistを却下 |

Tの最低424サイトの余白は未実装DSPが収まる証明ではない。
S all-RSの失敗も、別実装・別分担の全否定にはしない。
旧direct-only endpointの合格値を新connected endpointの合格に流用しない。

180秒のunknownを900秒で再試行した結果、T/S splitともheap placerが合法配置を作れず終了した。
未使用回路を明示的に除いた現在の実装も測定した。

| mode-specialized seed1 | 最小サイト / 8640 | routing LUT4＋ALU | DFF / 6480 | BSRAM/26・DSP/20 | 結果 |
|---|---:|---:|---:|---|---|
| T | 8217（95.10%） | 未確定 | 未確定 | 未確定 | 合法配置失敗。fmax未確定 |
| S split | 8024（92.87%） | 8078（93.50%） | 3678（56.76%） | 16・2 | 41.25 MHz、90 MHz不合格 |
| S all-RS | 8518（98.59%） | 未確定 | 未確定 | 未確定 | 合法配置失敗。fmax未確定 |

T/S all-RSのSA placer・seed2も試したが、toolがsegmentation fault（exit−11）で終了した。
tool crashを実装の不可能性にはしない。すべての失敗logと測定時の入力RTL bytesをhash照合して保存した。
これらは今回の具体部分実装の不合格／未確定であり、whole stage所有者320候補の全否定ではない。

## SDKと起動容量の再検算

実IDF 5.5.1／GCC14.2で、control/IQ credit/enable ACK/GPIO pulseもT FFT/S RSと同じELFへ保持。
[新SDK証拠](s3-runtime-control-union-evidence/results.json)を旧SDK証拠と別に保存する。
generated overlayのC/headerが保存対象の現sourceと同じhashであることを確認している。
static余白とstartup allocatorは変更後のmapから計算し、旧値を流用しない。
SDK appはlink-onlyで、新runtimeやGPIO pulseを実機で実行していない。

| 変更後の実ELF／起動容量必要条件 | bytes |
|---|---:|
| pipeline state | 1808 |
| static peer stack | 2048 |
| mode-switch state | 72 |
| GPIO reconfig state | 12 |
| RF境界までのstatic gap | 16088 |
| allocator/起動task考慮後、4KiB pool前の内部空き**上限** | 30004 |
| 4KiB pool後の内部空き**上限** | 25908 |

静的peer stack/TCBは既にBSSに計上し、再びdynamic費用として引かない。
PHY、実SPI/SCT allocation、fragmentation等を引き切った保証下限ではない。
固定CSTはOctal/Quad16本＋GPIO counter5本のSoC21 GPIOと、別RECONFIG GPIO40を使う。
更新した指定順の[320候補評価](s3-ordered-evaluation/results.json.gz)に、新SDKと各CAD失敗を反映した。
保存SDKと現sourceのhash不一致がある場合、そのmemory boundを変更後firmwareへ使えないよう明記する。

TのRF上限2ページに合わせて、全Mode/GIの[36必要条件](s3-runtime-schedule.json)も再計算。
API wire overhead20µsの仮定では最短GIのOctal余裕はMode1 −7.52%、Mode2 −3.67%、Mode3 −1.75%。
API20µs active、packing4 cycles/sample等の仮定ではcore0余裕もそれぞれ−11.07%、−10.92%、−12.70%。
仮定を実測として扱わず、この固定経路・費用条件の不合格を別経路の不合格へ一般化しない。
現在のpacker39命令と4 cycles/sampleの仮定は別の量であり、4を実装のWCETにしない。

## Sの期限と対応範囲の検算

[ITU-R BO.1408-1](https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-1-200204-I!!PDF-E.pdf)
Table3の48 slot／8 frame／203 byte／38976 main symbols／39936 total symbolsを用いて
[frame budget](s3-isdb-s-frame-budget.json)を追加。28.86 MBdではTS52.17 Mbit/s、main RS34687.5 CW/s。
現2667 clocks/CWのmain平均必要条件は92.5115625 MHz。
TMCC RS64をzero拡張して既存RS204へ共用する場合の平均必要条件は92.7524780 MHz。
両方ともbuffer、deinterleaver、TMCC期限、実FEC結合を保証しない。
94.7902 MHzはoverheadなし無待ち行列の瞬間率で、全buffer付き実装の最低clockではない。
ideal main CW arrival試験では92.6 MHzで待ちCWが発生し、93.15 MHzでは発生しない。
未実装の実deinterleaver到着順・TMCC仕事はこの試験に含めない。

Sの現在のmetric/trellis partialはTC8PSKのみ。一般SにはBPSK/QPSKのK7/64-state path、
puncture context、TMCC RS(64,48)、slot/TS ID、77952 Bのinter-frame payload保持、
sync復元・descrambleも必要。TC8PSK部分回路だけをS全受信機と扱わない。

## 未完了の理由と範囲

| 項目 | 現在 | 残る依存・必要な作業 |
|---|---|---|
| SDKの同時code/data/stack/driver | 変更後の実SDKリンク、ROM/map/target ABI、startup allocatorを再検算 | PHY・実driver allocation・fragmentation・stack high-water等の実起動/runtime確認は残る |
| 全受信top | **未実装** | FIR、同期、equalizer/demap、全interleaver、FEC連結、TMCC、符号語保持/補正、TS。実機待ちと分類しない |
| CPU/通信/buffer joint schedule | **未完了** | 全DSPと実API費用を含むイベント試験。既存36条件は仮定を使う必要条件で、新creditの保証ではない |
| NOR切替の実driver binding | C state machine、実status/ACK client、quiescent-gated GPIO pulseを実装・試験、全system bindingは未完了 | RECONFIG_Nの1.8 V level shifter、外付けNORからbootするT/S/recovery image、実tune/lock driver。background programmingは基板外付けNORだけ |
| 実機が必要な確認 | 未取得 | native RF dump互換性/品質、各kernel/API/IRQ WCET、stack high-water/PHY heap、共有SRAM競合、GPIO/SPI電気timing、NOR boot、連続TS |
| 正式採用 | 0 | 全体性能確認→全messageの通信割当→非空候補採用を維持。未評価候補は不可能や通信路ゼロとは書かない |

この追加で残作業全体が完了したとは記載しない。
`complete_estimate=false` / `receiver_adopted=false` / `safe_to_flash=false`。

## 検証と再現

追加前後のS3 broad suite：142件／378.679秒で合格。
その後のmode specialization、S両port、delayed CSR enable ACK、nonce wrap、GPIO pulse、
frame期限修正、新SDK条件は最終関連33件／13.674秒で合格。SPI/RTOS/PHY/GPIO hardware境界はshim。
SDK実コンパイル・リンク、ROM非重複、actual ABI、startup検算は別に合格。
配置配線失敗・timing不合格・tool crashは上記の通り保存し、host合格で置き換えない。

```sh
python -m unittest discover -s tests -p 'test_s3_*.py' -v
python ci/s3_runtime_endpoint_evidence.py --mode T --pnr-timeout 600
python ci/s3_runtime_endpoint_evidence.py --mode S --pnr-timeout 600
python ci/s3_runtime_endpoint_evidence.py --mode S-all-RS --pnr-timeout 600
python experiments/s3_isdb_s_frame_budget.py --output reports/s3-isdb-s-frame-budget.json
# pinned IDF 5.5.1/GCC14.2/upstream e74f2a4/ROM-ELFの環境：
RF_PROFILE=native-direct-phy-runtime32 python ci/s3_rf_coexist_probe.py
python ci/s3_rs_link_evidence.py --profile native-direct-phy-runtime32
```

localではPython constraints確認を省略し、cmake3.30.5、依存package一覧、source/tool/hashを保存。
OSS CAD release2026-10-04のloader経由ではABCの既定pathがlibを指したため、
localのlib/yosys-abc→../bin/yosys-abc linkを追加。mapper binary／アルゴリズムは変更していない。
