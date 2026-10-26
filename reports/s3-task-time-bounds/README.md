# ② 実taskからRF観測間隔へ戻した時間条件

2026-10-26。runtimeは992f497、SDK ELFは7ee25471a6dc96c056c2afd883cf4f70282fd186be920cced7dddefa40554fc7。①は変更しない。性能合格・正式通信路割当・採用はいずれも0。

## 今回確定したこと

1. `esp_task_wdt_reset` は、生成ELFでも `xPortEnterCriticalTimeout(lock, -1)` を呼ぶ。timeout=-1の分岐はCAS再試行へ戻り、期限カウントで脱出する処理を持たない。再試行1回はcallee外5命令＋CAS本体。登録entryを2個に限定しても、この待ち時間の上限は決まらない。
2. ownerの7回の `s3_native_poll` 呼出しは7回のINDEX観測ではない。settling早期returnとsettlement/acceptの両方がINDEXを読まない。実native Cを呼ぶ試験で通常pollは1read、settlingの2経路は0readを確認した。
3. したがって、平均CPU占有率やwatchdogの平均呼出し頻度が収まるだけではSの通常観測間隔50 µsを保証できない。期限条件には、watchdog resetを実行する1回そのものの費用と、INDEXを読まない経路の合成が必要。

これは実際に無限待ちが起こる証拠でも、受信案が不可能という証明でもない。現在得られている上限では性能合格にできないという判定である。

## 通常INDEX読取り経路の7つの間隔

隣接するpollが両方とも通常のINDEX読取り経路を通る場合、次の各項に「前pollのINDEX後の処理＋次pollのINDEX前の処理＋呼出し間制御」を加える。各elapsed上限にはIRQ・メモリ待ち・他core競合を含める。

| poll位置間 | 間に実行する処理 | 上限へ含めるもの |
|---|---|---|
| 1→2 | worker0 slice | 呼出し全体、2clock、DONE公開まで。configのslice_boundだけを転用しない |
| 2→3 | clock＋collect | 全bank確認・連続完了分の回収 |
| 3→4 | port0 reap | 完了/未完了の長い方とSDK critical section |
| 4→5 | port0 submit | 空/送信開始の長い方、descriptor/queue処理 |
| 5→6 | port1 reap | port0と同じ種類の費用 |
| 6→7 | port1 submit | port0と同じ種類の費用 |
| 7→次反復1 | feed判定＋loop | due時のSDK reset全体を含む。2.5秒平均に薄めない |

通常間隔の予算はT 30000 cycles=125 µs、S 12000 cycles=50 µs（240MHz、既存native LATE=2000 sampleの条件）。準備処理の追加時間は既存位相仮定の下でT35370 cycles、S26148 cyclesという別条件になる。数値だけを満たせば全受信が成立する意味ではない。

`gap-limits.json`は全未測定項をnullとして保存し、0には置き換えない。`experiments/s3_task_gap_limits.py --bounds file.json`へ各項の整数cycle上限を与えて再計算できる。上限が予算を超える場合は「その上限では証明できない」と判定し、実際の実行時間超過や候補全体の不可能性には一般化しない。宣言した数値が全て収まっても、実測/導出の裏付けや全体response-time検証は別なので採用フラグはfalseのまま。

## settling経路の別計上

通常の7間隔表には、INDEXを読まないsettling経路をそのまま当てはめられない。SELECT切替時のINDEX観測→settling待ち→境界探索/accept→次の通常INDEX読取りまでの空白と、次bank準備開始を別に追う必要がある。

境界探索は線形に7168wordを走査する処理ではなく二分探索。`first` のguard=3072は最大12回、`end` のguard=4096も最大12回の探索反復で、各反復1word read。入口の確認3readを加えた通常settlementの構造上限は27word read。最初のbankだけend guard=1024なので25word read。別途bank callback2回、healthy、clock3回、acceptと制御費用がある。このread数をcyclesへ換算はしていない。準備時のsentinel書込み3072+4096=7168wordとは別処理である。

## 生成ELFの待ち経路監査

`ci/s3_task_wait_audit.py`は分岐先から再decodeし、整列paddingを命令と誤読しない既存CFG読取りを使用する。wait-audit.jsonの10checkが成功。reachable.json/txtにreset、critical entry、task feedの到達命令を保存した。固定SDKコンパイラの配布SHAはe3e6dcf3d275c3c9ab0e4c8a9d93fd10e7efc035d435460576c9d95b4140c676。

reset本体はFlash、critical entryはIRAM。有限化に必要なのは、同じlockの所有側critical区間、Flash/PSRAM待ち、上位IRQ干渉、CAS費用と取得競合の条件。IRAMに呼出元を置いたという事実だけでは満たさない。

## 検証と残る判定

7 unittest成功（tests.log）：未知項の扱い、単発reset費用、境界値、予算超過と不可能性の区別、既存位相式、実nativeのINDEX読取り経路。CPU実時間は測定していない。

次に閉じる対象は通常/準備/settlingの各経路のelapsed上限、それらを使う2coreのbank到着・完了・reclaim、4送信arenaとSPI完了順序の応答時間。全startup heap、RF設定/指令系統、全FPGA fit/STAも残る。時間見積もりを具体化した結果であり、手順1の性能合格や手順2の正式割当を完了した報告ではない。

再現:
```sh
python -m ci.s3_task_wait_audit --profile reports/s3-raw-tasks/sdk-launcher/n16r8-late-stacks-no-phy-nvs-raw-only-spi --toolchain build/rs-toolchain/xtensa-esp-elf --output build/task-wait
python -m experiments.s3_task_gap_limits --output build/task-gaps.json
PYTHONPATH=tests python -m unittest test_s3_task_gap_limits test_s3_raw_schedule_limits test_s3_native_clock -v
```
