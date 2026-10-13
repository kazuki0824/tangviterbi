# S3-N16R8：未実施だったruntime実装の追加

> この資料の数値・SDK hash・133件の試験結果は `e6d9797` 時点の保存証拠。
> 後続の共有RF/FFT/IQ/status endpoint、3-bit RF credit、GPIO IQ publication、
> 39命令packerは [追加実装と現在の残作業](s3-runtime-endpoint.md) を参照。
> 旧SDK memory値を変更後のfirmwareへ流用しない。

2026-10-12。Tang Nano 9K完成基板、ESP32-S3-WROOM-1U-N16R8、従来ISDB-T/S、T/S排他切替。
RF payloadはnative I10/Q10を無損失に梱包する。通信のための追加software間引き・再量子化はしない。

**実装・host機能検証・実SDKリンクを追加した。全受信機の成立確認は未完了。**
この資料は以前の「この環境で進められる作業を残した」状態の修正を記録する。
1〜4をまとめて完了扱いにはしない。未実装回路は実機検証待ちには分類しない。

## 今回実施した項目

| 項目 | 実装と検証 | 判定の範囲 |
|---|---|---|
| T Mode1/2/3のFFT | `s3_fft_simd_tile_n` / `s3_fft_worker_init_n`：2048/4096/8192点、全stage、64-butterfly tile。各modeの乱数・最大振幅・zeroを独立したwhole ANSI FFTと全bin照合 | host機能合格。周期内実行は未測定 |
| 実taskの生成・core固定・終了 | `s3_fft_tasks`：既存main/core0と静的core1 task。2 KiB stack、StaticTask_t、notify、stage barrier。STOP ACKに加えて実suspended状態を確認後delete | actual Cをpthread境界shimで6 full frame試験。実IDFコンパイル・リンク合格。実task実行時間とstack high-waterは未測定 |
| SPI driverとRF page leaseの結合 | `s3_rf_pump`：actual pinned SCT/通常SPI API、2 port reap、remote credit、lease保持、エラー時capture停止 | 400 page/1,638,400 Bをnative整数oracleと照合。DMA中の不変性、完了順序違い、100回のGray wrap、信用不正を試験 |
| RF remote credit | `s3_rf_credit`：consumer最終word受理でのみ2-bit Gray更新。hostは未消費の総page数を最大3に制限し、modulo4の0/4同一視を防ぐ | RTL SPI波形/CDC/BSRAM/IQ unpack試験とhost adapter試験。電気的なGPIO CDCは未検証 |
| FFTフレームの往復と再利用 | `s3_fft_exchange`：IQ read DMA→両core FFT→64点ずつbit reversal→全binを自然周波数順にreturn DMA。2つのfull frameをDMA終了まで保持 | 3 mode×12 frame。全payload照合、遅延DMA、slot再利用、重複buffer拒否、join後も未完了RXを保持、ready fault停止が合格 |
| SoC runtimeの接続 | `s3_pipeline_esp`：実pin/80 MHz Octal＋Quad、capture service、RF pump、FFT exchange、stop/join/drain/closeを接続 | actual SDK link。診断appはこれを実行しない。FPGA ready/identity/epochを読み取る実制御路は別途必要 |
| NOR切替のC実装 | `s3_mode_switch`：T→S→recovery→T。stop→全worker/DMA drain→RECONFIG→実image確認→fresh epoch ACK→tune/lock→enable。timeout、epoch wrap、誤imageはfail-stop | actual Cを独立したcallback-event oracleで試験、SDKにcode/stateを保持。physical callbacks、受信image、実bootは未完了 |
| 同時memoryの代案 | `native-direct-phy-runtime32`：RF ringを32 KiBにしてT SIMDとS RS、実task/driver/frame/switch adaptersを同じELFへ保持 | ROM予約非重複、実ABI・実SDK map検算。起動容量必要条件が通る。runtime全allocationの証明ではない |
| CIの既知の失敗 | FPGA benchmark / receiver new-componentsのNumPy未導入を修正。数値oracle用numpy2.2.6、Python3.12を固定。runtime32 SDK、credit P&RもCI対象に追加 | 旧CI failureの原因は3 numerical test import error。修正commitのCI結果は別途追跡 |

adapterのhost試験は実装Cを使うが、SPI silicon/FreeRTOS scheduler/PHYはshim。
速度・IRQ挙動・driver allocationの証拠に転用しない。SDK診断appはlink-onlyである。

## 同時メモリの再検算

[実SDK証拠](s3-runtime-union-evidence/results.json)。IDF v5.5.1 / `fcae328`、GCC14.2、
upstream esp-sdr `e74f2a4`。local Python constraintsチェックは省略。pinと依存一覧、ELF/map hash、
生成probe/CMake/receiver、build log、target DWARFを保存した。

| 実ELFでの量 | bytes |
|---|---:|
| RF 3 bank | 196,608 |
| packed RF ring | 32,768 |
| 排他的mode slot 0/1 | 32,768 / 32,768 |
| T SIMD coefficient arena | 16,384 |
| pipeline state（StaticTask_t等を含む） | 1,640 |
| static peer stack | 2,048 |
| C mode-switch state | 72 |
| static RF境界までのgap | 18,080 |
| reclaimed early heap：0x3fce8000〜0x3fce9710 | 5,904 |
| late heap：0x3fce9710〜rev0 ROM開始0x3fceee34 | 22,308 |
| startup allocator/stack/TCB考慮後、pool前の内部空き**上限** | 31,676 |
| 4,096 B pool後、内部空き**上限** | **27,580** |

peer stackとTCBは既にstatic BSSに計上したため、dynamic task費用をもう一度引かない。
PHY/calibration、実SPI/SCT allocation、constructor、heap_caps metadata、fragmentation等を
まだ引き切っていない。27,580 Bは実測空きでも保証下限でもない。

旧64 KiB ringのpool後上限1,416 Bと、2 KiB dynamic worker追加時−980 Bは、
[旧同時SDK証拠](s3-mode-union-evidence/results.json)の結果として保存する。
新構成の値と混ぜない。ringの縮小はsample表現を変えず、buffer容量と期限の条件を厳しくする。

係数定数はFlash rodata、実kernelの係数はinternal SRAM。
実起動ではRF停止中に16,384 Bの固定tableを係数arenaにcopyする必要がある。
link-only probe内のzero初期化は受信設定ではない。

## 部分FPGAと期限

90 MHz readerの4 B/3 clocks＝120 MB/sはcontinuous sinkの上限。
consumer stallを許してよい時間は全buffer空からでも最大3 credit×4096 Bに制限され、
S100 MB/sで122.88 µs、T40 MB/sで307.2 µs。途中の占有・commit待ち・CDCは余裕を減らす。
これをjoint scheduleの保証値にしない。

窓判定を追加pipeline化した実装と、RF credit GPIOを含むpartial topを測定した。
[各生成top・CST・CAD log](s3-direct-stream-evidence/)を保存する。旧失敗も上書きしない。
FECはsynthetic inputで、RF→FEC→TSの接続はまだない。

| window pipeline＋credit partial | routed LUT4＋ALU / 8640 | BSRAM/26 | MULT18/20 | core fmax | 判定 |
|---|---:|---:|---:|---:|---|
| T | 7,327（84.80%） | 16 | 0 | 98.55 MHz | 90 MHz通過 |
| S split | 7,008（81.11%） | 16 | 2 | 59.25 MHz | 90 MHz不合格 |
| S all-RS | 7,526（87.11%） | 18 | 2 | 88.43 MHz | 99 MHz不合格 |

後続の [ISDB-S frame検算](s3-isdb-s-frame-budget.json) では、94.7902 MHzは
TMCC/burstなしの瞬間率・無待ち行列モデルの値と判明した。
28.86 MBdでのmainフレーム平均は92.5115625 MHz、burstを含む無待ち行列条件は92.9584783 MHz。
88.43 MHzは平均条件にも不足する。これは測定したseed/実装の不合格。
所有者分担全体・別kernel・別topの不可能性にはしない。

## 実core配置と全T mode/GI

[36条件の再計算](s3-runtime-schedule.json)。3 FFT size×4 GI×3 API-active条件。
RF準備、packing、SPI API、output reorderを実装どおりcore0へ計上し、両FFT workerを各coreへ計上。
FFTの105.769/230.769/500 µsはN log2 Nで換算した**仮定**。reorder/IRQ/barrier等の
未測定費用をゼロにした楽観条件も保持し、合格を実績へ昇格しない。

raw/FFT replyをOctal、IQ inputをQuadに固定し、API wire overhead20 µsとする場合、
GI1/32のMode1/2はOctal平均時間自体が100%を超える。
Mode3はOctal平均時間が収まっても、packing4 cycles/sample、準備20,000 cycles/bank、
FFT500 µs、API-active20 µsを全て現在のcore配置に積むとcore0が100%を超える。
別coreへ費用を移した表は現adapterの成立根拠にしない。

正式通信割当は全体性能通過後に行う。全320候補と境界情報、既存全通信catalog／帯域余裕を
[ordered JSON](s3-ordered-evaluation/results.json.gz)に維持し、runtime32条件と新partial証拠を追記する。
正式割当・採用数は0であり、探索で帯域に収まる経路数を採用数へ読み替えない。

## 物理制御線

GPIO38/39 / FPGA55/56をstreaming中のRF consumer Grayとして使う提案。
旧`control_sda/control_scl`と同時使用する配線ではない。
cold identity/epoch/ready手順は未実装であり、SPI等の別制御protocolを確定する必要がある。
GPIOは同じIN1 registerの1回readで両bitを採取する。2回の安定性チェックは電気的CDCの代替ではない。

NORはTang基板外付け4 MiBのみ。T/S/recovery各512 KiB、R17 strap変更、
pin9/R18の1.8 V RECONFIG_Nへのopen-drain level shiftが必要。
C switchのpulse/identity/epoch/tune/lock callbacksはその実driverを要求する。
Background Programmingを別memoryやstreaming転送へ広げない。

## 残る作業の区別

| 残作業 | この環境で実施できる部分 | この環境で取得していないもの |
|---|---|---|
| 全受信top | FIR、sync、equalizer/demap、全interleaver、RF→FEC結合、保持/補正/TS、FFT戻り入口を実装・vector試験・合成/P&Rする作業は**未実装** | 実RFからの連続TS、外部IO STAに必要なboard電気条件 |
| control/status | FPGAのIQ ready、実image identity、epoch ACK、C switch callbacksとSoCを接続する作業は**未実装** | RECONFIG pulse/boot/NOR image切替実測、RF tune/lock実測 |
| joint期限 | 全鎖とreal frame/statusを結んだイベント試験、stack call-chain/driver allocation追跡は引き続き実装できる。今回の36条件は必要条件の再計算で、**joint完了ではない** | target packing/tile/reorder/RS/API/IRQ WCET、DMA/共有SRAM競合、PHY heap、stack high-water |
| 最終採用 | 性能条件が確定した候補へ全message通信を割当て、固定T/S構成を確定する | その前提の全体performance証拠がまだ揃っていない |

この表の未実装項目を「環境ではできない」としてはいない。
追加したadapterだけをもって、この環境で可能な全作業を完了したとはしない。

## 検証・再現

S3 broad suite：133 tests、372.908 s、全合格。その後のordered/runtime/task/SPI/switch関連12件と
FFT exchangeの停止・drain/fault追加試験も合格。CAD/SDKの結果は上記の別証拠。

```sh
python -m unittest discover -s tests -p 'test_s3_*.py' -v
python experiments/s3_runtime_schedule.py --output reports/s3-runtime-schedule.json
python experiments/s3_ordered_constraints.py --output reports/s3-ordered-evaluation/constraints.json
python experiments/s3_ordered_evaluation.py
python ci/s3_direct_stream_evidence.py --mode T --window-pipeline --runtime-credit
python ci/s3_direct_stream_evidence.py --mode S --window-pipeline --runtime-credit
python ci/s3_direct_stream_evidence.py --mode S-all-RS --window-pipeline --runtime-credit
# pinned IDF / GCC / upstream checkout / ROM ELF環境：
RF_PROFILE=native-direct-phy-runtime32 python ci/s3_rf_coexist_probe.py
# s3_startup_memory_bound.pyのactual ELF/map/config/ROM引数はCIと同じ
python ci/s3_rs_link_evidence.py --profile native-direct-phy-runtime32
```

`complete_estimate=false` / `performance_stage_completed=false` / `receiver_adopted=false` / `safe_to_flash=false`。
