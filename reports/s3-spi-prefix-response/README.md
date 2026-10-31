# ② SPI公開・送信・回収をaccept時の容量条件へ接続

2026-10-27。前回の容量式に、2本のSPIで順序付き回収が終わる時刻の保守的上限を接続した。runtime変更なし。①は変更しない。全受信機の性能合格・正式割当・採用は0。

## 実装との対応

実ownerはcollect後にport 0のreap/submit、port 1のreap/submitを行い、各操作間にRF pollを挟む。各portの転送は同時に1件、s3_pp_takeはchunkのsequence順。先のsequenceが先に完了しても、retiredは欠番を越えない。これらを時間式の前提とする。

- P[i]: chunk iの末尾を含むbankがcollectされ、chunk全体が公開される時刻の上限。
- S: 任意の開始時刻から、利用可能な両portを公平に巡回して必要なqueue処理を完了するまでの上限。単一APIの費用ではない。
- W[0], W[1]: queue成功から完了が回収可能になるまでの上限。driver待ち、header、payload、DMA競合、完了通知まで含む。
- R: 回収可能になってから実際のreap/completeまでの上限。ownerの実行待ちと割込みも含む。

全て物理elapsed cycleの上限で、240 MHz固定の同一時刻軸を用いる。watchdog等の例外費用を落とさない。既存のworker応答モデルで得るbank解放上限はcollectまで含むためPの根拠に利用できるが、switch_earliest等の基準時刻を足す必要がある。今回実機のS/W/Rは取得していない。

## 順序付き回収の上限

`D = S + max(W[0], W[1]) + R`

`U[i] = max(P[i], U[i−2]) + D`、i<2では過去のUを起動時刻0とする。

U[i−2]までに先頭i−1個が回収済み。P[i]までにはchunk i−1とiが両方公開済みである。その時点で両方が未送信なら両portが空いている。一方が既に送信中なら他方に使えるportがある。後続chunkがportを占有している場合は、FIFO takeにより対象chunkは既に送信済みである。従ってS以内に対象2chunkのqueueが終わり、その後max(W)＋R以内に両方を回収できる。これが順序逆転を許す十分条件。

前回の累積sample Nに対する必要回収数 `k=max(0,ceil((5×floor(N/2)−131072)/32768))` を使い、各bankの最早accept時刻Aで `U[k−1] < A` を要求する。k=0なら容量上の回収義務はない。同一cycle内の実行順へ依存しないよう厳密不等号を使う。既存RF bank解放期限・worker期限は別途検査する。

入力bankごとにsample数、最早accept、最遅publishを与える計算器を追加。chunk境界を初めて覆うbankの最遅publishからPを構成し、全acceptの必要prefix、時刻上限、余裕を出す。未取得の時間は0で埋めずunproved。有限の到着列で合格しても、無期限運転の証明ではない。

## この上限の弱さも数値で確認

この式は速いportへ多くのchunkを配分する効果を捨て、2chunkごとに遅いportの時間を課金する。従って非対称portの成立判定には厳しすぎる場合がある。

例えば既存候補の80 MHz 8lane＋4laneではpayloadだけの理想時間が32 KiB当たり409.6µs/819.2µs。この式はS/R/headerを仮に0にしても2chunk/819.2µs=80 MB/sしか保証しない。Sの流入100 MB/sをこの式で長期保証することはできない。一方、理想合計帯域は120 MB/sであり、この結果を候補不可能とはしない。Tの40 MB/sも、実S/W/Rや有限bufferの条件が未確定なので合格ではない。

したがってこの式だけをS候補の棄却規則にはしない。同じ検算内で、次の非対称上限も追加した。

## 非対称portの上限

portごとの次回送信機会までの時間を `Tp=S+W[p]+R` とする。区間開始時に既に転送中でも、その残り・回収・次のqueueを最初のTpへ課金する。未送信の対象が残り続ける区間tには、両port合計で少なくとも `floor(t/T0)+floor(t/T1)` 回の送信機会がある。対象がそれより前に全て送信済みになった場合は、残りの最長転送時間を課金する。

`L(n)=min{t: floor(t/T0)+floor(t/T1)≥n}` を整数二分探索で求める。探索上端n×min(Tp)は1本のportだけでもn回の機会がある時刻であり、任意のtimeoutではない。

既に回収済みのprefix jを基点にすると、対象j+1〜iの上限候補は

`max(P[i], U[j]) + L(i−j) + max(W) + R`

となる。j=−1では起動時刻0を用いる。全ての過去prefixと先の2chunk式から得られる上限の最小値を採用する。各候補は独立に十分な上限なので、その最小値も上限。FIFO割当、fair scan、全時間上限という前提は共通である。

この式は十分長い公開burstではport別のサービス頻度を保持する。上の理想値・S=R=0なら、長期の係数は80+40=120 MB/sへ近づく。ただし有限128 KiBの容量条件には起動待ち、公開の遅れ、最後の遅い転送も効くため、120 MB/sという値だけでSを合格にしない。実ownerを固定の交互port割当に変更した計算でもない。

## 検証

独立した整数時刻の送信・完了・reap・FIFO take simulationで、巡回周期1〜4、両portの全位相、転送時間1〜4、同時公開/段階公開の計960条件を列挙。順序付き回収の実時刻がUを超えないことを確認した。数値は試験用で実SoC時間ではない。

4最大bankの予約で必要な最初のchunkが、acceptと同時刻なら未証明、1 cycle早ければ余裕0で条件付き合格になる境界も試験。関連10 unittest成功（tests.log）。保存した結果は実入力未取得のunprovedで、receiver_adopted=false。

非対称上限についても、周期1〜8の全64組×必要機会1〜29の最小時刻を検算し、128chunkの非対称公開burstで単純2chunk式より改善することを確認した。これは受信中に128chunkを保有できるという主張ではなく、サービス式だけの試験である。

残るのは実S/W/Rと公開/到着の包絡、全core・RF・メモリ・全FPGAの成立確認。今回の容量条件の接続を受信機全体の性能合格とは扱わない。

再現:
```sh
python -m experiments.s3_spi_prefix_response --output build/spi-prefix-response.json
PYTHONPATH=tests python -m unittest test_s3_spi_prefix_response test_s3_arena_limits test_s3_parallel_pack -v
```
