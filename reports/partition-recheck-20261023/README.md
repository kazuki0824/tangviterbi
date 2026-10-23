> 続行結果：[32 KiB案のcore別・RAM・bank寿命と既存通信形式](../s3-batch-bank-closure/README.md)。既存構成への設定変更だけでは不成立。以下の96.477%は2core合計模型であり、並列化・再配置・通信形式変更は未実装です。

# ②20K＋S3×2：HEAD検算と処理分担の再選定（2026-10-23 JST）

**成立確認済みとして採用できる分担は0件。次に具体化する分担は、S3-T/SともRF取得・可逆I10/Q10梱包を担当し、FPGAが全復調・T/S独立TS出力を担当する案です。** 通常SPIのAPI費用を減らす32 KiB転送案を新たに定量化しました。CPU高費用モデルのS側は96.477%に収まりますが、全FPGA性能・コア別WCET・内部RAM・実PHYの未確定部分を含むため、性能合格又は正式経路採用とはしません。

①は既存PR #8のまま変更しません。②の旧PR #9 HEAD `f23ffeb1ec652f42c7b164e68f5162e781828090` に本見積もりを積みます。default branch HEADは `9a5b5d28d2350a312bf0d73d264ac5af6fe83dd6` であり、両者を混同しません。

## 判定順序と結論

1. **処理性能・資源・期限**：全処理所有者を再計算。既存CPU模型で高費用条件まで通信前に収まる境界は両S3ともRFのみ。ただし全受信機の資源・期限は未確定、最新部分統合回路も最低周波数に未達。この段階の合格は0。
2. **実現可能な通信路の正式割当**：段階1の合格がないので0。要求された根拠を欠かさないため、全帯域候補・余裕と新しい転送単位の感度計算は補助表として保存する。
3. **非空の正式経路を持つ分担を採用**：0。帯域に入るという理由だけで採用を先取りしない。

これは「どんな回路でも不可能」「全候補を探索済み」という結論ではありません。今回の成果は既存算術の再現、証拠の照合、比較台帳と追加の設計仮説です。実現できそうな**検証対象**は提示できますが、指定の3段階を通過した**採用案**は現時点で提示できません。

## 1. 処理分担候補すべてと比較範囲

TはFIR→同期/GI→FFT→等化/demap→時間DI→Viterbi→RS→TSの8段、SはFIR→同期→内符号→frame DI→RS→TSの6段。各段のSoC/FPGA所有者を全列挙するとT256、S64、同時16,384組です。RFはSoCで取得する前提を維持します。

- [全16,384組](all-16384-pairs.csv.gz)：各組の方向適合、両CPU、部分段資源、判定。
- [全320所有者の詳細](all-ownerships.json.gz)：所有者、転送情報の型・方向・速度、各段資源占有率、必要MHz、CPU、欠落費用。
- [逆方向データを要しない全16境界](all-boundaries.md)：T9＋S7。
- [許可された全63組の部分資源](all-allowed-pairs.json.gz)／[全63組の通信集合](all-63-route-products.json)。

FPGAへ渡した後にSoCへデータを戻す所有者列は除外し、SoC prefix＋FPGA suffixだけを残します。16,321組が方向制約で除外されます。FFT入力、LLR、syndrome、誤り位置・値、TSを指令と呼んで逆送しません。

| 分担 | S3-T | S3-S | FPGA | 通信前CPU低/高 | 判断 |
|---|---|---|---|---|---|
| R | RF取得・可逆packing | RF取得・可逆packing | T/Sの全復調、TMCC、FEC、TS×2 | T31.953/38.620%、S76.758/93.424% | 優先する処理分担。ただし全体性能未達 |
| F | R＋同品質FIR | R | RからT FIRを移管 | T89.678/123.435%、SはRと同じ | 高費用模型でT超過。SIMD等による新実装まで否定しない |
| T同期以降をSoCへ | 連続prefix | 任意のS prefix | 残りsuffix | Tは最低でも低103.018% | 現kernel模型では余裕なし |
| S FIR以降をSoCへ | 任意のT prefix | 連続prefix | 残りsuffix | Sは最低でも低232.133% | 現kernel模型では余裕なし |

CPUの低/高はWCETの上下限ではなく費用感度模型です。未知のSIMDアルゴリズム・任意の内部stage切断・独自PHYを網羅した表ではありません。段グラフ内の所有者は全列挙しましたが、「全ての可能な実装」という無限集合には一般化しません。追加ソフトウェア間引き・有効bit削減は行いません。通常の同品質FIRの配置変更は別です。

## 2. リソース占有率・リアルタイム期限

[再計算されたK7実装別資源表](recomputed-k7-resource-variants.json)は、旧共有RS構成の全blockを再加算し、T/S K7を二度引かずに共有K7へ置換しています。最小の部分合格slotaddr案の混合予算はlogic20,472/20,736（98.727%）、FF13,189/15,552（84.806%）、BSRAM46/46、DSP34/48（70.833%）。**その後の統合結果や全受信機の実測占有率ではありません。** 残る段・統合予約を含む過去の見積もりであり、残264 logicを今の余白として使いません。

最新cursor-mask部分構成は保存netlistから再集計しました。

| 項目 | 検算結果 | 適用範囲 |
|---|---:|---|
| 物理位置 | 19,627/20,736＝94.652% | probeを含む部分構成。全受信機ではない |
| FF | 8,673/15,552＝55.768% | 同上 |
| BSRAM | 29/46＝63.043% | 部分構成 |
| DSP | MULT18×6＋probe ALU54D×21 | ALU54Dは42 MULT18相当。6/48だけを全DSP使用率としない |
| 配線後Fmax | 152.091263 MHz | 保存されたSTA。今回P&R再実行なし |
| K7最低周波数 | 152.626638 MHz | T25.212121＋S50.505 Mstep/s、2 clocks/step、127/128 service率 |
| K7占有率 | 100.352% | 上記Fmaxでは未達 |
| 設計目標 | 154.285714 MHz | 最長経路を0.093519 ns短縮する必要がある |
| T Mode1/2/3最短GI周期 | 259.875/519.750/1039.500 µs | 最短周期だけで全mode/階層を検証済みとはしない |
| 共有RS平均必要周波数 | 136.487918 MHz | 2672 cycles/CW、T/S/TMCC到着率の加算。有限queue保証ではない |
| 時間DI有限試験 | 2,566,080−2,562,998＝3,082 clocks余裕 | 設計clock・試験負荷条件のみ。現Fmaxでの実時間合格ではない |

T時間DIの5,690,880 Bは8 MiB SDRAMの67.841%。他のFFT/保持領域・実アクセス競合は別に必要です。全体資源、全clock/外部IO STA、全到着位相・停止/選局/再同期・最大3階層の保持/期限は未確定です。

### 新しい比較案：R分担のままSPI転送を大きくする

既存RのS側Octal＋Quadは高CPU106.804%、Octal＋eMMCは106.620%。今回の仮説は**両portを同じ大きさの非同期DMA transactionにする**ものです。既存の3page Octal SCT＋1page Quad firmwareの実績とは区別します。処理分担・I/Q精度は不変です。

式：B bytesごとに、Octal時間=B/80＋1＋20 µs、Quad時間=B/40＋1＋20 µs。1 µsは80-bit headerをsingle lane 80MHzで送る保守仮定、20 µs/APIは未測定の感度条件。Sの要求100.01 MB/sには上り設定指令0.01 MB/sを含めます。S高CPUは `448.4375 + 100.01×240×20/B` Mcycles/s。両portの負荷を有効容量比例で分けます。

| B/port | S上り帯域余裕 MB/s | S高CPU | S二重送信buffer（2port） | 判断 |
|---|---:|---:|---:|---|
| 4 KiB | −10.086 | 117.841% | 16 KiB | 両portとも1pageの比較条件では不足 |
| 12 KiB | 7.809 | 101.563% | 48 KiB | CPU不足 |
| 16 KiB | 10.599 | 99.529% | 64 KiB | 平均算術では通るが未計上CPU余裕0.471%のみ |
| 32 KiB | 15.089 | 96.477% | 128 KiB | 次に検証する通信実装候補。正式採用ではない |

32 KiBではT側OctalのみのCPU高模型39.841%、T二重buffer64 KiB。S側はAPI active時間が平均43.089 µsを超えると、他の未計上処理をゼロとしてもCPU合計予算を超えます。**2コア合計の余裕で、packing偏在やbank返却期限が合格するとは言えません。** DMA中のbusy polling時間を無料にするモデルでもなく、非同期APIと独立進行を前提とします。

[全数値・port別負荷・batch到着間隔・service時間](batching-hypotheses.json)。Sの128 KiBは送信bufferだけで、capture、PHY、RTOS、stack、DMA descriptor等を含む完全な内部RAM予算は未確定。SPI burstの順序復元と吸収bufferをFPGAへ無料追加しません。PSRAMがあることだけで内部DMA SRAMの不足を埋めたとは扱いません。

[Espressif SPI master v5.5.1](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/spi_master.html)の非同期キュー、DMA buffer制約と転送長設定を参照しました。これらは32 KiBで20 µs/API、80 MHz基板通信や無欠落受信を保証する資料ではありません。既存adapterは3page制限があり、変更・実測が必要です。

## 3. SoC/FPGAが交換する情報

| 分担 | S3-T→FPGA | S3-S→FPGA | FPGA→各S3 |
|---|---|---|---|
| R、上記batch案、専用GPIO案 | native I10/Q10、可逆20bit、16 MSa/s＝40 MB/s | 同形式40 MSa/s＝100 MB/s | 選局・電源・開始停止・流量許可等の指令のみ |
| F | 同品質FIR後Q15複素、32.507937 MB/s | Rと同じ | 同上 |
| 他の全prefix | [全所有者台帳](all-ownerships.json.gz)のflowsに型・方向・速度を記載 | 同左 | 同上 |

上りにはepoch/順序/length等のframingが必要。TSはFPGAの独立外部端子2系統へ出力します。T/SのRFは独立で同時、②の資源はsumでありmax(T,S)にはしません。外部周波数変換・LNB電源・RF帯域/CN/MER/BER確認も残ります。40 MSa/sで必要なS品質を満たすことは設定値だけでは証明できません。

## 4. 上下転送経路すべてと帯域余裕

有限カタログの範囲：HEADの18周辺機器profile、controller/GDMA/SoC信号数を満たす555集合。それぞれにUART、I2C、各既存SPI/SDの半二重返送を掛け合わせ、両方向容量とFPGA34信号条件を検査します。

- [全カタログ](bandwidth-catalog.json.gz)：必要速度別に全port集合、各portの割当・残MB/s・残率、指令代替の再配分。
- [全63組の直積定義・件数](all-63-route-products.json)：`T.data_pins+T.command.extra_pins+S.data_pins+S.command.extra_pins+TS6 <= 34`。同じ通信台帳を参照することで候補ごとの経路を省略しない。
- [RのUART基準18組とCPU](raw-18-routes-with-CPU.json)。SはOctal＋QuadまたはOctal＋eMMC4 DDR40の2通り、T9通りとの直積。各組の余裕を全件記載。
- UART 1 Mbaud/8N1は0.1 MB/sから指令0.01を控除して0.09 MB/s余裕。I2C400kは設計0.04から0.01を控除して0.03 MB/s。SPI/SD半二重返送はそのportから0.01 MB/sを控除して上りを再配分する。指令の遅延・packet overhead保証は未完了。

専用GPIO方式を通常peripheralのカタログ外という理由で除外しません。[GPIO単独4組と指令代替](gpio-pairs.json)、[GPIO/通常peripheral混在993組](mixed-gpio-peripheral.json.gz)も列挙しました。GPIO JSONにはI/Qに対する余裕と上り設定0.01 MB/s控除後の余裕を併記し、混在表は控除後です。下表はI/Qに対する余裕です。GPIOの設定framing実装とCPU費用は未検証です。

| T/S GPIO lane数 | UART×2＋TSを含む信号数 | I/Q帯域余裕 T/S MB/s | 判断 |
|---|---:|---:|---|
| 1/1 | 26 | 61.800/1.800 | 本数・データ帯域条件のみ。S余裕小、single-lane bank所有変更未実装 |
| 1/2 | 34 | 61.800/103.601 | 同上。Sの順序復元・独立clock移植未達 |
| 2/1 | 34 | 163.601/1.800 | 同上。S余裕小 |
| 2/2 | 42 | 163.601/103.601 | 現34信号条件では除外 |

GPIOの基礎は91 cycles/40 bytes/core、追加3000 cycles/unitという未測定予算。全bank長・alignmentを走査した必要条件で、busy polling coreは100%占有。差分を復調の自由CPUとして流用しません。2laneの全raw spillはSで追加200 MB/sを要するため、外部RAM帯域も無料にはできません。GPIOとDMAを**同じSoC内で**併用する新設計、任意の新clock・custom PHYは、この有限カタログでは未評価です。

新32 KiB案も帯域上はT Octal＋S Octal/Quad＋UART×2＋TS6で34信号。ただし端子の電圧・搭載負荷・BL616競合・clock入力・独立clock同期・TSの追加SYNC要否が未検証です。数だけで物理配線を成立と認定しません。

## 静的完了条件確認・残作業・今回の境界

[検算結果](audit.json)に入力SHA256・全件判定を、[チェック全件](all-checks.json.gz)に個別結果を保存。途中のNGで後続検査を省略しない。全所有者・全組の被覆、旧CPU差分、全帯域catalog一致、負荷保存、全block加算、最新netlistの物理位置、保存source/hash、STA周波数と遅延の逆数を検査します。[既存unittest結果](tests.log)も保存します。チェックのOKは記録・算術の整合で、受信機の性能合格ではありません。

| ユーザー要求 | 今回の状態 |
|---|---|
| 1 全処理分担 | 宣言した8/6段の全16,384組を列挙。未知の全microarchitectureは未網羅 |
| 2 資源・期限 | 全候補の部分段資源/CPU/期限、共有資源の別見積もり、最新部分P&Rを検算。全体未計上費用・WCETは未確定のまま |
| 3 交換情報 | 全所有者flowsと境界表に記載。逆方向payloadを除外 |
| 4 全経路・余裕 | 宣言した全profile/指令代替の直積、GPIO・混在、batch仮説を記載。物理成立は未確認 |
| 性能→通信割当→採用 | 性能段階未通過のため正式割当0・採用0 |

未完了：全FPGA段と全体資源・精度・STA、時間DI descriptor/3buffer/cold-fill、全mode/階層/到着・動的期限、S3無欠落取得とcore別WCET・内部RAM、通信PHY、SDRAM外部IO、RF→TS同時実機試験。今回32 KiB案を追加したことで、それらを完了扱いにはしていません。

今回Aは、HEADの再計算・全候補台帳・追加batch仮説・採用可否を再現可能な形でPRへ保存した地点です。次のBは32 KiB非同期転送のcore別処理/内部RAM/FPGA保持まで含む具体化と実装、又は現FPGAタイミング経路の変更と再P&Rです。Bは今回の見積もり値を保証へ変える追加実装検証であり、今回のPRは見積もりのレビュー単位として提出します。時間上限や環境障害で止めたのではなく、採用案の提示という目的は未達であることを明記します。探索終了の判断ではありません。

## 再現

```sh
python experiments/control_only_estimate.py --board 20k --output reports/partition-recheck-20261023
python experiments/partition_recheck_20261023.py
python -m unittest discover -s tests -p test_control_only_estimate.py -v
```
