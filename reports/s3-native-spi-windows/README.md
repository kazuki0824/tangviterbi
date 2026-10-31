# ② native到着時刻とSPI回収期限の接続

2026-10-27。SPI応答式へ渡す到着時刻を、native境界条件から導く計算器を追加。初回と通常bankを区別する。runtimeと①は変更しない。性能合格・正式割当・採用は0。

## 時刻原点とRFの仮定

原点は最初のbankを切り替えるときのINDEX観測の物理時刻。RF enable、最初のaccept、時計の読取り値そのものとは異なる。連続したunwrapped sample index、cpp=240/rateの周期、sentinel境界が真の書込み境界を表すこと、校正誤差による物理時刻の包含を仮定する。RF ABIや実機でこれらを確認したという意味ではない。

初回終端は `end(..., write_index, write_index, 1024)` で探索するので、初回切替INDEXをw0、終端をe0とすると `0≤e0−w0≤1023`。これは通常bankのEND=4096とは別。初回受理countの最小値も11264で、通常bankの12288とは異なる。

bank k≥1について `C=Σ count[1..k−1]` とする。初回countはこの和に入らない。通常切替は `THRESHOLD≤written≤THRESHOLD+LATE` なので、そのINDEXの原点からの進行量は

`C+12288 ≤ advance ≤ C+1023+12288+2000`。

任意sample位相に対し、少なくともn sample進む最早時刻は `(n−1)cpp+1` cycle、進行量がm以下の観測の最遅時刻は `(m+1)cpp−1` cycle。settlingは時計誤差の補正込みで物理16cpp以上を要求する。従って

- 初回acceptの最早時刻: `16cpp`。
- 通常bankのaccept最早時刻: `(C+12288−1)cpp+1+16cpp`。
- 通常bankの切替INDEX最遅時刻: `(C+1024+12288+2000)cpp−1`。

switch_earliestはINDEX観測より前なので、最後の値はswitch_earliestの上限にも使える。最初のswitch_earliestは原点以前である。

## 公開上限と容量の接続

既存worker/DONE/collectモデルから、各bankのswitch_earliest基準の物理公開遅延上限Hを与える。初回の公開上限はH、後続は上記切替上限＋H。prefixとして単調になるよう累積最大値を取る。実際の公開より前にならない保守的上限であり、最早acceptにHを足す誤った作り方はしない。

各bankのcount、最早accept、最遅publishを既存 `s3_spi_prefix_response.connect` へ渡す。必要な順序付き回収prefixが最早acceptより前に終われば、容量の十分条件になる。count列が有限なら、その列の条件付き検査であって全ての到着列や無期限運転の証明ではない。全到着列についての成立には、受理長の変動を覆う包絡/不変条件が必要。

保存例はT/Sともnominal count=12288の8bank。任意の受理長を入力できるが、例示の8bankを全ケースとは扱わない。未取得のHはnullとし、unprovedを維持する。Hが未確定の間は仮の公開時刻で性能合格を出さない。

## SPI直列化時間とソフト待ちの区別

実ソースの設定は80 MHz、command 16 bit、address 64 bit、dummy 0、headerもmultiline、payload 32768 byte。

| port | SPI clock数 | 240 MHz換算cycle | 直列化時間 |
|---|---:|---:|---:|
| 8lane | 32778 | 98334 | 409.725 µs |
| 4lane | 65556 | 196668 | 819.450 µs |

これは必要なSPI clock数からの計算。driver開始待ち、DMA停止/競合、割込み・完了通知、reapまで含むelapsed上限ではない。queue APIが返る前にDMAが始まる可能性もあるので、上記を「queue成功で返った後から完了まで」の時間Wの下限としても用いない。転送開始からの直列化時間と、API return基準の残り時間を混同しない。

実S/W/R、Hと通常/例外処理の時間上限は引き続き必要。既存SDK ELFや命令数だけをelapsed上限へ読み替えてはいない。

## 検証

独立の整数sample counterで、T/Sの全21位相×初回終端ずれ3条件×後続count変動27条件=1701条件を照合。切替遅れを含む実時刻が最早accept・切替上限・公開上限の間に入ることを確認。初回最小count、通常bank最小count、累積countの影響、header込みclock数も検査した。人工counterの数学的検算であり実RF計測ではない。

関連13 unittest成功（tests.log）。既存SPI回収上限・容量式・実Cの機能試験を含む。今回のCI成功を意味しない。

再現:
```sh
python -m experiments.s3_native_spi_windows --output build/native-spi-windows.json
PYTHONPATH=tests python -m unittest test_s3_native_spi_windows test_s3_spi_prefix_response test_s3_arena_limits test_s3_parallel_pack -v
```
