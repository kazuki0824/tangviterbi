> 2026-10-18追記：最新のT decoder実測・全候補予算・S RS有限待ちの訂正は[軌道修正報告](folded-t-recovery.md)を参照。本書の以前の予算は履歴として保持する。

# 2026-10-17：指令だけを逆方向へ返す処理分担の検算方法

この文書は初回検算の方法と固定入力を説明する。続行で追加した実回路測定は[共有FFTの実装・GPIO保持上限・全候補更新](shared-sdf-followup.md)へ分けた。旧320所有者は保持し、FFT実装variantを加えた448行・許可84組を追加している。性能未確認の案を採用しない規則は同じ。

基準は `main@9a5b5d28d2350a312bf0d73d264ac5af6fe83dd6`。①9K切替と②20K同時の両PRは、この**同じ固定入力**を読む。添付JSONのSHA256で入力を特定する。新しい受信機の実測値を作った報告ではない。

## 条件と判定の順序

1. 処理・資源・期限を検査する。未実装の費用を0としない。
2. 1を通過した候補だけに通信路を正式割当する。
3. 正式割当が非ゼロの候補だけを採用する。

今回、**全体性能確認済み0、正式通信割当0、採用0**。以下の帯域計算は、要求された通信根拠を欠落させないための補助計算である。`auxiliary` と明記し、先に通信が通る案を選んで性能を後付けしていない。これは「どんな実装でも不可能」という証明ではない。一方、全体の未確認値を残したまま「性能余裕内の第一案を確定した」とも報告しない。

RFは過去HEADと同じS3内蔵RF/private captureを対象とする。外部ADC・復調ICを勝手に追加しない。TのUHFとSのLNB IFをS3受信帯へ移すミキサー、帯域フィルター、LNB電源等は別途必要で、指定のFPGA基板とSoCモジュールだけでアンテナ直結できる意味ではない。Sは従来ISDB-S。ISDB-S3、映像復号、CAS解除は含めない。

T=16 MSa/s、S=40 MSa/s、native I10/Q10を保持し、32-bit格納語の未使用bitだけを除いて2 sample/5 byteへ可逆梱包する。T40 MB/s、S100 MB/s。S40 MSa/sの設定はESP-SDR固定sourceで確認したが、Sの約38.961 MHz帯域で所要C/N・BERを満たす保証ではない。eSpDR固定sourceの公開設定は16/80 MSa/sであり、そこに40 MSa/s版が実装済みとはしない。S80 MSa/sの場合は200 MB/sを別評価する。

FPGA→SoCは選局、電源、開始/停止、流量許可などの**指令のみ**。IQ、FFT入出力、LLR、syndrome、誤り多項式/位置/値、TSを返す案は除外する。これらを「control/status」と改名して残さない。統計値の常時返送も必要条件にしていない。TSはFPGAの外部端子へ出す。

## 全候補の範囲と漏れの扱い

有限の処理グラフを以下に固定した。

| 系 | 段 | 全所有者組合せ | 逆方向データなし |
|---|---|---:|---:|
| T | FIR/resample → 同期/GI → FFT → 等化/demap → 時間deinterleave → Viterbi → RS → TS | 256 | 9 |
| S | FIR → 同期 → TC8PSK/内符号 → frame deinterleave → RS → TS | 64 | 7 |
| TとSの組 | 上記の直積 | 16,384 | 63 |

RFがSoCにあるので、データの所有者がFPGAに移った後でSoCへ戻る所有者列は許されない。従って、許されるのはSoCの連続prefixとFPGAのsuffixだけ。`all-ownerships.json.gz` は**320件すべて**の所有者・境界データ・方向・CPU・部分資源・期限・除外理由を保持する。`all-boundaries.md` は許される16件すべて、`all-allowed-pairs.json.gz` は63組すべてを掲載する。残る16,321組は少なくとも片側に禁止方向のデータがあるため除外できる。

旧FFT offloadや4種類のRS部分offloadは、この制約で全て除外。SoCが自分でFIR・同期を行ってからFFTする案と、FPGAからFFT入力を返してもらう案を区別する。SoC上の通常の復調用FIR/resampleは比較集合に残すが、同じ周波数応答・演算精度を保つ必要がある。**リンクに合わせる追加デシメート、IQ/LLRの有効bit削減、平均圧縮率への依存は候補に入れない。**

これは未知の全アルゴリズムを網羅する主張ではない。FIR tap構成、FFT radix/streaming/folding、FEC内部の共有、Tの最大3階層、Sの変調切替、物理I/O回路は追加の設計自由度として残る。特に旧Sのstage budgetはTC8PSK中心であり、BPSK/QPSKを無料で追加できない。Tの複数階層のdecoder contextも無料とはしない。

## CPU計算の訂正と限界

`experiments/s3_partition_audit.py` は `stage_CPU_models` 内の `FFT_reorder_unpack` を加算した後、FFTをSoCへ置いた行で同じ並べ替え費用をもう一度加算していた。新計算はこれを一回にする。削除量は低46.791727、高93.583454 Mcycles/s。全320件で、これを足し戻すと旧値との差は最大約1.82e-12 Mcycles/s。単なる別模型との不一致ではなく、二重加算箇所を特定して再現した。

通信前のT FIR+同期+FFTは、それでも低135.581%、高182.678%。「FFTをS3へ移せば解決」とはならない。公式1024点sc16 FFTの15,623 cyclesは確認したが、8192点・RF同時実行・並べ替え・RTOS込みの測定ではない。旧scalar targetの不合格も維持する。新しいSIMD/FIR実装の最適化可能性まで否定しない。

CPU低/高は旧命令費用の感度モデルであり、WCETの上下限や統計的な信頼区間ではない。2 coreの480 Mcycles/sを合計で割っただけでは、1 coreへのpacking偏在、RF bank期限、割込み、DMA仲裁に合格しない。低モデルだけ通るT FIR案を採用しない。新表は旧200 cycles/pageを通信前の値から除き、通信表でAPI費用を別に付加する。SPI/SD20 µs、LCD8 µsは感度条件。I2Sのcallback費用0は未計上であり、最良CPU欄は楽観的必要条件にすぎない。

## 資源・期限の検算

| 項目 | 再計算値 | 判断上の用途 |
|---|---:|---|
| T Mode1/2/3、GI1/32周期 | 259.875 / 519.750 / 1039.500 µs | GIが長い場合だけの合格では不足 |
| T最大TS | 23.234699941 Mbit/s | 全13セグ、64QAM 7/8、最短GI |
| T RS到着 | 15,448.603684 CW/s、64.730769 µs/CW | バッファ付き最悪遅延は別検査 |
| S RS保守到着 | 35,541.871921 CW/s、28.135828 µs/CW | `28.86e6×2/(203×8)`。TS平均52.17 Mbit/sから期限を緩めない |
| S compact RS、2667 clocks/CW | 94.790172 MHz必要 | 93.1532 MHzは無バッファ条件に未達。有限FIFOは別途判定 |
| T/S/TMCC共有RS、2672 clocks/CW | 136.487918 MHz必要 | 162 MHz目標で平均84.252%。非preemptive待ち時間は別問題 |
| T32ACS＋S QPSK32ACSを共有する処理需要 | 151.434242 MHz | 162 MHzで93.478%。context切替費用は未計上 |
| T時間deinterleave | 5,690,880 B | FPGA 8 MiBの67.841%。SoC N16には外付PSRAMなし |
| 旧tile FFT+SDRAM平均需要 | 271.265875 MB/s | 135 MHz×32 bit×65%=351 MB/sは保証値ではない |
| 9K PSRAMモデルの同数read/write | 299.928994 MB/s | 99 MHz、256 B burst、82+87 clocks。任意scatterアクセスへ転用不可 |

RS到着間隔は持続サービス率の条件であり、各語が必ずその間隔以内に完了するという契約ではない。有限FIFOを含む遅延上限が必要。Tの短GIは時間的に最も厳しいが、全Mode/GI・階層/符号化率の実装を省略してよい意味ではない。

各段資源は固定入力の数値を再加算した**不完全な旧設計予算**。LUT4だけをlogic位置と呼ばず、実配置ではALU/独立FFの位置制約も必要。全体資源は `null` とする。①は画像ごとで最大値、②は同時搭載なので加算。共有RS等の別microarchitectureは専用予算として区別する。

## 全通信候補の有限カタログ

各シナリオの `summary.json.profiles` に18 profileすべてを保持する。任意clockを無限に列挙する代わりに、確認できる周辺機器モードとHEADの設計clockで比較する。以下は電気的に実証した帯域ではない。

| profile | 線速度 MB/s | header/API等控除後 MB/s | data/control信号数 |
|---|---:|---:|---:|
| SPI2 Octal80 | 80 | 70.327658 | 10 |
| SPI2/3 Quad80 | 各40 | 各33.395842 | 各6 |
| SPI2/3 Dual80 | 各20 | 各18.180204 | 各4 |
| SPI2/3 Single80 | 各10 | 各9.512308 | 各4 |
| LCD16 / LCD8 40 MHz | 80 /40 | 68.956229 /36.967509 | 19 /11 |
| SDIO4 SDR40 | 20 | 17.651368 | 6 |
| eMMC8 SDR40 /eMMC4 DDR40 | 各40 | 各31.690522 | 10 /6 |
| I2S0/1 TX40 | 各5 | 各4.980545 | 各3 |
| CAM16/8、I2S0/1 RX | 80/40、5 | 表の反対方向相当 | 今回は逆方向bulk不要 |

SPIはS3 master。SPI2 octalは3×4096 B/API、他は4096 B/API。80-bit header、20 µs/API、octalのみ0.25 µs/segment。LCDは4096+16 B、8 µs gap。SD系はcommand/CRC/20 µsを控除し、FPGA側card emulationの未実装を明示。SDMMCの2 slotを2 controllerとして合算しない。I2Sはmaster clock設計条件でありslaveの上限と混同しない。SPI0/1はモジュールのFlash/PSRAM用なので使用しない。

18 profile中、逆方向bulkの4個は不要。残りの全subsetについて同じcontrollerの重複、5組のGDMA、S3信号数を検査した**555集合**を作る。その各集合に必要な↑payload+0.01 MB/sの設定指令を配置し、port別負荷・残MB/s・残率・API感度を保存する。FPGA→S3は1 Mbaud UART、8N1の100 kB/sから指令10 kB/sを予約した基準witness（余裕90 kB/s）。送受各方向の能力を二重に使わない。

さらに各rowの `command_alternatives` に、**既存の全half-duplex port上の指令返送**とI2C400 kHz（40 kB/s設計容量、余裕30 kB/s）を記録する。half-duplex返送は0.01 MB/sをそのportから引き、↑の配分を再計算する。追加信号数も記録する。これらはcommandのpacket化・応答期限を検証した実装ではない。任意の指令返送方式まで全実装を網羅したとはしない。

`bandwidth-catalog.json.gz` は必要payload速度をkeyにした全合格subset、各portの割当と帯域余裕を持つ。各処理候補からkeyで参照する。候補対の全組合せは、このカタログの直積を次の条件で絞った**factorized集合**として完全に定義する。

- ①：T/Sの同一controllerの最大配線幅を取り、異なるcontrollerは配線unionを取る。基準UART1本＋TS3本を足して35以下。mode切替時だけS3 GPIO matrixとFPGA imageを切り替える。本数条件だけで固定pin map合格にはしない。
- ②：T/Sは別モジュールなので全配線数を足し、指令2本＋TS6本を足して34以下。両SoCのclockを同期したとは仮定しない。
- 指令経路を変える場合は基準UART分を除いて `extra_pins` を足し直す。両方向を同じSPI/SD portで使う場合はそのrowの再配分を用いる。

`raw-route-pairs.csv.gz` は上記集合のうちraw T/S＋UART基準を明示展開したもの。①19,203組、②18組。その他のprefixもカタログ参照と上記式で全組合せを定義している。これらの数は**性能合格数でも物理配線確定数でもない**。pinの電圧、clock入力位置、搭載負荷、NOR用pin、BL616競合、setup/holdは未確定。

UART/I2C/TWAIはraw主経路には不足する。TWAIの指令経路は外付transceiverを要する別ハード案で、このモジュール直結catalogには採用しない。USB FSは12 Mbit/sの線速度でrawにもT最大TSにも不足。Wi-Fiは同じRFを取得に使うので加算しない。S3にPARLIO/USB HSがある前提を置かない。独自DDR GPIO、未評価の高clock LCD、外付bridge、基板の追加pin取り出しは成立確認済みの経路として水増ししない。

## 専用GPIOを別に検算する理由

eSpDRの2×8-bit専用GPIO方式はS3実装の一次資料があり、通常DMAカタログの外だからという理由で落とさない。固定sourceの `protocol/link.h` と `transmit.S` は16 pairs→40 Bを91 CPU cycles/coreで送る。**梱包＋checksum＋送信を含む**ので旧DMA模型のpackingを再加算しない。一方でDMA帯域としてCPUと独立に加算もしない。

| T/S native速度 | lane数 | payload | loopだけの能力 | 下記の追加予算込み能力 | 余裕 |
|---|---:|---:|---:|---:|---:|
| T16 MSa/s | 1 | 40 MB/s | 105.494505 | 101.800269 | 61.800269 MB/s、60.707% |
| T16 MSa/s | 2 | 40 | 210.989011 | 203.600539 | 163.600539、80.354% |
| S40 MSa/s | 1 | 100 | 105.494505 | 101.800269 | 1.800269、1.768% |
| S40 MSa/s | 2 | 100 | 210.989011 | 203.600539 | 103.600539、50.884% |
| S80 MSa/s | 2 | 200 | 210.989011 | 203.600539 | 3.600539、1.768% |

追加予算はframing等600 cycles/unit、capture/管理2400 cycles/unit（10 µs）の**未測定設計条件**。合法unit長15,360～16,288とalignment0～15を全走査した。最悪相対費用はn=15,362、alignment15、service377.258333 µs。S40二laneの同一core到着間隔768.1 µsに対し49.116%、T16一laneは960.125 µsに対し39.293%。単laneはupstreamの二lane bank所有者を変える新実装が必要。upstreamのbusy pollingはcoreを100%占有するので、差分をそのまま復調用の自由CPUと扱わない。

**大きな見落とし防止：二laneで順番が前後したunitを保持する費用は無料ではない。** 最大packed unit40,760 Bは32-bit/byteの2 KiB/BSRAM換算で20 block。既存FPGA予算に追加すると厳しい。外部メモリへ全rawを一度書いて一度読む素直な方法はS40で200 MB/s、S80で400 MB/sを追加する。FPGAで復元後の32-bit語を保存すればそれぞれ320/640 MB/s。入力rateを超えるburst吸収、有限reorder深さ、低遅延serviceは別検証。小分けunitへの変更にはCPU overhead再計算が必要。

eSpDRはArtix-7上で20 MHz forwarded referenceから240 MHz sampling/120 MHz処理を生成する。Tangへ移植済みではない。①は受信PLLとPSRAM/復調PLL、②は2個の独立RF参照とSDRAM/復調clockを2 PLLでどう成立させるかが未解決。MS5351の追加clockがあるだけで位相同期済みとはしない。

同sourceの内部メモリ領域はvectors16＋core1 32＋core0 64＋data/work64＋capture256=432 KiB、512 KiBの84.375%。これは実リンクの使用量や自由heapではなく領域予約。capture bankとROM workspaceの重なりを、upstreamはRAM-only起動と独自処理で扱う。N8R8/N16/N16R8用Flash起動、private PHY初期化、ROM呼出との整合を新たに確認する必要がある。PSRAM8 MiBをその代わりの高速内部SRAMに数えない。

## 一次資料

- [Sipeed 9K仕様](https://wiki.sipeed.com/hardware/en/tang/Tang-Nano-9K/Nano-9K.html)：8,640 logic、6,480 FF、26 BSRAM、20 DSP18、2 PLL、8 MiB PSRAM、基板SPI NOR4 MiB。
- [Sipeed 20K仕様](https://wiki.sipeed.com/hardware/en/tang/tang-nano-20k/nano-20k.html)：20,736 logic、15,552 FF、46 BSRAM、48 DSP18、**2 PLL**、8 MiB SDRAM。総合比較表の4 PLLを転用しない。
- [Espressif WROOM-1/1U datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)：N16はPSRAMなし、N8R8/N16R8は8 MiB。GPIO35～37等のメモリ予約も考慮が必要。
- [ESP-SDR固定receiver.c](https://github.com/ESPARGOS/esp-sdr/blob/e74f2a470972ec163c247f1fe88d32e08579242a/main/targets/esp32s3/receiver.c)：16/40/80 MSa/s hardware rate、native IQ format。設定と連続受信保証を区別。
- [eSpDR固定source](https://github.com/h0m3us3r/eSpDR/tree/f279bf823eee41796dfd1ac21f13e1ed9b418c82)：`protocol/link.h`、`esp32s3/src/transmit.S`、`esp32s3/memory.ld`、`fpga/rtl/link_lane.v`、`docs/CLOCK-SYNC.md`を照合。
- [公式ESP-DSP benchmark](https://docs.espressif.com/projects/esp-dsp/en/latest/esp32/esp-dsp-benchmarks.html)、[SPI master v5.5.1](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/spi_master.html)、[I80](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/lcd/i80_lcd.html)、[dedicated GPIO](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/dedic_gpio.html)。
- [ITU-R BO.1408-1](https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-1-200204-I!!PDF-E.pdf)：Sの伝送フレーム、TC8PSK/QPSK/BPSK、RS/TMCC。
- [ARIB STD-B31公開英訳1.6-E2](https://www.arib.or.jp/english/html/overview/doc/6-STD-B31v1_6-E2.pdf)：TのMode、階層、RS、GIの基礎パラメータ。[版一覧](https://www.arib.or.jp/english/std_tr/broadcasting/std-b31.html)は最新版2.3を示す。旧英訳だけで最新規格への全面準拠を認定しない。
- [Gowin UG290公開目録](https://www.gowinsemi.com/en/document/main/database/1751/)：2.9.1E。今回最新版PDFの再取得はtimeout。9K切替はHEADの固定証拠と[旧公式UG290](https://www.gowinsemi.com/upload/database_doc/41/document/5b96299fe6aa7.pdf)の外部Flash address起動を照合した範囲に限定し、最新仕様の全面再確認済みとはしない。

## 再現と検査範囲

```sh
python experiments/control_only_estimate.py --board 9k --output build/control-only-9k
python experiments/control_only_estimate.py --board 20k --output build/control-only-20k
python -m unittest discover -s tests -p test_control_only_estimate.py -v
```

10個のunittestは全所有者の被覆、禁止方向、旧CPUの再現/二重計上訂正、有理数からのrate、port/GDMA競合、帯域保存則、未知の採用禁止、N16保存容量、旧資源加算、GPIO overhead/reorder費用を検査する。全項目を実行しfail-fastにしない。受信機RTLの機能・全体P&R・STA・実S3 WCET・RF品質の合格を意味しない。
