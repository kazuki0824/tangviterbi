# T 診断フィルタの品質評価

**診断候補の周波数応答と整数演算は検証できたが、元 receiver と同品質であるとは認定できない。**
元方式の係数、丸め・scale・飽和・出力時刻の受入条件、定義された channel 条件に対する
MER / C/N / BER の合格基準が、今回確認できた資料には含まれていないためである。

以下は2026-11-05に新しく計算した結果であり、失われた過去の解析ファイルを同じ bytes で
復旧したものではない。保存済みの診断用係数 HEX と halfband31 の係数をそのまま使用した。
係数は元 receiver の係数と称していない。

## 周波数応答

baseline は16 MHz入力を32/63で変換する32 tap・32 phase。
residual は16 MHz入力を31 tap halfbandで8 MHzにしてから、32 tap・64 phaseで64/63変換する。
両者とも出力は512/63 Mcomplex/s。残存 FPGA の係数設計は cutoff 3.6 MHz、Kaiser β=8.6、
各phaseのQ15 DC和を32768とした診断設計である。

| 指標 | baseline | halfband + residual |
|---|---:|---:|
| 全phaseの passband ripple（p-p） | 0.530511669 dB | 0.005352807 dB |
| 指定 stopband 上の最小減衰 | 74.745973692 dB | 73.590077752 dB |
| 最大 rational image | −88.332375179 dBc | −90.465008904 dBc |
| nominal prototype delay | 0.999023438 µs | 2.936523438 µs |
| 量子化後・全phaseの passband delay範囲 | 0.998975066–0.999071809 µs | 2.936368366–2.936678509 µs |

passband は0から `39/14 + 0.1 = 2.885714286 MHz`、stopband は
`8 − pass_edge = 5.114285714 MHz` から8 MHzまでと定義した。
これは halfband の alias 対域を含む診断用の帯域定義であり、元 receiver の合否基準ではない。
passband/stopband 各4097点、全域16385点で、baseline32 phaseとresidual64 phaseをすべて計算した。
表の extrema はこの有限格子上の値であり、連続周波数全体の数学的最大・最小の証明ではない。

rational image は、実際の出力順序 `phase = m*63 mod L` に並べたphase応答から、
desired toneとの位相差を補正してDFTで求めた。各 passband周波数で、baseline31本、
residual63本の全imageを確認した。imageの比は共通するhalfband利得に依存しない。
別途、9周波数・全phaseを直接複素和で照合し、halfbandは対称性を使ったcosine式でも照合した。
4周波数では実際のrational anchorでL個のtone出力を計算し、直接DFTとFFTのimageを比較した。

[quality-results.json](quality/quality-results.json) に全計算条件・誤差・入力hashがある。
全域のphase最小/最大包絡は
[baseline CSV](quality/baseline-frequency-envelope.csv.gz) と
[residual CSV](quality/residual-frequency-envelope.csv.gz) に保存した。
CSVの表示下限は−320 dBであり、表の extrema 計算にはこの表示制限を使っていない。

## 固定小数点演算と飽和の上限

rawは各I/Qがsigned10、halfbandは `floor(acc/1024)`、residualは
`floor(acc/32768)`、それぞれsigned16へ飽和する契約で評価した。
baselineはsigned10入力から `floor(acc/1024)` とした。
halfband係数和は実際には **32766**、DC利得は0.99993896484375であり、
品質評価の都合で32768へ変更していない。

zero、正負impulse、正負DC、alternating、square、全範囲乱数、符号乱数、
0.5 MHz・passband端・stopband端のcomplex toneという12入力を各2048 complex sampleで調べた。
baselineとresidualの24組をすべて実行し、途中の失敗で後続を省略しない。

- halfbandは `numpy.convolve` と、Python整数のscalar畳み込みを全出力で照合した。
- 残存resamplerはRTLの状態やRAM配置に依存しない、直接rational畳み込みoracleを使った。
- 丸め誤差の基準は、Q15係数をそのまま使ったraw入力からの合成FIRであり、途中のfloorを省いた線形応答である。

| 誤差・上限（signed16出力のLSB単位） | baseline | halfband + residual |
|---|---:|---:|
| 今回の入力集合での最大観測丸め誤差 | 0.999023438 | 2.029756129 |
| 全入力に対する厳密なfloor誤差上限（未満） | 1 | 2.969116211 |
| 任意signed10入力に対する線形合成応答の絶対値上限 | 25700 | 31096.149871826 |
| floor誤差を加えた整数出力の絶対値上限（未満） | 25701 | 31099.118988037 |

残存resamplerのphase係数をc、halfband係数をhとすると、raw入力からの合成係数は
`convolve(upsample2(c), h) / (1024*32768)` である。この全phaseの絶対値和に512を掛けて、
任意signed10入力の線形出力を抑えた。halfband出力自体も飽和しない上限に収まる。
halfbandのfloor誤差は1未満なので、residual通過後の誤差は
`max_phase(sum(abs(c)))/32768 + 1 = 2.9691162109375` 未満になる。
両上限の和31099.118988037は32767より小さく、選択したcascadeは任意signed10入力で飽和しない。
これは有限入力試験だけで無飽和を推定した結論ではない。

この誤差は固定Q15係数に対するfloor誤差であり、理想実数係数からQ15へ量子化する誤差とは別である。
係数量子化の最大phase L1差と最大係数差もJSONに記録している。

## 元 receiver の契約との区別

[contract-evidence.json](quality/contract-evidence.json) には、元のFIR cycle/tap-countモデル、
fractional FIRのtrial契約、halfbandの候補API、診断係数generator、保持された技術報告という
5資料のhashと該当行を記録した。読み取りと明示的な契約制約の8条件はPASSである。
これはこの5資料の確認であり、未確認の資料にも仕様が絶対に存在しないという主張ではない。
受信品質の同等性は `UNVERIFIED` のままで、診断結果を用いて架空のMER/C/N/BER基準を作らない。

```sh
python experiments/t_halfband_fpga/quality.py \
  --output reports/s3-t-preprocess-integration-v2/quality-fpga/quality
python experiments/t_halfband_fpga/contract_evidence.py \
  --output reports/s3-t-preprocess-integration-v2/quality-fpga/quality/contract-evidence.json
```

Python3.12、numpy2.3.5で実行した。品質計算の70条件をfail-fastにせず確認し、全条件PASS。
合否は各直接計算との一致、係数構造、誤差上限、無飽和の証明、有限な周波数計算結果に対して付けた。
同品質認定や実機の物理タイミング合格に対するPASSではない。
不正な係数からNaN/Infinityが生じても、該当値をJSONのnullと診断理由へ変換し、
すべての条件を含むFAIL報告を出力する。途中のJSON出力例外で報告自体を失わない。
