# ② 固定した部分構成の配置配線：目標速度を達成

2026-10-28 JST。[Actions run 40524351929](https://github.com/kazuki0824/tangviterbi/actions/runs/40524351929) の2試行が完了した。ツールのjob成功とSTA目標達成は区別し、出力report・exit・ログ・netlistを確認した。

| 試行 | Fmax | 最低152.6266MHz | 目標154.2857MHz | logic site計数 | FF | BSRAM |
|---|---:|---|---|---:|---:|---:|
| 保存基準 weight10 / seed1 | 152.0913MHz | 未達 | 未達 | 19627 | 8673 | 29 |
| weight20 / seed1 | 152.9520MHz | 達成（+0.213%） | 未達 | 19666 | 8673 | 29 |
| **weight10 / seed2** | **166.2234MHz** | **達成（+8.909%）** | **達成（+7.737%）** | **19658** | **8673** | **29** |

seed2のlogic計数は基準比+31、容量20736に対し1078を残す。この部分構成については、速度不足を現在も未解決とは扱わない。追加31を旧全段台帳へ機械的に加えて全体fitを認定することもしない。

対象は保存済みFFT・SDRAM service/reader・tile・S retention・共有K7と測定fixture。RF endpoint、equalizer、interleaver、RS/TS、PHYや段間契約を全て接続した受信機ではない。fixtureには21個のALU54Dを使うscanレジスタと観測用メモリがあり、今回の資源数を全受信機の余りへ読み替えない。実ボードの動作、外部IO timing、信号品質も未確認。

入力mapped netlist、改変backend source 2ファイル、chipdbのhashが基準と一致する。新2試行のbinary hashは一致するが、保存基準とはコンパイラ・binaryが異なるため、改善の全量をseedだけの因果効果とは断定しない。合法性判定は緩和していない。routed netlist hash、logic再計数、STA reportと終了コード、配線完了ログ等9check×2試行が成功。検算は `python -m ci.cursor_mask_route_result_audit`、結果はaudit.json。各試行ディレクトリには実成果物とartifactのhash/出所を保存。

ローカル試行の途中ログは `*-incomplete-local` に保存。セッションとプロセス、完了結果が取得できなくなった原因は不明。「計算中」と断定した説明を訂正した。今回の値は、その途中ログではなく完了したActions成果物に基づく。
