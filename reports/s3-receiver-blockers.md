# Tang Nano 9K + ESP32-S3-WROOM-1U-N16R8：成立までの不足と実行結果

2026-10-10更新。対象はISDB-T全セグメントと従来ISDB-SのTS出力、実行時切替。
採用済み受信機は0。`receiver_adopted=false`を維持する。

**資源見積もりを訂正する。配置後のJSONのLUT4欄だけではロジック位置の占有率にならない。**
ALUが同じ位置を占めるため、今回のnarrow-LUT構成では配置後のLUT4＋ALUを使う。
旧S距離/TC8PSK/RSの5602 LUT4には別に2028 ALUがあり、合計7630/8640＝88.31%。
実PSRAM受信経路は2461＋616＝3077/8640＝35.61%。
単体の数値をそのまま足して全体配置にすることはできない。

さらにpacked netlistから、LUT/ALUと同じ位置を共有できないFFを数える下限監査を追加した。
旧S用同時配置topは最低10498位置、出力bufferを1 BSRAMへ移した版でも最低9946位置を要し、
8640位置をそれぞれ1858/1306超える。これら**既存mapped netlistは収まらない**。
RTL再設計まで不可能という意味ではない。計算時間だけ増やす試行から資源構成の変更へ進む。
根拠は `ci/s3_logic_site_audit.py`、`reports/s3-logic-site-audit.json` と
nextpnr e2fe86b3 の `GowinImpl::slice_valid/create_passthrough_luts`。
監査の下限は、配置済みPSRAM単体1648位置・受信経路3077位置とも矛盾しないことを確認した。

**今回も実装を進めたが、「この環境で可能な全作業を完了」した状態ではない。**
全復調器、RTOS統合、PSRAM校正/全体STA、全体配線の実装はなお残り、実機待ちには分類しない。
以下の第6節が残る設計・実装、第7節が今の環境で実行できない物理確認である。

## 2026-10-10追記：資源・期限を満たさない圧縮候補を明示

[圧縮の実装・独立検証・採否](s3-fec-compaction.md)、
[再現証拠](s3-fec-compaction-evidence/results.json)を追加した。
TC8PSK出力/B1保存、RS表のBSRAM化、22 ACS、Q15契約下の正確な12-bit modulo、
距離演算の3クロック共有を実装した。新たなSoCデシメート・再量子化はない。

| 現在の判定 | 結果 |
|---|---|
| 同時配置topの必要位置下限 | 10498→8616。最後の版もheap/seed1で合法配置未発見、Fmaxなし |
| 圧縮FEC＋抽象メモリ単体の実Fmax | seed1/2/3＝75.59/83.86/83.44 MHz。全て99 MHz不合格 |
| 最良配置での実時間 | TC8PSK27.9548 MSymbol/s＜28.86、RS31.8013 µs＞28.8288。性能条件を満たさず採用しない |
| 復号機能 | 最終S3 unittest 56件全合格。任意cost/Q15それぞれ655360状態を無限精度ACSで照合。RS262 vectors、途中reset、失敗経路も合格 |
| 残る環境内作業の優先項目 | 面積と実時間を同時に満たすFEC/メモリ分担の再設計。下限に残る24位置は使用可能な余裕ではない |

以下の履歴表にあるLUTのみの列は物理位置占有率ではない。最新値は上記圧縮レポートを優先する。

## 2026-10-10追加：PSRAMとIQ返送の実装を前進

[追加実装・検算](s3-psram-and-iq.md)、[source hash付き証拠](s3-psram-evidence/results.json)を保存した。

| 環境内で進めた不足 | 結果 | 完了としない範囲 |
|---|---|---|
| 抽象メモリから実DDRプロトコルへ | 2 die、256 B wrapped burst、CR0/ID読戻し、ODDR/IDDR、27→99 MHz PLL、write/read buffer、確定ackを追加 | sampling eye/IODELAY校正と全IO/位相STA |
| SPIとPSRAMの結合 | Octal/Quad各80 MHzからDDR端子モデルを通して96頁393216 Bが一致。出力stallとring周回を含む | S3 API/status、RF復調、散在interleaveアクセス、実機 |
| 結合時のoverflow | 32-tokenではoverflowする反例を確認。128-tokenへ増やして再検査PASS、BSRAM数は不変 | 実CPUの送信gapと全メモリ負荷のworst case |
| 頁commit後のack消失 | 未ackのprogress watchdog追加。両portで最終ack欠落を検出し未確定頁を公開しない | S3側の停止/再初期化 |
| PSRAMを含む受信経路のP&R | 2461 LUT4 /1391 FF /4 BSRAM /1 PLL、seed2でcore99.91 MHz。SPI2 226.40、SPI3 160.93 MHz。99/80/80制約PASS | IQ返送/FEC/復調を含む全体の合成ではない |
| TのIQ生成と返送の重畳 | 4 KiB×2面を追加。GIを含む129.9375 µs/頁、16頁65536 Bが一致。片面のACKで他面のtimeoutを解除しない | 実IQ producerとS3 scheduler/statusの統合 |
| 2面IQ通信回路のP&R | 1627 LUT4 /963 FF /6 BSRAM、core99.59、Octal191.28、Quad93.48 MHz。99/80/80制約PASS | このtopのmemoryはモデル。上のPSRAM topとの同時実装ではない |
| BIST image | PSRAM BIST `.fs` を生成・保存 | T/S受信imageではない。`safe_to_flash=false`、書込み/起動は未実施 |
| S用FECと実PSRAM受信経路の同時配置 | 配置前8022 LUT4 /4758 FF /10 BSRAM /2 DSP /1 PLL。heap計算打切り、sa異常終了、探索上限を短くしたheapは合法配置未発見 | 合法配置・99 MHz達成は未確認。まだ同期・全復調を含まない |
| 全S3機能試験 | unittest 45件、142.443秒、全合格 | 全受信機・実機の合格ではない |

以下は旧結果の履歴も含む。最新のメモリ/2面IQの範囲は上表で判定し、
旧「PSRAMのPHYも初期化もない」という状態とは区別する。

## 2026-10-10追記：通信の実装・結合検査

今回、以下を追加した。詳しい契約・制約は[s3-communication.md](s3-communication.md)、
検算可能な結果・source hash・失敗した配置履歴は
[通信証拠](s3-communication-evidence/results.json)を参照。

| 今回進めた不足 | 実施結果 | まだ含まないもの |
|---|---|---|
| 2 portの頁順序復元と書込み完了管理 | 16-slot ring、registered grant、未ack数、安定したwrite仲裁を実装。64頁262144 Bを照合 | 物理PSRAM/read経路、RF/FFT別ringの統合 |
| FPGA→S3のIQ返送 | 4 KiB RAMを全量fill後に公開。Quad/Octal各8頁、32768 Bが一致。最後のSCKで解放、6種の異常はepoch停止 | ready/status firmware、上流IQ producer、CRC、実IO setup/hold |
| 2本のSPIからの結合試験 | Octal/Quad各80 MHz→CDC→guard→reorder→ack付きメモリモデルで24頁98304 Bが一致 | メモリモデルはPSRAMの実帯域証明ではない |
| 受信異常の停止 | 切断/停止SCKのwatchdog、FIFO満杯、4096 B超過を試験。CS解除ではfatal状態を消さない | 電気的bit誤り・長時間実機試験 |
| 通信pin配置配線 | 1511 LUT4 /879 FF /4 BSRAM、seed3でcore100.25・Octal123.61・Quad84.29 MHz。99/80/80 MHz制約PASS。seed1/2の失敗も[s3-comm-endpoint.json](s3-comm-endpoint.json)に保持。SPI専用配線警告をBUFGで解消 | PLL、外部IO遅延、Gray/bundled-data制約、全受信機のSTA |
| S距離回路＋TC8PSK＋RSの再測定 | 5602 LUT4 /3498 FF /6 BSRAM /2 MULT18X18、100.16 MHz、99 MHz制約PASS | 全S復調、実PSRAM、通信を含む全体ではない |

38件のS3 unittestを再実行しすべてPASS。通信RTLの各修正にも、頁関連4件
（guard/reorder/store/wire結合）を再実行した。最終ログとsource hashを通信証拠に保持する。
以前に未commitだったログが失われたため、今回のFEC・通信結果は固定CAD環境で再生成した。
実ESP-IDFの旧リンクJSONは保存済みだが、この追記でSDKを再ビルドしたとは主張しない。

以下は2026-10-09までの履歴も含む。特に「送信endpoint・2 port再構成・独立timeout未完」
という旧行は上表で更新し、物理PSRAM/status/full receiverの不足と区別する。

## 2026-10-09までの実装履歴

今回、GitHub Actionsのstep開始前失敗に依存しないよう、実ESP-IDF5.5.1/Xtensa toolchainと
固定OSS CAD suite 2026-10-04をこの環境へ導入し、実コンパイル・合成・配置配線を行った。
その結果、旧RF queue配置がROM予約と4556 B重なり、SDKがapp_mainより前にabortする問題を発見した。
旧「リンク成功＝配置候補」という扱いを撤回する。ROM-safe配置とPHY直接初期化案へ進めたが、
PHY直接初期化によるRF dump互換性と全runtime allocationは未検証である。

| 今回追加・修正したもの | 実施結果 | 残る限界 |
|---|---|---|
| ROM予約監査 | target ELFの予約表と公式S3 rev0 ROM ELFを突合。旧64 KiB RF queueは4556 B衝突 | 実moduleのROM revision照合が必要 |
| ROM-safe SRAM配置＋PHY直接初期化 | 実SDKリンク成功。RF前の静的余白31832 B。起動task/TCB/allocatorを引いたDMA pool前上限21632 B、4 KiB poolの必要条件PASS | 全driver/workerの同時live allocation、起動、RF動作は未証明 |
| native RF MMIO driver | 16/40 MSps用bank切替・sentinel・所有権・64-bit時刻・fault停止をCで実装。正常/強制停止の4ケース、4911104 Bを照合 | 割込みを有効にしたRTOS統合、WCETとRF実機互換性は未完 |
| FPGA SPI受信、CDC、頁検査 | Octal/Quad各80 MHzで6頁ずつ、6162 token/portを照合。末尾SCK停止後の排出も検査。頁境界・epoch等の不正入力を拒否 | 送信endpoint、2 port reassembly、実PSRAMと独立timeoutは未完 |
| 通信部分のpin配置配線 | 766 LUT4/469 FF/2 BSRAM。core121.60、SPI2 113.33、SPI3 93.90 MHz。99/80/80 MHz制約PASS | core PLL、external IO delay、CDC skew、全受信機は含まない |
| native IQ10展開RTL | 全1048576値＋境界を含む1048832 sampleを独立byte列と比較、停止/backpressureを検査 | 2 portの順序復元後に接続する部品 |
| Tのデパンクチャ＋消去対応Viterbi | 符号化率1/2・2/3・3/4・5/6・7/8を独立符号化データで検査。欠落bitのcostは厳密に0 | frame/TMCC、interleave、demapperとの統合は未完 |
| SのTC8PSK survivor | 符号化bitに加えて選択した非符号化bitを保存・逆追跡。未知状態、入力停止、metric周回を含め16128情報bitで不一致0 | 全S復調器ではない。単純なbinary Viterbi代用を撤回 |
| SのTC8PSK距離回路 | FPGAのQ15 symbol入力から4枝の9-bit costとB1選択を生成。4145点の独立計算と一致。survivor接続も16128情報bitで不一致0 | carrier/timing/AGC、C/N性能、TMCC/frame、全回路の時系列は未完 |

根拠：`reports/s3-receiver-evidence/`、[通信合成](s3-comm-area.json)、
[拡張FEC合成](s3-fec-extensions.json)、第4節の実SDK/ROM監査。
以下の旧結果は比較履歴として残す。新しいTC8PSKやROM-safe配置へ旧Fmax/heap値を転用しない。

## 1. この環境で実行したこと

| 項目 | 実施内容 | 得られた結果・限界 |
|---|---|---|
| Viterbiの独立検算 | RTLと独立した171/133符号化器で無雑音入力を生成 | 旧32-ACS版は出力1792 bitの区間に対し、−256〜256の位置合わせを探索しても最小551 bit不一致。旧Fmaxを正しい復号器の根拠として使わない |
| 正しい方向のtraceback | 256行survivor、124段逆追跡、64 bit単位の出力を実装 | normalized14/modulo13の2方式で独立ビット列に一致。入力停止、長期metric周回、未知の初期状態、処理途中resetも検査 |
| metric幅の削減 | 13-bit剰余metricと符号付き差による比較を実装 | 無限精度Python oracleと2048 step×64状態＝131072値で一致。入力soft 8 bitを維持し、再量子化していない |
| FPGA面積・周波数 | survivor RAMと64択selectorの間に64-bit registerを追加し、PR workflowで実配置配線 | modulo13-pipe FEC+メモリprotocol部分は4782 LUT4、2653 FF、4 BSRAM、104.06 MHz。共通99 MHzを達成 |
| RS検証 | 独立ISDB RSベクトル、0〜8誤り、訂正不能、reset境界 | 262/262合格、最大2666 clocks/block。最新RS単体は107.52 MHz。全受信機の結果ではない |
| RF bank寿命 | sentinel書込み/再使用前の所有権確認と、期限・sequence・wrap・停止処理をCで実装 | 90 unit、1109925 sample、2772992 Bの完了payloadを独立に検査。未消費bankを黙って捨てずfaultへ移る。今回MMIO driverへ接続しfake-MMIOでも検査。全RTOS統合は未完 |
| キュー拡張 | 8/16頁、2ポート完了順逆転、分割arenaに対応 | 32/64 KiBそれぞれ10000頁＝40960000 Bを照合。全1048576種類のnative20値の梱包/復元も検査 |
| deadline再計算 | raw bank単位のバースト公開、有限packing速度、FFT停止区間をeventモデルに追加 | 検討中の方針ではTの32/48 KiBが失敗。64 KiBは4/6 cycles/sample仮定で4位相×100 msを通過。ただしCPU割込み全体を含む証明ではない |
| 実SDKのメモリ配置 | 8192点のFFT係数をquarter表で厳密に再構成し、RF初期化＋PSRAM＋SPIと実リンク | 係数16384→4098 B。旧20680 B案はROMと衝突し不採用。ROM-safe/直接PHY版は下位余白31832 B、詳細は第4節 |
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
これはbinary decoderの条件。今回のTC8PSKは9-bit cost最大511で別途6×511＝3066、7×511＝3577＜4096を確認し、剰余比較を使用する。
未知初期状態の取得時は先頭64 decoded bitを破棄する。連続入力を前提とするため、入力終了時の
最終64 bitのflushは未実装。下流にbackpressureは出せず、出力を常に受けられる必要がある。

SのRS期限は188 B / 6.52125 MB/s＝28.828829 us/block。
2666 clocksを99 MHzで処理すると26.929293 us、余裕1.899536 us（6.589%）。
旧80.08 MHzの共通clockでは33.291708 usだったが、今回の部分回路は99 MHz制約に通った。
この部分のRS期限のために別clockを追加する必要はなくなった。ただしbenchmarkのViterbi/RSは負荷回路であり、deinterleave等を含む実データ経路、全復調器、SPI endpoint、PLL/IOの全体STAは未完。
SのTC8PSK用距離・並列枝選択・非符号化bit保存は別回路として実装した。binary版の104.06 MHzをSへ流用しない。survivor＋RSの旧seed1は76.41 MHzで99 MHz未達だった。2026-10-10に距離回路を含む別構成を再生成し、100.16 MHzで99 MHz制約を通過した。source/各構成の結果は拡張FEC JSONを参照。構成を跨いでFmaxを転用しない。

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

## 4. ROM予約を含む実SDKの再監査

`ci/s3_rom_layout_audit.py`はapp ELFの`.reserved_memory_address`と、公式ROM ELFの
`ets_rom_layout`、`_dram0_rtos_reserved_start`を読み、SDKの動的予約と重ならないかを検査する。
rev0の予約は`[0x3fceee34,0x3fcf0000)`。SDKの`s_prepare_reserved_regions()`は
静的予約との衝突時にabortするため、リンク成功だけでは足りない。
旧quarter queue `[0x3fce8000,0x3fcf8000)`も旧late queue `[0x3fce4000,0x3fcf4000)`も衝突する。
証拠：[旧配置ROM監査](s3-memory/ROM-unsafe-quarter.json)。

新しい`PROBE_ROM_SAFE=1`の配置：

| 保持する情報 | SRAM領域 | 容量 |
|---|---|---:|
| native raw RF 3 bank | `[0x3fcb0000,0x3fce0000)` | 192 KiB |
| lossless packed RF ringの先頭14頁 | `[0x3fce0000,0x3fcee000)` | 56 KiB |
| ringの末尾2頁 | 下位static SRAM | 8 KiB |
| FFT slot0 | `[0x3fcf0000,0x3fcf8000)` | 32 KiB |
| FFT slot1 | 下位static SRAM | 32 KiB |
| Q15 quarter係数 | 下位static SRAM | 4098 B |
| 起動後にheapへ戻る範囲 | `[0x3fcee000,0x3fceee34)` | 3636 B |

ring合計64 KiB、FFT2面を維持し、ソフトウェア間引き・再量子化を追加していない。
late heapはmain task開始後に有効になるため、初期task生成の容量不足を救えない。

| 比較profile | 実SDK link | 下位静的余白 | ROM予約 | 起動task/allocator/DMA poolの必要条件 |
|---|---|---:|---|---|
| native-quarter-pool4 | PASS | 20680 B | **4556 B衝突** | 起動不可として除外 |
| native-quarter-romsafe | PASS | 12488 B（native-bank code追加前） | PASS | early task/allocatorだけで676 B不足。late解放後も4 KiB poolに1488 B不足 |
| native-direct-phy | PASS | **31832 B**（native-bank codeを実link） | PASS | early容量PASS。pool前内部空き上限21632 B、4096 B pool必要条件PASS |

直接PHY版は`esp_phy_enable(PHY_MODEM_WIFI)`を使い、NVS、PHY校正、上流のtune/prepareを保持する。
`esp_wifi_init`/802.11 MAC packet処理/event taskを起動しない。**私有RF dumpがMAC初期化を
必要とするかは未確認**なので、成立/安全なflash用firmwareとは扱わない。
このprobeのapp_mainは新bank loopをまだ呼ばず、`RF_bank_loop_invoked_by_app=false`。
新bank loop自体はlink済みであり、その分のcode/dataも31832 Bの値に含む。

直接PHY版の容量内訳は下位DIRAM31832＋RTC fast8168＋late3636 B。
起動6 taskのstack最低18432、TCB2040、allocator等最低1532 Bを引くと21632 B。
これは**空き容量の上限**で、連続領域確保成功、全初期化、fragmentation、receiver worker/SPI/PHYの
同時live allocationを保証しない。poolはheap内の予約であり、総容量へ二重加算しない。

- [pool4実link](s3-memory/RF-native-quarter-pool4-local.json)、[ROM-safe実link](s3-memory/RF-native-quarter-romsafe-local.json)、[ROM-safe起動容量](s3-memory/RF-native-quarter-romsafe-startup.json)
- [直接PHY実link](s3-memory/RF-native-direct-phy-local.json)、[直接PHY起動/ROM監査](s3-memory/RF-native-direct-phy-startup.json)
- [toolchain・ELF・sourceのhash](s3-receiver-evidence/local-toolchain.json)

上流RF sourceは`ESPARGOS/esp-sdr@e74f2a470972ec163c247f1fe88d32e08579242a`、
SDKはIDF v5.5.1 `fcae32885b0296b32044cb99ecbdc50d98dddb83`。上流指定SDKとの互換性は実機未確認。
生成sourceはGPL-3.0の出典を保持し、profile切替時は毎回immutable upstreamから再生成する。
以前のActions step前失敗は[記録](s3-memory/pool4-ci-blocker.json)として残すが、
現在はSDK/CADをここで実行できるため、実リンクや合成ができない理由にはしない。

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
| native RF driverとRTOS/SPIの結合 | bank lease、native MMIO loopと強制停止、PHY直接初期化の実SDK link | core役割、割込み配置、FFT/SPIを含むschedulerと実runtime確保を含むfirmware |
| 高速FFT/梱包と統合scheduler | quarter係数の厳密復元＋scalar FFT並列tile、梱包の完全値試験、45条件のdeadline計算 | S3 SIMD tile、2 core間barrier、必要ならSの並列packing、実SDKでコンパイルした全schedule。500 usはまだ目標値 |
| T全復調RTL | FEC、5率depuncture、消去cost、FFT入出力契約、部分合成 | RF FIR/resample、AGC/CFO/clock同期、Mode1/2/3/GI、TMCC、等化、階層/demap、time/frequency/bit/byte deinterleave、energy descramble、TS framingの結合と独立TS照合 |
| S全復調RTL | RS修正、TC8PSK距離/並列枝/B1保存/逆追跡までの機能試験 | matched filter/timing/carrier recovery、TC8PSK/QPSK/BPSK、burst/frame同期、TMCCとそのFEC、slot/TS選択、frame deinterleave、descrambleの結合と独立TS照合 |
| 通信endpointと物理PSRAM | SPI/SCT adapter、RX/CDC/guard/unpack、ack付き頁store、PSRAM burst/DDR/初期化/頁reader、2面IQ TXを実装。wire→DDR pin-model→頁readが一致。ack timeoutも試験 | RF/FFT別ring、実IQ producerと2面TX接続、ready/status/creditのfirmware統合、IODELAY校正、全アクセス/refresh競合のworst-case設計 |
| 全体clock/容量成立 | 旧部分FEC・PSRAM/RX・2面IQは別topで99 MHz制約PASS。実PSRAM＋FECの旧netlistは資源超過。圧縮版も同時配置未達、単体Fmax83.86 MHzでS期限未達。ROM-safe直接PHY版の必要条件PASS | 起動からRF/PHY/SPI初期化までの同時live allocation、通信とFEC等の統合、全PLL/reset/IO/位相/CDC制約、T/S各bitstreamの全体配置配線・STA。必要なら処理分担を再探索 |
| 切替firmware/復旧image | NOR配置と状態機械を実装/試験 | 実T/S/recovery image、書込み/読戻しdriver、RECONFIG drive、identity/epoch確認、壊れたheaderを含む復旧手順 |
| RF前段・電源の実装設計 | S3内蔵RFへUHF/LNB IFを直接入れる構成では不足と確認 | 周波数変換器、LO、T/S切替filter、利得/attenuator、LNB給電/保護、S3電源、clock、connector、終端を選定した回路図/BOM/PCB。部品値・製品BOMは未確定 |

この表の項目は、ソフトウェア/設計としてさらに進められる。現在のturnで全ての完成実装を
作ったとは報告しない。とくに全受信RTLとSIMD/RTOS統合は、試験済み部品を集めただけでは完成しない。

## 7. 今の環境では実施できない確認

| 不足しているもの | できない理由 | 必要な物・入力 | 合格条件 |
|---|---|---|---|
| T/S両RF前段の実特性 | RF回路/信号源/測定器が接続されていない | 設計後の前段、アンテナ/LNB又は校正信号源、スペアナ/VNA等 | 必要帯域、image/alias抑圧、雑音・利得・直線性を満たす |
| native16/40 MSps連続取得・直接PHY互換性 | S3実機がない | N16R8 module、ROM revision、RF入力、cycle counter/診断trace | PHY直接初期化でRF dumpが動作し、全sampleを途切れず取得。ROM予約衝突・bank上書き・sentinel誤判定なし |
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
- [ARIB STD-B20概要](https://www.arib.or.jp/english/std_tr/broadcasting/desc/std-b20.html)、[ITU-R BO.1408-1](https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-1-200204-I!!PDF-E.pdf)、[ARIB STD-B31 v1.6 E2](https://www.arib.or.jp/english/html/overview/doc/6-STD-B31v1_6-E2.pdf)

```sh
python -m unittest discover -s tests -p 'test_s3_*.py' -v
python ci/s3_legacy_decode_audit.py
python experiments/s3_bank_schedule.py --output build/s3-capture/bank-schedule.json
python ci/s3_comm_benchmark.py
python ci/s3_comm_endpoint_benchmark.py
python ci/s3_fec_extension_benchmark.py
python ci/s3_comm_evidence.py
```

過去の全S3試験17 methodと旧decoder反例は既存記録を保持。今回は追加回路/driver/起動監査を個別に検査し、実施していない全体試験へ読み替えない。

ホスト試験はunittest、C compiler、NumPy、Icarusを使用。FPGA計測は固定OSS CAD suite（過去はCI、今回はローカルでも実行）。
RF linkは`.github/workflows/s3-rf-coexist.yml`、メモリprobeは`s3-memory.yml`。
生データは`reports/s3-receiver-evidence/`と個別JSONに保存。PR #4はdraftのまま、mergeしない。
