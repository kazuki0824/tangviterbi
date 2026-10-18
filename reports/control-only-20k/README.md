## 2026-10-18：軌道修正後の実測比較（最新）

[T Viterbi縮小・全候補再計算・S RSの訂正](../folded-t-recovery.md)を追加した。②を先行し、Tの全5符号率に対応する16並列・6 clocks/step・1 BSRAM版を実装。部分P&Rは3431 logic、1833 FF、194.250 MHzで162 MHz目標通過。同条件の旧32並列＋erasure版から303 logic・1 BSRAMを削減した。旧T予算2952の過小見積もりも補正し、R＋Hは**21160/20736 logic、13843 FF、45/46 BSRAM、34 DSP**へ更新。全体の424位置超過と統合費用は残る。

各測定条件ごとに旧448行・84組を再計算し、通信情報・CPU・全経路カタログを保存した。正式通信割当・採用は0。S側RSは「93.153 MHzでは有限FIFO付きでも不可」という一般化を訂正し、理想main＋TMCC到着の772位相条件では有限待ちになることを確認。ただし実deinterleave/DMA/停止を含む期限保証は未完。

15 CAD条件、12件のローカルunittest（subtestを含む）、RTL再生成・全行検査の証拠を[保存](../folded-t-evidence/)。受信機全体の配置配線、実メモリ、階層context、S3 WCET、物理配線・実機RF/TSは合格していない。**以下の共有FFT時点・初回検算の数値は履歴であり、現在の置換予算はこの更新を優先する。**

# ② Tang Nano 20K×1＋S3×2：T/S同時、逆方向は指令のみ

## 続行更新：共有FFTは162 MHz通過、全体予算は依然ほぼ無余裕

[共有FFTの実装・全候補再計算・検証結果](../shared-sdf-followup.md)を追加した。全Modeを連続処理するhybrid FFTは2,729 logic・1,502 FF・10 BSRAM・4 DSP、配置配線後222.568 MHzで162 MHz目標を通過。residentも単体目標を通るが18 BSRAMを使う。PHYと全受信機の合格ではない。

旧共有RS BのFFT予算を実測値へ置換すると、hybridは20,681 logic（99.73%）・13,512 FF・46/46 BSRAM・34 DSP、residentは54 BSRAMとなる。未実装のcache等を加えた余裕は未成立。全[19境界](../shared-sdf-evidence/updated-20k/boundaries.md)・[84組](../shared-sdf-evidence/updated-20k/allowed-pairs.json.gz)を更新し、情報型・転送速度は保持した。GPIOの順序逆転分は未測定の時間上限を条件にpacked1,600 Bまで絞ったが、入力平滑化・CRC保持等は別。32 unittest成功。採用0を維持する。

**以下は初回検算のスナップショット。最新の置換予算・今回の未達と区切りは上の続行報告を参照。**

**結論：最も残しやすい処理分担は「各S3はRF取得・可逆転送、FPGAでT/Sの全復調とTS出力」だが、性能余裕内の採用案は確定できていない。** 旧PR6のtile FFT案は全体未成立、旧PR7のunshared SDF実装はDSP超過。通信が通ることだけを理由に再採用しない。指定手順の①全体性能は未通過、②正式通信割当0、③採用0。

これは構成全体の実現不可能性を示すものではない。今回の結果は、比較対象・検算・改善が必要な箇所を保存した見積もりPRである。基準は `main@9a5b5d28d2350a312bf0d73d264ac5af6fe83dd6`。[共通方法・全通信profile・一次資料](../control-only-method.md)も参照する。

## 1. 全処理分担候補

[全所有者台帳](all-ownerships.json.gz)はT256＋S64件。[全境界表](all-boundaries.md)は逆方向payloadを要しないT9＋S7件。[全63組](all-allowed-pairs.json.gz)には両SoCのCPU、境界データ、同時FPGA資源の参照・集計を保存する。残る16,321組は少なくとも片側にFPGA→SoC受信データがあるため除外。

| 分担群 | S3-T | S3-S | FPGA | 判断 |
|---|---|---|---|---|
| R：両方RFのみ | native16 MSa/s、可逆IQ10転送 | native40 MSa/s、可逆IQ10転送 | T FIR/同期/FFT/等化/interleave/FEC/TMCC/TSと、S FIR/同期/TC8PSK・BPSK・QPSK/frame/FEC/TMCC/TS | 主な設計比較対象。全体資源/WCETは未確認 |
| F：T FIRだけ追加 | R＋通常の同品質FIR/resample | Rと同じ | RからT FIRを除く | 低CPUモデルだけ通る。高費用条件でSoC-T超過 |
| T FIR＋同期以降 | 全境界表の残り7通り | 全S候補 | 各suffix | 低CPUでも103.018%以上。選択kernel模型では除外 |
| S FIR以降 | 全T候補 | 全境界表の残り6通り | 各suffix | 低CPUでも232.133%以上。選択kernel模型では除外 |

TのFFTだけ、SのRS solverだけをSoCへ返す案は今回不許可。通信都合での追加software間引き・再量子化は使わない。通常復調FIRの処理位置を変えるFは、同一の周波数応答と演算精度を保つ条件付き。

S3-WROOM-1U-N8R8とN16R8はどちらもPSRAM8 MiBで、Flash容量差はDSP能力差にならない。各S3は独立周波数を同時に取得する。T/S image切替や `max(T,S)` による資源削減は②には使わない。

## 2. リソース占有率と期限

完成回路の資源は不明。以下は未完成の旧設計allocationを再加算した結果で、全体P&Rの値ではない。

| RのFPGA実装候補 | logic /20736 | FF /15552 | BSRAM /46 | DSP18 /48 | 検算後の扱い |
|---|---:|---:|---:|---:|---|
| A：tile FFT、T/S独立RS | 22252（107.311%） | 14186（91.217%） | 47（102.174%） | 38（79.167%） | この予算で容量超過 |
| B：tile FFT、T/S/TMCC共有RS | 20452（98.630%） | 13034（83.809%） | 44（95.652%） | 38（79.167%） | 計算上の空き284 logic/2 BSRAM。全体成立の証拠なし |
| C：内蔵RAM常駐FFT、共有RS | 18952（91.397%） | 13034（83.809%） | 56（121.739%） | 34（70.833%） | この予算でBSRAM超過 |
| 旧D：SoC FFT往復 | 18452（88.985%） | 12522（80.517%） | 40（86.957%） | 30（62.5%） | 今回は禁止方向。余裕があっても候補にしない |

[summary.json](summary.json)の `rechecks.archived_20k_allocations` は各blockを再加算して旧合計と一致したことを記録する。一致するのは算術であり、そのallocation以内で未実装blockを作れるという証拠ではない。

| 追加比較すべきmicroarchitecture | 定量的に言える範囲 | 未確定でゼロにしない費用 |
|---|---|---|
| H：乗算器を共有するhybrid/streaming FFT | N8192のdelayは32764 B、最大4096語を外部へ置くと内部16380 B＝最低8 BSRAM。外部delay read/write平均63.045695 MB/s | twiddle精度、DSP/LUT、各stageの時間多重、保持・reorder、gapless入力。PR7の50 DSP実装を流用しない |
| K：T/S K7 engine共有 | 処理需要だけで151.434242 MHz。162 MHzなら93.478%、180 MHzなら84.130% | T最大3階層とSのcontext、metric/survivor切替、depuncture、mode境界、追加FIFO、180 MHzのSTA。旧S K72952 logicを無条件に削除しない |
| F：T FIRをS3へ | 旧BからT FIRのstage予算752 logic/1536 FF/2 BSRAM/8 DSPを引くだけなら19700/11498/42/30 | 通信・schedule変更、FIRの実CPU、追加保持。SoC-T高模型123.435%で不合格 |

H/Kは**未見積もり部分が残る設計仮説**。新しい全体占有率を作ったことにはしない。次の比較を進めるならHを優先し、Kはcontext費用と期限が厳しい別比較とする。第一案を成立済みとして選んだのではない。

| 期限・需要 | 再計算 | 意味 |
|---|---:|---|
| T Mode1/2/3周期 | 259.875 /519.750 /1039.500 µs | 全Modeを評価。Mode3だけで通過にしない |
| tile FFT、2 clocks/butterfly＋4 clocks/交差twiddle | 30720 /65536 /139264 clocks | 162 MHzで189.630 /404.543 /859.654 µs、計算占有72.970 /77.834 /82.699% |
| T K7 | 50.424242 MHz | 32 ACSの2 clocks/step |
| S TC8PSK距離 | 86.58 MHz | 3 clocks/symbol |
| S QPSK K7 | 101.01 MHz | 保守最大7/8、2 clocks/step |
| 共有RS | 136.487918 MHz | 162 MHz目標で平均84.252%。有限queue/最悪phaseの証明ではない |
| T/S TS出力 | 23.234700 /52.17 Mbit/s | serial27/81 MHz目標ならpayload余裕3.765300 /28.83 Mbit/s |

S RSは28.135828 µs/CW、Tは64.730769 µs/CW。共有RSはnonpreemptiveなので平均処理率だけでは個々のdeadlineに合格しない。保存された共有RSの部分P&Rは162 MHz指定に対して157.431 MHz、終了失敗。DSP/RAMの一部timing arc不足も記録されており、全体162 MHzの根拠にできない。

S3のR・通信前CPU模型はT31.953～38.620%、S76.758～93.424%。API20 µsの費用を追加するとSの高条件は超過する。新しい専用GPIOの場合はpacking＋送信を一体化した別kernel模型で再評価し、旧packing費用を二重加算しない。ただしbusy pollingがcoreを占有するので、模型の空きは自由な復調時間ではない。

### 同時メモリ負荷を落とさない

旧tile案はFFT189.137085＋T LLR57.627706＋S frame14.501084＋その他10＝**271.265875 MB/s**。135 MHz×32 bit×65%＝351 MB/sという設計条件との差は79.734125 MB/s。過去のrow-conflict/refresh/位相の反例があるため65%を保証として使わない。

PR7のhybrid＋外部T保持案は平均202.802 MB/sという置換仮説だったが、別passのreorderを加えると265.848 MB/sになる。Sの専用GPIO二laneを全raw spill方式で追加すれば、**さらに200 MB/s**を要し、402.802/465.848 MB/sで351 MB/s設計容量を超える。S入力保持を無料にして「GPIOで解決」としない。順序逆転の最大量を制限する新schedule、必要なunitだけのspill、小unit化、メモリ配置変更のどれかを具体化して再計算する必要がある。40,760 Bの1 unitだけでも20 BSRAM相当で、旧Bの2 block空きに収まらない。

外部8 MiB SDRAMはT時間interleaveだけで5,690,880 B（67.841%）。FFT・S frame・I/O保持と同時に使う。容量と持続帯域と最大待ち時間は別の条件である。

## 3. SoC/FPGA間の情報

| 分担 | S3-T→FPGA | S3-S→FPGA | FPGA→各S3 | FPGA外部 |
|---|---|---|---|---|
| R、A/B/C/H/Kの各microarchitecture | native I10/Q10、40 MB/s | native I10/Q10、100 MB/s | 選局/電源/開始停止/流量許可等の指令だけ | T/S独立serial TS、各data/clock/valid |
| F | 同品質FIR後complex Q15、32.507937 MB/s | 同上 | 同上 | 同上 |

epoch、順序、lengthはSoC→FPGAのframingに含める。FPGA側の復調中間結果、decoder係数、TSを指令名義で返送しない。TS独立SYNC pinを必要とするsinkなら後述の信号数へ2本追加する。

## 4. 帯域に入る全通信候補

[帯域カタログ](bandwidth-catalog.json.gz)は、各境界速度について18 profileから全555有効subsetを検査した結果。各portの必要量、余裕、API感度、指令返送の全宣言済み代替を格納。[raw T/S同時配線の全18組](raw-route-pairs.csv.gz)も保存した。全63分担対のリンク集合は、各速度のカタログの直積と同時pin条件で定義し、CPU不合格をリンク合格で覆さない。

以下は指令返送を各S3へ1 Mbaud UART1本ずつ割り当てた基準。↑の設定指令0.01 MB/sも控除する。

| S側の全2通り | ↑容量 MB/s | ↑必要 MB/s | ↑余裕 MB/s |
|---|---:|---:|---:|
| S-P：SPI2 Octal80＋SPI3 Quad80 | 103.723500 | 100.01 | 3.713500 |
| S-E：SPI2 Octal80＋eMMC4 DDR40 | 102.018180 | 100.01 | 2.008180 |

| T側の全9通り | ↑必要 MB/s | ↑余裕 MB/s | 組み合わせられるS側 |
|---|---:|---:|---|
| SPI2 Octal80 | 40.01 | 30.317658 | S-P、S-E |
| SPI2 Quad80＋SPI3 Single80 | 40.01 | 2.898150 | S-P、S-E |
| SPI2 Quad80＋SPI3 Dual80 | 40.01 | 11.566046 | S-P、S-E |
| SPI3 Quad80＋SPI2 Single80 | 40.01 | 2.898150 | S-P、S-E |
| SPI3 Quad80＋SPI2 Dual80 | 40.01 | 11.566046 | S-P、S-E |
| SPI2 Single80＋eMMC4 DDR40 | 40.01 | 1.192831 | S-P、S-E |
| SPI2 Dual80＋eMMC4 DDR40 | 40.01 | 9.860726 | S-P、S-E |
| SPI3 Single80＋eMMC4 DDR40 | 40.01 | 1.192831 | S-P、S-E |
| SPI3 Dual80＋eMMC4 DDR40 | 40.01 | 9.860726 | S-P、S-E |

9×2の直積が上の18組全て。T10＋S16＋TS6＋指令2＝**34/34信号**。指令を既存SPI/SDへ載せる代替は各rowに保存し、そのportの容量0.01 MB/sを引いて↑を再割当する。UART分のpinを節約できる可能性があるが、polling/API/指令期限を確認していないため完成配線とはしない。

優先して測る通常peripheral経路はT Octal、S Octal＋Quad。理由はTの帯域余裕が最大で、未実装card emulationを増やさず既存SPI endpointを利用する方向だから。ただしSの3.58%余裕は小さく、CPU高条件も不合格。採用経路ではない。

専用GPIOではT1 lane9信号＋S2 lane17信号＋TS6＋指令2＝34。追加overhead予算後のpayload余裕はT61.800269 MB/s、S103.600539 MB/s。T2 lane＋S2 laneは42信号となり、このconnector条件で除外。S1 laneは98.232% service占有で余裕1.768%しかなく、RF/管理jitterを考慮した推奨経路にはしない。S80 MSa/sの2 laneも同じ1.768%で、メモリspill400 MB/sを含む再設計が必要。

20KのJ5/J6は合計34信号というHEADの回路図確認を使用。搭載LED/audio/SD/HDMI/BL616の負荷は残る。実GPIO割付、3.3 V、clock-capable入力、80/240 MHzのsetup/hold、BL616側Hi-Zを確認したとはしない。2 PLLと独立2個のS3参照の整合も未確定。配線数の一致は物理成立の証拠ではない。

## 静的完了条件確認・未達・今回の境界

| 確認箇所・方法 | 判定 |
|---|---|
| 全320所有者の方向と9/7 prefix、全63組の同時加算 | 算術・被覆OK。禁止方向を除外 |
| 保存された4案のblock別資源を再加算 | 旧合計と一致。A/Cは予算超過、Dは方向禁止、Bは全体未確認 |
| 2048/4096/8192の周期、FFT cycle、T/S/TMCC RS到着率 | 再計算OK。実STA/queue/WCETの合格は未確認 |
| 18 profile/555集合、raw18組のport別帯域・pin・GDMA | 必要条件計算OK。全物理経路の成立は未確認 |
| GPIO kernel/framing/全unit長・alignment、reorder保存費用 | 追加費用を計上。全raw spillでは上記SDRAM容量を超える組合せを指摘 |
| PR7資源・旧RS/Fmax証拠の採用可否 | 50 DSP実装は不採用。部分Fmaxを全体へ転用しない |

検査は全項目を走査しfail-fastにしていない。**依頼の「性能余裕内の分担を採用する」は未達**で、全体資源/WCETと物理通信路の成立が残る。この時点でPRを提出するのは、HEADの誤差・除外根拠・未確認事項を固定し、同じ第一案を無根拠に再採用しないための見積もりレビュー境界である。次の成立確認の境界までは、Hの実回路、全復調・FEC/TMCC/context、入力reorder、全メモリschedule、S3 firmwareを実装して測定する必要がある。これらの未実装を実機不足に置き換えてはいない。今回の記録はレビュー可能だが、完成見積もりや採用決定の品質には到達していない。

再現方法・10件の検査は[共通方法](../control-only-method.md#再現と検査範囲)。主要数値は[summary.json](summary.json)。
