# ② service＋T readerの統合測定と実現可能性の判定

**後続検算:** [TC8PSK独立割当の見直しと共有core試作](tc8psk-sharing-reassessment.md)。独立TC8を実費に置換した診断値は22532/20736で超過。TC8共有prototypeは機能と部分CADを通過したが、全体資源は未確定。②は依然未確定・正式採用0。

## ②は不可能か

**現時点の判定は未確定である。成立を確認した分担はなく、検証中の分担は現台帳の資源条件を満たさない。②の条件を満たすすべての分担・実装が不可能であるという証明もない。** 未確定であることを、実現できる代案を既に確認したという意味には使わない。

| 問い | 現在の回答 | 根拠 |
|---|---|---|
| ②で成立するハードウェアを提示できたか | No | 全体資源・期限・RF連続取得・S3 WCETが未確認。正式採用0 |
| 検証中の分担は現台帳のまま資源に収まるか | No | 統合測定で置換しても追跡22095/20736 logic、1359超過 |
| ②の条件を満たす全方式が不可能と判明したか | No／未証明 | 残stageはallocationを含み、今回の追跡値は全実装の資源下限ではない。別分担の成立／不成立を今回の測定だけで確定できない |

したがって、現分担を「実現できそうな第一案」として採用する根拠はまだない。全方式についてYes/Noを確定したようには報告しない。

## 統合回路と測定

[t_soft_sdram_service.sv](../rtl/t_soft_sdram_service.sv) は既存serviceとreaderを一つに接続した。T readerがclient 1、FFT cacheがclient 5を専有し、外部背景4 laneはclient 0/2/3/4へ対応する。port 1のrequest address／validとresponse readyは実readerから駆動し、write data/DQMは0固定。soft出力はFPGA内部の後段へ渡すもので、SoCへの復調データ戻しではない。

両者のfaultを統合出力へ出し、global resetを共用する。他の背景producer保持・S FIFO・RF端点・SDRAM PHYは追加していない。

| 測定対象 | logic位置 | FF位置 | Fmax MHz |
|---|---:|---:|---:|
| service単体 | 2485 | 982 | 155.981918 |
| reader単体 | 1373 | 500 | 163.532303 |
| 単体の費用合計 | 3858 | 1482 | 合算不可 |
| **service＋reader統合実測** | **3854** | **1481** | **169.664063** |

同じdevice・seed 1・154.285714 MHz目標を使用した。統合で減ったのは4 logicと1 FF位置だけで、救済に必要な規模の削減ではなかった。BRAM/DSPは0/0、RAM16SDP4×24で、そのblocker96 logic/144 FF位置を表に含める。

各単体probeと統合probeは外部境界が異なるため、4 logicを一般的な統合削減量とはしない。今回の接続を実測することが目的である。全体への上書きには統合費用3854を一度だけ使い、単体費用を重ねない。

## 全体追跡予算の置換

以前の混在台帳20472から、未実装integration残予約2231を引き、統合回路3854を一度入れる。

`20472 − 2231 + 3854 = 22095 logic`

| 資源 | 追跡使用／device | 判定／制約 |
|---|---:|---|
| logic位置 | 22095／20736（106.5538%） | **1359超過** |
| FF位置 | 13024／15552 | 旧allocationを維持 |
| BSRAM | 46／46 | 既存予約を無料で解放しない |
| DSP | 34／48 | 旧allocationを維持 |

これは旧stage allocationを維持し、その他未実装integrationの追加logic費用を0とする診断計算。全受信機のP&R値でも資源下限でもない。残るstage／producerの実費を入れずに「あと1359削れば完成」とはしない。

service＋readerを同時合成すれば大幅に小さくなる、という期待は今回の結果では裏付けられなかった。台帳を固定する限り、少なくとも1359 logicに加えて未計上部分を収めるだけの削減・実費置換が必要となる。

## 検証と観測範囲

[13位相のcycle比較](../tests/test_t_soft_sdram_service.py) は、元の別々のreader/serviceと統合wrapperへ同じ入力を与える。合成背景producerのwrite payload/DQMも疑似乱数化し、lane写像、DQ write、response、cache、soft、fault、bank live、command/address/readyを比較する。[結果JSON](t-soft-sdram-service-trace.json)。

負荷は前回と同じMode 3相当1 symbol：T read/write各936 BL8、T deinterleave代理2091、S frame代理744、management代理325、FFT cache8192 sample。T sink常時ready、DQは定数刺激。独立SDRAM data oracle、実K7、実FFT算術、実RFは含まれない。1-symbol期限160380 clocksは診断条件であり、実stageの契約保証ではない。

全13位相で外部出力がcycle単位に一致し、T供給139946 clocks、FFT cache完了158800 clocks、全仕事160324 clocksだった。診断上の余裕は56 clocks（約0.363 µs）で、以前と同じ。長時間と実T/S burstを保証する余裕とは扱わない。

[統合probe](../experiments/t_soft_sdram_service_probe.sv) は1452入力bit、368出力capture bit、digest13 bit、計1833 FFを持つ。probeのregisterとそのpassthrough LUT／digestだけを除外し、capture D側の組合せ回路は本体に課金した。[368 laneすべての観測試験](../tests/test_t_soft_sdram_service_probe.py)も通過した。

[CAD summary／source hash](t-soft-sdram-service-evidence/summary.json)、[追跡予算JSON](t-soft-sdram-service-budget.json)。core単独合成とprobe付きP&Rのnetlist、commands、ログを保存した。外部IOタイミング／PHY、FFT算術・K7との全連成、全受信機STAは未検証である。

## 再現と次の判定

```
T_SOFT_INTEGRATED_REPORT=reports/t-soft-sdram-service-trace.json \
python -m unittest tests.test_t_soft_sdram_service tests.test_t_soft_sdram_service_probe -v
python ci/t_soft_sdram_service_evidence.py --output reports/t-soft-sdram-service-evidence
```

次の資源検証は残stageのallocationを実RTLの所有権へ対応させる。特にS TC8PSKの3208 logic allocationがmetric／survivor／管理のどこまでを含むかを既存証拠と照合し、速度と精度を保った実費へ置換できるか判定する。共有K7にS TC8PSK全体まで含まれると誤認して削除しない。削減できることを前提にはしない。

並行して残る成立条件は、他producer保持・実T/S burst、全体P&R/STA、SDRAM PHY、実基板接続、S3のRF連続取得・転送・WCET、RF→TSである。小規模な統合差や有限試験だけで②が成立したとは判定しない。

分担候補全件、占有率・期限、境界情報、上下経路候補と帯域余裕は[PR9](https://github.com/kazuki0824/tangviterbi/pull/9)の4項目から参照する。SoC→FPGAはnative I10/Q10のT40 MB/s／S100 MB/s、FPGA→SoCは指令のみ。品質低下を伴う追加softwareデシメート／再量子化は行わない。正式性能合格・通信路割当・採用は0。①の探索は停止のまま。
