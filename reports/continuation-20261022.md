# ②：配置拒否理由を実測し、制御をLUTへ移す案まで検証

**前回の静的診断から、固定版配置器での動的診断へ進めた。局所的な拒否理由を特定し、それに基づくmapping変更を試したが、合法配置・統合Fmaxにはまだ到達していない。**
①停止、②の正式受信機・通信路採用0を維持する。全方式不可能の証明ではない。

## 動的診断の結果

固定nextpnr `e2fe86b3ce6feaa3f09d8db5c0971c1cda3fc641` の `slice_valid` に14種類の拒否理由と受理回数を記録する計測を追加した。
戻り値と分岐条件は変更していない。逆置換で元の関数と完全一致することをpatcherが検査する。
最初は対象FF名を固定し、次の版は環境変数で対象を選べるようにした。両版のsource/patch/binary hashを保存した。

| 固定netlist／条件 | 対象FF | データ接続不一致 | 隣接FF型不一致 | 隣接CE不一致 | 対象FFの受理 |
|---|---|---:|---:|---:|---:|
| onehot通常 | dut.fft.in_valid_DFFRE_Q |22726|4|2|0 |
| 恒等LUT事前挿入 | dut.fft.active_mode_DFFE_Q |0|1663|3133|0 |
| さらに同期制御をLUTへ移す | dut.bg_address_DFFRE_Q_60（変更後typeはDFF） |0|3787|0|0 |

全条件exit125、cell探索10001回上限。600秒上限を設定した最後の変更案も壁時間上限ではなく探索回数上限で終了した。
通常条件は公式配布binary・同じソースの無変更build・診断buildの3者で失敗cellとerrorが一致。
事前挿入条件と変更後条件も、公式binaryと診断binaryで失敗cellとerrorが一致した。
そのため診断追加によって別の失敗を作ったという観測結果ではない。

**回数は `slice_valid` 呼出しごとの最初の拒否理由であり、セル数・独立した配置場所数・探索attempt数ではない。**
同じ場所を繰り返し検査する。先の条件で拒否されれば後の条件は評価されない。
対象FFの受理0も、チップの全配置を列挙して合法位置0を証明した意味ではない。
また、表は失敗先の特定FFについての集計であり、全回路でその条件が解消した意味ではない。
例えば制御移動後でも全回路のCE拒否は487746回ある。

[通常条件3者比較](placement-dynamic-audit/comparison.json)
／[事前挿入の比較](placement-dynamic-prebuffer/comparison.json)
／[制御移動後の比較](placement-dynamic-folded-controls/summary.json)。

## セル名だけで帰属を判断しない

通常条件の `dut.fft.in_valid_DFFRE_Q` は、source属性をたどるとprobeのscan保持always blockに由来する。
`scan_next[3]` などのaliasも確認した。FFTという名前を根拠にFFT内部状態FFとみなしてはいけない。
一方、事前挿入条件の `ff_input_identity_127` は受信回路の `dut.fft.active_mode_DFFE_Q` 用のLUTである。
従って、観測回路だけの問題と断定することもできない。
[帰属と恒等LUT対応](placement-dynamic-audit/attribution.json)。

## 拒否理由に基づいて試した変更

事前挿入された恒等LUTのうち、DFFE/DFFREだけを駆動するものを対象に、
CEによる保持と同期RESETをLUTへ移し、FFをDFFへ変更した。
DFFEは `CE ? D : Q`、DFFREは `RESET ? 0 : (CE ? D : Q)` であり、同期RESETがCEより優先する。
非同期RESET/PRESET、負エッジFF、その他の型は変更していない。

- 2393 FFを変更。既存LUT1をLUT3/4に使い替え、LUT数・FF数を増やさない。
- 各変更LUTの出力に、対象FF以外のconsumerがないことを検査。top portへも露出しないことを追加検算。
- 元cell記録を戻すと変換前の全JSONと完全一致。元のFFパラメータとINITを保持する。
- 固定OSS CAD Suite収録の**Yosys Gowin primitiveモデル**と、全Q/D/CE/RESET状態・INIT・エッジ間保持をIcarusで照合して通過。
  ベンダー公式simulation model・実機試験ではない。
- 他consumerがある不適切な変換を拒否するunittestも通過。
- 次状態の論理的等価性を検証したもので、物理タイミングの等価性は主張しない。

| 資源・配置結果 | 事前挿入onehot | 同期制御移動後 |
|---|---:|---:|
| 全fixture LUT位置下限 |19404/20736|19404/20736 |
| FF数 |8662|8662 |
| BSRAM（probe11を含む） |29/46|29/46 |
| MULT18位置換算（receiver6＋probe42） |48/48|48/48 |
| CLK/CE/LSR/互換型の群数 |272|226 |
| 制御群切上げ＋RAM blocker |10452/15552|10416/15552 |
| 実配置 |失敗|失敗 |
| 統合Fmax |未取得|未取得 |

公式版の変更後配置は `ff_input_identity_57`（LUT4）で終了し、対応FFは `dut.bg_address_DFFRE_Q_60`。
名前には旧DFFREが残るが変換後typeはDFF。診断ではこのFFの最初の拒否理由は全3787回とも隣接FF型不一致だった。
**制御移動案を解決策として採用しない。** データ接続と対象CEの扱いを変えた後も、型が混在する局所配置を通せなかった。
制御群総数だけではこの局所失敗を説明できず、逆に有限配置探索の失敗を資源の普遍的不足へ一般化もしない。

[変換器](../ci/gowin_fold_identity_controls.py)／[primitive照合](placement-dynamic-audit/fold-controls-tests.log)
／[資源](shared-receiver-fft-tile-folded-controls-route/placement-gate.json)
／[公式配置](shared-receiver-fft-tile-folded-controls-route/summary.json)
／[全結果の検算](continuation-20261022.json)。

## 再現条件と環境復元

OSS CAD Suite 2026-10-04、GW2AR-LV18QN88C8/I7、family GW2A-18C、目標154.285714 MHz、seed1、heapを維持。
固定版のsource buildはGCC13.3.0、Boost1.83.0、GUI/Python/IPO無効、公式chipdbを外部参照。
CMakeの生成device一覧を空にし、既存公式chipdbを再生成しない。実行deviceは変更していない。
通常buildと診断buildは同一ビルド環境。公式binaryとの比較も行った。

workspace整理で旧toolchainが消えていたため復元した。apt-getは環境のユーザー切替で失敗し、
公開Ubuntuパッケージをworkspaceへ展開して依存を用意した。環境の保護設定は変更していない。
初回buildはapycula不在でDB生成に失敗したため、上記外部DB構成へ修正した。失敗ログも保存。
これらは準備段階の問題であり、今回の配置失敗や自動承認レビュー失敗とは別。

[build条件](placement-dynamic-audit/build-provenance.json)
／[CMakeCache](placement-dynamic-audit/CMakeCache.txt)
／[計測patch](placement-dynamic-audit/instrumentation.patch)
／[対象選択版patch](placement-dynamic-audit/instrumentation-targeted.patch)。
各runのcommand、ログ、入力とbinary hashは各比較ディレクトリに保存。
再実行する場合、通常条件のmapped.jsonはshared-receiver-fft-tile-onehot-route/mapped.json.gz、事前挿入条件はshared-receiver-fft-tile-onehot-prebuffer-route/mapped.json.gzを展開して使う。制御移動後のmapped.json.gzは今回の公式配置ディレクトリに保存した。

## 現在残るボトルネック・未完了

| 項目 | 現在の状態 |
|---|---|
| 統合合法配置・全体資源 |必要LUT位置下限19404は容量内だが合法配置未達。今回3条件で局所拒否理由を確認。未実装stageまで含む全体資源は未確定 |
| 統合速度 |今回もFmaxなし。旧FFT統合146.220200 MHzはK7最低152.626638 MHz、設計154.285714 MHzに未達。単体合格を統合へ流用しない |
| 時間DI全体 |onehotの312 tiles有限期限は通過済み。全descriptor、3buffer交代、cold-fill RTL接続は未完成 |
| 全受信stage |FIR／同期／TMCC／等化／demap／完全なT・S DI／RS／TSの一貫した接続・精度・資源が未確認 |
| 長期・動的期限 |全mode／I／rate／最大3階層／位相／実到着包絡／RS burst／選局・再同期・停止・reset／最終TS期限が未検証 |
| S3処理 |高費用CPUモデル106.8042/106.6197%は超過。実無欠落取得、可逆packing、DMA/IRQ、core別WCETは未確認 |
| SoC/FPGA物理経路 |帯域算術の18組は未認定。通常S経路の余裕3.7135/2.00818 MB/sに対してpin、搭載負荷、PHY、独立clock同期、lane整列、保持量が未確認 |
| SDRAM IO |pad、tri-state、PLL位相、min-max setup/holdが未検証。周期とaccessの差をsetup余裕とは扱わない |
| RF・実機 |帯域/CN、外部変換、LNB、実S3連続取得、RF→TS誤り率・無欠落が未確認 |

既に通過した部分試験や古い候補の資源超過を、現在の未達原因へ戻さない。
今回の制御移動はソフト値幅、SoC転送量、FPGA→SoCは指令のみという制約を変えていない。

## 未完了と区切りA/B

前回のB（配置器に計測を加えた動的診断）まで実施し、さらにその結果に基づく制御移動案と再診断まで進めた。
今回Aは、3条件の拒否理由・比較対照・変換の状態遷移検証・失敗後の再診断を確定しPRへ保存する地点。
次のBは、残る型混在に対してLUT/FF組の割当・mappingを変更し、面積と状態遷移を検証した上で合法配置と統合clockへ到達する地点。

Aで返す理由は、今回立てた「既存LUTへ同期制御を移せば配置を救える」という仮説を、試験から実配置と再診断まで閉じ、不成立と判定できたため。
Bまで進む選択は可能だが、次はさらに別のmappingまたは配置方法を設計する作業になり、同じ変換にseedを追加するだけの探索は選ばなかった。
許可待ちでも全作業が実機待ちでもない。source/入力hash、primitive状態遷移、公式版との比較、失敗ログまで確認したという意味で実験単位の品質は確保した。
受信機全体の完成品質と依頼全体の完了には達していない。
