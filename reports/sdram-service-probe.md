# ② 実SDRAM controllerへ競合要求を接続した供給試験

追記：[到着時刻・write完了・cache空きを接続した試験](sdram-finite-clients.md)を追加。背景を最大128要求ずつまとめる方式は有利な均等到着モデルの16 symbolで通過した。実burst/K7接続・物理合格ではない。

2026-10-19 JST。**104 clocks後にTを優先する試験用仲裁は、今回の3アクセス列でT読出し完了間隔160 clocks以内を満たした。全clientの期限合格ではない。** 前回の固定間隔の仮想完了を、既存controller RTLが実際に返す応答へ置換して測定した。

## 接続したもの

[試験](../tests/test_sdram_service_probe.py)は`rtl/dual_sdram_burst.sv`を実行し、T soft読出しと背景要求を同じポートへ投入する。背景は順次アクセス、同bankの2行を交互に使うread/write、既存Mode 3 FFTの6転送・6144 BL8アクセス列の3種。FFT列は入力write、2段のrow/column転置read/write、出力readを含み、連続して繰り返す。

両clientは常時backlogがある条件。Tは専用領域を循環読出し、背景とはアドレスを分離する。T cacheの空き、実symbolのrelease、T time-deinterleave/S frameの実到着列、spill write完了条件は未接続である。背景列はそれらすべてを統合した実トラフィックの代用ではない。

仲裁はtestbenchで実装し、1要求ずつ発行する。直前T応答からG clocks経過後の選択でTを優先し、それまでは背景を選ぶ。要求はreadyまで保持、応答を常時受理し、次の選択までのdispatch bubbleも含める。**Gは要求選択の閾値であり、応答間隔そのものではない。合成可能な仲裁RTLの資源/Fmaxは未測定。**

154.285714 MHz、初期wait30858、refresh1203、tRP/tRCD/tWR/tMRD=4、tRFC=12、CL3、open-page。これらは従来の仮定付きデジタル条件を継承し、PHY認定済みの値にはしない。独立pin-commandモデルと別の要求側参照memoryで、readデータ・write・command timing・refreshを検査する。アナログsetup/holdや実機は対象外。

## 全9条件の測定

[JSON・source hash](sdram-service-probe.json)。各12000要求、計108000要求。帯域は初回acceptから最終responseまでを分母とする有限区間の実測値であり、最悪保証帯域ではない。

| 背景列 | 優先閾値G clocks | 最大T完了間隔 clocks | 160超過回数 | T MB/s | 背景 MB/s |
|---|---:|---:|---:|---:|---:|
| 順次 | 160 | 212 | 872 | 27.190 | 346.553 |
| 順次 | 112 | 162 | 3 | 37.752 | 333.278 |
| 順次 | 104 | 153 | 0 | 39.343 | 330.077 |
| 同bank行交互 | 160 | 197 | 1333 | 27.352 | 218.695 |
| 同bank行交互 | 112 | 156 | 0 | 35.966 | 212.791 |
| 同bank行交互 | 104 | 156 | 0 | 35.966 | 212.791 |
| FFT 6転送 | 160 | 213 | 922 | 26.525 | 318.328 |
| FFT 6転送 | 112 | 157 | 0 | 36.802 | 307.948 |
| FFT 6転送 | 104 | 153 | 0 | 38.823 | 307.037 |

refreshの最大観測間隔は条件ごと1194〜1202 clocksで、上限1203以内。データ照合・command timing検査も通過。160閾値が失敗する負の対照をassertし、104閾値では全3列の160超過0をassertした。ローカルunittest 1 method、内部9条件が成功。CI合格とは別。

## 判定の範囲

1. **160 clocks経過してから要求する方式は不採用。** 応答までの行切替・refresh等を含めると今回の全列で供給不足となる。前回の「32 B/160 clocksの完了機会」という条件を、この要求間隔に読み替えられない。
2. 112閾値も厳密な160 clocks契約を満たさなかった。超過が小さければcacheで吸収できる可能性はあるが、未接続のcacheに吸収できたとはしない。
3. **104閾値を有限queue接続の次の試験対象とする。** 今回の最大156 clocksは観測値。全refresh位相・全アドレス列を網羅した上界ではない。
4. Tへの過剰な優先で背景を犠牲にしてよいわけではない。今回のTは必要平均28.813853 MB/sより多く受けている。実cacheが満杯なら余分なT要求を止め、背景へ譲る必要がある。逆に背景の観測213〜330 MB/sを、全clientに保証された帯域とも扱わない。

## 次の具体的な接続

次はこのcontrollerへの要求生成を、常時backlogから**有限queue・実release時刻**へ変える。T cacheに空きがあるときのみ要求し、Tのspill writeが終わるまで当該soft値を読ませない。FFT、T time-deinterleave、S frame処理の要求を個別に計上して、完了期限・最大待ち量・T bank寿命・Sの非欠落を測る。追加spill read+write最大57.627706 MB/sを省略しない。

背景queueが増大するなら、この仲裁とアドレス配置の組合せを落とす。Tの160 clocks達成だけで採用しない。通過した場合に仲裁/cacheをRTL化し、残統合予約2231 logic/1646 FF位置/13 BSRAMへ実費を置換、配置配線で確認する。

今回の変更は試験・測定・文書で、controller本体や資源予算は変更していない。PHY、全体P&R、S3 WCET等は未達。正式な受信機性能合格・通信割当・採用0を維持。①は変更していない。

再現：

```sh
SDRAM_SERVICE_REPORT=reports/sdram-service-probe.json python -m unittest discover -s tests -p test_sdram_service_probe.py -v
```

Icarus Verilog/vvpがPATHに必要。使用環境はOSS CAD Suite 2026-10-04。
