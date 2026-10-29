"""Render the latest instruction-based receiving estimate and its residuals."""
import json
from experiments.s3_joint_runtime import ROOT
p=ROOT/'reports/s3-receiver-cost-ledger'
a=json.loads((p/'instructions.json').read_text());r=json.loads((p/'runtime.json').read_text())
lines=['# ② 受信ループ・割込みの費用と発生頻度、同じ費用での期限評価','',
'2026-10-29。**宣言した受信構成のソフトウェア費用模型を更新。S側は今回の条件でも継続受信不成立。全SoCの実時間上限は未確定。**',
'', '## 結果と確度','',
'単価と発生回数は同じ実C実行に接続した。台帳と時刻へ同額を一度だけ課す。RFの準備・切替・受渡し、collect、空packing、owner/worker制御、tick本体、同優先度task再選択、割込み入口・復帰の従来の割当を、保存SDK ELFの命令計数へ置き換えた。命令数は宣言条件での経路値／保守的包絡、cycle値は命令数×1.1の模型。実測値ではない。',
'', 'T/Sの全段FPGA、実RF ABI、最終アプリ全体、cache/バス待ち等の保証を意味しない。S ELFの5/16分担・Tへの適用はパラメータ比較であり、それぞれの全経路再リンク証明ではない。2048/3072語予算は模型のみ。本番1024語は変更していない。',
'', '| 系統・分担 | 準備語/反復 | 到達/要求bank | 結果 | RF監視最大間隔µs | arena最大byte | 次の受入れ要求byte |','|---|---:|---:|---|---:|---:|---:|']
for profile in r['profiles']:
 for x in profile['rows']:
  if x['requested_banks']!=4000:continue
  status='有限通過' if x['scenario_pass'] else '準備未完' if x['native_fault']==5 else '128KiB容量超過' if x['accept_reject_reason']==2 else 'packing期限条件拒否'
  lines.append(f"| {'T' if x['rate']==16 else 'S'} {x['share']}/16 | {x['prepare_per_iteration']} | {x['banks']}/{x['requested_banks']} | {status} | {x['max_rf_poll_gap']/240:.3f} | {x['peak_arena_bytes']} | {x['attempted_arena_bytes']} |")
lines += ['', '上表は512pair、追加stall0%の条件。全45条件（256/512pair、stall0/10%、準備1024/2048/3072語）は [runtime.json](runtime.json) と [run.log](run.log)。100bank通過だけで終了せず、同じ条件を4000bank要求でも確認した。途中のRF/collect費用だけを置換した試行では100bank通過・135bank停止という例があり、その後、249命令のIRQ入口・復帰も含めて全条件を再計算した。上表がその最新値。',
'', '## 受信中の費用境界（240MHz cycle模型）','',
'下表の回数は各実行の `cost_ledger[core][処理].events`、回/sは `events_s`、CPU%は `cpu_percent` に記録。停止までの短区間の回/sを定常頻度とは解釈しない。busy pollingの空振りも計上するため、総CPUがほぼ100%でも、それ自体を能力不足とは判定しない。',
'', '| 処理 | 単価 | 発生条件・包含範囲 |','|---|---:|---|',
'| OWNER_SHELL | 190/反復 | 最大経路200命令からnative直接call2箇所に重なるpoll wrapper28命令を除いた172命令。collect用時計・通常feed判定を含む |',
'| WORKER_SHELL | 62/反復 | 継続worker反復56命令。通常feed判定を含む |',
'| PACK_EMPTY | 143/回 | raw wrapper25＋quantized/impl/時計105＝130命令。3bank走査込み |',
'| PACK_SLICE | 319/非空slice | 既存slice223＋時計21×2＋raw wrapper25＝290命令。block/run/slow pairは別 |',
'| PACK_RUN/BLOCK/SLOW | 130/50/191 | 既存CFG118/45/173命令。実run/block/pair訪問ごと |',
'| RF_BASE | 213/poll | quiet native179＋wrapper14＝193命令。時計callbackのcarry分岐も含む |',
'| RF_PREPARE追加 | 132/未prepared poll | prepare native299−quiet179＝120命令。available/reclaimとfill呼出し制御を含み、fill本体は除外 |',
'| RF_SWITCH追加 | 36/切替 | switch211−quiet179＝32命令。MMIO書込み込み |',
'| RF_ACCEPT追加 | 755/受渡し | settling/accept865−quiet179＝686命令。境界二分探索、bank取得、accept wrapper、pp_accept込み |',
'| FILL | 下記式 | 毎回のcallとwrap spanに課す。bank当たり費用の語数割りを廃止 |',
'| COLLECT | 35/108/176/245 | owned bank数0/1/2/3に対応。31/98/160/222命令。DONE状態の並行変化を許す分岐包絡 |',
'| SUBMIT_EMPTY/SUBMIT_DONE | 63/939 | take、成功時bulk準備・SDK queueを含む。ISRは別 |',
'| REAP_RUNNING | 42/44 | SPI2/3のguard経路。SDK result queueを呼ばない |',
'| REAP_DONE | 469 | SDK取得・prefix退役込み。idle-empty経路は別に209命令と既に計数済み。今回の完了IRQ即時公開模型では発生しない |',
'| SPI開始IRQ S/T | 2287/2402 | 本体1830/1934＋入口復帰249命令。初回は2550/2665cycle |',
'| SPI完了IRQ | 1037 | 本体693＋入口復帰249命令 |',
'| TICK_IRQ core0/core1 | 1846/1696、100Hz | 本体564/366＋task再選択を含む入口復帰642命令。さらにpeer kernel lock待ち519/587cycleを含む |',
'| WDT追加 | 516/更新 | 更新経路289−通常判定42＝247命令の272cycleに、peer reset全体221命令からの待ち包絡244cycleを加える。判定はshellで課済み。前回判定時刻＋2.5sを初めて越えた反復で発生 |',
'', '`FILL = ceil(1.1 × [5 + Σspan(41 + 17 floor(span/8) + 3(span mod 8))])`。5命令はbank callbackをcallごと1回。41は各spanの非loop命令を全て課す保守的包絡。1poll最大1024語なのでringをまたぐspanは最大2。境界探索は各最大12反復、準備内fill呼出しは最大2、collect走査とprefix退役は各最大3としてCFGを展開。未宣言のcycleやcallを検出すると監査を失敗させる。',
'', 'settling中の待機だけの経路は120命令であり、quiet 179命令のBASE内に収まることも確認した。一つのpollにBASE＋該当状態の差分＋実fillを加える。calleeをBASEと差分の両方へ丸ごと追加しない。quiet/prepare/switch/settlingの包絡は独立した最大値なので、差分を実測の追加時間とは解釈しない。旧U0/U1、差分scan、API20µs、一律IRQ300/1000は加算しない。DMA線上時間はCPU費用に加えず、lease保持・完了イベントへ反映する。',
'', '## 割込み条件と残額を明示した全費用式','',
'level-1のnonnested・1pending sourceの入口/復帰を、vector→user exception→lowint→context save/restore→user exitまで計数した。再選択なし249命令、同優先度の2受信taskから同じtaskを再選択するscheduler経路込み642命令。launcherは呼出し側のpriority[2]を受け取る。ここでは2taskを同優先度と仮定したため、異なるcoreに固定していてもtickが再選択を要求しうる。固定実装の事実ではない。今回は各tickに再選択側を課した。SPI IRQには249命令を課す。Cハンドラ本体は別。tickは1経過tick、1alarm処理round、delayed taskの起床なし、scheduler非suspend、tick counter非wrapを条件とする。IWDT callbackは両core、USB SOF callbackはcore0に最大1、追加application callbackなしを構成仮定とした。link-only ELFの存在だけから実登録を認定しない。',
'', '観測区間HのCPU費用は `C_total(H) = Σイベント数×上表単価 + C_window(H) + C_lock(H) + C_hw_wait(H) + C_memory(H) + C_other_app(H)`。後半は下表の残額であり、0と認定していない。今回の0/10%追加stallは感度点で、残額の上限保証ではない。通常のkernel/WDT共有lock待ちは既に上表へ含めた。固定2task構成でpeerのkernel incrementとscheduler各1回の全関数費用をhold時間の包絡として用いる。core0はpeer 131＋340命令から519cycle、core1は193＋340から587cycle。WDTはpeer reset全体221命令から244cycle。10ms/2.5s期間内に複数回到来しないという同じ費用模型の条件であり、window/cache/高位IRQ延長はこの待ち包絡にも別途加わる。',
'', '| 残額 | 単価・回数／未確定理由 | 同じ処理での重複防止 |','|---|---|---|',
'| C_window | overflow/underflow4/8/12の各handlerは5/10/14命令。発生数はwindow状態と割込み位置に依存し未確定 | 通常call/ret命令と別に例外handlerだけを加える。context save中の例外もここ |',
'| C_lock | 上表のpeer kernel/WDT待ち包絡を越える延長、追加のlock利用者・CAS再試行。通常の待ちは計上済みだが、最終アプリの全利用者は未確定 | 成功1回のcritical/CASと上表のpeer待ちは計上済み。それ以外の追加分だけを加える |',
'| C_hw_wait | SPI_UPDATEは開始ごと、systimer capture待ち・snapshot再試行はtickごと。解除までの反復上限がSDKにない | 初回成功checkは単価に包含。追加反復・待ちだけを加える |',
'| C_memory | flash/cache、PSRAM/内部RAM/MMIO/DMA競合の追加遅延。window handlerのload/store待ちも含む | 既存instruction×1.1と追加stall感度を重ねて実測上限とはしない |',
'| C_other_app | tick catch-up/起床/別taskへの切替、他IRQ/IPC/PHY活動、制御指令等。最終アプリ登録と到来制約が未固定 | 上表の通常tick/ISRを再加算せず差分または追加eventだけを加える |',
'', '起動・再選局・停止・fault処理は連続受信の成功phaseと分ける。各イベント回数とその費用が必要であり、0費用ではない。FPGA→SoCは指令のみという制約を維持する。保存ELFの `experiments/s3_raw_probe/main/raw_probe.c` はlink-only probeで、app_mainが受信を開始しないと明記されている。従って、それを最終受信アプリと読み替えて全task/IRQ/指令頻度を確定することはできない。',
'', '## 指定2点に対する到達点','',
'1. 受信ループと宣言した通常SDK/IRQ構成の費用・発生回数は台帳化し、未測定割当を命令計数へ置換した。全SoCの数値確定には上の残額が必要。残額を式に置いたことと、数値を確定したことは別。',
'2. 同じ単価で実owner順序・RF監視・送信・prefix退役・buffer容量を評価した。有限条件の通過／拒否を全45条件に記録。残額を含む実機期限保証には未到達。',
'', '前回の「途中成果を提示するため」という中断は依頼の終了条件に合わず、合理的な中断理由ではなかった。今回、実機未測定を理由に止めず、ソフトウェア側で計数できるRF各状態、worker、collect、tick、IRQ入口復帰を追加で監査した。',
'', '## 再現・検算','', '```sh',
'python -m ci.s3_receiver_cost_audit --toolchain ../toolchain/xtensa-esp-elf',
'python -m ci.s3_tick_cost_audit --toolchain ../toolchain/xtensa-esp-elf',
'python -m ci.s3_irq_entry_audit --toolchain ../toolchain/xtensa-esp-elf',
'python -m experiments.s3_receiver_joint_runtime',
'python -m experiments.s3_receiver_cost_report',
'python -m unittest tests.test_s3_receiver_cost_ledger tests.test_s3_sdk_cost_ledger tests.test_s3_joint_runtime',
'```','',
'[通常処理命令台帳](instructions.json)、[tick台帳](tick.json)、[IRQ入口・window台帳](irq-entry.json)、[費用・頻度・期限](runtime.json)、[検算ログ](tests.log)。正式採用0。','']
lines += ['検算：今回13件＋既存36件、合計49件成功。','']
(p/'README.md').write_text('\n'.join(lines))
