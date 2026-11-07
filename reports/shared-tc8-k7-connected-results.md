# ② TC8対応共有stageの接続検証

**最新：[SDRAM service・reader・共有K7の同時接続検証](shared-receiver-service-results.md)。** 以下のcore/stage単体・19891等の診断値は、その時点の測定範囲の記録。新しいS保持・接続後のclock合否は最新レポートを参照。

**②全体の可否は未確定。成立確認済み分担・正式通信路割当・採用は0。** 今回はcoreだけでなくmetric生成、depuncture、FIFO、調停を接続した代替stageを測定した。独立TC8を残す案は引き続き資源超過。この共有構成には具体的な測定上の改善があり、探索を打ち止めにはしない。

## 接続した回路と契約

[接続top](../experiments/shared_tc8_k7_depuncture_stream.sv)、[FIFOと調停](../experiments/shared_tc8_k7_stream.sv)、[共有core](../experiments/shared_tc8_k7_context.sv)。生産用RTLは変更せず、実験回路として保存した。

- T context 0–2: 各8-bit soft列→独立depuncture→各16×18-bit FIFO→共有K7。全5符号化率、erasureを維持。
- S TC8: 既存Q1.15 IQ16×2→既存folded metric（COST_SHIFT=22、1 symbol/3 clocks）→16×40-bit FIFO（4×9-bit cost＋4-bit B1選択）→同じ共有K7。coded B0とuncoded B1を同時に出力。
- S binary: context 3のdepuncture→同じS FIFOの18-bit部分→共有K7。T3との同時稼働を維持。
- 入力pair/metric調停は空きFIFOを選び、共有core側はS:T=2:1、T内RR、空きclassへのslot譲渡、128 slotに1回の保守、登録grant、2 clocks/slot。
- S modeと各rateはglobal resetをepoch境界とする。mode変更はsticky faultとなり新規入力を停止。Tを継続したままSだけretuneする機能はない。出力backpressureは未対応。

これはFPGA内部の接続。SoC/FPGA間の情報境界、native I10/Q10、追加softwareデシメート/再量子化禁止、FPGA→SoCは指令のみという条件は変えない。IQ16は既存S復調後の内部metric契約であり、新たな通信量削減ではない。

## 部分配置配線の実費

[collector](../ci/shared_tc8_k7_connected_evidence.py)、[summary](shared-tc8-k7-connected-evidence/summary.json)。GW2AR-LV18QN88C8/I7、family GW2A-18C、seed 1、目標1080/7 MHz、Yosys/nextpnrの版をsummaryへ記録。

| 接続stage | logic位置 | FF位置 | BSRAM | DSP18 | RAM16SDP4 | routed Fmax MHz |
|---|---:|---:|---:|---:|---:|---:|
| T3＋S TC8/binary、metric・depuncture・FIFO・調停込み | 7468 | 3528 | 5 | 2 | 249 | 154.631210 |

目標154.285714 MHzを通過。ただし余裕は0.345496 MHz（約0.224%）で、全回路配置や実IOのSTAへ一般化しない。RAM16のblocker 996 logic/1494 FF位置を含む。scan57＋capture12＋digest2＝71 FFと対応passthrough/digestのみをprobeとして除外し、capture D側の組合せlogicは本体へ課金する。合成後・配線後cell照合とsource hashを保存した。

## 台帳への一度だけの置換

[直前の台帳](t-soft-sdram-service-budget.json)の22095 logicは、旧共有K7/depuncture 6464と独立TC8 allocation 3208を両方含む。今回のstageは両方のcoded処理とTC8 metric/B1履歴を実際に含むので、その2項目を一度だけ除き、7468を加える。S同期/frame/TS等1128のallocationは残す。

`22095 − 6464 − 3208 ＋ 7468 ＝ 19891 logic`

| 資源 | 混在診断値 | デバイス容量 | 占有率 | 残り |
|---|---:|---:|---:|---:|
| logic位置 | 19891 | 20736 | 95.925% | 845 |
| FF位置 | 11759 | 15552 | 75.611% | 3793 |
| BSRAM | 43 | 46 | 93.478% | 3 |
| DSP18 | 34 | 48 | 70.833% | 14 |

FFは13024−3035−1758＋3528、BSRAMは46−4−4＋5、DSPは34−0−2＋2。独立chainの実費3645を先に加えた22532から、旧3208をもう一度引く計算はしない。

**他stageはallocationのまま、他の未実装接続費用は0の混在診断値であり、全回路P&R・資源下限・完成した分担ではない。** 以前の残logic予約2231はservice＋readerへ既に全額置換済み。845を二重に予約として足したり、別の未実装FIFOを無料と扱ったりしない。従来の13 BSRAM予約は消費先未確定のまま残し、既存448 B等とのalias creditも認めない。独立survivorの削除creditはこの接続stageの範囲に限る。

## 機能と有限期限の試験

[接続機能試験](../tests/test_shared_tc8_k7_connected.py)、[結果](shared-tc8-k7-connected-test.json)。6 epoch×4 context×768 step＝1179648状態のpath metric・survivor decisionを独立の無限精度ACSと照合。Tの全5符号化率、S TC8を5 epoch、S binaryを1 epoch、並行IQ/soft入力、random context交錯、FIFO詰まりに伴うbackpressure、global reset越し切替、禁止mode変更faultを検査した。各context/epochで704出力、先頭64以後640出力が既知列へ一致し、S TC8はB0/B1両方を照合。soft stalls 13343、IQ stalls 7930を保持契約に従って回復した。これは飽和入力の機能検査であり、実時間通過率の根拠ではない。

[有限実速度試験](../tests/test_shared_tc8_k7_paced.py)と[結果JSON](shared-tc8-k7-paced-test.json)。T Mode 1、1/5/7 segment、全階層7/8、2 symbolを投入した。T softは28.813853 MB/s、SはTC8 28.86 MSymbol/sまたはbinary soft 57.72 MB/sの有理数均等到着。T sourceはsymbol開始時に全量が読めるtestbench保持であり、実SDRAM reader/serviceを使わない。

| S同時mode | T最大symbol ACS完了 clocks | 期限40095との差 | S source保持最大 | 内部pair FIFO最大 T0/T1/T2/S |
|---|---:|---:|---|---|
| TC8 | 21207 | 18888 | IQ 1 sample | 16/16/16/2 |
| binary 7/8 | 38831 | 1264 | soft 17 B | 16/16/16/16 |

S testbench保持は最大256要素（TC8は32-bit IQ sample、binaryは8-bit soft byte）で、実装回路としての費用・burst耐性を測ったものではない。内部FIFOの満杯はreadyで処理し、入力の欠落はなく、各contextのACS数が入力step数へ一致。出力済みbit列は先頭64以後で既知列へ一致した。traceback/decoded出力は64-bit bank単位なので、有限列末尾の未確定bankを全量出力済みと扱わない。

初回の試験側期待値は出力数をN−64としていたため失敗した。実際のbank契約は64×(floor(N/64)−1)であり、期待値を修正して再実行し、通過した。RTLを変更して通したものではない。

これは条件付き有限試験で、実SDRAM仲裁・S deinterleave burst・全位相・長期運転・TS最終期限の保証ではない。

平均演算量の必要条件はTC8時54.072121 Mstep/s、S binary最悪75.717121 Mstep/s。2 clocks/slot、1/128保守の能力76.540179に対し70.6454%と98.9247%。binaryの余裕は約1.075%しかない。平均値と実到着期限は区別する。

## 分担・情報・経路の扱い

分担はS3側RF取得、FPGA側の復調/FECを追う現候補を維持。①は停止したまま。要求された全候補の根拠は以下に残す。旧catalogの全variantを今回の部分実装だけで性能合格に変更しない。

1. [全ownership](control-only-20k/all-ownerships.json.gz)、[448 variant資源台帳](folded-t-evidence/budgets/20k-all-variants.json.gz)。今回の置換はこのreportに示す特定の診断構成に限り、他variantへ無条件適用しない。
2. 資源占有は本表・[CAD](shared-tc8-k7-connected-evidence/summary.json)。期限は接続試験と[有限保持](k7-finite-retention.md)、[FFTの要求契約](sdf-memory-trace.md)。未計測stageや未接続期限は未確定。
3. [情報境界一覧](control-only-20k/all-boundaries.md)。SoC→FPGA native I10/Q10: T40 MB/s、S100 MB/s、FPGA→SoC指令のみ。
4. [全帯域catalog](control-only-20k/bandwidth-catalog.json.gz)、[raw経路組合せ](control-only-20k/raw-route-pairs.csv.gz)、[制約付き組合せ](control-only-20k/all-allowed-pairs.json.gz)。代表の算術値はT Octal80 有効70.327658−需要40.01＝30.317658 MB/s、S Octal80＋Quad80 有効103.7235−100.01＝3.7135 MB/s、逆指令UART0.1−0.01＝0.09 MB/s。実S3の同時連続取得・転送・WCETや基板配線を確認した値ではない。

性能余裕を満たす分担を先に確定し、その後に実現可能経路を割り当て、経路が0でないものを採用する順序を維持する。現時点でその全条件を満たす分担は0。

## 次のゲートと打ち切り条件

次はこの共有stageとT reader＋実SDRAM serviceを同時に接続し、T write/read・FFT・S frame等の競合下で有限保持、実到着burst、bank再使用、ACS/TSまでの期限を測る。Sの追加保持、mode管理、TS後段と既存reservationの所有権を明示し、残845 logic/3 BSRAMへ収める必要がある。SDRAM PHY、他stage統合、全受信機P&R/STA、実S3連続取得/転送/WCET、RF→TSは未達。

今回の接続stageは資源・clockの部分ゲートを通過したので、この構成の救済を打ち切る理由にはならない。今後その統合が資源・最悪期限を満たせず、測定根拠のある大きな削減も残らなければ、この構成の救済探索を打ち切る。それを②全方式の不可能性の証明とは呼ばない。
