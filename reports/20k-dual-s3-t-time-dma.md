# 実T time-deinterleaverとFFT／Sの接続

対象は従来から残っている第1項目（実client、有限保持、同時競合、資源）です。共有RSの第2項目には進んでいません。受信機全体の成立・採用を示すものではありません。

## 今回実装した境界と所有権

`dual_t_time_dma.sv` は周波数deinterleave／demap後のLLR列を受けます。入力順はsegment、carrier、bitの順で、1 carrierにつき6個の8-bit LLRを変更せず処理します。入出力portは連続4 byteを32-bit wordにまとめ、先頭byteをbits [7:0]へ置きます。RF入力やFFT出力を直接受けるdemapperではありません。

- 固定パラメータのMode、13 segmentsの3階層、合法I値から、遅延 `I*(95-(5*i)%96)` の同値groupをRTLのROMへ展開。同じ遅延の階層をまとめ、密ringのaddress／maskをRTLが生成します。PythonのT要求列を使いません。
- 1 symbol分のRAMで入力と並べ替え済み出力を交換。前symbolの同じ位置の4 byteを下流が受け取るまでは、新wordで上書きしません。全入力を受けてからgroup順にSDRAMと交換し、自然順の位置へ戻します。
- SDRAMの旧byteは専用32 Bレジスタへ退避してから書換えます。旧byteの出力、次blockの入力保持、SDRAM動作を重ねます。Tのgroup長とcursorは偶数byteなので、交換回路とsymbol RAMの間は2 byteずつ転送します。読出し完了時のwrite、write完了時の次readを同じedgeで受け渡せるようにします。元のsymbol RAMのbyteを先読みする前に旧byteで上書きすることも禁止します。
- 最後のwrite ACKと旧byte出力が両方完了してからring cursorを更新します。未蓄積の遅延位置は中立LLR=0。`out_settled`は全遅延が満ちたことを示します。最後の結果は`drain_only`で排出します。
- symbol RAMはMode 1/2/3で8/16/32 KiBの深さ、別に固定group表とcursor RAMがあります。上流はvalid/readyに従って入力を保持する必要があります。この上流保持は実capture回路へまだ接続していません。

`dual_fft_ts_memory.sv` は実T、既存実S、FFT、外部IO要求を接続します。T優先のT/IO仲裁、S優先の背景仲裁、FFT bank 0／背景bank 1–3を使用します。Tは交換回路内で旧応答を保持し、仲裁段の重複応答レジスタを省きます。IOが応答を停止すれば共有busへbackpressureします。各DMAが自分の未受理要求を保持し、旧256-descriptor FIFOは使いません。旧要求列試験のFIFO量を、この構成の保持容量として流用しません。

## 独立照合と期限の判定

単体ではcarrierごとの履歴式から期待byteを作り、RTLが生成するaddressを期待値生成に使いません。入力・要求・応答・出力を停止させ、全byte、symbol境界、隣接byte、所有権を確認します。Mode 3/I=1では98 symbolsを投入し、95段すべての立上がりとring再利用を確認します。

vector単体は全32開始offset×長さ1/32/33/773 Bの128 vectorsを、遅延応答モデルと実SDRAM controller＋端子モデルの両方で照合します。出力停止中の旧データ保持、部分write、隣接byte、refreshを検査します。2-byte版も全16偶数offset×長さ2/32/34/774 Bの64 vectorsを同じ2種類のmemory modelで照合します。

同時試験のT sourceは各OFDM周期に自然順の1 symbolを解放します。計算完了期限は解放＋1周期、前結果の出力期限は解放＋2周期です。source側に未captureのsymbolが何個残るかも数えます。機能試験の終了は期限合格を意味しません。

**`queue.peak_bytes`は実T接続時にはIO／管理要求の待ち量です。Tの待ちは`T_DMA.pending_input_bytes`に別記します。`staging_64KiB_pass`だけで全保持量が収まると判断しません。** Tの仮契約は未capture最大1 symbol＋DMA内1 symbolです。未実装の上流保持を無限容量とみなして採用することはありません。

## 結果

最初のbyte単位・直列交換実装では、48-symbol試験でTの計算期限48件／出力期限46件を超過し、未capture最大15 symbols＝112,320 B、最大解放→計算完了4,141.627831 µsでした。全byte一致を性能合格としません。[不合格JSON](20k-dual-s3/t-time-dma/serial-byte-integration.json)と、その全source hashに一致する[ソースsnapshot](20k-dual-s3/t-time-dma/serial-byte-sources.tar.gz)を保存します。

最終RTLの[Mode 1・48-symbol試験](20k-dual-s3/t-time-dma/mode1-short.json)では、計算／出力期限違反とも0、未capture最大1 symbol＝7,488 B、最大解放→計算完了220.637141 µs / 期限259.875 µsでした。FFT最大219.671626 µs、S／IO／管理も記載期限内です。IO／管理の最大待ちpayloadは9,024 B。Tを優先してもこの条件のIO期限は破っていません。

[単体125 symbols／3,294,720 B](20k-dual-s3/t-time-dma/unit.json)はすべて一致。vector試験は[4件合格](20k-dual-s3/t-time-dma/vector-unittest.log)。テストで使うSは既存の48 active TC8PSK profile、S出力は1 byte / 16 memory clocks、T入力は解放済み1 symbolを上流が保持してready時に4 B/clockを供給し、T出力は常時readyという条件です。135 MHzの4 B/clockはburst時540 MB/s、各Modeの平均LLR量は約28.814 MB/sです。この内部word転送はS3との通信路ではありません。未接続decoderがこの受け入れ条件を満たすと保証したものではありません。

3 ModeでSを連続3 super-frames投入する長さまで実行しました。全224 FFT frames、Tの2,875,392 B、Sの全9 super-framesを照合し、全clientの期限違反0、Tの未captureは最大1 symbolです。

| 条件 | FFT frames / S SF | T最大完了 µs / 期限 µs | FFT最大 µs / 期限 µs | T上流待ち B | IO／管理待ち B | 全期限違反 |
|---|---:|---:|---:|---:|---:|---:|
| [Mode 1](20k-dual-s3/t-time-dma/mode1-long.json) | 128 / 3 | 230.007439 / 259.875 | 219.734269 / 259.875 | 7488 (1 symbol) | 9728 | 0 |
| [Mode 2](20k-dual-s3/t-time-dma/mode2-long.json) | 64 / 3 | 346.610090 / 519.750 | 427.807544 / 519.750 | 14976 (1 symbol) | 17216 | 0 |
| [Mode 3](20k-dual-s3/t-time-dma/mode3-long.json) | 32 / 3 | 504.016032 / 1039.500 | 860.606504 / 1039.500 | 29952 (1 symbol) | 26688 | 0 |

全位相の上限証明ではなく、記載固定profile・到着／下流サービス条件での有限試験です。CIには単体試験と各Modeの短い同時試験（48/24/12 FFT frames、各S 1 SF）を追加し、データ一致に加えFFT期限、全client期限、IO／管理64 KiB、T未capture最大1 symbolの4条件を必須にしました。全受信機の採用ゲートではありません。

## 部分合成と資源

固定OSS CAD Suite 2026-10-04で合成し、`check -assert`を通しました。[全cell数・source hashes・log](20k-dual-s3/t-time-dma/synthesis/summary.json)。刺激・観測回路を含む部分topです。

| 部分top | logic / 20,736 | FF / 15,552 | BSRAM / 46 | DSP18 / 48 |
|---|---:|---:|---:|---:|
| T単体 Mode 1 | 2,265 (10.92%) | 1,020 (6.56%) | 7 (15.22%) | 4 (8.33%) |
| FFT＋実T＋実S＋memory Mode 1 | 9,231 (44.52%) | 4,425 (28.45%) | 17 (36.96%) | 10 (20.83%) |
| FFT＋実T＋実S＋memory Mode 3 | 9,328 (44.98%) | 4,429 (28.48%) | 29 (63.04%) | 10 (20.83%) |

当初の自然順RAM記述は分散RAMへ展開されました。read addressとwrite addressを明示して同期RAMの4 byte banksへ分け、全容量を増やさずBSRAMへ推論させました。合成結果のDSP数は部分topごとに最適化された値なので、単体値を単純に足して接続値へ置換しません。

Mode 3のこの部分だけでBSRAMは29個を使用し、残りは17個です。旧44-BSRAM allocationに無償で追加できるものではありません。上流の1-symbol保持、未接続の復調・FEC・capture等も含む全体収容は未確認です。上流保持を同じBSRAMに別途置くならMode 3ではさらに16 BSRAM相当が必要で、今回の29個へ無償で含めていません。実際の保持先・再利用は未確定です。また、応答から次要求への組合せ経路が増えるため、135 MHzを満たすかは全経路STAで確認が必要です。

## 継続する完了条件

今回の固定profileの実T grouping/reorderは実装しました。以下は元の第1項目内の残りです。

- 実capture／demapper／outputと有限保持・所有権の接続。固定パラメータのTをTMCCに従う設定へ接続し、SのTMCC連動slot制御を実装。
- 記載profileの期限・待ち量の反例は今回解消。未確認profileと実到着／下流サービス条件を接続し、全位相・最大burst・長期安定性を検証。
- 部分topと従来allocationの重複を除いた、全受信topの資源精算。

その後の共有RS接続、全体P&R／STA、S3 driver／実機WCET、RF／連続TSの確認という順序は変えていません。135 MHz／162 MHzはシミュレーションの条件であり、実機Fmaxの確認値ではありません。精度低下を伴うSoC追加decimation／requantizationは導入していません。


## 再現

Icarus VerilogとPython/NumPyを用意し、repository rootで実行します。合成はCIに固定版とarchive hashを記録しています。

```sh
DUAL_T_TIME_REPORT=build/dual-t-unit.json python -m unittest discover -s tests -p test_dual_t_time_dma.py -v
python -m unittest discover -s tests -p test_dual_vector_exchange_pipelined.py -v
DUAL_TRACE_REAL_T=1 DUAL_TRACE_REAL_S=3 DUAL_TRACE_FRAMES=128 DUAL_TRACE_MODES=11 DUAL_TRACE_LAYERS='[[3,4],[3,8],[7,16]]' DUAL_TRACE_REPORT=build/dual-t-mode1.json python -m unittest discover -s tests -p test_dual_memory_trace.py -v
DUAL_TRACE_REAL_T=1 DUAL_TRACE_REAL_S=3 DUAL_TRACE_FRAMES=64 DUAL_TRACE_MODES=12 DUAL_TRACE_LAYERS='[[3,2],[3,4],[7,8]]' DUAL_TRACE_REPORT=build/dual-t-mode2.json python -m unittest discover -s tests -p test_dual_memory_trace.py -v
DUAL_TRACE_REAL_T=1 DUAL_TRACE_REAL_S=3 DUAL_TRACE_FRAMES=32 DUAL_TRACE_MODES=13 DUAL_TRACE_LAYERS='[[3,1],[3,2],[7,4]]' DUAL_TRACE_REPORT=build/dual-t-mode3.json python -m unittest discover -s tests -p test_dual_memory_trace.py -v
python ci/dual_memory_clients_evidence.py --yosys /path/to/pinned/yosys --components t_time1,ts_clients1,ts_clients3 --output build/dual-t-synthesis
```
