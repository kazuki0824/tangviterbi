"""Render instruction accounting and same-cost schedule results."""
import json
from experiments.s3_joint_runtime import ROOT
p=ROOT/'reports/s3-sdk-cost-ledger'
l=json.loads((p/'results.json').read_text());r=json.loads((p/'runtime.json').read_text())
lines=['# ② SDK費用を呼出し先まで計上した再評価','',
'2026-10-29。**S側は今回の45条件でも通過せず。T側の通過は条件付き。全SoC費用の数値確定・実機成立認定は未完了。**',
'', '## 変更した根拠','',
'保存済みS側ELF（SHA256 `'+l['sdk_elf_sha256']+'`）から通常受信経路を命令数で計数した。call命令はcallerに1回、callee本体は呼出しごとに1回だけ加える。queueの20byteコピー、HALの48byteコピー、transactionの56byte初期化もEspressif ROM ELFまで追跡した。SDKの公開ROMアドレスにあるl32r/jxの2命令と実関数の宛先を照合済み。分岐先から再逆アセンブルし、padding誤解釈を避け、ハードウェアループの反復を加算する。',
'', 'ROM配布物はesp-rom-elfs 20241011、archive SHA256 `921f000164a421c7628fbfee55b173384aafaa51883adc65cd27bf9b0af9e9a9`。IDF固定commit `fcae32885b0296b32044cb99ecbdc50d98dddb83` のtools.json指定版。toolchainはxtensa-esp-elf 14.2.0_20241119。',
'', '## 通常経路の費用（callee込み）','',
'次の命令数は宣言した分岐経路または非logging非循環分岐のown-instruction包絡。到達性を証明した全経路WCETではない。cycle欄はceil(命令数×1.1)という既存仮定で、実測ではない。',
'', '| 処理 | S:命令 | S:cycle模型 | T:命令 | T:cycle模型 |','|---|---:|---:|---:|---:|']
import math
for k in l['roots']['5']:
 a=l['roots']['5'][k]['inclusive_instructions'];b=l['roots']['9'][k]['inclusive_instructions']
 lines.append(f'| {k} | {a} | {math.ceil(a*1.1)} | {b} | {math.ceil(b*1.1)} |')
lines += ['', 'T欄はS ELFのDMA記述子数を5→9へ置換した比較であり、T ELF全経路の再計数結果ではない。submit/reapはraw wrapper込み。running guardはrawのみ25/27命令で、runtimeの42/44cycleは外側wrapper込みの従来根拠を維持した。idleだがresult queueが空の経路も209命令と計上したが、今回のcore0完了IRQ直後に取得する模型では出現しない。実アプリでこの状態を除外するにはIRQ遅延等の根拠が必要。',
'', 'WDTは登録taskが2つの条件。markのみ158命令、timer feedを伴う221命令。feed wrapperの通常判定40命令はshellに含め、更新時の追加26命令とreset本体221命令の合計247命令→272cycleだけをWDTイベントへ課した。これにより更新時の時刻再設定等を落とさず、通常判定も重複加算しない。反対コアがlockを持つ待ち時間はこの命令数には入らない。',
'', '## 二重計上を避けた費用境界','',
'- submitはtake・bulk記述子準備・SDK queueまで。開始ISRは別イベントで一度課す。旧4000cycleや別枠API20µsは加えない。',
'- reap成功はSDK queue受取・uninstall・prefix completeを含む。旧800cycleは加えない。通常高位word一致・最大8leaseの全prefix退役を用いる。',
'- DMA記述子組立ては開始ISRのcalleeに入る。DMA線上転送はCPUに加えず完了時刻へ反映する。',
'- WDTの時刻判定はshell、reset本体はWDTイベント。tick費用は従来2000cycle/100Hz/coreという割当のまま。',
'- RF/packing/collectは前の模型の区分を維持。旧U0/U1、旧差分scan、その他の一括予備費は加えない。',
'', '## 同じ費用による処理順序・期限評価','',
'実owner順序・native/packing/lease状態遷移に新しい単価を接続した。台帳への加算と仮想時刻の進行は同じ関数で行う。45条件について回数・回/s・CPU%・cycle保存則をruntime.jsonに記録。失敗までの短い区間の回/sを定常値と解釈しない。',
'', '旧模型には、開始ISR費用を課す前にwire完了時刻を設定し、開始ISR全体をwire時間と重ねる誤りがあった。今回は開始ISR全体を課した後にwireを開始する保守的な置き方へ修正。実ドライバはISR末尾近くで開始するため、実機の厳密な命令時刻とは異なる。旧費用42条件も同じ修正で再実行した。',
'', '| T/S・分担 | slice | 準備語/反復 | stall | bank到達/要求 | 結果 | RF最大間隔µs | arena最大byte | 次の要求byte |', '|---|---:|---:|---:|---:|---|---:|---:|---:|']
for prof in r['profiles']:
 for x in prof['rows']:
  status='有限通過' if x['scenario_pass'] else '準備未完' if x['native_fault']==5 else '容量超過' if x['accept_reject_reason']==2 else 'packing期限条件拒否' if x['pack_fault']==6 else 'その他'
  lines.append(f"| {'T' if x['rate']==16 else 'S'} {x['share']}/16 | {x['slice_pairs']} | {x['prepare_per_iteration']} | {x['stall_percent']}% | {x['banks']}/{x['requested_banks']} | {status} | {x['max_rf_poll_gap']/240:.3f} | {x['peak_arena_bytes']} | {x['attempted_arena_bytes']} |")
lines += ['', 'S5/16・512pair・2048語・stall0%は93bank後に133824byte必要となり2752byte超過。3072語は30bank後に137825byte必要となり6753byte超過。S6/16・2048語は40bank後に1808byte超過。本番の準備予算1024語は変更していない。命令費用を下げた項目があっても、系全体の期限成立にはならない。',
'', '## 全処理費用の残りを0として扱わない台帳','',
'受信ループ模型の全区分はruntime.jsonのfixed_cost_cycles/dynamic_costsと各coreのcost_ledgerにある。以下は数値確定に必要な残額であり、未計上費用を隠す予備費へ合算しない。',
'', '| 対象 | 発生回数・頻度の境界 | 現在の根拠／未確定値 |','|---|---|---|',
'| owner/worker、空packing、RF各状態、collect | 実状態機械で全訪問数を記録 | 通常経路命令数と未測定割当が混在。全状態の費用は未確定 |',
'| packing本体・RF fill | 実block/run/slow pair/語数を記録 | CFG命令数×1.1。fill呼出しの固定費・状態別最大費用は未確定 |',
'| SPI API/ISR | 成功submit/reap各1回、開始/完了IRQ各1回/転送という模型 | 本報告の宣言経路数。ISR entry/exit、window exception、idle-empty、他の分岐は残る |',
'| SPI_UPDATE待ち | 各開始ISR内1箇所 | 反復1回につき追加3命令。解除までの反復上限はSDKにない。ハードウェア最大遅延が必要 |',
'| critical section、CAS | 各callee訪問時。queueはcore0のみという構成 | uncontended/success1回を計数。WDT共有lock・他IRQ/他task競合の上限は未確定 |',
'| tick | config100Hz/core | 2000cycleの割当。ハンドラ・起こすtask・割込み位相の全費用は未確定 |',
'| WDT | 各core、前回feedから2.5s以上になった最初の反復 | 2登録taskのmark/feed命令数。flash/cache/lock待ちは別 |',
'| キャッシュ・PSRAM・内部RAM・MMIO・DMA競合 | 各アクセスと同時活動次第 | 0/10%は感度点。上限を意味しない |',
'| その他IRQ/IPC/他task | 実アプリの登録・到来制約次第 | 最終アプリ構成が固定されていないため未確定 |',
'| FPGAからの選局・電源等の指令 | 指令到来数。受信データの逆送は禁止のまま | ハンドラと最大到来頻度未固定。0費用とはしない |',
'| 起動・再選局・停止・fault処理 | 各イベントごと。定常受信と分離 | 停止許容時間・最終RF/PHY処理・実装が未固定 |',
'', '従ってこの45条件は全アプリの期限証明ではない。未確定費用を仮定値で埋めれば数値は出せるが、ユーザー指定の「SoC全処理費用を確定して期限確認」まで完了したことにはならない。実機仕様・最終アプリの不足とは別に、表のソフトウェア経路監査にも残作業がある。',
'', '## 再現','', '```sh',
'python -m ci.s3_sdk_cost_report --toolchain ../toolchain/xtensa-esp-elf',
'python -m experiments.s3_sdk_joint_runtime',
'python -m experiments.s3_sdk_cost_report',
'python -m unittest tests.test_s3_sdk_cost_ledger tests.test_s3_joint_runtime',
'```','',
'[命令台帳](results.json)／[45条件の費用・頻度・期限](runtime.json)／[検算ログ](tests.log)。正式採用0。','']
lines += ['検算：SDK費用台帳11件＋既存25件、合計36件成功。','']
(p/'README.md').write_text('\n'.join(lines))
