# ② T soft値の有限保持と共有K7供給条件

追記：[実controller競合試験](sdram-service-probe.md)を追加。160 clocksは完了間隔の条件であり、要求発行間隔ではない。104 clocks後から優先する試験用仲裁が今回の3アクセス列で条件内となったが、有限cache・全clientの実到着は未接続。

2026-10-19 JST。**160 clocksごとに最大32 BのT読み出し機会を与える条件付きモデルでは、今回の試験列を処理できた。実SDRAM仲裁の成立証明ではない。** 192 clocks間隔は継続帯域不足で除外する。①は変更しない。

## 今回作ったもの・前提

[cycleモデル](../experiments/k7_finite_retention.py)、[結果JSON](k7-finite-retention.json)、[unittest](../tests/test_k7_finite_retention.py)。RTLのdepunctureの各符号率・途中X保持、4×16 pair FIFO、S:T=2:1のK7仲裁、128 slotに1回の保守、2 clocks/stepと起動8 clocksを参考にした**新しい供給候補のモデル**である。RTLとのcycle一致検証はまだ行っていない。

- Tは最大64QAM、最大3階層。Mode 1/2/3、セグメント分割13/0/0と1/5/7。各symbolのsoft値はrelease時点でSDRAMへ書込み済みと仮定する。実FFT・deinterleave出力時刻と書込み競合は未接続。
- TのSDRAM保持は2 symbol分（Mode 3で59904 B）。古いsymbolから読み、未読byteが残るbankの再使用を拒否する。既存ringとのaliasは使用しない。
- T読出しcacheは各階層64 B、合計192 B。空きがある階層へ最大32 Bを供給し、読み終えたsymbolのbankを解放する。これは固定間隔の仮想完了機会であり、実controllerのread完了通知ではない。
- Sは7/8 QPSKの57.72 MB/sを正確な有理数で均等到着させ、256 Bのsoft FIFOへ入れる。S復調・deinterleave・memory burstによる到着変動は未接続。
- 単一byte ingressは受入可能なcontextを巡回する。この供給制御のRTLとready接続は未実装。入力soft値の精度や個数は減らさない。
- TのACS完了をpop+3 clocksとして記録する。traceback・RS・最終TS期限は含まない。bank再使用の判定と、ACS完了の判定は別に行う。

T cache 192 B＋S FIFO 256 B＝448 Bは**今回の追加候補**。別報告にある既存の448 B予約と同一とは確認しておらず、名前やbyte数の一致だけで相殺しない。配置先・logic/FF/BSRAM費用も未測定であり、現資源表に収容済みとは扱わない。

## 必要帯域と有限保持の試験結果

全Modeで最大T受信soft値の平均読出し需要は28.813853 MB/s。32 B固定機会の間隔をGとすると、無限に溜めないための必要条件は

`G ≤ (40095 clocks × 32 B) / 7488 B = 171.346154 clocks`。

整数間隔なら171以下が必要。ただしcache満杯で機会を捨てることもあるため、これだけでは十分条件ではない。

| 読出し機会間隔 | 公称供給 MB/s | 需要との差 MB/s | 今回の結果 |
|---:|---:|---:|---|
| 160 clocks | 30.857143 | +2.043290 | 3 Mode×2分割の4 symbol列、Mode 1の16 symbol列×2分割、Mode 3の供給位相8条件で通過 |
| 170 clocks | 29.042017 | +0.228164 | 3 Mode×2分割の4 symbol列、Mode 1の16 symbol列×2分割で通過。余裕は小さい |
| 192 clocks | 25.714286 | −3.099567 | 4 symbol列だけなら通過して見えるが、16 symbol列では11個目のreleaseで未読bank再使用となり失敗 |

160 clocks条件の位相試験は0,20,…,140 clocksの8点であり、全位相・全burstの証明ではない。160/170 clocksの機会は**refreshや他client競合を経た後にも得られるという仮定**。実仲裁でこの間隔にrefreshをさらに加算する場合、上表をそのまま適用してはいけない。

| Mode | symbol周期 clocks | 160間隔時の最大ACS完了遅延 | 170間隔時の最大ACS完了遅延 |
|---:|---:|---:|---:|
| 1 | 40095 | 38987 | 39941 |
| 2 | 80190 | 77809 | 79725 |
| 3 | 160380 | 155469 | 159283 |

この表は基本4 symbol列・2分割における最大値。160/170では次symbolまでに処理を終えた。S soft FIFOの観測最大は1 Bだが、均等到着モデルの結果であり、実機で256 Bも不要という結論にはならない。K7のout_validから先を保証する数値でもない。

192間隔の失敗は両分割ともMode 1のclock 400950、symbol index 10。短い試験の通過より、継続帯域の必要条件を優先する。独立した入力byte保存則とpair保存則を各試験で検査し、unittestでは全5符号率の出力step数を分数式と照合する。過負荷時のbank再使用拒否と、短期通過から長期失敗への変化も回帰試験に含めた。

## 次に閉じる条件

**160 clocks案を次の実仲裁への接続候補にする。正式採用ではない。** 170は比較用、192の継続供給条件は不採用。

1. 実BL8 controllerへT write/read、FFT、T time-deinterleave、S frame処理等の競合を接続し、仮想供給機会を実完了へ置換する。平均帯域だけで160 clocks契約を満たすとしない。
2. T全量spillの追加write＋read 57.627706 MB/sを必ず計上する。今回はwriteをrelease前に終えた仮定なので、この費用をモデル内で処理済みとはしない。
3. 実到着burst・アドレス寿命・Sの有限queueを確認し、cache/仲裁RTLを作って資源・タイミングを測る。残予約2231 logic/1646 FF位置/13 BSRAMへ実費を置換する。

対象SDRAM PHY未確定、全体配置配線未完、S3 WCET未確認は維持。今回の進捗は有限保持の供給条件と失敗条件の具体化であり、受信機全体の性能合格・正式通信割当・採用は0。

再現：`python experiments/k7_finite_retention.py`、`python -m unittest discover -s tests -p test_k7_finite_retention.py -v`。
