# ② 現行SDF FFTの外部delay契約と旧負荷モデルの訂正

追記：[有限32 B cache＋実controllerの接続試験](sdf-delay-cache.md)で、他clientなしのMode 3全bin一致を確認。以下は理想RAM時点の測定記録。競合・全体資源は引き続き未達。

2026-10-19 JST。現在の資源見積もりに使う `shared_sdf_fft.sv` と、直前のSDRAM競合試験のFFT負荷が異なることを確認した。**旧6転送FFTの128要求まとめ処理が通過した結果を、現行SDF FFTを接続できる根拠には使わない。** 旧試験はその合成負荷に対するcontrollerの測定として残す。

## 今回直接確認した範囲

[試験](../tests/test_sdf_memory_trace.py)は現行FFT RTLの入力受理・外部read・外部writeを記録する。各条件で非零乱数の4 frameを投入し、先頭3 complete frameの全binを独立整数FFT参照モデルと比較した。外部RAMは理想同期RAM、external_readyは常時許可であり、SDRAM/controller/cacheは未接続。

paced条件は154.285714 MHz、GI 1/32で、有効期間に1215/64 clocks/sampleの入力を提示する。実際の受理は13 clock slotに量子化される。これはFFT入力であり、SoCからのnative RFサンプルの到着再現ではない。

| 条件 | 比較bin数 | 外部read/write数（各） | 8 wordごとのread開始間隔 clocks | 整数比較 |
|---|---:|---:|---|---|
| Mode 1 paced | 6144 | 0 | 対象外 | 一致 |
| Mode 2 paced | 12288 | 0 | 対象外 | 一致 |
| Mode 3 paced | 24576 | 32768 | 最小143、最大5018（GIを含む） | 一致 |
| Mode 3 最速連続入力 | 24576 | 32768 | 常に104 | 一致 |

Mode 3の各受理sampleについてread要求は受理の1 clock後、writeは6 clocks後、両アドレスはsample番号 mod 4096と一致した。RTLのread値使用は受理の2 clocks後である。read要求時点と値使用時点を混同しない。Mode 1/2はこの外部outer delayを使わない。

## 帯域と期限の読み方

現行Mode 3は8192 sample/symbolを各4 B read＋4 B writeするため、outer delayだけで65536 B/symbol。GI 1/32の1039.5 µsで割ると **63.045695 MB/s**。8 wordをまとめられるcacheを実装できればread 1024＋write 1024＝2048 BL8/symbolとなる。このBL8数は提案するまとめ方の算術値で、実装結果ではない。

JSONのexternal_MBpsは全条件でこの放送symbol期間に正規化した値。最速連続入力の実行時帯域ではない。最速条件は8192×13 clocks/symbolなのでouter delay平均は94.945055 MB/sとなる。短期要求を平均63.045695 MB/sだけで判定してはいけない。

旧6転送負荷は6144 BL8/symbol、189.137085 MB/sだった。両者は同じ処理境界を保証しないため、差126.091390 MB/sを受信機全体の削減として差し引かない。入力・出力frame staging、bit-reversed出力の後段アクセス、各バッファ所有権と二重計上の再監査が必要。仮に入力writeと出力readを別途全frameで必要とすれば、それだけでも65536 B/symbolが加わる。

## 次の実装ゲート

1. read lineを事前取得し、受理時に2 clock後のread値と6 clock後のwrite格納場所を予約する有限cacheを実装する。未準備ならexternal_readyを下げる。cache lineのdirty/validと4096 word折返しを管理し、旧値の先読みと新値のwritebackの順序を保証する。
2. 実controllerへ接続し、refresh・T優先割込み・行競合を含む条件で同じ全bin比較を通す。受理停止を含むframe完了期限、入力滞留量、cache容量を測る。現行slotを保つ場合、最速の次line開始は104 clocks後だが、これはcontrollerへの一律応答期限やシステム全体の保証ではない。
3. cache/仲裁を合成し、既存の全体見積もり（20472/20736 logic、46/46 BRAM）へ実費を反映する。未実装予約との置換を明示し、容量を無料と扱わない。続いて実K7・deinterleave・S frameを接続する。

**今回の成果は現行RTLの要求列と整数演算の確認まで。cache接続、SDRAM期限、PHY、全体資源/STA、S3 WCETの合格ではない。採用は引き続き0。①は探索停止のまま変更なし。**

[機械可読結果とsource hash](sdf-memory-trace.json)。再現：Icarus/vvpをPATHへ置き、repo直下で `SDF_MEMORY_TRACE_REPORT=reports/sdf-memory-trace.json python -m unittest discover -s tests -p test_sdf_memory_trace.py -v`。1 test、内部4条件、63.402秒で成功。
