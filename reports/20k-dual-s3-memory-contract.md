# 第1項目の再監査：メモリ配置の必要条件

2026-10-14。**第1項目は未完了。第2項目へ進まない。** 前回の有限競合試験で全frameが期限内だった事実は維持するが、それを実T/S clientのFIFO・全phase・長期安定性の確認へ読み替えない。

## 規格と配置を分けて検算

参照：[ARIB STD-B31 v2.2-E1](https://www.arib.or.jp/english/html/overview/doc/6-STD-B31v2_2-E1.pdf)、3.11.1、図3-23、表3-12／3-30（印刷頁36–37、62）。送信遅延は `I*((5*i)%96)`。受信側で `I*(95-(5*i)%96)` を加えて相補遅延とする。Iの選択肢はMode1が0/4/8/16、Mode2が0/2/4/8、Mode3が0/1/2/4。以下は64QAMの6本の8-bit LLRを全て保持する設計計算であり、規格がこのSDRAM配置を要求するわけではない。

`experiments/dual_memory_contract.py` は次の3配置を区別する。

| 配置 | 保存とアクセス | 状態 |
|---|---|---|
| carrier_padded | carrierごとに6 Bを32 Bへ整列。1回read＋1回write | 容量・帯域とも棄却 |
| aligned_group | **実際の受信遅延が同一**のcarrierを階層をまたいでまとめ、各symbolのvectorを32 Bへ切り上げ | 一部構成で容量超過。grouping回路は未実装 |
| compact_group_masked | 同一遅延vectorを隙間なくd個のringへ保存。各vectorにかかる全BL8を転送し、端のwriteにbyte maskを使用 | 容量は改善。現接続にはmask経路がなく未実装 |

各groupの遅延をd、1 symbolのpayloadをn bytesとすると、整列配置の容量は `d*32*ceil(n/32)`、密配置はgroup全体だけ整列して `32*ceil(d*n/32)`。d=0は直接bypass。d個のslotを使うにはread応答とconsumer保持を確定してから同じslotへwriteする必要があり、writeを先行させてはいけない。

密配置の転送数はslot kごとに `ceil(((k*n)%32+n)/32)`。これを全d slotで平均する。境界の余剰転送を無視せず、RMWを省くにはDQMが必要。現在の`dual_fft_memory.sv`はcontrollerの`req_dqm`を0へ固定しているため、密配置をそのまま接続すると隣接データを破壊する。

## 容量反例

Mode1、階層の `(segment数,I)=(1,4),(1,8),(11,16)` を使う。同じ遅延のgroupは既に階層間でも統合しており、さらに単純に統合できる余地を二重に見込まない。

| 項目 | 整列group | 密group＋mask（未実装） |
|---|---:|---:|
| T ring | 7,888,896 B | 5,144,832 B |
| S／FFT／staging／管理の既存予約 | 614,656 B | 614,656 B |
| 合計 | **8,503,552 B** | 5,759,488 B |
| 8 MiBまでの余裕 | **−114,944 B** | 2,629,120 B |
| T read＋writeのBL8交通量 | 93.829726 MB/s | 99.623890 MB/s |
| FFT全6アクセス＋S＋管理込み | 308.889570 MB/s | 314.683734 MB/s |

Sはここでは204-byte CWを個別に32-byte整列し、7 burstsのread＋7 burstsのwriteとする。既存の有効payloadだけの14.501084 MB/sに対し、転送量は15.922759 MB/s。これはS frameデインターリーブ全体のscatter実装の証明ではない。

正のsegment数を持つ1〜3階層、合計13 segments、全I選択の**各mode 4,420構成、計13,260構成**を整列group方式で列挙した。Mode1で6構成（上記の階層順列）が容量超過、Mode2/3ではこの容量必要条件の超過は0。変調混在・階層間出力順序・TMCC切替時の二重保持を含む全受信機の網羅性は主張しない。結果：[memory-contract.json](20k-dual-s3/memory-contract.json)。

## 長期queueに関する否定証拠と未確定部分

carrier単位の非集約配置は、全modeで総需要519.206068 MB/s。現controllerの最短経路でもrequest受理間隔は12 memory clocks以上（IDLEからCL3 readまたはTWR3 write完了を経てIDLEへ戻る）。135 MHzでの**楽観上限**は32×135/12＝360 MB/sで、refresh・row miss・仲裁・CDCはこの上限をさらに下げる。

したがって、この配置では平均でも159,206 bytes/ms以上の未処理交通が蓄積する。有限FIFOを選ぶことで永続動作へ変えることはできない。これは有限試験から外挿した判定ではなく、需要がサービス上限を超えることによる棄却。ただし、**集約・密配置まで不可能とする証明ではない**。

一方、360 MB/s以下という必要条件を通っても、実際のサービス下限や期限内処理は保証されない。単体controllerの良好な333 MB/s等を全アクセスへ適用しない。

## FIFOと資源

前回の5376 Bは合成queueの観測最大であり、容量保証へ採用しない。上記Mode1の非zero-delay groupは191個。例として各groupにread/write各1 burstをオンチップ保持する単純案だけでも `191*32*2=12,224 B`、2048 B/blockで最低6 BSRAM相当になる。descriptor、port構成、入出力reorderは別費用。

旧allocationの44/46 BSRAMへ単純追加すれば50/46となるが、既存枠の再配置・共有可否は未検証。**6 BSRAMは全実装の必須下限ではなく、具体的な単純cache案のpayload量からの下限**。SDRAMへcacheを置けばそのread/write交通も追加する必要がある。容量だけを増やして第1項目を閉じない。

## 第1項目を閉じる条件

1. 不合格の整列配置を置き換える。密配置ならbyte maskをCDC・仲裁まで通し、grouping／read-before-write／出力reorderを実装し、隣接領域保護と全LLR保存を検証する。
2. T/S・capture/outputの実address列と到着契約を結合する。予約済frameへの同時アクセスを排除し、FIFO／cacheの最大占有と配置予算を確認する。
3. その契約に対する最悪待ち時間と長期queue安定性を確認する。合成trafficの長時間試験は補助証拠として扱う。

これは新たな独立作業項目の追加ではなく、第1項目に元から必要だった条件の具体化。第2項目の共有RSには変更を加えていない。

再現：

```sh
python -m unittest discover -s tests -p test_dual_memory_contract.py -v
python experiments/dual_memory_contract.py --output build/dual-memory-contract.json
```

## 32 frame試験：FFT期限だけでは合格にできない

密group例の総需要314.683734 MB/sからFFT DMA内の4 frame転送126.091390 MB/sを除き、背景要求を**188.592344 MB/s**へ変更した。Mode1、row衝突profile 2、clock phase 2 ns、異なる入力の32 frame、GI1/32の259.875 µs周期。背景read/writeの照合・refresh検査・全FFT binの照合は従来と同じ。

結果：[fft-memory-long-stress.json](20k-dual-s3/fft-memory-long-stress.json)。全32 frameでbit exactかつFFT期限内、最大完了243.403400 µs。しかし背景未応答queueの累積最大は次のように増えた。

| frame index | 背景queueの累積最大 |
|---:|---:|
| 0 | 8,928 B |
| 8 | 69,376 B |
| 16 | 129,952 B |
| 24 | 190,496 B |
| 31 | **243,584 B** |

**この負荷契約では既存の65,536 B staging全体を背景queueへ与えても不足する。** FFTが期限内に終了しても同時trafficを保持できず、試験全体を性能合格にはできない。試験末尾で背景producerを止めてqueueがdrainできることは、連続受信の安定性を意味しない。

このprofileは転送量を配置検算へ合わせた**合成row衝突列**であり、191 groupの実address列を再生したものではない。したがって「全ての密配置が不可能」という結論にはしない。現行仲裁・現行合成負荷契約の不合格を保存する。採用には実address配置を固定してこの負荷を避けられる証拠、または仲裁・controllerの改善が必要。

再現（IcarusをPATHへ追加）：

```sh
DUAL_FFT_MEMORY_FRAMES=32 DUAL_FFT_MEMORY_MODES=11 \
DUAL_FFT_MEMORY_PROFILES=2 DUAL_FFT_MEMORY_BACKGROUND=188.592344 \
DUAL_FFT_MEMORY_REPORT=build/dual-memory-long-stress.json \
python -m unittest discover -s tests -p test_dual_fft_memory.py -v
```

`unittest OK`は機能／protocol照合の成功。期限、queue容量、採用の判定とは別。旧145.174484 MB/s・24 frame条件も再実行し、元の結果を維持している。
