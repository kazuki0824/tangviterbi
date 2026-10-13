# S3-N16R8：実SPI転送・無損失梱包・起動後SRAM配置

> 後続の[成立条件の再検証](s3-receiver-blockers.md)で、旧Viterbiの復号不良、
> RF bank公開を含む32 KiB queue案の期限違反、およびRF本体を含めた
> SRAM配置の問題を確認した。本稿の旧見積もりだけで成立と判定しない。

2026-10-09、PR #4。前回の[RS/FFT検証](s3-offline-closure.md)に続く実装記録。T/Sは基板外付けSPI NORの別imageへ切替。追加のソフトウェア間引き・再量子化は行わない。

**SPI/SCTアダプタとバッファ管理を実装し、実SDKでリンクを検証した。受信機全体の成立判定は引き続き未達。** 主な新しい問題は、通常SPI APIの時間を2 usと置けないこと、および実ドライバーを含めたSRAM配置である。

## 実装したもの

| ファイル | 役割 | 完了した検証 |
|---|---|---|
| `experiments/s3_transport.c` / `.h` | native I10/Q10の無損失20-bit梱包、4 KiB×8頁のqueue、2ポート完了順の逆転への対応、epochとモード停止、TのRF batch受付判定 | C実行、独立復号、2 host thread、UBSan / ThreadSanitizer |
| `experiments/s3_spi_transport.c` / `.h` | SPI2 Octal SCT / SPI3 Quad、DMA payload直接参照、リング末尾を跨ぐ複数頁、SPI完了確認までleaseを保持 | ESP-IDF v5.5.1の実コンパイル・リンク。実ピンでの通信は未検証 |
| `experiments/s3_sct_schedule.py` | API batch処理時間とSCT内gapを分離したT/Sの通信・所有権モデル | 正常条件と意図した過負荷条件、Tの256開始位相 |
| `experiments/s3_memory_probe` | 実ドライバー・hot IRAM・transaction object・FFT slotを含めた配置 | 実ELF/map。RF/PHY本体と完全なruntime heap/stackは未統合 |

RF処理への接続口は `s3_iq10_push`。入力wordのlow 20 bitsを保存する。8 sampleを20 bytesへ梱包する経路と、入力呼出し・4 KiB頁境界を跨ぐ端数処理を実装した。`consumed`は取り込んだword数を返し、queue満杯なら`BUSY`と未送信の端数を保持する。呼出側は未消費のRF bankを保持して再開し、bankの再使用期限を満たす必要がある。ここを無視してsampleを捨てる実装は採用しない。

RF送信の `s3_rf_submit` / `s3_rf_reap` はringと実SDK APIを結び付ける。SPI2のRF batchは最大3頁、SPI3は1頁。FFT送信はSPI2に8頁をまとめて渡せる。SPI2の内部SCT APIは **IDF 5.5.1に固定**し、SDK版が違えばコンパイルを拒否する。

送信完了の後続頁を先に解放しない。両ポート分の連続した完了prefixだけを解放する。世代違い・重複完了を拒否し、未完了DMAがあればモード切替resetも拒否する。epochは65535で使い切りとし、暗黙に再利用しない。予期しないSDK queueエラーではportを停止状態にし、payloadを再利用しない。自動的な故障復帰は未実装。

## ヘッダーをpayloadから分離

通常の公開SPI APIは1個の連続した送受信bufferを取る。旧案の「16-byte header＋別payload」を任意のDMA列に組む設計は未実装だった。現案はヘッダーをSPIのcommand/addressに移し、payload自体を加工せず参照する。

| フィールド | ビット数 | 内容 |
|---|---:|---|
| command | 16 | magic/version＋RF write / FFT write / IQ read request |
| address上位 | 16 | epoch |
| address中位 | 32 | stream中のbyte offset、2³²で循環 |
| address下位 | 16 | payload長4096 B |
| data | 32768 | 元の4096 B。RFは無損失20-bit列、FFT/IQは複素Q15 |

command/addressもdataと同じ4/8本で送る。ヘッダーは10 bytes相当で、Octalで0.125 us、Quadで0.25 us。SPIのDMA descriptor上限4092 Bとtransaction長を区別し、4096 B payloadはSDKの2 descriptorで送る。4 KiBは32768 BのRF queue/FFT slotを等分するための単位で、1 sample=20 bitsとの境界は一致しなくても、byte offset順に再結合すれば全bitが戻る。

`SPI_TRANS_DMA_BUFFER_ALIGN_MANUAL`と内部DMA領域・alignment検査により、SDKの暗黙なpayloadコピー／PSRAMへの退避を拒否する。SCT用configurationのコピー・確保は残る。ヘッダー変更に対応するFPGA endpoint、並べ替え、IQ ready/status、CRC等の信号品質検出は未実装。特にIQ readの要求ヘッダーだけでは、FPGAが新鮮なframeを返したことを証明できない。

## ホストで確認したこと

- 全 **1,048,576種類の20-bit値**を、上位12 bitsに無関係な値を置いた入力から梱包し、別のbit accumulatorで復号して一致を検査した。奇数入力・4 KiB境界・queue満杯・モード停止を含む。
- 別の2スレッド試験で **10,000頁、40,960,000 B**を照合した。5,000組で後続SPIの完了を先に返し、未完了payloadの上書きと重複完了を検査した。
- epoch切替、sequenceのUINT32_MAX跨ぎ、満杯、未送信取消、処理中reset拒否、Tのbatch受付限界の1 CPU cycle差を検査した。
- UBSan、ThreadSanitizerとも成功。証拠は [s3-transport-host.json](s3-transport-host.json)。これはS3上の実行時間や実DMA競合の検証ではない。

## SPI処理時間を再計算

[ESP-IDFのSPI説明](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/spi_master.html#transaction-duration)の約2 usはDMA linked-list設定部分の目安であり、API全体のWCETではない。同資料は通常の割込み転送について20 us程度のoverheadを含む式も示す。これを実装確認済みの固定gapと扱ってはいけない。

比較例としてAPI overheadを20 usと置くと、通常転送の容量はOctal **57.427270 MB/s**、Quad **33.395842 MB/s**。TのOctal下り71.522848 MB/sも、Sの2ポート合計100 MB/sも満たさない。これは20 us条件での不採用判定であり、全実装でこの速度に固定されるという主張ではない。

SPI2のSCTは複数segmentの設定と転送をDMAで連続させる。SPI3はこのSCTに対応しない。[SDK内部API](https://github.com/espressif/esp-idf/blob/v5.5.1/components/esp_driver_spi/include/esp_private/spi_master_internal.h)と[S3のcapability](https://github.com/espressif/esp-idf/blob/v5.5.1/components/soc/esp32s3/include/soc/soc_caps.h)に合わせた。APIはbatchごとにconfigurationを確保・解放するため、この費用もゼロとはしない。

以下は **FFT 500 us、API batch 20 us、SCT内実効gap 0.25 us、Quad API 20 us**という仮定である。0.25 usは設計上の仮定で、`sct_gap_len=1`の1 clockと等しいという意味ではない。DMA設定の読出し・競合も実効gapに含めて実測する必要がある。

| 使用方式 | 実効容量 | 必要量・余裕 |
|---|---:|---|
| T/S Octal・RF 3頁batch | 70.327658 MB/s | RF単独連続batch時の容量 |
| T Octal・FFT 8頁batch | 75.746648 MB/s | 32768 B返送に432.6 us |
| T Quad・IQ 1頁 | 33.395842 MB/s | 必要31.522848、平均余裕1.872994 MB/s |
| S Octal＋Quad | 103.723500 MB/s | 必要100、合計余裕3.723500 MB/s |

TではRFとFFTが同じOctalを使う。RFを常に3頁でまとめられる理想条件でも、必要なbus時間は約98.49%となる。実際はFFTのbuffer再使用期限を守るためRF batchを短くする場合があり、単一の「Octal容量」だけで成立を判定しない。

| eventモデル | 結果 |
|---|---|
| T：256位相×256 symbol | 全位相で期限違反0、slot解放最大1039.000391 us /1039.5 us |
| T：RF queue | 最大live32689 B、頁予約は32768 B /32768 B。余白は非常に小さい |
| T：期限を見ないbatch受付 | 位相519.75 usで期限違反を検出 |
| T：APIを30 usへ増加 | queueが1.2 MB相当まで増加し不成立 |
| T：SCT内gapを2 usへ増加 | queue容量超過で不成立 |
| S：100 ms、2ポート完了順を含む | queue頁予約最大32768 B、順番待ち完了payload最大4096 B |
| S：両APIを40 usへ増加 | 合計約91.818 MB/sとなり不成立 |

T用のbatch受付判定はCにも実装した。coordinator coreの拡張240 MHz cycle countを使用し、次のFFT期限に収まるRF batchだけを受け付ける。時間上限はcallerが与える契約であり、関数そのものが実WCETを保証するわけではない。

全結果：[s3-sct-schedule.json](s3-sct-schedule.json)。RFからの頁公開を一定rateで扱うモデルで、実RF bankの取得・512 sample等の処理slice・両core/内部SRAMの競合・Quadの到着過程までは統合していない。RF bankにデータを保持してbackpressureを吸収する場合の期限も未検証。256位相の試験は連続時間の形式証明ではない。

前回のT45組/S5組は、旧framing/2 us gapという有限の容量モデルに対する列挙記録として残す。今回の実SPI実装で全50組の通信を実証したことにはならない。**受信機採用数は0のまま。**

## 実ドライバー込みのSRAM配置

初回の実SPIリンクでは、RF queueを低位BSSに置くT配置が **5440 B超過**した。これは前回の最小probeの7080 B余白を上回る増分であり、旧配置をそのまま採用しない。

改訂配置はtwiddle `[0x3fce0000,0x3fce4000)`、RF queue `[0x3fce4000,0x3fcec000)` をheapから予約し、`app_main`より前は触らない。後者はROM起動stackの跡地を含む。[IDF main_task](https://github.com/espressif/esp-idf/blob/v5.5.1/components/freertos/app_startup.c)が`heap_caps_enable_nonos_stack_heaps()`を`app_main()`より前に呼ぶことと、[memory_layout.c](https://github.com/espressif/esp-idf/blob/v5.5.1/components/heap/port/esp32s3/memory_layout.c)の再利用区間を確認した。SDK更新時は再監査する。

さらに梱包・queue・batch受付・SPI送受信・scalar FFTのhot関数をIRAMへ置いた。実SDKの最終結果は次のとおり。低位queue案はこの段階で8000 B超過となる。

| 最終probe | リンク | BSS末尾 | RF領域までの静的余白 |
|---|---|---|---:|
| T・低位RF queue・hot IRAM | FAIL | `0x3fcb1f40` | −8000 B |
| T・起動後RF queue・hot IRAM | PASS | `0x3fca9f40` | **24768 B** |
| S専用・起動後RF queue・hot IRAM | PASS | `0x3fc99f40` | 90304 B |

計測sourceは `b5c6aae44001105aaf59446e0ab64a1a5f70a5c2`、[SDK workflow 37907725179](https://github.com/kazuki0824/tangviterbi/actions/runs/37907725179)、ESP-IDF v5.5.1 commit `fcae32885b0296b32044cb99ecbdc50d98dddb83`。成功probeの10個の検査対象hot symbolがIRAMに存在することもELFで確認した。ただしSDK内部も含む全call graphのflash不使用やWCETを証明したものではない。失敗probeを含めた測定完了でworkflowはsuccessとなるため、個別の `link_succeeded` を判定に使う。

生データ：[T低位](s3-memory/T-SPI-low-queue.json)、[T起動後](s3-memory/T-SPI-late-queue.json)、[S専用](s3-memory/S-SPI-late-queue.json)。hot IRAM化前の測定も `*-before-hot.json` として残す。host CIは [37907725151](https://github.com/kazuki0824/tangviterbi/actions/runs/37907725151) で成功した。

TのFFT slot 65536 Bとscalar FFT codeを残したprobeを、T/S共存firmwareの静的な基準とする。小さいS専用probeの空きは比較用で、同じfirmwareをSに切り替えれば自動的に65536 Bが空くとは扱わない。

実ABIでport構造28 B、segment56 B、ring管理84 B、DMA descriptor12 B。SPI2 descriptor pool576 B、SPI3 pool48 B、8segment SCT configuration480 BはSDKのruntime確保に必要で、このほかhost/device/queue/GDMA等のheapとstackも残る。これらがすべて空き静的領域に収まると実証したわけではない。

## 残っている作業と今回の到達点

| 実機なしでも残る作業 | 実機で必要な確認 |
|---|---|
| RF captureとの結合、bank寿命と両core処理の統合scheduler、実runtime heapの監査 | FFT・梱包・API・SCT gapを併走条件で測り、採用した上限以下であること |
| SIMD FFT、FPGAの新wire endpoint・並べ替え・ready/status、T/S全復調RTL、全pin/PLL/CDCの配置配線 | 80 MHz電気特性、RF入力と連続TS、PSRAMと内部SRAMの競合 |
| 外付けNOR image選択・復旧と停止/再開手順 | 書込み・再構成・電源断復旧、切替停止時間 |

今回閉じたのは「payloadをコピーせず送るためのコードがない」という不足と、そのCの所有権・梱包機能、SDKへの接続・静的配置である。SPIの実測時間や完全受信機まで完了したという意味ではない。とくにTの条件付きモデルの余裕は小さく、20 us /0.25 usを測定せず成立扱いにできない。
