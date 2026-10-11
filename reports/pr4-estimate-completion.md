# PR4：最良候補を決める前の不足と、継続する検証

2026-10-11。基準HEAD `28f4ec4c36f1392fb6221792c3320e2a912ef75c`。

現行PR4から**成立済み／最良と確定した第一案へ絞り込むことはできない**。
個別案の実装・測定は必要な比較資料を増やす作業として続ける。
PR5で撤回したのは、部分共配置の結果から第一案を決定した判断であり、
個別案を検証する行為でも、9K＋S3の可能性全体でもない。
PR5はclosedを維持し、実装全体を無条件で取り込まない。

「最良」は比較対象・基板条件・性能条件・評価軸を固定した集合に対する判断とする。
全候補を同じ深さまで実装する必要はない。対象を限定した資源・期限の必要条件で
除外できる実装は除外できる。未評価の代替実装までその失敗を拡張しない。
残った未確定候補が最良判定を変え得る間は、比較を閉じたとしない。

## 現在の台帳の範囲

`reports/s3-partition-audit/estimate.json.gz` の検算結果：

| 対象 | 列挙済みの全stage所有者 | CPU平均モデル通過 | 全体performance未確定 | 比較の状態 |
|---|---:|---:|---:|---|
| S3・T | 256 | 22 | 256 | 必要条件の探索。最良候補未確定 |
| S3・S | 64 | 2 | 64 | 必要条件の探索。最良候補未確定 |
| C5・T/S | 本台帳に含まない | 未評価 | 未評価 | 未列挙を「成立0」と読まない |
| S31・T/S | 本台帳に含まない | 未評価 | 未評価 | 未列挙を「成立0」と読まない |
| C61・T/S | 本台帳に含まない | 未評価 | 未評価 | 未列挙を「成立0」と読まない |

S3の320行はstage所有者の有限集合であり、全microarchitectureの集合ではない。
24行のCPU平均通過、2169 port subset、通信容量の余裕は全体性能の合格数ではない。
全体成立を確認した候補はまだなく、未知の候補を含めた実現不能の証明でもない。

元の4構成（C5-WROOM-1U、S31-WROOM-3U-N16R16V、S3-WROOM-1U-N8R8、
C61-WROOM-1U-N8R2）と、現在のPR内S3-N16R8実験の対応も明示する必要がある。
Flash/NOR容量、PSRAM予約GPIO、内部SRAMとDMA領域を型番別に検算する。
今回、元のHTMLの現在版は読取りエラーで取得できなかったため、固定済みS3入力の
範囲だけを検算した。残る3 SoCの最新判断や対象変更履歴を復元済みとはしない。

## 不足と閉じる条件

| 不足 | 既存証拠の限界 | 環境内で続ける作業／見積もりを閉じる条件 | 実機に残す確認 |
|---|---|---|---|
| 4 SoCの比較集合・対象型番 | S3台帳しか再検算していない | 元資料と型番対応を復元し、SoC別の分担・除外理由・未確定事項を同じ条件で列挙 | RF ABI・対象モジュールの実動作 |
| 全体FPGA／内部・外部メモリ | 単体・部分topの資源と、条件付きSDK余白 | 各残存実装のFIR、同期、復調、全interleaver、FEC、保持、TS、通信、CDCを含むtop／map／P&R／STA。容量と競合をmode別に検算 | PSRAM PHY校正・同時IO timing |
| 各coreの期限とbuffer寿命 | CPU平均と仮定した500 µs等。scalar実装は既に下限で不合格 | SIMD worker、RF/packing、SPI API、RS/RPC、IRQ、段間同期、全frame ingress/egressの配置を定義し、実装と対応する費用・上限・未知項目を候補ごとに記録 | RF/GDMA併走WCET・poll jitter・連続性 |
| 性能確認後の通信割当 | 平均帯域の探索。endpoint/ready/credit未結合 | 性能条件を通過した分担について、全messageの方向・burst・半二重競合・pin/clock/GDMA・CPU費用・同一batch依存を閉じる | 信号品質・実gap・DMA完了順序 |
| T/S排他的動作・切替 | 別imageという方針 | 固定配線のunion、work area再利用、NOR容量・image選択・停止/drain/reset/復旧を一貫した制御へ結ぶ | 再構成・再起動・復旧・停止時間 |
| 復調品質・連続TS | ANSI FFT／FEC局所vector | 全8192 binとnative IQを保持し、独立T/S信号から全鎖の出力TSを照合。通信都合の間引き／再量子化を追加しない | C/N、偏差、マルチパス、長時間TS |

見積もり上の条件付き成立と実機確認済み成立を分ける。実機未確認という欄は、
未実装のtop・endpoint・schedulerを完成したことにする代用にはならない。
最良候補の確定には、比較を変え得る未知項目が解消されるか、限定した結論を
変えない根拠が必要。見積もりを完成させただけで実受信機の動作が保証されるわけではない。

## 今回進めた不足：bounded FFT workerとRF serviceの接続

`experiments/s3_fft_worker.c` は2 coreに各stageの512 blockを固定割当する。
13 stage、1 step最大16 block＝64 butterfly、全体832 tile call。
acquire/releaseの単調progressで段間の書込み可視性を保証する。
相手のstage完了を待つstepは戻るので、待機中もserviceを呼べる。
各stepの前後でserviceを呼び、tile/service失敗を共有faultへ記録する。
最後のservice成功前に完了を公開せず、faultを持つframeはreadyにしない。
frameを再利用・送出する前に両workerを停止/joinする契約を維持する。

`s3_fft_capture_service.c` はcore0だけで既存のnative RF poll、上限付き無損失packing、
nonblocking DMA/credit callbackへ接続する。core1から同じRF/ringを操作しない。
packingまたはpumpが失敗した場合はRF writerを停止する。
実RTOS task起動/pinning、FFT frame受渡し、実SPI DMA/credit、stack/heapの同時占有は未結合。

検証結果：

- 2 host threadで実C workerとANSI tileを実行し、random/extremesの全8192 binが公式ANSI全FFTと一致。
- 片coreをstage境界で200 step停滞させ、次stageのtile数が増えずserviceが400回呼ばれることを確認。
- tileとRF serviceの開始前／終了後failureではframeをreadyにせず、相手もfaultを検出。
- native fake-MMIOと接続し、T/S×通常／処理停滞の4条件を試験。通常の完了payload **4,919,296 B**を独立byte列と照合、停滞時にRF停止。
- このRF接続試験のtileは**合成した24-cycle stub**。150 frameを完了したという結果を8192点SIMDの速度へ転用しない。
- 関連21 unittest合格。固定Xtensa GCC14.2でworker込みSIMD bundleは未解決symbolなし。RF service objectの依存は既存3入口のみ。

worker追加でtarget bundleのtextは2832→3284 B（＋452 B）。IRAM section470 B＋literal20 B、
係数rodata16384 Bは不変。これはSDK外objectのsection値で、SDK実リンク後のIRAM／heap占有ではない。
SDK profileにもworker state／codeの保持とIRAM検査を追加したが、今回の実ELF再リンクは未実施。

先行HEAD `28f4ec4` のSIMD/tile SDK jobはCIで成功し、IRAM配置・定数表保持を確認した。
そのmapの静的RF境界までの余白は18,264 B。allocator考慮後の起動時空き**上限**8,064 Bから
4,096 B DMA poolを引くと上限3,968 B。追加FFT worker task/stack、PHY/driver同時live memory、
fragmentationは未計上で、十分な余裕とは判定しない。
[固定HEADのCI結果・ELF/map hash](s3-fft-simd-evidence/prior-sdk-ci.json)を保存した。
新workerを含むSDK結果へ流用しない。

`CPU_WCET_verified=false`、`SIMD_executed=false`、`receiver_adopted=false`を維持する。

再現：

```sh
PYTHONPATH=tests python -m unittest -v test_s3_fft_worker test_s3_native_capture test_s3_fft_simd test_s3_fft_simd_tiles test_s3_startup_memory_bound
python ci/s3_fft_simd_evidence.py --cc xtensa-esp32s3-elf-gcc
```

source/object hash・逆アセンブル・log：
[SIMD証拠](s3-fft-simd-evidence/results.json)、
[worker全bin照合](s3-fft-simd-evidence/worker-result.json)、
[21 unittest](s3-fft-simd-evidence/worker-unittest.txt)。

`complete_estimate=false` / `performance_stage_completed=false` / `receiver_adopted=false`。
