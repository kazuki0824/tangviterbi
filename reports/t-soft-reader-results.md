# ② T soft reader・3階層cacheの実装と実K7接続

**後続版:** [固定context化の資源・再試験結果](t-soft-reader-fixed-results.md)。以下は可変index版2251 logic時点の比較元として保持する。現行readerは1373 logic、全体追跡22099/20736で依然超過。

## 判定

T soft readerと3×64 B cache、2-bank symbol descriptorをRTL化した。実共有K7との有限試験でT最大3階層とSの復号bitを照合し、実SDRAM serviceとの別の有限競合試験も13位相で完了した。**機能・供給条件の部分検証は前進したが、面積超過のため受信機として不採用／未成立**である。

reader/cache単体の部分P&Rは2251 logic位置・579 FF位置・0 BSRAM・0 DSP、Fmax179.051025 MHz。生産用serviceの追跡値20726へそのまま足すと22977/20736 logic（110.8073%、2241超過）。この加算は旧stage allocationを維持し、その他未実装integration追加logic費用を0とする診断値で、統合回路の測定値や資源下限ではない。既存stageの保持と重なることを証明していないため、その費用を無料として省略しない。

## 回路と保持所有権

[t_soft_reader.sv](../rtl/t_soft_reader.sv) は以下を所有する。

- 2 bank × 3 contextの開始address／残byte数とbank live状態。commitは当該symbolのSDRAM書き込みが完了してから行う。
- 3×64 Bのbyte cache（distributed RAM）と1-byte出力保持。soft値は受信した8-bitのまま保存し、erasureの展開は後段depunctureに任せる。
- read descriptorのaddress／context／byte数をreadyまで保持する。汎用256-bit要求コピーは作らない。read専用service port 1に接続できる。
- controllerの256-bit responseをreadyまで保持させ、1 clockに1 byteずつcacheへコピーする。最終byteでresponseをackする。別の256-bit response registerは作らない。
- 最古のbankを先に読み、3 contextの空き容量を見てreadを選ぶ。要求中にcacheが溢れないようburst全体の空きを確保する。全responseがcacheへコピーされた後でbankを解放する。K7が未消費のbyteはcache／出力register側に残る。

address単位は既存controllerと同じ**32-bit word**。32 BのBL8はaddress下位3 bit=0、次burstは+8 wordである。末尾は必要byteだけ取り込み、SDRAMには丸めた最後のBL8まで有効な領域を用意する。alignment違反とdevice範囲を越える丸め済み領域は拒否してfaultをラッチする。

commit側は2 bankを交互に使う。再使用対象bankがliveならreadyを返さずreuse_blockedを出す。入力側にその待ちを吸収する実write producerはまだない。T time-deinterleave、SDRAM write producer、S soft FIFO、context別retune／rate切替、PHYはこの回路に含まれない。外部ring容量59904 Bの候補と、今回のon-chip 192 B＋1 Bを同じ保持として相殺しない。

## 機能試験

[byte/address oracle](../tests/test_t_soft_reader.py) は40 symbol、394 read要求について、独立したsymbol/context cursorと期待byte列を使って次を検査した。

- 3 contextの全10890 byte（3359/3767/3764）が順番・内容とも一致。
- 0-byte context、32 B未満の末尾、pointer wrap、同時cache入出力、要求／応答待ち、出力待ち中のvalid/context/data安定性。
- 22550 clocksのbank再使用待ちと7885 clocksの出力stall。旧bankに未読byteまたは未完responseがある間の再commitを拒否。
- alignment／device範囲違反の拒否とresetによるfault解除。

[結果JSON](t-soft-reader-functional.json)。この試験のSDRAM応答は独立address関数から作る抽象応答であり、pin timingモデルではない。

## 実K7との接続

[連成試験](../tests/test_t_soft_reader_k7.py) はMode 1のT 2 symbol、階層segment数1/5/7、T/S全context符号率7/8を対象とする。符号化した既知bitからpuncture後のsoft列を作り、reader→実depuncture→実共有K7へ供給した。

| 項目 | 結果 |
|---|---|
| T soft入力 | 1152 / 5760 / 8064 B、合計14976 B |
| T SDRAM要求 | 468 BL8 |
| S soft入力 | 29992 B、57.72 MB/s相当の有理数pace |
| S有限queue peak | 22 B、試験上限256 B以内 |
| T第1 symbolのACS完了 | commitから8795 / 32803 / 38909 clocks |
| 復号出力bit数 T0/T1/T2/S | 896 / 4928 / 6976 / 26176 |
| 復号bit照合 | 各contextの先頭64 bit以後が既知bit列と一致 |

後尾はtraceback／出力blockの遅延を持つため、全入力bitの最終flushまで完了したとはしない。第1 symbolは試験の2-symbol予算80190 clocks以内だった。

この試験のメモリは**160 clocksごとに最大1 readを受理し、16 clocks後にresponseを提示する仮定**である。responseを32 clocks保持してbyte展開する実readerは動くが、実service／仲裁はこの試験にはない。S queueとT/S soft muxもtestbenchであり、実S frame burst・S FIFO RTLの証明ではない。[結果JSON](t-soft-reader-k7.json)。

## 実serviceとの有限競合試験

[別の連成試験](../tests/test_t_soft_reader_service.py) では実reader、cache、arbiter、controllerを接続し、Mode 3相当の1 symbolに以下の仕事を同時releaseした。

| client | 1 symbolの仕事 |
|---|---:|
| T soft read | 936 BL8、29952 B、readerがbyte展開 |
| T soft write | 936 BL8 |
| T time-deinterleave代理 | 2091 BL8 |
| S frame代理 | 744 BL8 |
| management代理 | 325 BL8 |
| FFT外部delay cache | 8192 sample、read＋writeを受理から+1/+6 clocks、最短13 clocks cadence |

FFTは実cacheの要求契約を使う合成sample列で、FFT算術は動かしていない。T領域はword address8192以後、FFTは0〜4095、他clientは65536以後に置き、領域を分離した。DQは定数刺激でdata oracleではない。背景producerはtestbenchのcounterであり、この表のstage保持費用を測ったことにはならない。

FFT入力の開始offset 0〜12 clocksを試し、全13条件でT byte供給139946 clocks、最終FFT cache書き戻しと次line再充填158800 clocks、全仕事160324 clocksで完了した。診断上の1-symbol期限160380 clocksに対し56 clocks（約0.363 µs）だけ残る。**実stageのburst契約から導いた期限ではなく、この有限負荷の診断条件**である。[全trace／source hash](t-soft-reader-contention.json)。

T sinkは常時readyなので、K7 backpressureはこのservice試験には入っていない。上の実K7試験とこの実service試験を組み合わせて「実service＋K7の全連成が通った」とはしない。長時間・複数symbolでのbank再使用と実T/S burst、すべての仲裁位相は未証明である。

## 部分CADと追跡予算

[CAD summary](t-soft-reader-evidence/summary.json) にsource hash、合成/P&Rログ・netlistを保存した。独立scan入力371 bit、capture39 bit、digest3 bitの計413 FFをprobe用として分離した。39出力laneすべての観測を[専用試験](../tests/test_t_soft_reader_probe.py)で確認した。captureのD側組合せ回路は本体へ課金する。

| reader本体 | 費用 |
|---|---:|
| LUT/ALU | 2155 |
| RAM16SDP4 | 24、logic blocker96／FF blocker144 |
| logic位置 | 2251 |
| 実FF／FF位置 | 435／579 |
| BSRAM／DSP | 0／0 |
| 部分Fmax | 179.051025 MHz、目標154.285714 MHz通過 |

独立部分P&Rの費用をserviceの費用に単純加算した診断値は以下。stageとの実際の共有・重複を証明した時だけ置換できる。

| 追跡資源 | 使用／device | 注意 |
|---|---:|---|
| logic | 22977／20736 | 2241超過 |
| FF位置 | 13104／15552 | 旧allocationを維持 |
| BSRAM | 46／46 | 既存予約を無料で解放しない |
| DSP | 34／48 | 旧allocationを維持 |

以前の「背景5本に各1件コピーする案」は不採用のまま。この追跡値にその3761 logicを重ねてはいない。基準は保持なしservice2485 logicの20726であり、そこへreader2251を足したもの。T reader以外のproducer保持、S FIFO、RF端点、管理、PHY等の追加費用は依然0の診断計算である。

## 再現と次の判定

```
T_SOFT_READER_REPORT=reports/t-soft-reader-functional.json \
T_SOFT_K7_REPORT=reports/t-soft-reader-k7.json \
python -m unittest tests.test_t_soft_reader tests.test_t_soft_reader_probe tests.test_t_soft_reader_k7 -v
T_SOFT_SERVICE_REPORT=reports/t-soft-reader-contention.json \
python -m unittest tests.test_t_soft_reader_service -v
python ci/t_soft_reader_evidence.py --output reports/t-soft-reader-evidence
```

直接要求を保持すれば残り10 logicに収まる、という見込みはこの実装で裏付けられなかった。次の資源検証ではreaderの可変indexによる6組のdescriptor選択／更新回路を固定したcontext別構造へ置き換えて差を測り、既存T stage保持との実際の共有範囲も確定する。単独のreader削減だけで全未実装部分が収まるとは約束しない。資源超過を解消できなければ、現分担のまま統合を進めて成立扱いにしない。

SoC→FPGAはnative I10/Q10のT40 MB/s／S100 MB/s、FPGA→SoCは指令のみ。追加softwareデシメート／再量子化は行わない。境界情報・上下経路候補と帯域余裕のカタログは[PR9](https://github.com/kazuki0824/tangviterbi/pull/9)の4項目を維持する。全体性能合格・正式通信路割当・受信機採用は0。①の探索は停止のまま。
