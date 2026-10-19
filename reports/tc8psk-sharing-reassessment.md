# ② TC8PSK割当の検算と、共有coreへの構成変更

**更新：[metric・depuncture・FIFO・調停まで接続した結果](shared-tc8-k7-connected-results.md)を参照。** 接続stageの部分P&Rが通過し、混在診断値は19891 logicへ改善した。以下はcore単体を測った時点の記録で、接続未実施・credit 0という記述はその時点の状態。②全体の成立確認は依然0。

## 結論と打ち止めの判断

**②全体は未確定で、成立を確認できた分担は0。今の時点では探索を打ち止めにしない。** 理由は「不可能と証明されていないから」だけではなく、TC8PSKを既存の共有K7 coreへ載せる具体的な試作が、機能と部分P&Rを通ったためである。

ただし、これは完成した別案の成立確認ではない。metric生成・FIFO・仲裁・depunctureと接続した共有stageの費用・期限が未確認なので、全体収容の見込み値を作って第一案に採用しない。正式性能合格・通信路割当・採用は0。

**独立TC8PSK回路を残したまま割当を小さく見直す救済は、今回失敗した。** 旧3208 logicより実費が大きく、診断上の超過は1359から1796へ増える。

## 旧3208割当の所有権と再測定

出典は[dual_s3_20k_estimate.py](../experiments/dual_s3_20k_estimate.py)の `S_TC8PSK = 3208 logic / 1758 FF / 4 BSRAM / 2 DSP`。集約allocationであり、20K上の同じclock・scopeを実測した費用ではない。

TC8PSKのmetric生成は、1 symbolごとに4種類の9-bit branch costと4-bitのuncoded B1選択を作る。survivorはcoded B0とuncoded B1の両方を復元する。従来の共有K7はS BPSK/QPSKを共有対象とし、TC8PSKは独立に残していた。**TC8PSKまで共有済みだったと扱って3208を削除することはできない。**

[測定用chain](../rtl/s_tc8psk_chain.sv)で既存metricとcompact survivorを実際に接続し、22/32 ACSの2版を同じ20K・seed 1・目標154.285714 MHzで測った。同期／TMCC／frame／RS／TS／mode切替は含まない。

| 独立TC8PSK chain | logic位置 | FF位置 | BSRAM | DSP | Fmax MHz | 目標 |
|---|---:|---:|---:|---:|---:|---|
| 22 ACS、12-bit path metric | 3645 | 1521 | 4 | 2 | 155.617798 | pass |
| 32 ACS、12-bit path metric | 3929 | 1567 | 4 | 2 | 254.841995 | pass |

12-bit化は既存Q15／COST_SHIFT=22のmodulo比較であり、入力sampleやbranch costの追加再量子化ではない。IQ16 bit、9-bit costの内容は既存回路と同じ。32 ACS版もmetric生成が1 symbol/3 clocksなので、chainの連続処理能力はどちらも51.428571 MSymbol/s。Sの28.86 MSymbol/sに対する平均clock占有は56.1167%。burstや他stageの最悪期限を証明した値ではない。

最も都合よく旧3208をchain全額で置換しても、22 ACSで

`22095 − 3208 + 3645 = 22532 / 20736 logic（1796超過）`

となる。FF位置12787/15552、BSRAM46/46、DSP34/48。旧allocationを維持し、その他未実装費用を0とする診断値で、全回路の測定・下限ではない。管理等の未収容分を含めて完成したと扱わない。[22 ACS CAD](tc8psk-20k-evidence/acs22/summary.json)、[32 ACS CAD](tc8psk-20k-evidence/acs32/summary.json)。

## 構成変更：TC8PSKも共有coreへ

TとS TC8PSKのcoded B0は同じ171/133・64状態trellisを使える。違うのはbranch costとuncoded B1の扱いである。[prototype generator](../experiments/shared_tc8_k7_context.py)から[試作RTL](../experiments/shared_tc8_k7_context.sv)を作った。現行の生産用K7 RTLは変更していない。

- context 0〜2は従来の8-bit soft×2＋erasureを維持する。
- S context 3では4×9-bit costを直接使い、2-clock slotの後半までcostとB1選択を保持する。S binary modeでは従来のsoft入力を使う。
- Sだけに256×4-bit branch historyを追加し、共有survivor RAMと同じtagged forwarding／保持のlatencyへ揃える。TのslotでSのread pipelineを進めない。
- tracebackでuncoded B1を選び、S用の2-bank decoded保持を追加する。B0とB1を同じ出力clockへ揃える。出力backpressureは未対応。

modeはepochを通じて一定とする試作で、S binaryへの変更はglobal resetを挟んで試験した。Tを動かし続けたままSだけをretuneする制御や、mode識別付きの実stream入力は未実装。B1出力が意味を持つのはTC8PSK epochのS出力である。

## 共有coreの測定と機能確認

| 同じ比較用probe、seed 1 | logic位置 | FF位置 | BSRAM | DSP | Fmax MHz |
|---|---:|---:|---:|---:|---:|
| 元の共有K7 core | 5705 | 2681 | 4 | 0 | 161.134384 |
| TC8PSK対応の共有core試作 | 5968 | 2878 | 5 | 0 | 156.054932 |
| 差 | **+263** | **+197** | **+1** | 0 | 両方154.285714通過 |

両方RAM16SDP4×224で、blocker896 logic/1344 FF位置を含む。元の別probeで得た5695と今回の5705は観測・packing境界が異なる。この比較には同じboundaryの5705を使った。**実stream込み6464へ263を足せば完成する、という測定ではない。**

baselineでは未使用TC8入力・B1出力がpruneされるためprobe FFは30、拡張版は72。各版の生き残ったprobe FFをmapped sourceから分類し、passthrough LUT／digestだけを除外する。capture D側の組合せ回路は本体へ課金する。拡張版の全7出力laneの観測も試験した。[baseline CAD](shared-tc8-k7-evidence/baseline/summary.json)、[拡張CAD](shared-tc8-k7-evidence/extended/summary.json)。

[独立oracle試験](../tests/test_shared_tc8_k7_context.py)は4 epoch×4 context×768 step、**786432状態のmetricとsurvivor decision**を無限精度整数oracleと照合した。3 epochはT3＋TC8PSK、最後はSもbinaryにしてglobal reset越しの切替を検査した。random interleave、連続context、idle slot、長い停止、slot後半の入力破壊、処理途中resetを含む。

各epoch/contextの出力は704個。TC8 epochのSは、先頭64を除く640 pairについてcoded B0・uncoded B1が既知情報と一致。binaryのcoded出力も対応epochで一致し、Tの4種類のerasure指定もmetric oracleへ一致した。[結果JSON](shared-tc8-k7-prototype-test.json)。これは手動slot供給のcore試験であり、実burstや実仲裁での期限保証ではない。

## 追加の独立検算

独立TC8 chainも両ACS版について8192 symbolを連続投入し、初回受理clock2・最終24575・最大受理間隔3 clocksを確認した。各版8128 pairの先頭64以後、16128情報bitが既知入力と一致した。[chain試験](tc8psk-20k-chain-test.json)。

既存のQ15検算も再実行した。4145 IQ対（境界値・全象限・stall）を独立constellation oracleで比較し、10240 symbol・655360状態の12-bit metricを無限精度および13-bit版へ照合した。観測候補差766、全Q15入力に対する既存の幾何学的上限1964<2048という証明契約も維持。[検算結果](tc8psk-20k-oracle-results.json)、[unittest log](tc8psk-20k-oracle-tests.log)。

## 残る検証と打ち切り条件

共有TC8時の平均需要はT最大25.212121＋S28.86＝54.072121 Mstep/s。現clockの2 clocks/slot・1/128保守を仮定した76.540179 Mstep/sの70.6454%である。S BPSK/QPSK時の最悪75.717121 Mstep/sも維持する必要がある。**実schedulerのTC8対応がないため、この比率は必要な平均演算量の検算にとどまる。**

次はS FIFOを4 cost＋B1選択を保持できる形にし、metric→FIFO→仲裁→共有coreを接続する。Tのdepunctureと既存S binaryも保持し、追加保持・grant・mode管理を含めて実費を測る。**独立survivorを外すcreditは、その代替を接続して測ってから認める。** 今回は共有案の全体logicを未確定とし、資源内に入る数字を作らない。

この接続後の資源・最悪期限を満たせず、根拠のある別の大きな削減が残らなければ、この共有構成の救済探索を打ち切る。②全方式の不可能性と、その特定構成の打ち切りを区別する。現在は機能とcore実費を確認できた具体策があるため、その検証を続ける。

SoC→FPGAはnative I10/Q10のT40 MB/s／S100 MB/s、FPGA→SoCは指令のみ。4 cost/B1選択はFPGA内部情報でありSoC転送を追加しない。処理分担候補・占有率と期限・境界情報・上下経路全件と帯域余裕のカタログは[PR9](https://github.com/kazuki0824/tangviterbi/pull/9)の4項目を維持。通信都合の追加softwareデシメート／再量子化は行わない。正式経路割当・採用0、①は探索停止のまま。

[比較・判定の機械可読JSON](tc8psk-sharing-budget.json)。

## 再現

```
python ci/tc8psk_20k_evidence.py --output reports/tc8psk-20k-evidence
python ci/shared_tc8_k7_evidence.py --output reports/shared-tc8-k7-evidence
TC8PSK_20K_TEST_REPORT=reports/tc8psk-20k-chain-test.json \
python -m unittest tests.test_tc8psk_20k_chain tests.test_tc8psk_20k_probe -v
SHARED_TC8_K7_REPORT=reports/shared-tc8-k7-prototype-test.json \
python -m unittest tests.test_shared_tc8_k7_context tests.test_shared_tc8_k7_probe -v
```

共有prototype RTLはgenerator出力と一致することを試験内で確認する。CAD source hash、生成survivor hash、netlist、commands、logsを保存した。全受信機のP&R/STA、他stage保持・burst、PHY、RF連続取得・S3転送/WCET、RF→TSは未達である。
