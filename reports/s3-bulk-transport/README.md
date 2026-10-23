# ②：32 KiB raw SPI送受信の実装検証

②だけを進め、前回 `588704f` の「既存4 KiB通信形式では32 KiBを送れない」を解消する実験用API・RTLを実装した。**32 KiB送受信の機能試験は合格。全受信機の成立判定・採用はまだ0件**。①の構成・PRは変更しない。

## 変更と接続条件

- `s3_spi_open_bulk` / `s3_spi_prepare_bulk`：SPI2 Octal又はSPI3 Quadを、SCTなし・非同期・単一32 KiBトランザクションで送信する。D711、epoch、4 KiB境界のbyte offset、length=32768、payloadは無変更。連続した内部DMA領域が必要。queue/reapを既存実装と共有し、完了前再利用、polling、旧page/IQ read APIとの混用を拒否する。**新API自身はbank/ring所有権を管理せず、呼出側がbufferを保持する契約**。
- `s3_spi_rx`：既定4096を維持し、明示的な `WRITE_BYTES=32768` でcounter・終端を変更。実行時の任意可変長ではない。
- `s3_bulk_page_split`：32 KiB frameのheader/epoch/lengthを検証し、無コピーで8個の4 KiB token frameへ分割する。各pageのoffsetを4096増分し、2^32 wrapも保持。既存page guard/reorder/storeへ接続可能。合成header中は入力FIFOに待ってもらう。
- 接続は各portについて `rx(32768) → bulk_page_split → 既存guard/store`。RX overflowとsplit faultをstore/TSのepoch停止に合流させる必要がある。今回の2port試験ではこの接続まで実施した。既存受信機top・RF pumpを自動でbulkへ切り替えてはいない。
- 新経路はSoC→FPGA raw payloadのみ。FPGA→SoC payload、追加softwareデシメート・再量子化は導入しない。

## 検証結果

[全チェックとsource hash](results.json)、[全試験ログ](tests.log)、[2port統合結果](pipeline-result.json)。`python experiments/check_s3_bulk_transport.py` で10 test moduleを全件実行し、失敗しても後続を実行する。17 unittestと `git diff --check` が全てOK。

| 検証 | 結果 | 検証の限界 |
|---|---|---|
| 実C API、SPI2/3 descriptor、length/方向/offset、busy/reap、無効prepare後の再送禁止 | OK | ESP-IDF境界はhost shim。実SDKリンク・DMA動作・実CPU時間ではない |
| 80 MHz 4/8lane SPI → CDC → split → page guard、random stall、offset wrap | OK、各65536 B、16page commit、16432 tokenを全比較 | 99 MHz consumerの有限trace。実配線・P&Rではない |
| bad length、bad epoch、途中切断、余分な末尾byte | 両lane幅で検出 | framing検出。CRCや任意bit error検出ではない |
| Octal/Quad同時、遅いQuadが中間32 KiB、共有16page store、後続Octal追越し | OK、98304 Bを全word比較し順序回復 | 3batch、ack付きbehavioral memory。無限時間のskew/SDRAM保証ではない |
| 従来4 KiB RX、overflow、store、C ring、control、RF pump、FFT exchange | 全てOK | 旧機能の回帰確認。②でFFT往復を採用する意味ではない |
| 前回bank/CPU模型の6試験 | 全てOK | 前回の不成立条件を維持。実CPUの測定にはならない |

余分な末尾byteの試験では既に8pageがcommitした後にRX overflowを検出する。過去pageを巻き戻す設計ではないため、fault時のTS停止は必須。フレーム全体の検証が済むまで全pageを保留したことにしてはいけない。現split watchdogは262144 consumer clocks、既存page guardは32768 clocks。いずれも停止検出限界であり、全体リアルタイム期限合格を意味しない。

Icarus Verilog 12.0をローカル展開して実行した。最初の試行時はシミュレータがなく、その後導入して全件を再実行した。最終結果に未実行をOK扱いした項目はない。

## 見積もりへの反映

全分担・全経路候補は[既存台帳](../partition-recheck-20261023/README.md)を継続する。今回の実装はraw分担Rの32 KiB仮説の**通信機能だけ**を進めたもの。以前の「通信形式変更は未実装」はこの新API/RTLについて更新するが、旧 `s3_wire_make` は引き続き4 KiB専用であり、その否定試験も正しい。

| 条件 | 継続する見積もり／現在の状態 |
|---|---|
| S raw上り | native I10/Q10、100 MB/s（＋前方設定0.01 MB/sを前回模型で確保） |
| S Octal＋Quad、32 KiB、header保守値1 µs、API20 µs | 合計余裕15.089 MB/s。multiline headerの実際のbit数はより短いが、余裕を水増ししない |
| S 2core CPU高模型 | 理想RF均等分割＋port別所有で97.460% / 95.493%。新API実測値ではない |
| S送信buffer | 128 KiB仮説。今回APIは1bufferの連続性を要求するが、allocator/link map/2core共有ringは未実装 |
| FPGA追加資源・timing | 新splitの配置配線は未実施。旧部分回路94.652%使用・152.091 MHzを新回路の値として流用しない |
| FPGA全復調、T/S独立TS | 未統合。旧共有K7最低152.627 MHz未達も未解決 |
| 下り | 指令のみの既存UART/I2C候補。今回bulk機能による下りpayload追加なし |

したがって性能合格→正式通信路割当→採用の数は0→0→0を維持。機能試験合格を性能合格に繰り上げない。

## 未完了と今回の保存境界

今回Aは「実C送信descriptorとFPGA受信分割、2port reorderへの接続を有限試験で確認した地点」。Bは2core bank/packing所有権、raw-only内部RAM配置、実SDK送受信タスク、全FPGA統合とP&R・実機計測である。Aを独立したレビュー可能な変更として保存するのは妥当だが、依頼全体をAで完了とするのは妥当ではない。

Bのソフトウェア実装やSDK準備を続けることは可能であり、この保存境界を外部制約による探索終了とはしない。実ボードは本作業環境に接続されておらず、実機CPU時間・RF品質・同時RF→TSの成功を記録する根拠はない。採用分担の確定は引き続き未完了。
