# ② 固定context descriptorによるreader面積削減

**後続測定:** [service＋reader統合の実測・②の実現可能性判定](t-soft-sdram-service-results.md)。単体費用の合計から4 logicだけ減り、現追跡値22095/20736、1359超過。以下は単体比較の記録として維持する。

## 判定

T reader/cacheは**2251→1373 logic位置（878削減）**、FF位置579→500へ減った。最終版の同一probe・seed 1の部分P&RはFmax163.532303 MHzで、目標154.285714 MHzを通過した。3×64 B cache、2 bank、soft精度、要求・応答のclock契約は維持した。

旧stage allocationと保持なしserviceの追跡値20726へ1373を加えると、**22099/20736 logic、1363超過（106.5731%）**。FF位置は13025/15552、BSRAM予約46/46、DSP34/48。その他未実装integrationの追加logic費用を0とした診断値のままであり、全体収容や受信機成立を確認した結果ではない。既存stageとの重複削減creditも0とする。

## 回路変更

1. bank/contextから6要素配列を可変indexで更新する回路を、6本の固定write enableへ変更した。read側はcontextごとの2-bank選択とし、更新演算は共有する。alignment検査を通るaddressの下位3 bitは保存値を0に固定した。
2. 3-context RRは固定priority maskとencoderへ置換した。選んだaddress/lengthはone-hotで直接選択する。cacheが32 B以上空いている場合と、末尾の短いchunkだけ入る場合を分けて判定し、広い加算・比較の連鎖を短縮した。
3. 領域終端はBL8単位で判定する。lengthの商は最大2047なので、overflowはdevice最後の2048-burst窓でしか起きない。開始burst下位11 bit＋length/32の12-bit加算と上位窓の判定を並列に行う。丸めた終端がdevice末尾に一致する場合の許可、末尾partial burstによる超過の拒否は維持する。
4. 非live bankのpayload registerのcapture enableから、全3領域の合法性判定を分離した。**commit_readyとbank liveは従来どおり全領域を検査する**。不正descriptorはackされずfaultとなるが、そのedgeに非live registerが不正値をcaptureしても、有効なbankにはならない。faultはglobal resetまで解除されず、そのresetでdescriptorも消える。この分離で合法性判定→広いpayload書き込み許可の最長経路を除いた。入力が無条件に受理される変更ではない。

追加pipelineやsoftの再量子化は導入していない。controllerのresponseは既存と同じbyte展開中保持、1 read in flightのままである。

## 同じCAD境界での比較

| 版 | logic位置 | FF位置 | Fmax MHz | 154.285714 MHz |
|---|---:|---:|---:|---|
| 元の可変index版 | 2251 | 579 | 179.051025 | pass |
| 固定context化のみ | 1503 | 500 | 137.532669 | **fail** |
| burst単位の終端比較 | 1429 | 500 | 145.793839 | **fail** |
| one-hot選択・cache空き判定短縮 | 1376 | 500 | 148.765244 | **fail** |
| 終端を最後の窓で判定 | 1369 | 500 | 137.570511 | **fail** |
| **payload captureとvalidityを分離** | **1373** | **500** | **163.532303** | **pass** |

面積が最小の1369版は速度不足なので選ばない。すべて同じtoolchain、seed 1、probe413 FF、39出力lane、同じclock目標。各版ともRAM16SDP4×24、BSRAM/DSP 0/0。logicとFF位置はRAM blocker96/144を含む。最終版の実FFは356。probeのcapture D側組合せ回路は本体に課金する。

失敗4版のsummary・netlist・logと当時のreader.svを各evidenceディレクトリに保持した。summaryの`rtl/t_soft_reader.sv` hashはそのディレクトリの`reader.sv`と照合する。最終版hashは現行RTLと照合する。

- [最終CAD](t-soft-reader-fixed-validity-evidence/summary.json)
- [固定contextのみ](t-soft-reader-fixed-context-evidence/summary.json)
- [burst終端比較](t-soft-reader-fixed-burst-range-evidence/summary.json)
- [one-hot版](t-soft-reader-fixed-onehot-evidence/summary.json)
- [窓判定版](t-soft-reader-fixed-window-evidence/summary.json)
- [機械可読の比較と予算](t-soft-reader-fixed-budget.json)

## 検証

[保存した元RTL](../experiments/reference_t_soft_reader.sv)と[cycle比較](../tests/test_t_soft_reader_equivalence.py)を行い、40 symbol・394要求・10890 B、stall、bank再使用、末尾、alignment/range faultとresetを含む外部出力の一致を確認した。[最終版trace](t-soft-reader-validity-equivalence.json)。有限traceの比較であり、formal equivalenceの証明ではない。

新しい終端判定は、[独立のbyte長→word終端oracle](../tests/test_t_soft_reader_ranges.py)で全65536通りの16-bit lengthを検査した。device終端の前後5点と開始0、alignment 0/7を使い、合法な開始addressについて786234 probeが一致した。contextはlengthにより交代させる。全address組合せの全数試験ではない。[結果](t-soft-reader-validity-ranges.json)。39出力laneの観測試験も再実行した。

最終RTLについて[実K7接続](t-soft-reader-validity-k7.json)と[実service競合13位相](t-soft-reader-validity-contention.json)も再実行した。試験条件・限界は[元のレポート](t-soft-reader-results.md)と同じである。復号出力896/4928/6976/26176 bitの各先頭64 bit以後が既知bitと一致し、T第1 symbolのACS完了8795/32803/38909 clocksも同じだった。service側13位相の全仕事160324 clocksも変わらず、診断期限までの残りは56 clocksである。

- Mode 1 T 2 symbol（階層1/5/7 segment）＋paced S、全context符号率7/8。T14976 BとS29992 Bを処理し、4 contextの復号bit列を既知入力と照合する。メモリは160-clock間隔の仮定で、実serviceは含まない。
- 実service側はMode 3相当29952 B、FFT cache8192 sample、同じ合成背景負荷。T sink常時ready、DQ定数刺激、K7は含まない。13位相の1-symbol診断期限を検査する。

この二つを別々に通しても「実service＋実K7の全連成」とは扱わない。実FFT算術、実RF、S frame burst、長時間の全位相は未検証である。

## 再現と次の判定

```
T_SOFT_EQUIVALENCE_REPORT=reports/t-soft-reader-validity-equivalence.json \
T_SOFT_RANGE_REPORT=reports/t-soft-reader-validity-ranges.json \
python -m unittest tests.test_t_soft_reader_equivalence tests.test_t_soft_reader_ranges tests.test_t_soft_reader_probe -v
T_SOFT_K7_REPORT=reports/t-soft-reader-validity-k7.json \
python -m unittest tests.test_t_soft_reader_k7 -v
T_SOFT_SERVICE_REPORT=reports/t-soft-reader-validity-contention.json \
python -m unittest tests.test_t_soft_reader_service -v
python ci/t_soft_reader_evidence.py --output reports/t-soft-reader-fixed-validity-evidence
```

次の資源判定はservice＋readerを一つの部分回路として合成・配置配線し、別々の部分費用を足した値を実費へ置換する。さらに旧T stage保持との実際の共有範囲を確定する。残る1363超過に加えて他の未実装費用もあるため、小規模な調整だけで全体が収まるとは主張しない。

SoC/FPGA境界はnative I10/Q10のT40 MB/s／S100 MB/s、逆方向は指令のみ。処理分担・期限・情報・上下経路と余裕のカタログは[PR9](https://github.com/kazuki0824/tangviterbi/pull/9)の4項目を維持する。全体性能合格・正式通信路割当・受信機採用は0。①は変更しない。
