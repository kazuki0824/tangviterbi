# ② FFT line回転と固定マスク仲裁の比較

追記：[観測回路を分割した同条件の再測定](pipelined-observation-results.md)で回転cache版は185.735519 MHz、全体追跡値20999/20736（263 logic超過）。機能検証済みの回転cache/固定maskを部分削減として採用した。旧probeの速度・帰属集計は以下の時点の記録として保持する。

2026-10-19 JST。read-only controllerの部分削減後も残る563 logic超過に対し、FFT outer-delay cacheのword選択と、仲裁の循環選択経路を改めた。全受信機ではなく、既存cache/仲裁/controllerの境界で比較する。

**結論：回転cache＋固定mask仲裁は機能試験を通ったが、面積が99 logic超過し、probe timingも未達のため未採用。現行RTLは9a038f8のread-only controller採用版を維持する。** 候補のRTLは `experiments/rotation_sdf_delay_cache.sv` と `experiments/rotation_sdram_client_arbiter.sv` へ保存した。

## 回路の変更

現行FFTのMode 3は各lineをword 0→7の順でreadし、その6 clocks後に同じwordへwriteする。旧cacheは8 wordから可変位置をreadし、write位置をdecodeしていた。変更後は常に最下位wordをreadし、write時に `{新word, 旧line[255:32]}` と回転させる。8回のwrite後には新word 0が最下位に戻り、既存BL8 writebackと同じ順序になる。line容量は32 B、外部delayは4096 wordのまま。

cacheは未完sampleを1個に制限する。sample受理後はwrite commitまでexternal_readyを下げ、read済み・順次アドレス・予約の有無を検査する。現行FFTは13 clocksごとの受理と6 clocks後のwriteなので、今回の接続ではこの制限が追加のstallを生まないことを実測で確認する。汎用ランダムアクセスcacheとしての互換性は主張しない。

最初の回転版は配置後134.517 MHzで目標未達。最悪経路は仲裁のcursorからowner選択へ至る可変加算・添字計算を含んだ。そのため、cursorに応じた固定maskと固定優先encoderを使用し、範囲末尾まで候補がなければ先頭へ回る方式へ変更した。FFT最優先・背景round robin・既選択要求固定・応答所有権の契約は維持する。

固定maskの初回合成はcursorをFSMへ自動再符号化し、配置不能な `$buf` を残した。カーソルを `fsm_encoding="none"` で3 bitのまま保持し、改めて測定した。この失敗は容量不足や性能合格と読み替えず、ログとsnapshotを保存した。CAD集計スクリプトにも、route未生成時は使用量null・失敗理由を保存する処理を追加した。

## 検証

- cache単体：8個の異なる旧wordと新wordで順序を確認。writebackを10 clocks止めた間のdescriptor保持、次lineへの移動、同時予約防止、誤アドレス・未予約write・read前writeのfaultを検査。
- 仲裁単体：5 cursor×64要求集合の320条件を独立した循環探索oracleと比較。要求固定・7 clocksの応答停止・DQM・FFT優先・背景cursor折返しも検査。
- 現行FFT＋実cache/仲裁/controller：常時valid/周期入力の2条件。背景は均等154.905243 MB/sのモデル、実K7/deinterleave/S frameは未接続。各3 complete frame・24576 binを独立整数FFT oracleで比較し、独立SDRAM pinモデルも維持。

## 測定記録

| 版 | 直接合成logic | 配置後本体帰属logic | probe Fmax MHz | 全体追跡値の超過 | 判定 |
|---|---:|---:|---:|---:|---|
| 現行read-only版 | 3210 | 3058 | 160.230728 | 563 | 部分採用、全体未成立 |
| 回転cache＋旧仲裁 | 2810 | 2947 | 134.517090 | 452 | probe timing未達 |
| 回転cache＋固定mask・自動再符号化 | 2730 | 未取得 | 未取得 | 算出しない | `$buf` 配置不能 |
| 回転cache＋固定mask・3 bit固定 | 2733 | 2594 | 133.582687 | 99 | 面積超過・probe timing未達、未採用 |

最終候補の追跡値は20472−2231＋2594＝20835/20736。これは未実装部分を0とした値なので、99だけ減らせば完成という意味ではない。最終版のFFは986、BRAM/DSPは0/0。直接合成と配置後の帰属差を、実受信機で保証される削減へ一般化しない。

最終候補の最悪pathはowner→仲裁/controllerの組合せ回路→観測用digest FFに至る。従って133.58 MHzは、この測定wrapperのtarget未達である。受信機本体に同じdigestは存在しないため、この数値だけで本体の速度上限を断定しない。次の速度測定では観測回路をpipeline化する等、計測境界の妥当性も再点検し、基準版と同じ条件で比較する必要がある。

最終候補の接続unittestは87.112秒で成功。常時validの後続frame間隔145054/146523 clocks、周期入力160381/160381、最大入力滞留5 sampleで基準と同じ。両条件とも24576 bin一致、背景最大未完1/1/2/1/1、試験用期限超過0。cache単体は0.031秒、仲裁は現行/候補の両方を含む4 testsが0.125秒で成功した。前段の回転＋旧仲裁（91.627秒）と固定mask再符号化前（88.678秒）も機能照合は成功したが、CADの失敗を取り消す意味ではない。

比較の数値・source hash・生成netlist・P&Rログは以下に保存した。

- [回転cache＋旧仲裁](sdf-sdram-rotating-cache-evidence/summary.json)／[FFT照合](sdf-rtl-arbiter-rotating-cache.json)
- [初回固定maskの配置失敗](sdf-sdram-rotation-mask-evidence/summary.json)／[FFT照合](sdf-rtl-arbiter-rotation-mask.json)
- [最終候補のCAD](sdf-sdram-rotation-binary-mask-evidence/summary.json)／[FFT照合](sdf-rtl-arbiter-rotation-binary-mask.json)

各失敗版にもcache/arbiter snapshotを保存し、source hashの指す試験時RTLを識別する。現行production RTLを、そのまま候補の試験版と読み替えない。

## 制約と次の作業

今回の費用は同じscan/signature wrapperの帰属集計であり、実受信機統合後の資源保証ではない。wrapper側との最適化が変わるため、直接合成の差と配置後帰属の差を区別する。全体追跡値は残予約2231を実費へ置換したもの。まだ実装されていないPHY/背景producer等を0と仮定した費用でもあり、余裕が出ても完成扱いにしない。

実K7消費、T time-deinterleave/S frameの実burst/アドレス、全体P&R/STA、SDRAM PHY、S3 WCET、RF→TS連続出力が残る。①は変更なし。

再現：Icarus/vvpで `test_sdf_rotating_cache.py`、`test_sdram_client_arbiter.py`、`test_sdf_rtl_arbiter.py` をunittest discoverで実行。CAD候補の再現は一時checkoutで `experiments/rotation_*.sv` を対応する `rtl/*.sv` へ置き、`python ci/sdf_sdram_service_evidence.py --output reports/sdf-sdram-rotation-binary-mask-evidence` を実行する。既存のFFT接続unittestも同じ一時checkoutで実行する。失敗版の再現は対応snapshotを用いる。現在の正規RTLへ未採用版を復帰させない。
