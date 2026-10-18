# ② 周期入力のFFT slot位相一巡を検証

2026-10-19 JST。前回のpaced試験で後続frame間隔が160381 clocksとなり、symbol周期160380より各1 clock長かった。短い観測だけでは累積遅延なのかslot位相による変動なのか区別できなかったため、現行FFT＋32 B cache＋実controllerを16入力frame・15出力frameへ延長した。

## 試験の範囲

Mode 3、GI 1/32、FFT優先仲裁、背景154.905243 MB/sの均等到着モデルを維持。背景の依存関係・アドレス・測定限界は[直前の競合試験](sdf-cache-contention.md)と同じ。実K7消費・時間deinterleave・S frame RTLは未接続である。

symbol周期160380 mod 13＝12、gcd(160380,13)＝1なので、symbol先頭のFFT slotとの相対位相は13 symbolで一巡する。今回は15 complete出力frameを比較し、入力提示開始の13位相をすべて含むことをassertした。ただしrefreshはcontrollerの要求・行状態にも依存するため、**13 symbolでシステム全体の状態が周期的に戻るとは扱わない**。全refresh位相・全client burst配置の網羅ではない。

異なるseedの非零乱数4群・計16 frameを入力し、最初の15 frameを独立整数FFT参照モデルで全bin照合する。ゼロのflush frameやframe間resetを挿入しない。各入力frameの最終受理時刻、各出力frameの完了時刻、提示開始からの遅延、symbol境界の入力滞留と背景の到着/完了/残件を保存する。

入力は初回cache準備後に開始する。起動前RFデータの保持を保証する試験ではない。保持はtestbench配列であり、入力FIFOを新設/合成したわけではない。背景の256未完閾値と1 symbol期限も前回と同じ診断値で、実FIFO容量や実stage期限ではない。

## 結果

**今回の観測では、＋1 clockは累積し続けなかった。13 symbol後に同じ遅延へ戻った。** ただしslot位相だけで全変動を説明したとはせず、refresh/背景競合も含む観測結果として扱う。

| 観測 | 結果 |
|---|---|
| 全bin比較 | 15 frame × 8192＝122880、全一致 |
| frame提示開始→完了遅延 | 最小315973、最大315987 clocks（幅14） |
| frame 0 / 13の遅延 | ともに315979 clocks、差0 |
| frame 1 / 14の遅延 | ともに315980 clocks、差0 |
| 隣接frame完了間隔 | 160368 / 160381 / 160394 clocksの3値 |
| symbol境界の入力残件 | 観測した15境界すべて0 |
| 全区間の最大入力滞留 | **5 sample＝20 B**（前回4 sample） |
| 背景最大未完数（T write/read、TI、S、管理） | 1 / 1 / 2 / 1 / 1 |
| 背景256未完閾値超過・試験期限超過 | いずれもなし |

frame 0→13の間隔合計は13×160380 clocksと一致する。遅延列は315979, 315980, 315981, 315982, 315983, 315984, 315985, 315973, 315987, 315975, 315976, 315977, 315978, 315979, 315980。単一の160381という間隔だけでは継続性能不足とは判定できないことを、この区間で確認した。**無限時間の遅延・待ち行列上界を証明したわけではない。**

最大入力滞留は12番目のsymbol境界の記録までに5へ増え、その後も5だった。前回の4 sampleは誤測定ではなく短区間の最大値だったが、4 sample FIFOの十分性の根拠にはならない。今回の5 sampleも実装容量の確定値にしない。背景の各記録で到着＝完了＋残件を照合し、最終残件もJSONへ残した。未完要求を全drainしてから終了した試験ではない。

数値とsource hashは[JSON](sdf-cache-phase-sweep.json)に保存。unittest 1 testが154.185秒で成功。全入力の最終受理と全15出力frameの確認まで実行した。

## この結果で閉じない項目

- 全refresh/背景到着位相、実burst/実scatterとK7消費での入力・背景待ち行列の上界。
- 出力の許容固定遅延と後段処理の本来のdeadline。フレーム間隔とframe開始→完了遅延を区別する。
- 仲裁の合成可能RTL化、実FIFO/descriptor保持、32 B cacheを含む予約資源の置換と全体packing/P&R/STA。
- SDRAM PHY、SoCの連続取得・通信・WCET、受信機全体のTS出力。

この追加検証で①の探索を再開しない。②の正式採用も未確定のまま。

[再現unittest](../tests/test_sdf_cache_phase_sweep.py)。Icarus/vvpをPATHへ置き、repo直下で `SDF_PHASE_REPORT=reports/sdf-cache-phase-sweep.json python -m unittest discover -s tests -p test_sdf_cache_phase_sweep.py -v`。
