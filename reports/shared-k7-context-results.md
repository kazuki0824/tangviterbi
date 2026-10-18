# ② T/S K7共有：4 contextの実装と配置配線

2026-10-18。[K7の意味と共有範囲](k7-explained.md)を先に説明する。K7は拘束長7の畳み込み符号を復号するViterbi回路。ここで扱うのはT最大3階層＋S BPSK/QPSKの4状態であり、S TC8PSK回路は別に残す。

**4 context共有回路を実装し、154.285714 MHz条件で単体配置配線を通過した。** 最終版は使用不能な周辺LUT/FFを含めて**5695 logic・2681 FF位置・4 BSRAM・0 DSP**。RAM16SDP4は224/648個、実FFセルは1337個。配置配線後Fmaxは156.764374 MHz。162 MHz目標では不合格なので、その条件を通ったとはしない。

全体の混合置換予算は**20472/20736 logic（98.727%、264残り）、13189/15552 FF位置（84.806%）、46/46 BSRAM、34/48 DSP**。前回21160から688減るが、これは未実装allocationを含む予算差であり、完成受信機同士の実測削減ではない。3,000 logic/13 BSRAMの統合予約も保持する。追加FIFO等をこの予約に置換し、超えた差分は264位置の余白を消費する。

**今回の前進は、4 contextの機能と、予算に収まる部分回路の速度を確認したこと。正式採用は0。** 共通core clockを下げる条件のPLL・全stage・最悪queueは未確認で、残演算時間は1.848%しかない。入力FIFO/仲裁/idle serviceを含めた次の判定を通す必要がある。

## 実装したものと外部への要求

32 ACSを共有し、1 slotを2クロックとして4 contextを選ぶ。metric・survivor・traceback途中状態・出力bankと読書き位置をcontextごとに分離する。T/SのRF取得は同時のままで、bitstreamの切替を使わない。8-bit soft値・zero-weight erasure・13-bit modulo metricの意味と、256行のsurvivor全情報を維持する。

- `slot_valid && slot_ready`で`slot_context`を2クロック固定する。そのslotの最初に`in_valid && in_ready`ならsoft pairを受理する。第2クロックで外部context/softを変更しても、進行中のslotへ混入しない。
- reset後は各contextへ入力なしslotを1つ与え、metricを初期化する。初期状態不明の受信では既存版同様、最初の64 decoded bitsを取得開始時の収束区間として破棄する。
- 入力が止まったcontextにも、tracebackと出力を進めるidle slotが必要。slotを与えなければそのcontextは進まない。今回、実受信の入力FIFO・仲裁・期限保証を実装済みとはしていない。
- `out_valid/out_bit/out_context`は停止不能の出力で、次段は有効bitを受け取る必要がある。出力backpressure、depuncture位相管理、T/S mode/epochの個別変更、共有RSとの接続は外部の統合課題。global resetによる処理途中の破棄は試験したが、独立したcontextだけの再選局は未実装。

survivorのBRAM出力は全体で1組にし、前の読出しcontextタグと保存値へのbypassを設けた。これによりcontextごとの同期RAM出力を直接記述したときのBRAM割当失敗を解消した。metricの保存先、アドレス幅、出力方式を変更して比較し、失敗した構成も保存した。最終版は異なるphaseで読むmetricを同じRAMの別アドレスへまとめ、32..63側のうち16状態の書込みを次のglobal clockへ送る。pending値とcontextタグを保持し、次のslotやidle時に確実に書き戻す。slot自体は2クロックのまま。各RAMの書込み/読出し順と次contextへの影響をoracle試験で照合した。

## 比較結果と資源集計の訂正

| 実装条件 | logic位置（RAM制限込み） | FF位置（RAM制限込み） | RAM16 / BSRAM | 目標 / Fmax MHz | 全体予算 / 単体速度 |
|---|---:|---:|---:|---:|---|
| localshift-162 | 6648 | 2856 | 288 / 4 | 162.000000 / 224.265518 | 超過 / 通過 |
| metricram-162 | 7193 | 2856 | 288 / 4 | 162.000000 / 152.718384 | 超過 / 未達 |
| narrow-162 | 7212 | 2856 | 288 / 4 | 162.000000 / 142.308243 | 超過 / 未達 |
| paired-162 | 5702 | 2681 | 224 / 4 | 162.000000 / 151.377533 | 内 / 未達 |
| shift-162 | 7149 | 2856 | 288 / 4 | 162.000000 / 207.856995 | 超過 / 通過 |
| slotaddr-154 | 5695 | 2681 | 224 / 4 | 154.285714 / 156.764374 | 内 / 通過 |
| slotaddr-162 | 5695 | 2681 | 224 / 4 | 162.000000 / 156.764374 | 内 / 未達 |
| tagged-fixed-162 | 9850 | 4648 | 32 / 4 | 162.000000 / 88.487747 | 超過 / 未達 |

全測定は20K、seed 1、162 MHz目標、同一のテスト用端子。PLL・実I/O delay・基板負荷・他receiver回路は未接続。RTL機能試験と配置配線は別の検証であり、この表は完成受信機の合格ではない。

**途中報告の訂正**：localshift版を最終JSONのLUT4＋ALUだけで数えると5496になったが、分散RAMにより使用不能になる周辺LUTを含んでいなかった。nextpnr `e2fe86b3`は`postRoute`でblockerセルを削除し、`slice_valid`ではRAMの周辺4 LUT/6 FFを他用途へ使えなくする。今回のGW2A-18Cでは、容量需要を以下で集計する。

- logic位置＝最終LUT4＋最終ALU＋4×RAM16SDP4。
- FF位置＝最終DFF＋6×RAM16SDP4。実FFセル数と配置上使えない位置を区別する。
- RAM16SDP4自体の個数・648個という上限も別に保持する。完成受信機の他stageでの使用個数・配置競合は未確定。

したがってlocalshift版は**6648 logic・2856 FF位置**。全体置換は21425 logic、689超過であり、途中の「20273、463残り」は撤回する。後の構成も同じ補正式で検算する。[根拠URLとsource hash](shared-k7-evidence/resource-accounting.json)、生の最終JSON、合成/P&Rログを保存した。旧FFT・旧T kernelの採用測定はRAM16SDP4＝0なので、この訂正を根拠に過去の全予算へ一律加算しない。

## 期限と、通過していないもの

T25.212121＋S50.505＝75.717121 Mstep/s、2 clocks/stepなので、演算だけの需要は151.434242 MHz。162 MHzの93.477927%を占め、残り10.565758 Mclock/sをidle service・入力停止等に使う。実到着burst・idle slot・contextの公平性を加えた最悪期限の保証は未完。配置配線後Fmaxが高くてもこの待ち時間予算が増えたとは扱わない。

4 contextのT/S演算を任意順で動かす回路は完成したが、T/Sの全受信処理をつなぐschedulerではない。資源だけが予算内になっても、実FIFO/cache/SDRAM仲裁、T全Mode/GI、S全変調/TMCC、共有RS、全clock STA、SoC各コアWCET、配線、RF品質とTS連続性のゲートは残る。したがって性能合格・正式通信割当・受信機採用は0を維持する。

## 154.286 MHzを共通演算clockにする比較

162 MHzは今回の設計目標で、ユーザー指定値ではない。FPGAの処理精度・受信sample rateを維持したまま、共通演算clockを27×40/7＝154.285714 MHzにする別条件も測る。K7だけのために3個目のPLLを要求せず、FFT/RS等も同じcore clockへ変更し、SDRAM側135 MHzと合わせ2 PLLという構成仮説にする。**既存162 MHzでのschedule/CDCをそのまま流用して合格にはしない。**

- K7演算占有98.151824%、余り2.851472 Mclock/s（1.848176%）。idle service・入力burst・FIFOの保証はまだ必要。
- FFT有効区間の演算占有68.477366%。既存RTLの連続入力試験だけで実cacheの待ちを保証しない。
- 共有RSはwrapper込み2672 clocks/CWを維持。平均需要136.487918 MHz、占有88.464391%、1 CWのserviceは17.318519 µs。非preemptive待ちと実到着・短縮RSは別の未達。

[Gowin UG286EのrPLL式・静的係数](https://cdn.gowinsemi.com.cn/UG286E.pdf)に対応する候補はIDIV_SEL=6、FBDIV_SEL=39、ODIV_SEL=4、PFD=3.857143 MHz、VCO=617.142857 MHz。[生成設定と検算](shared-k7-evidence/clock-alternative/)を保存。使用した`gowin_pll`のGW2AR表には`untested`注記があり、device名の解釈警告も出た。これはパラメータ候補であり、PLLを含めた配置配線、生成clock制約、lock/reset、実基板での確認が済んだ証拠ではない。

このclock変更でバス帯域のbyte/s需要が減るわけではない。実FIFO/cache/SDRAMの全client traceを新しいcore周期で再生し、最悪期限を満たさなければこのclock案を不採用とする。低clockにして部分回路が通ったことと、全分担が成立することを分離する。

## SoC/FPGA境界と通信

今回の変更はFPGA内部。SoC→FPGAはT40 MB/s・S100 MB/sのnative I10/Q10、FPGA→SoCは指令のみ。SのTC8PSK、共有RS、TS×2を削除していない。追加softwareデシメート・再量子化は行わない。旧448 variant/84組、18 profile/555集合と全経路台帳を維持し、新しいR＋H＋Kのjoint budgetを別に追加する。共有K7をT単体stageの費用へ無条件に入れ、S側を重複計上する更新はしない。

代表経路の帯域差は、T Octal80：70.327658−40.01＝30.317658 MB/s、S Octal80＋Quad80：103.723500−100.01＝3.713500 MB/s、逆方向指令UART：0.1−0.01＝0.09 MB/s。これは帯域必要条件で、性能合格に先立つ正式通信割当ではない。全経路参照先は[検算JSON](shared-k7-evidence/budgets.json)に保持する。

①はT/S別imageであり、今回の同時T/S共有の節約をそのまま使えない。説明・機能試験の共通成果は①PRにも置くが、9Kの配置配線通過を報告しない。

## 検証と再現

7個のRTL variantを各6 epoch×4 context×1024 step、計172032 stepで試験し、全64 metricとsurvivor選択を独立した無限精度oracleと照合した。任意soft/erasure、全5符号率の独立符号化列、未知の開始状態、contextのランダム交互処理と長い連続処理、idle slot、全体停止、第2クロックでの別context/入力の提示、途中resetを含む。slotを連続2クロックごとに受け付ける試験も含む。予算検算2件と合わせ**9 unittest methods**がローカルで通過。GitHub Actionsの結果とは別である。

8件の固定端子CAD測定（7 RTL variant、最終版は2 clock条件）と初期RAM割当失敗を保存した。RAM blockerの抜けを再発させない検算では、以前誤ったlocalshift全体予算が20273ではなく21425になることも固定している。

生成器の各optionから全測定RTLをbyte一致で再生成した。初期のBRAM割当失敗は`unmapped/dut.sv.gz`と合成logを保存。端子制約を書き忘れた途中runは回路性能の反例に数えず、固定端子で再測定した。

```sh
# OSS CAD Suite 2026-10-04 のbinをPATHに設定
python -m unittest discover -s tests -p test_shared_k7_context.py -v
python ci/shared_k7_evidence.py --output build/shared-k7-final --frequency 154.28571428571428 --metric-ram --narrow --shift-output --local-shift --paired-metrics --slot-address
python experiments/shared_k7_budget.py
```

CADは各証拠summaryのoptionで再現する。`rtl/shared_k7_context.sv`は最終比較対象の生成結果。外部memory・receiver統合topやfirmwareをこの回路へ自動的に差し替える変更はしていない。
