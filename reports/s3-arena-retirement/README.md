# ② RF bank解放と出力arena回収の接続条件

2026-10-26。RF bankが解放されても、その出力を保持する4×32768 byteのarenaが再利用可能になるとは限らない。実Cのaccept/complete条件を累積sample数から検算した。runtime sourceは変更せず、性能合格・正式割当・採用は0。

起動後に受理しようとする累積sample数をN、先頭から連続してDMA完了を回収済みのchunk数をkとする。可逆I10/Q10 packingの予約量は `B=5×floor(N/2)` byte、奇数の最後のsampleはcarryになる。容量条件は正確に `B−32768k ≤ 131072`。従って各accept時に

`k ≥ max(0, ceil((B−131072)/32768))`

が必要。これは**出力容量だけ**の必要十分条件で、RF bank所有権・sequence・deadline・fault等のaccept条件は別。完了済みchunkの総数ではなく、欠番のない先頭prefixの回収数である。

| 最大14352 sampleの累積bank数 | 累積予約byte | 最低限必要な順序付き回収chunk数 |
|---|---:|---:|
| 1 | 35880 | 0 |
| 2 | 71760 | 0 |
| 3 | 107640 | 0 |
| 4 | 143520 | 1 |
| 5 | 179400 | 2 |
| 6 | 215280 | 3 |

これは容量上の列挙であり、この最大bank列が特定時刻に到着するRFスケジュールの証明ではない。3最大bank分が出力に残ると空きは23432 byteで、次の最大bank35880 byteを予約できない。RF側の3 bankが全て解放済みでも起こる。

実C試験では最大サイズbankを1個ずつaccept/処理/collectして、RFのowned数を毎回0にした。最初の2chunkを送信し、chunk 1だけ完了してもretiredは0のまま、4個目のbankはBUSYになる。chunk 0も完了するとretiredは2になり、同じbankの予約が通る。拒否時の累積sample不変、faultなし、保有中DMA payloadと残る全出力のbyte一致も検査した。nativeに流量制御を追加したわけではなく、実native側ではaccept失敗は受信停止になる。

独立の逐次pair/carry計算と、奇数・偶数の受理長を混ぜた500bankの容量式を照合。関連6 unittest成功（tests.log）。実SPIの時刻を使う試験ではない。

残る接続条件は、各accept時刻までに上式のprefix回収が終わること。公開までのworker/collect遅延、port選択とsubmit、headerを含むwire時間、IRQ、reap、順序逆転の待ちを同じ時刻軸へ載せる必要がある。平均SPI帯域が流入を上回るだけでは証明できない。入力の実elapsed上限は未取得であり、ここでは性能合格を増やさない。

再現:
```sh
python -m experiments.s3_arena_limits --output build/arena-limits.json
PYTHONPATH=tests python -m unittest test_s3_arena_limits test_s3_parallel_pack -v
```
