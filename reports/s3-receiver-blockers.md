# Tang Nano 9K + ESP32-S3-WROOM-1U-N16R8：成立までの不足と実行結果

2026-10-09。対象はISDB-T全セグメントと従来ISDB-SのTS出力、実行時切替。
採用済み受信機は0。`receiver_adopted=false`を維持する。

実機なしで実施できる計算・ホスト試験・実SDKリンク・PR上の合成を進めた結果、
過去の成立見積もりには訂正が必要になった。旧Viterbiの復号不良、32 KiB RFキューの
期限違反、RF本体を含めたSRAM不足がある。PSRAMを有効にした旧再配置は起動stackだけでも容量不足だった。今回、FFT係数表の同値圧縮でSRAMを追加確保し、逆tracebackのパイプライン化で部分FECの共通99 MHz未達を解消した。受信機全体の成立はまだ確認していない。
**実機以外の作業を全部完了した段階ではない。未実装のソフトウェア/RTLを「実機待ち」に移さない。**

## 1. この環境で実行したこと

| 項目 | 実施内容 | 得られた結果・限界 |
|---|---|---|
| Viterbiの独立検算 | RTLと独立した171/133符号化器で無雑音入力を生成 | 旧32-ACS版は出力1792 bitの区間に対し、−256〜256の位置合わせを探索しても最小551 bit不一致。旧Fmaxを正しい復号器の根拠として使わない |
| 正しい方向のtraceback | 256行survivor、124段逆追跡、64 bit単位の出力を実装 | normalized14/modulo13の2方式で独立ビット列に一致。入力停止、長期metric周回、未知の初期状態、処理途中resetも検査 |
| metric幅の削減 | 13-bit剰余metricと符号付き差による比較を実装 | 無限精度Python oracleと2048 step×64状態＝131072値で一致。入力soft 8 bitを維持し、再量子化していない |
| FPGA面積・周波数 | survivor RAMと64択selectorの間に64-bit registerを追加し、PR workflowで実配置配線 | modulo13-pipe FEC+メモリprotocol部分は4782 LUT4、2653 FF、4 BSRAM、104.06 MHz。共通99 MHzを達成 |
| RS検証 | 独立ISDB RSベクトル、0〜8誤り、訂正不能、reset境界 | 262/262合格、最大2666 clocks/block。最新RS単体は107.52 MHz。全受信機の結果ではない |
| RF bank寿命 | sentinel書込み/再使用前の所有権確認と、期限・sequence・wrap・停止処理をCで実装 | 90 unit、1109925 sample、2772992 Bの完了payloadを独立に検査。未消費bankを黙って捨てずfaultへ移る。RFレジスタループとの接続は未完 |
| キュー拡張 | 8/16頁、2ポート完了順逆転、分割arenaに対応 | 32/64 KiBそれぞれ10000頁＝40960000 Bを照合。全1048576種類のnative20値の梱包/復元も検査 |
| deadline再計算 | raw bank単位のバースト公開、有限packing速度、FFT停止区間をeventモデルに追加 | 検討中の方針ではTの32/48 KiBが失敗。64 KiBは4/6 cycles/sample仮定で4位相×100 msを通過。ただしCPU割込み全体を含む証明ではない |
| 実SDKのメモリ配置 | 8192点のFFT係数をquarter表で厳密に再構成し、RF初期化＋PSRAM＋SPIと実リンク | 係数16384→4098 B、下位余白8664→20680 B。初期stackだけの不足を解消したが、全runtime allocationが収まる証明は未完 |
| 外付けNOR切替 | 3 imageの配置/次アドレス/容量/SHA256/readback検査、停止→再構成→epoch→RF lockの制御モデルを実装 | T/S/recoveryのモデル試験に合格。実際のT/S受信bitstream、S3レジスタdriver、実書込み/起動試験は未完 |
| 完成基板の配線 | Sipeed 3674回路図とS3-N16R8の予約GPIOを照合 | SPI2/3、制御、serial TSの割当案を作成。MSPI strap変更と1.8 V RECONFIG接続が必要。無改造完成基板のまま外部NOR切替が可能とは扱わない |

主なコード：`experiments/s3_viterbi_traceback.py`、`s3_capture_bridge.c/.h`、
`s3_transport.c/.h`、`s3_bank_schedule.py`、`s3_nor_images.py`、`s3_board_pins.py`。
独立した旧RTL診断は `ci/s3_legacy_decode_audit.py` で再現できる。

## 2. 復号器の訂正と実合成

| 実験 | Viterbi単体logic equivalents / FF | FEC core LUT4 / FF | FEC+mem LUT4 / FF / BSRAM | FEC+mem Fmax | 判定 |
|---|---:|---:|---:|---:|---|
| 16-bit既知初期状態・逆traceback | 5347 / 1650 | 7248 / — | 7410 / — / — | 配置失敗 | 除外 |
| 14-bit未知初期状態・正規化 | 3173 / 1490 | 5078 / 2531 | 5250 / 2669 / 4 | 76.49 MHz | 共通99 MHz不可 |
| 13-bit未知初期状態・剰余比較 | 2788 / 1409 | 4629 / 2450 | 4789 / 2588 / 4 | 80.08 MHz | 面積改善、共通99 MHz不可 |
| 13-bit剰余比較＋survivor出力register | 2799 / 1474 | 4641 / 2515 | 4782 / 2653 / 4 | **104.06 MHz** | **この部分回路で共通99 MHz達成** |

logic equivalentsは合成時のLUT+ALU尺度であり、packed LUT4と同じ意味ではない。
最新FEC+memは8640 LUT4に対し55.35%、6480 FFに対し40.94%、26 BSRAMに対し15.38%。
復調・通信endpoint・物理PSRAM・PLLを含まない。

13-bit比較の条件は、branch cost最大510、64状態のmetric差最大6×510＝3060、
比較するcandidate差最大7×510＝3570で、modulus 8192の半分4096より小さいこと。
これは実装した畳込み符号decoderの証明条件である。**TC8PSKのbranch metricへそのまま転用しない。**
未知初期状態の取得時は先頭64 decoded bitを破棄する。連続入力を前提とするため、入力終了時の
最終64 bitのflushは未実装。下流にbackpressureは出せず、出力を常に受けられる必要がある。

SのRS期限は188 B / 6.52125 MB/s＝28.828829 us/block。
2666 clocksを99 MHzで処理すると26.929293 us、余裕1.899536 us（6.589%）。
旧80.08 MHzの共通clockでは33.291708 usだったが、今回の部分回路は99 MHz制約に通った。
この部分のRS期限のために別clockを追加する必要はなくなった。ただしbenchmarkのViterbi/RSは負荷回路であり、deinterleave等を含む実データ経路、全復調器、SPI endpoint、PLL/IOの全体STAは未完。
SのTC8PSKには8PSKの距離、並列枝の選択、対応する情報bitの保存等が必要で、現在の
2個のbinary soft入力/1-bit出力のViterbiを置いただけではSの復号器にならない。

実測sourceと証拠：

- 16-bit：`49bc76a0c5f7317e5d8c32b70dbecb1430145421`、[run 37941691903](https://github.com/kazuki0824/tangviterbi/actions/runs/37941691903)、[JSON](s3-area/traceback16-99.json)
- 14-bit：`e8c457ab7864db6e5aaa2be4b1423fdb8ae78eb8`、[run 37943442608](https://github.com/kazuki0824/tangviterbi/actions/runs/37943442608)、[JSON](s3-area/traceback14-99.json)
- modulo13：`73ecc582e97bfcfb6bbd277cc9af96659324c194`、[run 37945570775](https://github.com/kazuki0824/tangviterbi/actions/runs/37945570775)、[JSON](s3-area/traceback-modulo13-99.json)
- modulo13-pipe：`1b8f772b4b41f1c9e6d5503b0e4cd4b4f1de21e6`、[run 37953530987](https://github.com/kazuki0824/tangviterbi/actions/runs/37953530987)、[JSON](s3-area/traceback-modulo13-pipe-99.json)

workflowのsuccessは「計測完了」を意味する。個別JSONのFmax/`meets_constraint_MHz`を判定に使う。
最新pipeの合成sourceにはparameter guardとreset試験も含む。

旧critical pathはsurvivor BSRAM→64択selectorで12.49 nsだった。RAM読出しの後に64-bit registerを置き、trace開始のprimingを1 clock増やした。124段追跡＋2 clockの準備＝126 clocksで、128-clockごとの64-bit出力blockに間に合う。inputは従来どおり2 clocks/step。量子化・入力レート・出力bit数は削減していない。最新critical pathはRS制御側9.61 nsへ移った。1 seedの部分配置配線結果なので、統合後の余裕に読み替えない。

host/CIとも3方式×5入力ケース（無雑音、孤立誤り、停止、16384 stepのmetric周回）を検査。pipe版はさらに未知初期状態＋処理中resetの8 epoch、2048 step×64状態の無限精度metric oracleに合格。RS独立262ベクトルも再度全合格。

## 3. 構成・帯域・CPU期限の現在位置

検討を続ける主経路はS3のnative I10/Q10をFPGAへ送り、FPGAからserial TSを出す構成。
TだけFFTをS3へ往復させる。SはFPGAでFIR、同期、TC8PSK、frame処理、RSを担う想定。
S3上の追加の間引き・再量子化は使わない。native wordのlow20を5 B/2 sampleに梱包する。

| モード | 送る情報 | 必要量 | 検討中の通信路 |
|---|---|---:|---|
| T：S3→FPGA | native16 MSpsのI10/Q10 | 40 MB/s | SPI2 Octal80、RF 3頁SCT batch |
| T：FPGA→S3 | FPGAでGI除去した8192 complex Q15 | 31.522848 MB/s | SPI3 Quad80、4096 B×8回 |
| T：S3→FPGA | 全8192 binのcomplex Q15 FFT結果 | 31.522848 MB/s | SPI2 Octal80、8頁SCT batch |
| S：S3→FPGA | native40 MSpsのI10/Q10 | 100 MB/s | SPI2 Octal80＋SPI3 Quad80へ分配 |
| 両方：FPGA→外部sink | serial TSとclock/valid/sync | T最大約23.2347、S52.17 Mbit/s | FPGA出力。S3のUSBを出口にする設計ではない |

仮定はAPI batch overhead 20 us、SCT内実効gap 0.25 us、payload4096 B、header10 B。
実効容量はOctal RF 70.327658 MB/s、Octal FFT 75.746648 MB/s、Quad 33.395842 MB/s。
TのQuad余裕は1.872994 MB/s。TのOctalはRFとFFTで時間を共用し、理想的なbatchでも
約98.49%を使う。Sの合計余裕は3.723500 MB/s（容量に対し3.59%）。全て実測前の条件値。

raw bankは12288 sample単位で公開され、周期はT768 us、S307.2 us。
次回sentinel準備までの期限も加えたモデルで、Tの32/48 KiBは4開始位相とも失敗した。
これは**指定した方針の反例**であり、32 KiBの全てのスケジューラが不可能という証明ではない。

| 64 KiBモデル | RF梱包の仮定 | event結果 | core0平均占有の条件値 |
|---|---:|---|---:|
| T、FFT500 us | 4 cycles/sample | 4/4位相PASS、slot解放最大2046.6 us /2079 us | 85.62% |
| T、FFT500 us | 6 cycles/sample | 4/4位相PASS、slot解放最大2048.525 us /2079 us | 98.95% |
| T、FFT500 us | 8 cycles/sample | raw bank期限違反 | 112.28% |
| S、単一packing owner | 4 cycles/sample | 条件付きPASS | 93.79% |
| S、単一packing owner | 6 cycles/sample | eventだけは通るがCPU割当超過 | 127.13% |
| S、単一packing owner | 8 cycles/sample | raw bank期限違反 | 160.46% |

core0欄にはRF準備へ1 bankあたり20000 cyclesを割り当て、その予算を満額消費する場合を含む。
この20000は上流に由来する保守的な設計予算で、native-only loopの実測値ではない。
SPI API/ISRや同期処理のCPU時間を全てscheduleしていない。特にT6 cyclesの残1.05%を
十分な余裕と扱わない。S6 cyclesは梱包だけでもcore0の100%となる。
2 coreに梱包を分けるには、現在の単一producer所有権を維持する別の並列化実装が必要。

[生データ](s3-receiver-evidence/bank-schedule.json)。64 KiBキューの最大予約量は65534 Bで、
容量も余裕が大きいわけではない。sample単位の2.5 B計数と実packerの端数状態の差、
sentinel書込み、割込み、全開始位相はさらに統合する必要がある。

旧候補列挙器に新FEC面積だけを代入するとT81組/S5組を返すが、旧2 us gap・旧CPU/SRAM値の
条件付き容量列挙である。これを今回の成立候補数にはしない。全処理分担と通信路の最終採用には、
完成した処理単位のWCET/資源を入れた再列挙が必要で、採用0のまま。
主2ポート案の全体資源予算はT8179 logic /6213 FF /16 BSRAM /14 DSP、
S7979 /5637 /25 /15だが、FEC以外は旧設計予算の置換計算であり、全体合成値ではない。
TC8PSK、同期・deinterleave・PHYの完成後に増える可能性がある。

## 4. 内部SRAM：RFを加えると何が変わるか

固定予約はraw RF 192 KiB `[0x3fcb0000,0x3fce0000)`、twiddle16 KiB
`[0x3fce0000,0x3fce4000)`、packed RF 64 KiB `[0x3fce4000,0x3fcf4000)`、
FFT slot 32 KiB×2。upper領域は32 KiB D-cache設定とIDF 5.5.1の起動stack解放後に限って使う。

| 実SDKリンク | 結果 | RF領域手前の静的余白 | 受信機としての意味 |
|---|---|---:|---|
| SPI/SCT＋bridge＋scalar FFT、RF本体なし | PASS | 23992 B | ドライバーと予約の配置が通った |
| 上流RFアプリ全体＋上記（PSRAM componentなし） | FAIL | −87272 B | そのまま共存不可 |
| SPEC/IQS/USB command/core1手動resetを除き、RF初期化/チューニングだけ保持（PSRAM componentなし） | PASS | 184 B | bank loopもruntime heapもない下限構成。これで完成とはしない |
| 上記＋Wi-Fi IRAM最適化無効を明示 | PASS | 184 B（増加なし） | 上流も既に無効だった。検査した8 hot関数はIRAM |
| esp_psram依存を追加し実際にOctal PSRAMを有効化 | FAIL | −7712 B | BSSがRF領域へ侵入 |
| 同上＋FFT slotの片方を上位SRAMに移動 | link PASS / 起動容量FAIL | 8664 B | 実mapとSDKから起動stack容量不足を確認 |

上流全体の実mapでは`ring_capture.c`のBSSが61207 B、手動core1 stackが8192 B。
不要機能削除の効果を推測だけで済ませず、上の縮小構成も実リンクした。
これらの上流最小ビルドではesp_psram componentが依存に入らず、SPIRAM設定がunknownとして無視されていた。従ってN16R8完成firmwareの配置成功とは扱わない。依存追加版ではeffective sdkconfigも検査し、要求したPSRAM設定が有効でなければCIを失敗させる。

184 Bは全heapの総量ではない。upper未予約区間等もあるが、Wi-Fi/PHY初期化、
RTOS stack、SPI/GDMA/SCTの実行時確保が収まることはまだ実証していない。

RF上流は`ESPARGOS/esp-sdr`の`e74f2a470972ec163c247f1fe88d32e08579242a`に固定。
上流が要求するSDK commitと、本診断のIDF5.5.1は異なる。コンパイル/リンク成功は互換性の
一部の証拠で、RF動作の証明ではない。全体版はcore1を手動起動し、両coreの割込みを止める。
そのまま割込み方式のSPI/SCTと合体させない。native-only SDK linkも書込み用firmwareではない。

証拠：[64 KiB](s3-memory/T-SPI-late64-queue.json)、[RF全体](s3-memory/RF-coexist-full.json)、
[map内訳](s3-memory/RF-coexist-map-audit.json)、[RF初期化のみ](s3-memory/RF-native-phy.json)。
64 KiBの[run 37944497464](https://github.com/kazuki0824/tangviterbi/actions/runs/37944497464)、
RF縮小の[run 37947639138](https://github.com/kazuki0824/tangviterbi/actions/runs/37947639138)。
追加の[設定照合run](https://github.com/kazuki0824/tangviterbi/actions/runs/37948696584)でも余白は増えなかった。
上位slot案はFFT0 `[0x3fce0000,0x3fce8000)`、RF packed `[0x3fce8000,0x3fcf8000)`、FFT1 32 KiBとtwiddle16 KiBを低位に置く。
両FFT slotはそれぞれ連続した32768 Bを維持する。下位の固定データは16376 B減った（16 KiBからpointer table8 B分を差引き）。上位の未予約16 KiBを消費するので総SRAM容量を増やしたわけではない。

PSRAMを有効にした[比較run 37949916628](https://github.com/kazuki0824/tangviterbi/actions/runs/37949916628)はsource `f2012cdf114b0db66a8a2453ad24257cce37636a`。
[旧配置](s3-memory/RF-native-phy-psram.json)と[上位FFT配置](s3-memory/RF-native-upper-fft.json)を実測した。後者の`_heap_start`は`0x3fcade28`、FFT1は`0x3fc9ffd0`、twiddleは`0x3fc9bfd0`で、宣言だけでバッファが消えていないこともmapで確認。

**上位FFT配置も既定SDK設定のままでは採用不可。** 通常内部heapの上限8664 BにRTC fast RAM全8192 Bまで加える甘い評価でも16856 B。
これに対しmain8192＋esp_timer3584＋IPC2個2560＋idle2個3072だけで17408 Bが必要で、**少なくとも552 B不足**する。
TCB、heap管理領域、追加stack補正、Wi-Fi/event task、SPI/GDMA/PHYのruntime allocationをまだ含まないので、552 Bだけ減らせば成立するという意味ではない。
標準FreeRTOS動的確保は内部RAM指定で、外部stackを明示指定できる設定だけではこの既定確保はPSRAMへ移らない。
内部DMA poolの設定値32768 Bも、残る別個のDMA可能byte数8664 Bを超える。
[起動容量の検算](s3-memory/RF-native-upper-startup-bound.json)は実map/SDKソースによる必要条件判定で、実機でbootさせた結果ではない。
SDKタスク/stack/heapと配置の再設計を、実機待ちにせず残作業とする。

### 4.1 今回の係数表同値圧縮

quarter表にはsinの絶対値2049個をunsigned 16-bitで保持する。終点32768を残し、
正の+1のみ32767へ飽和、負の−1は−32768として復元するため、元のcomplex Q15係数に厳密一致する。
全8192 bin、2個の32 KiB FFT slot、192 KiB raw bank、64 KiB RF queueは維持。
追加のdecimate/requantizeは行わない。scalar実装なので500 usの実行期限達成とは別である。

| 比較 | 旧full係数表 | quarter係数表 |
|---|---:|---:|
| 8192点係数容量 | 16384 B | 4098 B |
| RF/PSRAM/SPIを含む実linkの下位SRAM余白 | 8664 B | **20680 B** |
| IRAM終端 | 0x40389700 | 0x40389800 |
| `_heap_start` | 0x3fcade28 | 0x3fcaaf38 |
| 2個のFFT slot | 各32768 B | 各32768 B |

係数自体は12286 B減少し、追加code・配置alignmentを含めた正味余白は12016 B増えた。
4/32/256/8192点の全4242係数を独立sin/cos量子化と比較し、完全一致。
32/256/8192点×5信号では、2 thread tileのFFT出力も旧係数表と完全一致し、独立NumPy FFTとの8 LSB検査に通った。
[数値試験](s3-fft-quarter.json)、[実link](s3-memory/RF-native-quarter-fft.json)、
[run 37953530983](https://github.com/kazuki0824/tangviterbi/actions/runs/37953530983)、source `1b8f772b4b41f1c9e6d5503b0e4cd4b4f1de21e6`。

起動容量の新監査はmain/esp_timerへの各512 B追加を含め、実mapからRTC予約24 Bも差し引く。
FreeRTOS software timerはKconfigだけでは数えない。このlinkは`tasks.c.obj`のweak空constructorを使い、
`timers.c.obj`をリンクしていないため追加timer taskを作らない。構造体TCB容量はhost sizeofではなくtarget ELFのDWARFから抽出する。
DMA poolは、startup taskが確保された後に残るDMA heapから予約する順序で判定する。
「予約前の静的余白が8 KiB以上」だけでは合格にしない。以後のruntime需要へpoolを二重加算もしない。
最新の容量内訳は [quarter起動監査](s3-memory/RF-native-quarter-startup-refined.json) を参照。

さらに、実ELFのTCB340 B、multi_heap_info20 B、TLSF control_t36 Bと、IDFが固定する
TLSF sourceを照合した。内部2 arenaのallocator初期領域は最低744＋388＝1132 B、
6 task×stack/TCBの12 allocation headerは最低48 B。これだけで1180 Bを消費する。
管理領域無視の8376 Bから差し引くと、DMA pool予約前の内部空きは最大7196 B。
したがって**quarter表でも8 KiB poolの設定は最低996 B不足する**。動作未測定というだけでなく、
この設定の容量必要条件が不成立。[allocatorを含む検算](s3-memory/RF-native-quarter-startup-allocator.json)。

この判定ではheap_caps管理用record/lock、allocation順序、fragmentation、Wi-Fi、event queue、
PHY、SPIをまだ含めない。Wi-Fi static RX bufferも4個設定のままである。
4 KiB pool比較はこの起動予約を見直す案であり、総容量が増えたり、RF初期化全体が収まる証明になるわけではない。

`native-quarter-pool4`を比較profileとして実装した。同じ配置なら、管理領域を含む起動予約前の上限7196 Bに対し4096 Bを予約する必要条件には3100 Bの差がある。
これは旧mapを用いた条件計算で、4 KiB版の実link成功ではない。
source `7267d82bf3338da531abca955c1c71b54f7af97c` の
[run 37955618892](https://github.com/kazuki0824/tangviterbi/actions/runs/37955618892)は全jobがstep開始前に失敗し、対象jobの再試行でも同じ状態だった。
ログを取得できず原因は確定していない。課金・quota・ソースのコンパイル失敗とは断定しない。
[実行状態の記録](s3-memory/pool4-ci-blocker.json)を残し、4 KiB版は**実SDK再リンク未完**として扱う。

今回追加したhost検査は、Viterbi3 method（15入力ケース＋metric/reset oracle）、FFT2 method、起動/allocator監査5 methodが全合格。
FEC合成source、target ELF、local再計算の出所を別々に記録し、実機boot・全受信機成立は未判定のままにする。




## 5. 基板と外付けNOR

データ配線は[pin proposal JSON](s3-board-pin-proposal.json)のとおり。S3のN16R8用予約GPIOを
避け、SPI2/3それぞれSCLK、CS、8/4 bit dataを割り当てた。SPI clockはFPGAのclock入力対応pinを選ぶ。
microSD/LCD/HDMI等の共用負荷を付けない前提。IO delayを入れた完成受信機CST/STAは未完。

参照したSipeed3674回路図では、基板NORはP25Q32U、4 MiB。
MODE1はR17でGNDへpull-down、RECONFIG_NはFPGA pin9/R18の1.8 V領域で通常headerには出ていない。
外部NORのMSPI起動にはMODE1=1、MODE0=0となるstrap変更と、RECONFIG_Nへの1.8 V対応open-drain接続が必要。
S3の3.3 V GPIOをRECONFIG_Nへ直結する案は採らない。異なる基板revisionは別途現物/回路図照合が必要。

NOR配置はT=0、S=0x80000、recovery=0x100000、各512 KiB。
現imageのheaderに次imageのaddressを入れる固定順T→S→recovery→Tを使う。
S→Tは2回の再構成となる。実行時に任意address registerを書けば切替できるとは仮定しない。
パッケージャは本物の3個の`.fs`を受け取るもので、受信image自体を生成しない。
試験fixtureは起動可能なbitstreamではなく、vendor frame CRCも検証していない。
許可されたBackground Programmingの対象は基板外付けSPI NORだけとし、内部Flash更新へ拡張しない。

## 6. 実機なしでまだ残る実装・設計（実機待ちとは別）

| 残作業 | 今回までに進めた範囲 | 閉じるために必要な成果 |
|---|---|---|
| 4 KiB DMA予約profileの実SDK link | 実装・host必要条件検算、PR実行と再試行まで実施 | Actionsのstep実行が可能になった後に再リンク。現状のCI開始前失敗は実機の有無とは別の障害 |
| native RF driverとRTOS/SPIの結合 | bank lease C、上流割込み/core1監査、RF初期化の実link | silent dropのないMMIO loop、core役割、割込み配置、fault停止。実runtime確保を含むfirmware |
| 高速FFT/梱包と統合scheduler | quarter係数の厳密復元＋scalar FFT並列tile、梱包の完全値試験、45条件のdeadline計算 | S3 SIMD tile、2 core間barrier、必要ならSの並列packing、実SDKでコンパイルした全schedule。500 usはまだ目標値 |
| T全復調RTL | FEC修正とFFT入出力契約、部分資源合成 | RF FIR/resample、AGC/CFO/clock同期、Mode1/2/3/GI、TMCC、等化、階層/demap、time/frequency/bit/byte deinterleave、depuncture、energy descramble、TS framingの結合と独立TS照合 |
| S全復調RTL | RS修正、K=7共通部の機能/面積検証、TC8PSKとの差の明確化 | matched filter/timing/carrier recovery、TC8PSK/QPSK/BPSK、burst/frame同期、TMCCとそのFEC、slot/TS選択、frame deinterleave、descrambleの結合と独立TS照合 |
| 通信endpointと物理PSRAM | SPI/SCT側のwire/lease契約、pin候補、protocol-controller部分合成 | FPGA側80 MHz IO、CDC、2 port並べ替え、IQ ready/epoch/status/error検出、実PSRAM PHY/turnaround/refreshと競合検証 |
| 全体clock/容量成立 | 正しい部分FECが104.06 MHzで99 MHz制約を通過。FFT係数表削減を実SDK linkで確認 | 起動からRF/PHY/SPI初期化までの同時live allocation、全PLL/reset/IO制約、T/S各bitstreamの全体配置配線・STA。必要なら処理分担を再探索 |
| 切替firmware/復旧image | NOR配置と状態機械を実装/試験 | 実T/S/recovery image、書込み/読戻しdriver、RECONFIG drive、identity/epoch確認、壊れたheaderを含む復旧手順 |
| RF前段・電源の実装設計 | S3内蔵RFへUHF/LNB IFを直接入れる構成では不足と確認 | 周波数変換器、LO、T/S切替filter、利得/attenuator、LNB給電/保護、S3電源、clock、connector、終端を選定した回路図/BOM/PCB。部品値・製品BOMは未確定 |

この表の項目は、ソフトウェア/設計としてさらに進められる。現在のturnで全ての完成実装を
作ったとは報告しない。とくに全受信RTLとSIMD/RTOS統合は、試験済み部品を集めただけでは完成しない。

## 7. 今の環境では実施できない確認

| 不足しているもの | できない理由 | 必要な物・入力 | 合格条件 |
|---|---|---|---|
| T/S両RF前段の実特性 | RF回路/信号源/測定器が接続されていない | 設計後の前段、アンテナ/LNB又は校正信号源、スペアナ/VNA等 | 必要帯域、image/alias抑圧、雑音・利得・直線性を満たす |
| native16/40 MSps連続取得 | S3実機がない | N16R8 module、RF入力、cycle counter/診断trace | 全sampleを途切れず取得し、bank上書き・sentinel誤判定なし |
| CPU/SRAM/GDMA同時動作のWCET | host実行はXtensa実機時間を再現しない | RF＋SPI＋FFTを同時実行するS3 | 採用したpacking/FFT/準備/API/SCT上限を最大負荷で満たし、全期限内に完了 |
| SPI2 Octal80＋SPI3 Quad80の信号品質 | 実配線・IO遅延・負荷を測れない | 接続基板、オシロ/LA、長時間のパターン試験 | DMA並走中もbit誤り・欠落・順序違反なし。モデル以内の実効gap |
| 内蔵PSRAMの実帯域/待ち時間 | 実GW1NRのPSRAMがない | 完成PHY、Tang Nano 9K | read/write/refresh競合を含め、interleave/FIFO期限と容量を満たす |
| 外部NOR起動・再構成・復旧 | 基板改造と電源操作が必要 | 基板revision確認、MSPI strap、1.8 V RECONFIG回路、programmer | T/S両方向切替、正しいimage確認、故障時停止/復旧。電源断・書込み中断も検査 |
| full TS受信性能 | 実波/RF test vectorと受信機がない | T/S規格波形、可変C/N、TS analyzer又は外部sink | 既知TSとの一致、同期/RS/continuity counter、長時間無欠落、周波数切替後の再捕捉 |
| 電源・clock・温度余裕 | 実基板での電圧/温度を測れない | 完成電源回路、負荷、測定器 | RF＋FPGA＋PSRAM同時動作時も電圧・jitter・温度条件内 |

これらの試験に合格するには、前節の完成実装が先に必要。試験に使う最終RF部品と基板revisionは
まだ確定していない。既存2製品だけで完成すると断定する根拠はない。

## 一次資料・再現

- [Sipeed Tang Nano 9K](https://wiki.sipeed.com/hardware/en/tang/Tang-Nano-9K/Nano-9K.html)、[3674回路図](https://dl.sipeed.com/fileList/TANG/Nano%209K/2_Schematic/Tang_nano_9K_3674_schematics.pdf)
- [Gowin UG290](https://cdn.gowinsemi.com.cn/UG290E.pdf)：MSPI、Multi Boot、Background Programming。2026-07-31版2.9.1Eを照合。
- [S3 module datasheet](https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)、[IDF5.5.1 SPI](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/spi_master.html)
- [IDF5.5.1 memory layout](https://github.com/espressif/esp-idf/blob/v5.5.1/components/heap/port/esp32s3/memory_layout.c)、[Wi-Fi Kconfig](https://github.com/espressif/esp-idf/blob/v5.5.1/components/esp_wifi/Kconfig)
- [ESP-SDR固定source](https://github.com/ESPARGOS/esp-sdr/tree/e74f2a470972ec163c247f1fe88d32e08579242a)：生成する縮小RF sourceにもGPL-3.0と出典を保持。
- [ARIB STD-B20概要](https://www.arib.or.jp/english/std_tr/broadcasting/desc/std-b20.html)、[ITU-R BO.1408](https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-0-199910-S!!PDF-E.pdf)

```sh
python -m unittest discover -s tests -p 'test_s3_*.py' -v
python ci/s3_legacy_decode_audit.py
python experiments/s3_bank_schedule.py --output build/s3-capture/bank-schedule.json
python ci/s3_area_benchmark.py isdb-predecode4 --frequency 99 --receiver-viterbi --viterbi-metric modulo13
```

ホスト全S3試験は17 unittest methodが合格、skipなし（91.824 s）。bank準備CPU予算を加えた3 methodも再実行して合格した。旧decoderの独立反例も再実行して同じ551誤りを確認。

ホスト試験はunittest、C compiler、NumPy、Icarusを使用。FPGA計測はCIの固定OSS CAD suite。
RF linkは`.github/workflows/s3-rf-coexist.yml`、メモリprobeは`s3-memory.yml`。
生データは`reports/s3-receiver-evidence/`と個別JSONに保存。PR #4はdraftのまま、mergeしない。
