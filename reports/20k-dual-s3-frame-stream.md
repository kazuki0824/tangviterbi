# 実フレームcapture／出力とT/S DMAの接続

後続：[T入力保持RAMと位相別試験](20k-dual-s3-t-buffer.md)。以下の上流保持未実装・資源値・1P期限は当時の記録です。新構成の保持込み資源と複数条件による判定は後続を参照してください。

第1項目の実capture／出力所有権を進めた記録です。共有RS（第2項目）には進んでいません。

## 実装範囲

`dual_frame_io.sv`、`dual_fft_stream_memory.sv`、`dual_fft_stream_ts_memory.sv`を追加しました。試験側のSDRAM直接preload／直接readbackを置き換え、streamから実write要求、最後のwrite ACK、FFT起動、実read要求、stream出力までを回路で接続しています。入出力はQ15 complex 32 bitで、追加decimation／requantizationはありません。

入力は**同期・GI除去済みのFFT window**です。RF取得／同期回路を完成させたものではありません。FFTのbin出力とTのLLR入力の間の等化・demapも未接続で、同時試験では独立した2つのstreamです。Sは既存の48 active TC8PSK profileです。

3つのframe slotはFREE→CAPTURE→READY→FFT→OUTPUT→FREEを遷移します。最後の入力を受けた時点ではなく、最後のSDRAM write ACKでREADYになり、最後の出力wordを下流が受け取ってからFREEになります。FFT用中間領域は1つで、演算は直列です。最後のACK以前の起動、停止中の出力の変更、未消費frameの上書きを検査します。

| 領域 | bank 0内のlogical word address | 予約 |
|---|---:|---:|
| input slot 0 / 1 / 2 | 0 / 8192 / 16384 | 各32 KiB |
| middle | 24576 | 32 KiB |
| output slot 0 / 1 / 2 | 32768 / 40960 / 49152 | 各32 KiB |

合計224 KiBの予約は既存FFT予約256 KiB内です。Mode 1/2でも固定間隔を維持します。backgroundはbank 1〜3で、外部backgroundからbank 0への要求を拒否します。

capture FIFOは16 descriptorsのRAMに、既存FIFOのingress／output保持を加えます。さらに32 B pack、発行済みwrite、32 B output保持があります。「16×32 Bだけが全保持量」とはしません。FIFO外でstream sourceが止まる場合のRF保持は別に必要です。入力framingの早いlast／欠落lastはepochをfaultにし、reset後にのみ再開します。CDCは固定slotを保持するtoggle mailboxであり、物理CDC制約・STAは未検証です。

## 試験契約

core 162 MHz、memory 135 MHzのデジタルシミュレーションです。有効サンプルは123.046875 ns間隔、GI 1/32のframe周期は259.875／519.750／1039.500 µs。GIを含む周期へサンプルを均等化して負荷を低く見積もりません。

sourceはreadyが下がれば未送信sampleを試験器で保持し、後で追いつきます。これは回路外の有限RF bufferを実装した証拠ではありません。`blocked_cycles`はvalidがreadyを待ったmemory clock数です。**データ一致と、無停止入力の成立は別判定**です。下流は19 memory clocksごとに1 clock停止し、他は受理します。

`scheduled_window_end_to_output_ns`は、予定frame周期終端から最後のbin受理までの時間です。実際の最後の入力時刻からのlatencyではありません。遅れたsourceを基準に期限を後送りしません。

Tは各symbol周期に全LLRを解放し、上流保持は別契約です。Sは毎byteを実レートで解放、出力は1 byte / 16 memory clocks。同時試験では管理trafficを追加していません。したがって合格しても以前の管理負荷を含む条件へ一般化できません。

## 結果

### 2 slot案の不合格と修正

最初の2 slot案は全データが一致しても、3 Modeともcapture入力に待ちが発生しました。[結果JSON](20k-dual-s3/frame-stream/two-slot-concurrent.json)と[hash対応ソースsnapshot](20k-dual-s3/frame-stream/two-slot-sources.tar.gz)を残します。

| Mode | FFT frames | T期限超過 | T最大 µs | capture待ち clock | 予定frame終端→出力完了最大 µs |
|---|---:|---:|---:|---:|---:|
| 1 | 48 | 20 | 338.457726 | 286993 | 315.584555 |
| 2 | 24 | 0 | 385.306293 | 26863 | 538.047046 |
| 3 | 12 | 0 | 603.130509 | 12005 | 1056.907658 |

SDRAM最終仲裁の応答を直接渡す選択肢を加え、stream接続だけで有効化しました。既存topのdefaultは従来の応答保持です。さらにslotを3組にして、出力待ちのframeを保持したまま次のcaptureを受けます。SDRAM予約を160→224 KiBへ増やしますが、入力精度やサンプル数は変更しません。

3 slot構成の出力完了契約は予定frame周期終端＋2周期以内です。これは元の2 slot案の期限を後から緩めて合格にしたものではなく、回路と予約量を変更した別構成です。3番目のslot再使用期限、capture待ち0、T/S期限を同時に検査します。

### 3 slot構成の有限試験

[確定ソースの同時試験](20k-dual-s3/frame-stream/concurrent.json)は全84 FFT frames／294912 bins、T 1078272 bytes、S 3 super-framesを照合し、全データ一致でした。

| Mode | FFT frames / S SF | T最大 µs / 期限 µs | capture待ち clock | frame終端→出力最大 µs / 契約 µs | FIFO最大 |
|---|---:|---:|---:|---:|---:|
| 1 | 48 / 1 | 259.372045 / 259.875 | 0 | 317.985460 / 519.750 | 1 |
| 2 | 24 / 1 | 381.447034 / 519.750 | 0 | 528.274366 / 1039.500 | 1 |
| 3 | 12 / 1 | 598.360139 / 1039.500 | 0 | 1007.574820 / 2079.000 | 1 |

T計算・出力期限違反は全Modeで0、上流未captureは最大1 symbol。S入力未受理は最大1 byte、S出力完了は20.099405312／20.095138645／20.099286793 msで、2 super-frame後の再使用期限約21.608 ms以内です。

**Mode 1のT余裕は0.502955 µs（約0.19%）しかありません。** 今回の開始位相での有限成功を、全位相、別TMCC profile、管理traffic追加、実復調producer、長期安定性の保証へ一般化しません。性能余裕確認済みの正式候補には昇格させません。

[単体試験](20k-dual-s3/frame-stream/unit.json)は3 Mode各4 framesと出力長時間停止4 framesの計65536 binsを照合。長時間停止時には有限FIFO／所有権により入力へbackpressureを返し、未消費frameを壊さず再開しました。早いlast／欠落last／reset復帰も検査し、[2 unittest成功](20k-dual-s3/frame-stream/unit.log)。従来topはDIRECT_RESPONSE=0を維持し、[既存FFT-memoryのMode 1・profile 0・2 frames](20k-dual-s3/frame-stream/legacy-regression.json)も再確認しました。

## 資源と合成

[合成証拠](20k-dual-s3/frame-stream/synthesis/summary.json)は固定Mode／階層と256-bit刺激・観測回路を含む部分topです。

| Mode | LUT＋ALU | FF / 15552 | BSRAM / 46 | DSP / 48 | RAM16SDP4 |
|---|---:|---:|---:|---:|---:|
| 1 | 10735 | 5209 (33.49%) | 17 (36.96%) | 10 (20.83%) | 80 |
| 3 | 10955 | 5218 (33.55%) | 29 (63.04%) | 10 (20.83%) | 80 |

LUT＋ALU欄にdistributed RAMを含めません。使用toolchainの`gowin/lutrams.txt`は16×4 bit RAMのcostを4とするため、80個を320位置相当として別加算すると11055／11275位置、20736に対し53.31%／54.37%です。実配置占有率ではありません。

pinned Yosysの標準flowではmixed address busに未駆動の`$buf`が残りました。ABC9直前に`splitnets`を入れてbit接続へ展開し、FF mappingを含む全段を実行しました。最終`check -assert`を必須とし、未mapの`$_*`／`$buf`セルも拒否します。`setundef`で不具合を隠していません。旧topの合成flowは変更しません。

Mode 3は残り17 BSRAMですが、未接続T producerの1 symbolを別の32 KiB RAMに保持するなら16 BSRAM追加で45/46となり、既存共有RSの2 BSRAMまで単純に別置きすると47/46です。**この別置き方式を全体収容済みにはできません。** 他の復調回路・TMCC・RF取得・PHYも含めた全体合成値ではなく、以前の20452 logic／44 BSRAM予算へ無償で追加することもありません。

## 残件の範囲

この変更は第1項目のうち、同期済みFFT windowの実capture／出力と有限slot所有権を実装するものです。第1項目全体の完了ではありません。既に挙げていたRF同期・等化／demapperとの接続、T上流の有限保持、動的TMCC設定／S slot制御、全体資源、全位相・実到着／下流サービス条件の保証が残ります。2 slot案の不合格を修正した有限試験と、残る全位相の保証を区別します。正式通信割当・受信機採用は0件を維持します。

## 再現

```sh
DUAL_FRAME_REPORT=build/frame-io-unit.json python -m unittest discover -s tests -p test_dual_frame_io.py -v
python -m unittest discover -s tests -p test_dual_frame_io_fault.py -v
DUAL_FRAME_TS_REPORT=build/frame-ts.json python -m unittest discover -s tests -p test_dual_frame_ts.py -v
python ci/dual_memory_clients_evidence.py --yosys /path/to/oss-cad-suite/bin/yosys --components stream_ts1,stream_ts3 --output build/frame-stream-synth
```

機能試験が成功しても、JSONの`deadline_admitted=false`を合格へ読み替えません。有限条件の結果であり、全位相の上限証明でも全受信機の収容・STA合格でもありません。
