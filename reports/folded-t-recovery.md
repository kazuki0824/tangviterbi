# 軌道修正：T Viterbiの実装比較とS RSの有限待ち再評価

2026-10-18。①の検証用第一案A、②のR＋H、FPGA→SoC指令のみ、追加softwareデシメーション／再量子化禁止を維持する。**完成受信機の性能合格・正式通信割当・採用はいずれも0。**

## 結果と選択

②を先行し、正常復号を確認した`modulo13-pipe`から16/22並列の実回路を作った。単純な共有は速度不足だったため、ACS途中のregister、one-hot状態選択、survivor保存の16-bit化を順に比較した。Tの全符号率に必要なzero-weight erasureを追加し、枝メトリックの登録によって**16並列・6 clocks/step、3431 logic、1833 FF、1 BSRAM、0 DSP、162 MHz目標通過（配置配線後194.250 MHz）**を得た。

同じ端子・基板・162 MHz目標で再測定した既存32並列＋erasure版は3734 logic、1476 FF、2 BSRAM、218.723 MHz。新しい版は**303 logic・1 BSRAM削減、357 FF増加**である。2 BSRAMから1 BSRAMへの変更は16,384 bitsのsurvivor全情報を維持し、124-step tracebackを2 clocks/stepにした結果。traceback深度やsoft情報量を減らしていない。metric modulo 8192の正確な比較も維持する。

出力保存をshift register化した別版は3412 logic、1833 FF、1 BSRAM、171.585 MHzで通過したが、削減19位置に対して配置配線後のclock余裕が縮む。現時点では194.250 MHzの登録版を次の統合対象にする。両版の証拠を保持し、受信機として採用したとは扱わない。

①は22並列化で実用的な資源削減を得られなかった。one-hot＋pipeline版でも3844 logic、2131 FF、2 BSRAM、103.189 MHzで108 MHz目標に未達。16並列1 BSRAM版も109.769 MHzで、5 clocks/stepの必要126.061 MHzに届かない。**今回の①向け縮小実装系列は不採用**。指定9K構成に可能な実装が一つもないという証明ではない。

## 配置配線の全比較

対象は1 convolutional contextのdecoder＋tracebackのみ。外部soft入力・出力端子を保持する同条件probe。PLL生成、外部I/O delay、T三階層context、depuncture入力整列、RS、FFT、PHY、TSは含まない。zero-weight erasure対応とdepuncture expanderの完成は別である。表の通過はopen-source CADの部分回路判定であり、全clock/全受信機STAではない。全条件seed 1、同一のOSS CAD Suite 2026-10-04。負の測定も削除していない。

| 実験ID | logic位置 (容量比) | FF | BSRAM | clocks/step | 目標 / 配置配線後 MHz | 判定 |
|---|---:|---:|---:|---:|---:|---|
| 20k-16 | 3441 (16.59%) | 1596 | 2 | 4 | 162 / 95.905 | 目標不合格 |
| 20k-16-compact | 3199 (15.43%) | 1389 | 1 | 4 | 162 / 96.712 | 目標不合格 |
| 20k-16-compact-pipe | 3273 (15.78%) | 1807 | 1 | 5 | 162 / 130.480 | 目標不合格 |
| 20k-16-erasure | 3297 (15.90%) | 1814 | 1 | 5 | 162 / 141.884 | 目標不合格 |
| 20k-16-erasure-registered | 3431 (16.55%) | 1833 | 1 | 6 | 162 / 194.250 | 部分通過 |
| 20k-16-onehot-final | 3290 (15.87%) | 1812 | 1 | 5 | 162 / 221.484 | 部分通過 |
| 20k-16-pipe | 3503 (16.89%) | 2014 | 2 | 5 | 162 / 134.916 | 目標不合格 |
| 20k-16-shift | 3412 (16.45%) | 1833 | 1 | 6 | 162 / 171.585 | 部分通過 |
| 20k-baseline | 3714 (17.91%) | 1474 | 2 | 2 | 162 / 218.723 | 部分通過 |
| 20k-baseline-erasure | 3734 (18.01%) | 1476 | 2 | 2 | 162 / 218.723 | 部分通過 |
| 9k-16-onehot-final | 3337 (38.62%) | 1812 | 1 | 5 | 132 / 109.769 | 目標不合格 |
| 9k-22 | 3654 (42.29%) | 1553 | 2 | 3 | 108 / 56.322 | 目標不合格 |
| 9k-22-onehot-final | 3844 (44.49%) | 2131 | 2 | 4 | 108 / 103.189 | 目標不合格 |
| 9k-22-pipe | 3936 (45.56%) | 2127 | 2 | 4 | 108 / 84.495 | 目標不合格 |
| 9k-baseline | 3706 (42.89%) | 1474 | 2 | 2 | 108 / 101.471 | 目標不合格 |

全条件のgenerated RTL、source hash、tool version、CST、合成・配置配線ログとJSONを[証拠ディレクトリ](folded-t-evidence/)に保存した。`-pipe`はACS register、`-compact`は16-bit survivor、`-onehot`は状態選択の変更。`-erasure`は欠落ビットのzero weight、`-registered`は枝メトリック登録、`-shift`は出力のshift化。`onehot-final`はerasure追加前の比較対照。erasure非対応の版を全符号率対応として扱わない。

## 実装値での期限

T最大25.212121 Mstep/sを処理する。最終登録版は当初の4 clocks仮説ではなく**6 clocks/step**なので151.272727 MHzを要求し、162 MHzで93.378%を使う。階層切替、入力burst、待ちを除いた演算時間余裕は6.622%。

| T Mode / GI1/32 | 最大step数/symbol | 162 MHzでのACS service | symbol周期 | 差 |
|---|---:|---:|---:|---:|
| 1 | 6552 | 242.667 µs | 259.875 µs | 17.208 µs |
| 2 | 13104 | 485.333 µs | 519.750 µs | 34.417 µs |
| 3 | 26208 | 970.667 µs | 1039.500 µs | 68.833 µs |

block tracebackは124×2＝248 clocks。64入力stepの間隔384 clocks内に収まる。出力は64 bits/128 clocksで、連続blockでも保持が追い付くことを試験した。これは持続処理の契約であり、RFからTSまでの全遅延保証ではない。reset後の最初の64 decoded bitsは既存版と同様にacquisitionとして破棄する。

## 予算を過小見積もりへ戻さない

旧T trellis予算2952 logic/1502 FF/2 BSRAMは、今回の同条件32並列実測3734/1476/2より小さかった。旧20K合計20681から単に303を引いて20378とするのは誤り。いったん旧T allocationを除き、測定した3431を入れる。

- ②R＋H：20681 − 2952 ＋ 3431 ＝ **21160 / 20736 logic（102.045%、424位置超過）**。FF **13843/15552（89.011%）**、BSRAM **45/46（97.826%）**、DSP **34/48（70.833%）**。
- 同条件32並列＋erasureで置換すると21463 logicなので、実測同士の改善303は存在する。しかし旧予算を出発点にすると全体はまだ超過する。
- shift版の置換は21141 logic、超過405。これも全体採用に達しない。
- ①Tの既存32並列を同条件9K実測で置換すると10250 logic、6304 FF、16 BSRAM、18 DSP。22並列one-hot版では10388 logic、6961 FF、16 BSRAM、18 DSP。資源と速度を同時に救えていない。いずれも階層・erasure等の統合未達がある。

これらは部分実測と残stage見積もりを組み合わせた置換予算であり、全体の合成結果や普遍的面積下限ではない。既存IO/SDRAM/TMCC reserveと今後実装する回路の対応を照合し、既に確保した費用を二重加算せず、reserveを超える差分を別計上する。

[全候補の更新台帳](folded-t-evidence/budgets/)は各測定条件について、旧448所有者・FFT実装variantをすべて維持し、T ViterbiがFPGAの行だけを置換する。逆方向条件を満たす84組も①max／②sumで再集計した。②R＋Hの共有RS予算は単純stage和と区別している。候補を追加するためにCPUや通信を楽観化していない。

## SoC/FPGA間の情報・経路

分担境界は変えていない。第一検証案のSoC→FPGAはnative I10/Q10の可逆packing（2 sample/5 byte）、T 16 MSa/s＝40 MB/s、S 40 MSa/s＝100 MB/s。FPGA→SoCは指令だけで、I/Q、LLR、syndrome、TSの返送は0。TSはFPGAから外部sinkへ出す。

| 既存の帯域必要条件を満たす例 | 必要量（指令予約込み） | モデル実効容量 | 差 |
|---|---:|---:|---:|
| T：SPI2 Octal80 | 40.01 MB/s | 70.327658 MB/s | 30.317658 MB/s |
| S：SPI2 Octal80＋SPI3 Quad80 | 100.01 MB/s | 103.723500 MB/s | 3.713500 MB/s |
| FPGA→SoC指令：UART 1 Mbaud、8N1 | 0.01 MB/s | 0.10 MB/s | 0.09 MB/s |

上表は代表例。**全経路候補**は各PRの既存`bandwidth-catalog.json.gz`（18 profile/555集合）と`raw-route-pairs.csv.gz`（①19203組／②18組）をそのまま参照する。GPIO二laneなどを表から脱落させたという意味ではない。新台帳全行でflow、方向、CPU費用、rate、経路参照を保存したことを検査した。電気的な成立、同時DMA/IRQ、S3 WCETを保証する表ではなく、正式割当は引き続き0。

## S側RS：不合格理由の訂正

94.790 MHzは2667 clocks/CWの無バッファ瞬間条件。93.153 MHzを有限FIFO付き受信機の普遍的不可能性へ一般化しない。`buffered_s_rs_recheck.py`では既存の理想到着モデルにTMCCを加え、各main到着との前後関係を含む772位相条件を整数時刻で再生した。TMCCは既存204-byte decoderの2667 clocksを丸ごと課す保守的な仕事量であり、短縮RS機能が実装済みという意味ではない。

- 93.1532 MHz：理想main＋TMCCモデルの最大待ち28.630256 µs、到着から完了まで57.260513 µs、待ち最大1 job、各条件の末尾状態は周期的に反復。
- 平均必要clock92.752478 MHz。平均余裕は約0.430%。実デインターリーブのrelease、DMA burst、メモリ競合、出力停止はモデル外で、FIFO 1個で実受信機が十分という結論ではない。
- 90 MHz：平均から不足し、FIFO待ちが増大する負の対照を保持。

規格根拠は[ITU-R BO.1408-1 Table 3](https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-1-200204-I!!PDF-E.pdf)。既存フレームモデルと同じ48 slots、39936 symbols/frame、8 frames/superframeを用いた。有限位相試験を実到着全体の証明に昇格させない。

## 検証・残り・次の判断

- 16/22/32並列、pipeline、packed survivor、one-hotを比較。独立した無限精度oracleで全64状態metricと枝選択を照合。連続入力間隔、長い入力停止、unknown initial state、dirty reset、traceback中断、符号化信号と孤立誤りを検査。
- erasure版は任意soft値／任意erasureのmetric照合と、Tの1/2・2/3・3/4・5/6・7/8を独立符号器で試験。既存32並列erasure版も同じ試験を通す。最終2版はreset中断を別に検査。
- 15 CAD条件を保存。現在のgeneratorから全測定RTLがbyte一致で再生成できること、ハッシュ・全候補・方向・CPU保存、①max／②sumを検査。
- ローカル検証でありGitHub Actions成功とは報告しない。一般RTLを変更したため起動するCIがあれば別に状態を確認する。

今回完了したのは、見積もり上の縮小仮説を実装し、失敗条件を残しながら、②に使える1-context T kernelを測定値で選び直したこと。全体が収容できない現状で第一案を正式採用へ進めない。

次の設計ゲートは、②の**残424 logic＋既存reserveを超える統合費用**を削り、45/46 BSRAMへ実cache/CDC/階層contextを収めること。候補はinput順序復元からFIRへの直接streamと実SDRAM cacheで、既算1600 Bを全入力保持と扱わない。①では22並列の置換を進めず、②で確認した保存回路の圧縮を含めて別の全体資源配分を比較する。

実memory/PHY、三階層context、全S変調、共有RSと実到着、SoC同時WCET、配線/clock、①NOR切替、RF→TSの実機連続試験は未完。このターンでそれらを実装・合格させたという主張はしない。今回の縮小だけで最初の全体収容ゲートが閉じておらず、その下流へ正式通信割当を進めていない。

## 再現

```sh
# OSS CAD Suite 2026-10-04 のbinをPATHに追加
python -m unittest discover -s tests -p 'test_folded_t_*.py' -v
python -m unittest discover -s tests -p test_buffered_s_rs_recheck.py -v
python ci/folded_t_evidence.py --board 20k --lanes 16 --pipeline --compact-survivor --onehot --erasures --registered-costs --frequency 162 --output build/folded/20k-16-erasure-registered
python -m experiments.buffered_s_rs_recheck --output build/buffered-s-rs.json
python -m experiments.folded_t_budget --output reports/folded-t-evidence/budgets
```

他のCAD条件は各summaryのboard/lanes/baseline/pipeline/compact_survivor/onehot/erasures/registered_costs/shift_output/targetから再現する。baselineは`--lanes 0`。試験の探索失敗やclock不合格をexit codeだけで消さない。
