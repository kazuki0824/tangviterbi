# 第1項目の継続：実S frame DMAと有限保持

**後続更新：[SDRAM転送間の待ち削減と再検証](20k-dual-s3-memory-turnover.md)。旧128-frame反例を同条件で解消し、他Mode・位相変更も通過。実T/IO接続等を含む第1項目全体は未完了。以下は各段階の記録。**

**第1項目全体は未完了。共有RSの第2項目には進んでいない。** 前回の残件を追加・再定義したのではなく、「実S client」「producer保持」「実clientでの競合検証」を進めた。

## 規格と実装境界

[ITU-R BO.1408-1 Annex 1 §5 / Figure 6](https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-1-200204-I!!PDF-E.pdf)の8-frame byte transposeを実装した。`rtl/dual_s_frame_dma.sv`の入力はinner decode後のmain-signal byte列で、出力は元のframe/slot順の204-byte codeword。送信されない先頭0x47を復元する。**descramble、inner decoder、TMCC/dummy-slot除去、RS自体はこのmoduleに含めない。今回の具体的profileは48 active TC8PSK slots。** 混在変調のslot制御まで完成したとはしない。

Pythonは送信側の8×203行列から入力byte列と期待出力列を作るだけで、SのSDRAM descriptor列を与えない。Sのaddress、DQM、data、write/read順序は全てRTLが生成する。

- 入力は2×203 Bのpacket保持。物理RAMは512 B、合成は1 BSRAM。
- SDRAMは2×384×224＝172,032 B。各領域をFREE/FILLING/FULL/READINGで管理する。
- 最後のscatter write応答でFULLへ移行し、それ以前には出力readを開始しない。
- 出力を512×35-bitの有限FIFO（payload 2 KiB、CW末尾・SF末尾・領域IDを付加）と1 wordの出力registerへ保持し、最終codewordの最終byteが受理されるまで領域を再利用しない。
- 出力が停止しても反対側の領域への入力は続けられる。両面を使い切れば入力readyを下げ、未読データを上書きしない。停止不能RFの無制限保持を意味しない。
- background論理空間を物理bank 1–3へ変換する。FFT専用bank 0へアクセスしない。`LINEAR_BANKS=1`では2 MiBごとのbank連続配置、0では従来の1 KiBごとの3-bank stripe。悪化したbank連続案は実験用に残し、defaultは0。`SLOT_MAJOR=1`では同一slotの8 frame分を隣接格納する。

`rtl/dual_fft_s_memory.sv`で既存FFT/DMA/CDC/有限T FIFO/S優先仲裁/SDRAMへ接続した。Tとcapture/outputは依然として既存の明示的な試験入力である。

## 保持とスケジューリングの検証

独立送信行列と、各byte・CW境界・super-frame境界・領域所有権・padding byte保持を照合した。3 super-frames、233,856入力byte、235,008出力byte、15,120 write bursts、8,064 read burstsを各条件で検査する。

| 条件 | 入力停止回数 | packet保持の観測最大 | 結果 |
|---|---:|---:|---|
| 7.5 MB/s入力、出力に短い停止を挿入 | 0 | 1 / 2 | 全byte一致 |
| 出力を長時間停止してから再開 | 87,250 | 1 / 2 | 入力を止めて全byte保持、再開後一致 |
| 7.5 MB/s入力、出力1 byte / 16 memory clocks | 0 | 1 / 2 | 全byte一致、3面目の再利用時も入力停止なし |

初版のpacket単位write優先では最後の条件で20,057回入力が停止した。scatter writeのburst境界で出力readを挟むよう修正し、同じ条件で0回になった。その後、burst組立てを1 byte/clockにpipeline化し、2 KiB出力FIFOでreadをまとめる構成を追加した。最終版の単体試験も上表のとおり通過したが、後述のT/IO競合は依然不合格。過去の不合格を成功として扱わない。

[追加の満杯試験](20k-dual-s3/s-frame-hold-fifo.json)ではmemory serviceを先頭12,000 clocks停止し、2 / 2 packet slotsの満杯を実際に通した。288回入力を止め、1 super-frameの全byte・padding・境界が一致した。

この試験のmemory応答は可変遅延の抽象モデル。実SDRAM端子モデルとの接続試験は別のJSONに保存する。1 byte / 16 clocksは仮の下流サービス契約であり、未着手の共有RS queue/DMAが実際に提供すると保証したものではない。

[単体の全結果・source hashes](20k-dual-s3/s-frame-dma-fifo.json)。clockは135 MHzの設計条件であり、達成Fmaxではない。

## FFT・実SDRAM端子モデルとの同時試験

Mode 1を128 OFDM frames、Sを3 super-frames連続投入した。Tは既存の密ring要求、capture/outputは従来のstaging要求、管理は10 MB/sで競合する。全FFT binと全S出力byteは一致したが、次の配置はいずれもT/IOの期限・保持容量を満たさなかった。

| S格納順／background配置 | FIFO外の最大要求数 | 最大待ちpayload B | T期限違反要求数 | S期限違反 |
|---|---:|---:|---:|---:|
| frame-major／1 KiB stripe | 7,806 | 258,016 | 61,594 | 0 |
| frame-major／2 MiB bank連続 | 10,991 | 359,936 | 68,869 | 0 |
| slot-major／1 KiB stripe | 7,055 | 233,984 | 59,734 | 0 |

slot-majorは同じslotの8 frame分を隣接させ、read address変換で元のframe-major出力順を復元する。入力精度、出力順、SDRAM予約容量は変えない。bank連続配置は悪化したのでdefaultには採用しない。

上表はFIFOを増やして合格としたものではない。FPGA内FIFOは途中保持を含め最大257 entries、残りは試験器の外部要求列に滞留した。**実T producerがその量を保持できるという証拠はなく、64 KiB予算を超えるためこの到着・配置契約は不合格。** S DMAは全3 SFを再利用期限内に読み終え、S入力側は最大1 byte pending／1 packet保持だった。成功したS/FFTと、不合格のT/IOを分けて記録する。

最大平均traffic構成 `(segments,I)=(3,4),(3,8),(7,16)` でも128 framesを比較した。

| S DMA | 最大待ちpayload B | T期限違反要求数 | S期限違反 | FFT最大 µs |
|---|---:|---:|---:|---:|
| 1 byte/clock組立て、slot-major、32 B出力保持 | 242,400 | 60,491 | 0 | 230.601346 |
| 同組立て、slot-major、2 KiB出力FIFO（最終版） | **201,792** | **59,798** | **0** | **230.077153** |

最終版のT/IO/管理全体の最大遅延超過は884.723494 µs、FIFO外の最大要求数は6,049。Sの3 SF完了は20.098486 / 30.901923 / 41.706784 msで、再利用期限21.608316 / 32.412474 / 43.216632 ms内。S入力pendingは最大1 byte、packet保持は最大1 / 2。全FFTとSデータは一致するが、**統合performanceは不合格、正式採用は0件のまま**。

[最終版の全結果とhash](20k-dual-s3/s-frame-fft-fifo-worst-128.json)、[FIFO追加前の最大負荷結果](20k-dual-s3/s-frame-fft-pipeline-worst-128.json)。試験で使ったvariant RTLは`20k-dual-s3/s-frame-variants/`へhash一致の圧縮snapshotも保存した。unittest/CIの機能試験成功と、JSONの`client_deadline_pass=false`・`staging_64KiB_pass=false`を区別する。

[初回stripe結果](20k-dual-s3/s-frame-fft-128.json)、[bank連続結果](20k-dual-s3/s-frame-fft-linear-128.json)、[slot-major結果](20k-dual-s3/s-frame-fft-slot-major-128.json)。初回JSONの`source_requests[1]`は未使用になった旧S刺激生成器の件数であり、実転送数は`S_DMA`欄。後続では当該欄をnullにした。初回のRTLは`20k-dual-s3/s-frame-striped-baseline/`にhash一致の圧縮snapshotを保存した。

最初の端子試験にはtestbenchのposedge counterとready生成のraceがあり、出力readyが有効に観測されずtimeoutした。readyをnegedgeで固定してから再実行した。上の数値は修正後の結果であり、そのtimeoutをRTLの不具合や性能値へ数えていない。

## 転送量の訂正とT staging方式の棄却

実S transposeは1 super-frame当たり5,040 write＋2,688 read bursts。平均 **644 B/CW、22.888966 MB/s**。旧順次CW ringは448 B/CW、15.922759 MB/sで、**6.966207 MB/s少なく見積もっていた**。172,032 BのSDRAM領域は変わらない。転送量の差を消すための再量子化・間引きは行っていない。

[全13,260 T構成の再検算](20k-dual-s3/memory-contract-v3.json)と[具体的staging方式の判定](20k-dual-s3/reorder-admission.json)を保存した。

Tのnatural-order LLR全symbolを一度SDRAMに置き、group順に読み直す方式は、入力stagingだけで57.627706 MB/sを追加する。出力reorder、row miss等を無視しても次の必要条件になる。

| mode | 最大平均traffic構成の既存需要＋実S MB/s | 入力staging込み MB/s | 判定 |
|---|---:|---:|---|
| 1 | 322.412775 | 380.040481 | 棄却 |
| 2 | 298.893776 | 356.521481 | 棄却 |
| 3 | 287.134276 | 344.761981 | この必要条件だけでは棄却できない |

135 MHz、BL8最短12 clocks、1053 clocks以内のrefreshにtRP＋tRFC＝13 clocksを予約すると、controllerの楽観的な持続帯域上限は355.555556 MB/s。上表の最初の2行はこの上限も超える。**全symbolをoff-chipへ保存するこの方式を棄却したのであって、on-chip grouping、FFT出力順変更、その他の処理分担まで不可能としたわけではない。** Mode 3の必要条件通過も採用判定ではない。

## 合成と全体予算

固定OSS CAD Suite 2026-10-04で測定。刺激・観測回路込みの部分top。

| 対象 | logic (LUT＋ALU) | FF | BSRAM | DSP |
|---|---:|---:|---:|---:|
| S frame DMA単体 | 1,402 | 1,070 | 2 | 0 |
| FFT＋既存memory clients＋実S frame DMA | 7,063 | 4,474 | 15 | 8 |

[合成結果・log・source hashes](20k-dual-s3/s-frame-fifo-synthesis/summary.json)。controller全体への追加は前回5,425から1,638 logic。既存のS frame buffer予算、I/O予算との重複を精算していないため、この値を旧20,452へ単純加算して全体合成値とは呼ばない。全体の収容・P&R・STAは未確認。

## 残件の扱い

前回の3つの完了条件を維持する。

1. 実client：今回の48 active TC8PSK S permutation/有限packet保持/2面所有権を実装。T grouping/reorder、実capture/output接続、SのTMCC連動slot制御は未完了。
2. producer保持と資源：S側は具体化した。T/IO側のFIFO外保持と、全体の重複を除いた資源台帳は未完了。今回、現配置・仲裁・要求列は64 KiBを超える反例が得られたため、その契約のまま進める案は棄却する。
3. 最悪条件保証：現契約の不合格反例と特定staging方式の棄却を記録。実T/S全clientの全位相・最大burst・refresh競合に対する待ち時間上限と長期安定性は未証明。

再現：

```sh
DUAL_S_FRAME_REPORT=build/dual-s-frame.json python -m unittest discover -s tests -p test_dual_s_frame_dma.py -v
DUAL_TRACE_REAL_S=3 DUAL_TRACE_FRAMES=128 DUAL_TRACE_MODES=11 DUAL_TRACE_LAYERS='[[3,4],[3,8],[7,16]]' DUAL_TRACE_REPORT=build/dual-s-frame-fft.json python -m unittest discover -s tests -p test_dual_memory_trace.py -v
python experiments/dual_reorder_admission.py --output build/dual-reorder-admission.json
python ci/dual_memory_clients_evidence.py --yosys /path/to/pinned/yosys --components s_frame,s_clients --output build/dual-s-frame-synth
```
