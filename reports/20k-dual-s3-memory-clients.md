# 第1項目の継続：密配置・有限FIFO・bank分離・S優先入口

**第1項目全体は未完了。共有RSには進んでいない。** この変更は前回の容量／queue反例に対し、信号のbit幅・sample rateを維持したままメモリ接続を改修するもの。有限条件でのデジタル試験と、受信機全体の成立を区別する。

## 追補：有限長vector交換の実RTL（第1項目の一部）

`rtl/dual_vector_exchange.sv`を追加した。1 vectorの開始byte addressと長さを受理し、入力byte列からBL8のaddress/data/DQMを自律生成する。入力を32 B registerへ保持し、旧burstをreadし、その有効byteが出力先へ全て渡ってからmasked writeする。最後のwrite ACKまで次のvectorを受理しない。途中のバースト要求をPythonから与える方式ではない。

旧データはSDRAM controllerのresponse registerに保持し、出力の最終byteまでresponse readyを下げる。追加の旧データbufferは持たない。入力側はready/valid契約が必要であり、停止できないRF入力を32 Bだけで吸収できるという主張ではない。addressは物理byte addressであり、bank 0回避mapping、group選択、ring slot更新はこのmoduleの外側である。長さ0と8 MiBを越える範囲はfaultで拒否する。

`tests/test_dual_vector_exchange.py`の2試験が通過：

- 全32開始offset × 長さ1/32/33/773 B、計128 vectorsについて、旧byte列・更新後byte列・領域外の全byteを照合。
- 要求受付、応答、入力byte、出力byteを停止させ、valid/payload保持とread-before-writeを照合。
- 同じscoreboardを実`dual_sdram_burst`＋独立したSDRAM端子メモリモデルにも接続し、DQM、refresh期限、tRFC/tRCD/tRP/tRAS/tWRを検査。

部分合成は **1,003 logic、603 FF、0 BSRAM、0 DSP**。256-bit刺激回路と観測回路込みの単体値であり、既存topとの加算を最新全体占有率として扱わない。[source hashesと合成log](20k-dual-s3/vector-exchange-synthesis/summary.json)。P&R/Fmaxは未確認。

**今回も第1項目の完了条件は変更していない。** 下表の実T/S client、producer保持・全体資源、最悪条件保証の3行を引き続き未完了とする。特に、このmoduleはTのcarrier grouping/reorderでもS frame permutationでもなく、既存FFT同時競合試験のPython要求列を全て置き換えたものではない。前回の64-frame期限結果を、この新moduleの同時動作保証へ転用しない。共有RSの第2項目には着手していない。

再現：

```sh
python -m unittest discover -s tests -p test_dual_vector_exchange.py -v
python ci/dual_memory_clients_evidence.py --yosys /path/to/pinned/yosys --components vector --output build/vector-synthesis
```

## RTLで実装した範囲

- `dual_burst_cdc.sv`と`dual_burst_arbiter.sv`へ32-bit byte maskを追加。末尾・先頭の部分BL8を書き込んでも、同じburst内の隣接vectorを破壊しない。
- 仲裁はdownstreamが実際に受理する時だけupstreamへreadyを返す。停止中は選択したsourceを固定し、そのsourceのvalid/ready契約でpayloadを保持する。310-bitの重複保持を削除した。通常はclient別response slotを維持する。
- 背景入口の二段目仲裁だけはdownstreamのresponse slotを直接使う。S/T consumerのbackpressureは背景全体へ伝搬する。今回の期限試験はresponse consumerが常時readyという契約であり、無期限停止への性能保証ではない。
- `dual_burst_fifo.sv`は256 requestsを有限RAMへ保存する。310-bit descriptor（write/address/data/mask）を2×160-bitへ詰め、合成上**5 BSRAM**とした。途中でRAMが18個へ複製される問題も発見し、単一read/write port表現へ修正した。低半分を受理時にRAMへ書き、高半分だけ一時保持する。満杯時はreadyを下げ、上書きしない。
- `dual_fft_memory_clients.sv`がT/IO FIFOとS優先入口を既存FFT―SDRAM接続へ結合する。外側はFFT/background round-robin、背景内はS優先。S優先で無制限trafficを受け入れるわけではなく、後述するCW到着契約が必要。
- FFT専用bank 0を確保し、backgroundはbank 1–3へ配置する。FFT側のlogical word addressはbit配線だけでbank 0へ変換する。2 MiBのlogical FFT範囲外、T/Sからbank 0への要求は拒否・faultとする。

追加試験では512 masksのCDC転送、FIFOの4096 requests×2 depthsの満杯・周回、RR／priority／直接応答の各仲裁で1024 requestsと停止中のpayload保持、bank保護を検証した。

## 明示したメモリclient契約

`experiments/dual_memory_trace.py`で有効byte数だけでなく、各burstの物理address・DQM・write data・期待read data・解放時刻・期限を生成する。

| client | 今回の契約 | 今回含まない実装 |
|---|---|---|
| T | 同じ受信遅延の6×8-bit LLRをgroup化した密ring。read完了前に同じ位置を書かない。vector末尾まで到着した時にBL8要求を解放 | 周波数逆interleaveからのgrouping、carrier順への出力reorderのRTLと資源 |
| S | peak CW間隔28.135828 µs、204 B/CWを7 BL8へ配置。read/write計14 requests、S入口を優先 | 規格のframe/bit permutationを含む実S client。現在は順次CW ringのaddress列 |
| capture/output | Q15 complexの2 frame転送分、8 samplesごとに1 burstを解放 | RF入力frameのcommitやFFT出力の実消費。試験は別所有のstaging領域で同量の転送を行う |
| 管理 | 10 MB/s、32 Bごと3.2 µs | 実TMCC/control firmwareとの結合 |

FFT input/middle/outputの所有権は既存DMAで管理する。backgroundのstagingを稼働中のFFT領域へ重ねていない。背景trafficはRFから実際に生成されたものではないが、前回の一様な合成address列から、**密ringの境界・周回・部分writeを持つ具体的なaddress列**へ進んだ。

Tの各vectorの期限は**解放から1 OFDM symbol周期後**、SはCW解放から1 CW周期後。FFTの期限は従来どおりframe開始からGI1/32周期以内。T vectorをsymbol末尾近くで解放しながら同じsymbol末尾を期限とする初期試験では人工的な期限違反を作っていたため修正した。Tには全groupをそろえて出力する1-symbol pipeline境界が必要で、このreorder実装を省略したとは扱わない。

## 容量の再検算

前回のS予約155,904 Bは203-byte payload基準だった。今回の204 B/CWを個別224 Bへ整列する配置では、double bufferは `384×224×2=172,032 B`。**16,128 Bの不足を修正した**。旧報告の数値を黙って維持しない。

密配置を全13,260構成で検算すると、T ring最大は5,690,880 B、S/FFT/staging/管理込み最大は6,321,664 B。FFT用2 MiBとbackground用6 MiBの分割では、background予約は6,190,592 B、6 MiBまで100,864 B残る。これは未実装reorderの追加traffic／容量を自動的に吸収できるという意味ではない。

密配置の最大平均trafficは全modeで `(segments,I)=(3,Imin),(3,2Imin),(7,4Imin)`。

| mode | T BL8 read＋write | FFT6転送＋S＋管理を含む合計 |
|---|---:|---:|
| 1 | 100.386724 MB/s | 315.446568 MB/s |
| 2 | 76.867725 MB/s | 291.927569 MB/s |
| 3 | 65.108225 MB/s | 280.168069 MB/s |

[更新した容量・交通量の全構成extrema](20k-dual-s3/memory-contract-v2.json)。旧`memory-contract.json`は前回コミット時点の証拠として保持する。

## 合成占有率

固定版OSS CAD Suite 2026-10-04のYosysで、FFT/DMA/CDC/SDRAM/有限FIFO/S優先入口を一緒に合成した。固定frame bases・可変mode・256-bit刺激回路・観測回路を含む部分topである。

| 対象 | logic (LUT＋ALU) | FF | BSRAM | DSP |
|---|---:|---:|---:|---:|
| 接続回路全体 | 5,425 / 20,736（26.16%） | 3,420 / 20,736（16.49%） | 13 / 46（28.26%） | 8 / 48（16.67%） |

初期の7,022 logicから、要求payloadの重複保持・背景応答slotの重複・FIFOの一時registerを削減して5,425まで下げた。信号品質やbit幅の変更による削減ではない。

**5,425は受信機全体の使用量ではない。** 旧FFT 2,500＋I/O 3,000の合計5,500に近いが、そのI/O枠には未結合のRF入口・TS/TMCC等もある。全I/Oを今回のmemory回路へ置き換えた扱いで、全体の残量を計算してはいけない。grouping/reorderも未計上なので、旧98.63%を最新全体占有率として使わない。

[合成結果・source hash・再現log](20k-dual-s3/memory-clients-synthesis/summary.json)。配置配線と全domain STAの合格証拠ではなく、162/135 MHzのsimulation条件を達成Fmaxへ読み替えない。

## 第1項目の残りと完了条件

| 残り | 完了条件 |
|---|---|
| 実T/S client | T grouping/reorderとS frame permutationをRTLで生成し、今回のdescriptor列・転送量契約を満たすか再測定。capture/outputも実frame所有権へ結合 |
| producer側保持と資源 | 試験で観測するFIFO外の未受理要求、S CW保持、reorderを有限bufferへ対応させ、最新全体資源台帳を成立させる |
| 最悪条件の保証 | 下記有限条件の成功に加え、実client契約に対する全位相／最大burst／refresh競合の待ち時間上限と長期安定性を証明、または反例で棄却 |

つまり今回は、byte mask経路、有限FIFO、bank分離、S優先入口の実装と、その具体的なメモリ契約での検証を進めた。**実受信client生成をPythonからRTLへ移したわけではなく、第1項目を完了扱いにはしない。** 次の共有RS作業へ進む条件は維持する。

## 最終RTLの有限検証結果

全mode各4 frames、Mode1連続32 frames、Mode1半周期offsetで4 frames、密配置の最大平均traffic構成でMode1を16 frames、**計64 frames**。全FFT bin・背景read応答・部分writeの隣接byte保持が一致し、FFT／T／S／IO／管理の記載期限を全件通過した。旧24 frame条件も全件通過。

| mode | 試験内の最悪FFT完了 µs | 周期 µs | 最小余裕 µs | FIFO最大entries | FIFO外の最大未受理requests |
|---|---:|---:|---:|---:|---:|
| 1 | 226.080348 | 259.875 | 33.794652 | 201 | 8 |
| 2 | 440.049501 | 519.750 | 79.700499 | 90 | 12 |
| 3 | 878.901554 | 1039.500 | 160.598446 | 37 | 22 |

Sは最大14未応答requests（1 CWのwrite/read分）。FIFO最大201/256に対し少なくとも55 entriesの余裕があった。ただしFIFO外でsourceが保持した最大22 requestsも存在し、そのproducer側の有限保持回路は未実装。FIFOだけを見て入力全体が完成したとは扱わない。

32 frameで滞留が増え続ける前回の反例からは改善したが、別address列・別仲裁を使う結果であり、前回の合成row衝突契約まで合格へ変更したものではない。試験したphase／到着契約の範囲を超える上限証明にはしない。

[全結果とsource hashes](20k-dual-s3/memory-clients/final-mode1-32.json)。同directoryに全mode・phase変更・最大traffic・旧条件の結果を保存した。

再現：

```sh
python -m unittest discover -s tests -p 'test_dual_burst_*.py' -v
python -m unittest discover -s tests -p test_dual_memory_partition.py -v
DUAL_TRACE_FRAMES=32 DUAL_TRACE_MODES=11 DUAL_TRACE_REPORT=build/dual-clients-32.json \
python -m unittest discover -s tests -p test_dual_memory_trace.py -v
DUAL_TRACE_FRAMES=16 DUAL_TRACE_MODES=11 DUAL_TRACE_LAYERS='[[3,4],[3,8],[7,16]]' \
DUAL_TRACE_REPORT=build/dual-clients-worst.json \
python -m unittest discover -s tests -p test_dual_memory_trace.py -v
python ci/dual_memory_clients_evidence.py --yosys /path/to/pinned/yosys --output build/dual-memory-clients-synth
```
