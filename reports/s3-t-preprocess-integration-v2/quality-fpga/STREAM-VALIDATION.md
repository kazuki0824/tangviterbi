# T 残存 FPGA の RTL ストリーム検証

2026-11-05 に、保存済み v2 RTL と `run_stream.py` を使って9条件を実行した。
これは今回の新しい実行結果である。失われた別の出力ファイルを復旧したものとしては扱わない。

**9条件すべてで、受理した入力から独立に計算した整数 oracle と全出力が一致した。**
ただし、バックプレッシャーなしで2フレームまたは8フレームを連続送信すると容量不足になる。
最初に失うのはいずれも4798番目の complex sample、cycle 74011、約479.700926 µsである。
512 µs周期で8フレームを送る条件では損失がない。

| 条件 | 入力提示数 | 受理数 | 損失数 | FIFO最大 | 最初の損失（1始まり） | oracle最大誤差 |
|---|---:|---:|---:|---:|---:|---:|
| residual-periodic-8 | 32768 | 32768 | 0 | 438 | — | 0 |
| residual-back-to-back-2 | 8192 | 7829 | 363 | 512 | 4798 | 0 |
| residual-back-to-back-8 | 32768 | 29785 | 2983 | 512 | 4798 | 0 |
| residual-continuous-8M | 8192 | 8192 | 0 | 1 | — | 0 |
| baseline-continuous-16M | 8192 | 8192 | 0 | 2 | — | 0 |
| residual-core-stalled | 4096 | 4096 | 0 | 0 | — | 0 |
| baseline-core-stalled | 4096 | 4096 | 0 | 0 | — | 0 |
| residual-fifo-stalled | 4096 | 4096 | 0 | 512 | — | 0 |
| baseline-fifo-stalled | 4096 | 4096 | 0 | 512 | — | 0 |

1フレームは4096 complex sample。frame parser後の論理入力を、data区間40 MB/s相当、4 bytes/complexなので10 Mcomplex/sとした。
周期条件はフレーム開始間隔512 µs、連続フレーム条件は間隔を挿入しない。
論理クロックは1080/7 MHz、FIFOは front register を含め512 complex sampleである。
`core-stalled` / `fifo-stalled` 条件は、入力が ready を守り、出力も決定的に停止する条件を検査する。
この入力列は宣言した論理stress patternであり、SDKのcommand/address/dataのwire時間、
PHY、IRQ、transaction間の空白を再生した波形ではない。4798という損失位置を、
統合SDKの実際の2-frame転送波形で観測した値として扱わない。

## 照合方法

各条件でシミュレーション終了、全入力提示、受理入力の順序、出力数、全出力の整数一致、
出力停止中の安定性、FIFOの上限と排出、入力容量を独立に列挙した。
整数 oracle は RTL の circular RAM やパイプライン状態を使わず、
出力 m ごとに `anchor, phase = divmod(m*63, L)` と32項の直接畳み込みから計算する。
係数も HEX のメモリ配置から読まず、数式から生成した係数表を使う。
その生成表が復元済みの元の HEX と一致することは係数監査で別に確認する。

判定結果は [stream/stream-results.json](stream/stream-results.json)、
各条件の `accepted.txt.gz` と `output.txt.gz` には全入出力記録がある。
容量不足2条件は、算術・handshake の不一致と区別して `capacity=REJECT` と記録する。

```sh
python experiments/t_halfband_fpga/run_stream.py \
  --suite /path/to/oss-cad-suite-20261004 \
  --output reports/s3-t-preprocess-integration-v2/quality-fpga/stream
```

公式 OSS CAD Suite 2026-10-04 の archive SHA256 は
`8a4708629b0f0afd5a1835aca8b44d224fec5f6e544c5fd22a060ea5514f83c9`。
今回この hash を確認して展開した Icarus Verilog 14.0
`(s20260301-510-gcbbc0ebb3-dirty)` を使用した。

これは理想論理クロックでの RTL 検証であり、実 FPGA の当該周波数での動作保証ではない。
容量不足はこの FIFO と処理構成に対する判定であり、ESP32-S3 全般の不可能性を示さない。
