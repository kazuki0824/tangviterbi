# ②：K7比較回路とT時間デインターリーバの追加検証

①は停止を維持。②の完成受信機・正式通信路・採用は引き続き0。
この追記は前の記録を置き換えて成功を主張するものではない。

## K7比較経路の変更：機能一致、速度悪化のため棄却

実FFT＋metadata＋refresh版の最長経路は、K7メトリックRAMの読出しから
ACS比較を経てsurvivor書込みまで。13ビット減算を4/4/5ビットの
borrow lookaheadへ置き換え、同じmodulo-8192差を計算した。
精度、消費slot数、コンテキスト切替、外部通信方向は変更していない。

- 実RTLから抽出した比較関数についてYosys SATで全2^26入力対の等価性を証明。
- 4 epoch×4 context×768 step×64 state＝786432状態を独立の非有界整数oracleと比較。
  TC8の符号化bit・非符号化bit、binary S、T erasure、途中resetを含む試験は成功。
- 同じ実FFT probe・seed1・toolchainで配置配線を完了。

| 実FFT統合版 | logic（RAM blocker込み） | FF位置 | BSRAM/DSP | 配線後MHz |
|---|---:|---:|---:|---:|
| 前の最良metadata＋refresh | 14175 | 6801 | 16/6 | 146.220200 |
| 今回のgrouped比較 | 14522 | 6801 | 16/6 | 128.353226 |

目標154.285714 MHz未達。面積も速度も悪化し、改善案として棄却。
[CAD証拠](shared-receiver-fft-grouped-evidence/summary.json)、
[形式検証](k7-grouped-equivalence-test.log)、[機能試験](k7-grouped-test.log)。
実FFT統合の最良値は146.22 MHzのまま。

## 追加stallの必要条件を検算

2 clocks/step、1/128のmaintenance、T25.212121＋binary S50.505 Mstep/sを使用。
[F(有理数)での再計算](shared-receiver-stall-budget.json)。

- 追加stallなしでも最低152.626638 MHzが必要。
- 154.285714 MHzでは追加stall allowanceは全clockの1.066926%、
  Mode3最短GIの1 symbolあたり1711.13625 clocks相当。
- 146.220200 MHzでは平均3.178194 Mstep/s不足。FIFO増量だけでは定常運転不能。
- TC8では需要が小さいが、TC8だけ通ることを全方式対応と扱わない。

これらは平均必要条件。正の余裕がある場合のdeadlineやqueue上限の証明ではない。

## T時間デインターリーバの実配置を調べた結果

一次資料：[ARIB STD-B31 v2.2-E1](https://www.arib.or.jp/english/html/overview/doc/6-STD-B31v2_2-E1.pdf)
3.11.1、Fig.3-23、Table3-12。
送信側の各carrier遅延I*((5*i)%96)に対して受信側はI*(95-(5*i)%96)を与える。
Mode1/2/3の最大Iは16/8/4。既存の6個の8-bit soft値を保存する仮定で検算した。
生I/Qを6 bytesへ変更する案ではない。復調/demapと軟値の品質保証は別途未完了。

| 保存・アクセス案 | 今回の検算・判定 |
|---|---|
| carrierごとに必要深さだけ確保 | 最大5,690,880 bytes。従来容量値を確認。ただし実アドレス生成とburst効率は未保証 |
| 全carrierを最大深さで確保 | 11,381,760 bytes。8 MiB超過のためこの配置は棄却 |
| 1 carrierごとにBL8 read＋write | 最小304.146224 MB/s、dataだけでSDRAM clockの49.282953%。command・row・refresh・他clientは別 |
| 同じ遅延クラスの位置を共有 | 3階層×96 entryの位置管理RTLを実装し検証。全デインターリーバではない |

[layoutとtrafficモデル](t-time-interleaver-layout.json)、
[送信queue→受信ringの逆変換、全mode/I、wrap検査](t-time-interleaver-layout-test.log)。
BL8数の値はcarrier単位アクセスに限定した下限であり、すべての集約方式の下限ではない。

### 背景メモリの期限チェックにあった抜けを追加

従来の2 symbol試験のT時間DI模擬要求は523 BL8/symbol。
今回のcarrier単位方式ではMode1の非zero遅延carrierが1235本あり、最低2470 BL8/symbol。
この要求数へ増やし、既存のcontroller/reader/K7/S/FFT模擬要求と競合させた。
アドレスとDQMは旧試験の合成パターンのまま。**実時間DIのデータ配置試験ではなく要求数の負荷試験**。

旧チェックはT/FFT/書込みの期限を見る一方、時間DI背景要求の完了期限を数えていなかった。
初回は`deadline_misses=0`でも全要求完了が116445/117848 clocksへ伸びた。
実行した初回script/log/JSONを保存し、時間DIの第1/第2期限を追加して再実行した。

| S条件 | TTI第1完了／期限40095 | TTI第2完了／期限80190 | TTI期限違反 |
|---|---:|---:|---:|
| binary | 82212 | 116445 | 2 |
| TC8 | 83615 | 117848 | 2 |

データ照合は成功、**背景処理のdeadlineは失敗**。
[修正後結果](shared-receiver-direct-tti-load-test.json)、[ログ](shared-receiver-direct-tti-load-test.log)。
初回は[JSON](shared-receiver-direct-tti-load-initial.json)、[ログ](shared-receiver-direct-tti-load-initial.log)、
[実行script](direct-tti-initial-test.py.gz)。
この結果から旧523要求を全方式に十分だと解釈してはいけない。
ただし、この合成アドレスでの失敗は、集約した実配置を含む全方式の不可能性の証明ではない。

### 位置管理RTLの実装・比較

`experiments/t_time_pointer_bank.sv`は階層と96遅延クラスでpositionを共有する。
同一階層の同一遅延クラスでは全carrierが同じsymbol位置を使えるため、carrier数分のpointerは不要。
reset後の初期化と1 symbolごとの更新はそれぞれ288 entryを1 clockずつ処理。
更新中のqueryは無効。設定はreset間で固定、symbol更新要求はbusy中に送ってはいけない。
この288 clocksを含む上流buffer/slot調停はまだ統合していない。

| 位置管理のみの合成 | logic（RAM blocker込み） | FF位置 | RAM16SDP4 | BSRAM | DSP |
|---|---:|---:|---:|---:|---:|
| I×補数を乗算 | 531 | 335 | 54 | 0 | 1 |
| Iが2の冪であることを使いshift選択 | 578 | 335 | 54 | 0 | 0 |

両方で各879264位置のoracle検査成功。全有効I、全96class、3階層、複数周回、I=0、途中resetを確認。
現在DSPよりlogicの制約が強いため、この部品の次の統合候補は乗算版。
**合成だけで配線後Fmaxは未測定。受信機へ採用したとは扱わない。**
既存allocationにも時間DIが含まれるため、この531を単純加算して全体収容可否を判定しない。
[乗算版集計](t-time-pointer-bank-mul-summary.json)、[shift版集計](t-time-pointer-bank-shift-summary.json)、
[機能ログ](t-time-pointer-bank-test.log)。

## 残作業と次の技術的境界

1. compact配置の実アドレス・6-byte soft保持・BL8集約・read/write完了までの回路。
   位置管理だけでは不足。集約buffer容量・追加latency・SDRAM他clientへの影響を同時検証する。
2. 実FFT統合の154.29 MHz達成。今回の比較回路変更では解消しなかった。
3. FIR/同期/TMCC/等化/demap/周波数DI/bit DI/S frame/RS/TSを含む実データ経路統合。
4. 実stageの到着契約から全mode/rate/階層の長期queueと期限を検証。
5. SDRAM実pad/PLL/min-max制約によるSTA、S3連続取得・全量搬出・WCET・RF品質の実測。

1〜4にはこの環境で進められる実装作業が残る。5の実機測定は対象機材が接続されていない。
全件完了・打ち止め・全方式不可能とは結論しない。
