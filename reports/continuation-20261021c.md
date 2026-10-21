# ②：時間DIの実タイル転置とDMA、並行処理の検証

①は停止維持。正式通信路・受信機採用0。今回の回路も完成受信機として採用しない。
前回の「処理時間を仮定した要求列」から、値を保持・転置・位置合わせする実RTLへ進めた。
ソフト値6 bytes/sampleを維持し、追加の間引き・再量子化はない。

## 実装した回路

- `t_time_tile_store.sv`: 16×16 samples×48 bitのタイル。行／列の読出しと書込みを独立して動作させる。
  同一sampleの同時read/writeはcollisionとして検出し、試験で禁止する。
- `t_time_tile_dma.sv`: scratchから16行を読み、列ごとにringへ96 bytesを書き、
  遅延した96 bytesを読んで同じタイル列へ戻し、16行をscratchへ書き戻す。
  次の列のgatherを前の列のSDRAM処理と重ね、読出し後のprefix除去とscatterも並行させる。
- `t_time_tile_dma_static.sv`: BL8格納位置の可変part-selectを固定caseへ変更した同機能版。
  ブロックレジスタの容量、値、順序、処理周期は変更しない。
- `shared_receiver_fft_tile.sv`: 実FFT/service/共有K7のBGポート1個をタイルDMAへ置換した合成用接続。
  前回の直接発行・128要求仲裁を同じポート形のmodule名で接続する。

scratchは32-byte整列、strideも32の倍数。ring base/endは32-byte整列、write開始も整列、
read開始は2-byte整列。1 tileごとに16個のring descriptorを順に供給する契約。
resetはcontroller/arbiterを含む共通reset。in-flight中の独立reset/選局は対応済みとはしない。

**未実装部分:** 複数タイル全体のdescriptor供給・3buffer役割交代の実RTL、cold-fillの有効値管理、
実復調段からの入出力契約。この部分はtestbenchが供給している。
実タイル回路を作ったことと、時間DIサブシステム全体を完成したことは分ける。

## 実データ・期限の結果

独立SDRAM pin-commandモデルと実controller/arbiterへ接続した。
初期メモリはaddressから生成した決定的な値とし、ringの過去履歴を任意のデータで満たす。
Python oracleはbyteごとのring位置と最新writeで更新される区間を照合する。
ゼロデータだけの試験ではなく、全ring/scratch writeのaddressと256-bit payload、
全出力scratch word、衝突なしを検査した。

| 条件 | タイル数 | 出力照合word数 | write照合数 | 時間DI完了clock | 期間超過 |
|---|---:|---:|---:|---:|---:|
| 初版、部分動作確認 | 6 | 2304 | 573 | 42658 | 全期間判定には使わない |
| 初版、最大Mode3＋競合 | 312 | 119808 | 29796 | 2581912 | **15832** |
| 固定case版、同じ全期間 | 312 | 119808 | 29796 | 2581912 | **15832** |
| 固定case版、I=1・全96クラス | 6 | 2304 | 573 | 18448 | 全期間判定には使わない |

期限は16 symbol＝2566080 clocks。全期間条件の超過率は約0.617%。
初版と固定case版は全clientのfinish/late値も一致した。他5 clientの宣言期限違反は0。
I=1試験は全偶数byte offset 0..30、D=0 bypassを含む。warm-upデータの有効性を保証する試験ではない。

[初版全期間](t-time-tile-dma-full.json)、[固定case全期間](t-time-tile-dma-static-full.json)、
[全offset](t-time-tile-dma-offsets.json)、[部分試験](t-time-tile-dma-smoke.json)。対応する`.log`も保存。
unittestのOKはデータ照合と実験完走の意味であり、期限超過を合格にしない。

SとFFTの競合相手は前回の要求proxyであり、実stageの到着列ではない。
実FFT/K7との合成用接続は別の測定であり、その全データ経路をこの試験で検証したとは言わない。
全mode/I/階層/phaseの連続運転、実PHY、RF→TS品質は未確認。

## 回路資源と配線後速度

同じOSS CAD Suite 2026-10-04、Yosys 0.69+190、nextpnr e2fe86b3、seed1、GW2AR-LV18QN88C8/I7。

| 回路 | 合成時logic | 合成時FF | BSRAM | 配線後logic / FF | 配線後MHz |
|---|---:|---:|---:|---:|---:|
| タイルDMA初版 | 10255 | 5213 | 2 | 未実施 | 未実施 |
| 固定case版 | 9496 | 5213 | 2 | 10729 / 5213 | **175.438599** |

配線後値はscan/観測probeを分離し、RAM blockerと実装上必要なLUTも数えた。
合成時9496を物理占有10729と混同しない。固定case版単体は154.285714 MHzを通過。
しかし、このclockをFFT/K7統合版や全受信機へ転用しない。

[初版合成](t-time-tile-dma-evidence/summary.json)、[固定case合成](t-time-tile-dma-static-evidence/summary.json)、
[固定case配置配線・hash](t-time-tile-dma-static-route/summary.json)。

### FFT・共有K7へ接続した資源：この案は不採用

個別合成の単純加算ではなく、実際に接続したtopを再合成し、packしたnetlistを数えた。

| 接続済み部分回路 | logic枠（RAM blocker込み） | FF枠 | BSRAM | DSP18 |
|---|---:|---:|---:|---:|
| FFT/service/K7＋実タイルDMA、観測probe除外 | **21358 / 20736** | 12002 / 15552 | 18 / 46 | 6 / 48 |

logicは**622枠超過**。さらにdescriptor生成、他の復調段、RS/TS、入力PHY等は未実装。
622だけ削れば完成受信機が収まる、という意味ではない。

配置探索開始後、独立した`--pack-only`で観測回路を除外しても超過することを確定したため、
配置コマンドをCtrl-Cで中断した（終了130）。配置配線完了・統合Fmaxの結果はない。
ホスト容量不足、承認基盤エラー、timeoutを不採用理由にはしていない。
このpacked netlistが収まらないという判定であり、別実装・別mapまで不可能と証明したものではない。

[probe分離済み資源](shared-receiver-fft-tile-route/packed-budget.json)、
[中断理由](shared-receiver-fft-tile-route/placement-stop.json)、
[集計](shared-receiver-fft-tile-route/summary.json)、
[再集計スクリプト](../ci/t_time_tile_packed_budget.py)。packed/mapped netlist、コマンド、ログを圧縮保存した。

今回のブロックレジスタを多数持つ実装は、期限と面積の両方で不採用とする。
単体175.44 MHzの成功や、機能試験のOKだけで採用へ進めない。

## 現在の障害・確認不足（解消済みを除く）

| 対象 | 現在残るもの |
|---|---|
| 処理速度 | 従来の実FFT/K7接続版は最良146.22 MHzで、現K7のstallなし最低152.63 MHzへ未達。新タイル単体175.44 MHzを転用できない |
| 時間DI期限 | 実タイルDMAでは最大Mode3の有限競合条件で15832 clocks超過。全体descriptor生成・3buffer交代・cold fillは未接続 |
| FPGA資源 | 今回の接続済み部分回路は622 logic枠超過。全受信機の残stageを収容する実装もない |
| 全受信処理 | 同期、TMCC、等化/demap、実T/S DI、RS、TSまでの一貫した接続と精度検証が未完了 |
| 長期・動的条件 | 全mode/I/rate/階層/位相、実stage到着包絡、RS burst、選局再同期、停止時契約、最終TS期限が未検証 |
| S3処理能力 | 通常S経路のCPU高費用モデルは106.8042%/106.6197%。実無欠落搬出、DMA/IRQ競合、core別WCET、専用GPIOの費用も未確認 |
| SoC/FPGA物理接続 | 20K実ピン割当、搭載負荷、受信PHY、独立clock間同期、lane整列と保持量が未検証 |
| SDRAM電気的条件 | pad/tri-state/PLL位相/min-max制約を含むIO setup/hold検証が未完了 |
| RF・実機 | 必要帯域/CN、外部変換、実S3全量取得、RF→TS誤り率・無欠落が未確認 |

今回、「実タイル転置回路がない」「全てのデータはまだモデルだけ」という説明は解消済み。
3buffer容量とモデル上の所有権、serviceのみのclock、共有K7状態回路の不存在等も、
現在の障害へ戻さない。タイル実装完了と時間DI全体完了は区別する。

## 未完了と今回返す位置

今回のAは、実タイル候補のデータ・期限・単体P&R・接続後の物理資源を調べ、
不採用理由を確定した地点。前回のBのうち、全体descriptor供給までのRTL化はまだ終えていない。
次のBは、幅広レジスタの重複保持を減らすため保持方式と転送interfaceを設計し直し、
必要なRAMポート・保持量も数えた上で、同じデータ・期限・接続資源の検証を通す地点となる。
RAMへ移せば自動的に解決するとは仮定しない。

Aで返す理由は、同じ候補の配置探索や周波数調整を続けても、確定した資源超過を
解消できず、回路構造を変更する判断が必要になったため。これは私が選んだ技術上の区切りで、
Bへ着手できない外部障害があるという説明ではない。今回の候補を採用しない判定には
十分な証拠が揃ったと判断したが、依頼全体を完了したという品質水準には達していない。
上表の未完了作業と①停止を維持する。②全方式不可能の証明はしていない。
