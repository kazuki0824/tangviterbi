# ② 背景要求の保持所有権と追加1件保持案

## 判定

各背景producerの直後に要求を1件ずつコピーする案を実装・測定した。**この追加コピー案は不採用**。同じprobeでservice本体3761 logic/2248 FF、Fmax181.488190 MHz。速度目標154.285714 MHzは通るが、旧stage allocationを維持した追跡値は22002/20736 logic（106.1053%、1266超過）になる。

これはこの保持構成の反例であり、20K全分担の不可能性の証明ではない。stageが既存の保持領域から直接descriptor/payloadを維持する構成は残るが、その具体的RTL・所有権・資源と期限はまだ確定していない。

## 所有権の照合

旧stage allocationの出典は[dual_s3_20k_estimate.py の candidate_budgets](../experiments/dual_s3_20k_estimate.py)。`T_equalize_interleave_TS` は704 logic/576 FF/0 BSRAM/5 DSP、`S_FIR_sync_frame_TS` は1128/1472/9/14である。これらは集約allocationであり、今回必要な要求保持インスタンスが実装・計上済みだと示す対応表はない。9 BSRAM等の合計数から空きportや保持可能期間を推定して無料のbufferを作らない。

| service port | 情報／要求 | 本来の保持所有者 | 現時点の確認 |
|---|---|---|---|
| 0 T soft spill write | 受信8-bit softを32 Bずつ、address/write/DQM付き | T soft producer | 実producerと保持RTLは未接続 |
| 1 T soft spill read | addressのみ、戻り32 BをT 3 contextへ供給 | T soft reader/cache | read専用化済み、reader/cacheは未接続 |
| 2 T time deinterleave | stageの32 B、address/direction/DQM | T_equalize_interleave_TS | allocation内の対応保持インスタンス未確認 |
| 3 S frame | stageの32 B、address/direction/DQM | S_FIR_sync_frame_TS | allocation内の対応保持インスタンス未確認 |
| 4 management | 内部memory要求、address/direction/32 B/DQM | integration reserve | producer未実装 |
| 5 FFT cache | 外部delay lineの32 B要求 | sdf_delay_cache | 実装済み。今回の追加保持対象外 |

現service/arbiterは背景producerにvalid/address/payload/DQMをreadyまで保持させる契約であり、そのためのproducer bufferを内蔵しない。controllerのwrite bufferはrequest受理後の所有者で、選択待ちproducerの保持を代替しない。

Tの2 symbol ring 59904 Bは外部SDRAM上の候補領域。K7供給モデルのT 3×64 B cache＋S 256 B FIFO（448 B）は別の未実装候補である。SDRAM上の容量、on-chip cache、要求slotを同一の保持として相殺しない。time-deinterleave領域とのaliasにもlifetime証明が必要。今回の5 slotはこれらのcacheや長いburst平滑化queueの代替ではない。

## 実装・測定

[sdram_request_slot.sv](../rtl/sdram_request_slot.sv) は1件のelastic保持。4本は21-bit address＋1-bit direction＋256-bit data＋32-bit DQMを保持し、port 1は21-bit addressのみを保持する。各slotのoccupiedを加えると4×310＋21＋5＝1266 state bits。read専用違反のfaultは既存service側からslot側へ移る。payloadはresetせず、valid/faultをresetする。validがある時だけpayloadに意味がある。

[実験wrapper](../experiments/sdf_background_hold_service.sv) を元のserviceの前に接続した。input readyでproducerは要求を解放でき、slotは出力readyまで保持する。消費と補充を同じedgeで行える。read専用slotへのwriteは受理せずfaultをラッチする。responseは既存serviceからproducerへ直接戻すため、producer自身によるresponse対応付けも別途必要。

| 同じ観測境界、seed 1 | mapped logic | 配置後logic | FF | Fmax MHz |
|---|---:|---:|---:|---:|
| 保持なし、read専用＋refresh幅縮小 | 2428 | 2485 | 982 | 155.981918 |
| 5本に1件ずつ保持を追加 | 2481 | 3761 | 2248 | 181.488190 |
| 差 | +53 | **+1276** | **+1266** | — |

このtoolchain/packingでは追加FFに対応するpassthrough LUT等も資源を使う。mapped logicの差53だけを全体予算へ加えると過小評価になる。probeの2019 FFと1814 logicは両方の比較から分離しており、captureのD側組合せ回路は本体へ課金する。追加案のBRAM/DSP使用は0/0。波形・独立pinモデルで全受信機が通ったという結果ではない。

追跡計算は20472−残予約2231＋3761＝22002 logic。FF位置は13189−1646＋2248＝13791/15552（88.677%）。BSRAMは既存予約を維持して46/46、DSPは34/48。これらは**旧stage allocationを変えず、その他未実装integration追加費用を0とした診断値**で、統合回路の測定値でも資源下限でもない。stageとの実際の重複を証明できた場合に限って重複分を除ける。

## 検証・再現

`python -m unittest tests.test_sdram_request_slot tests.test_sdf_background_hold -v` はRW/RO各6000 clocksの独立1件queue oracleで、保持中の全payload、stall、消費＋補充、read専用write拒否、reset flush/fault解除を確認した。RWは1999件受理・1997件消費・3360 stall・1493同時補充、ROは1396/1395/2331/497。受理と消費の差はreset flushと終了時残りを含む。入力は各clock変えるため、受理後の入力変更から保持内容が独立することも検査する。さらに実service/controllerを接続した60000 clocksの5 lane queue oracleで、各lane 201件の受理・発行・応答完了が一致し、273184 lane-clocksの待機中にも全descriptorが保存された。後者のDQは定数刺激で、独立SDRAMデータoracleやFFT/K7連成試験ではない。

```
python ci/sdf_sdram_service_evidence.py --background-hold \
  --output reports/sdf-sdram-background-hold-evidence
```

[CAD summary/source hash](sdf-sdram-background-hold-evidence/summary.json)、[要求所有権・予算JSON](background-holding-budget.json)。前回比較元は[保存済みsummary](sdf-sdram-read-only-bounded-refresh-evidence/summary.json)。新collectorは元serviceを`rename`してから実験wrapperを読む。生産用serviceの構成は変えていない。FFT算術全bin照合や実burst込みK7との連成試験を今回新たに行ったとは主張しない。

## 次の実装対象

追加コピーで吸収する方針を止め、まずT soft readerのaddress生成・2 symbol ring寿命・3×64 B cacheを一つのproducerとして実装する。既存stageの実データ保持からreadyまで直接駆動できる範囲を特定し、response待ちとbank再使用を含めて実K7消費へ接続する。従来モデルの必要平均read間隔171.346154 clocks以下だけでなく、実仲裁で有限cacheが溢れずsymbol期限を守るか確認する。未計上費用を0にして10 logicへ押し込まない。

SoC→FPGAはT native I10/Q10 40 MB/sとS native I10/Q10 100 MB/s、FPGA→SoCは指令のみのまま。保持案によって境界情報や経路候補の帯域条件は変わらない。全候補・期限・上下経路は[PR9の一覧](https://github.com/kazuki0824/tangviterbi/pull/9)から辿れる。全体P&R/STA、PHY、実burst/scatter、S3連続取得/転送/WCET、RF→TSは未達。正式性能合格・通信路割当・採用は0。①は探索停止のまま。

## 直接要求を保持するreaderの追試

[T soft readerの実装・実K7接続・実service競合の結果](t-soft-reader-results.md)を追加した。追加汎用slotなしでも、reader/cache単体の部分費用2251 logicを計上すると追跡値22977/20736で超過する。機能と有限供給の試験は前進したが、直接保持案の全体収容を確認した状態ではない。
