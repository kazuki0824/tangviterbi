# ① Tang Nano 9K×1＋S3×1：T/S切替、逆方向は指令のみ

**結論：条件に合う比較対象は抽出できたが、性能余裕を確認した採用案はまだ出せていない。** 過去HEADの低費用CPUモデルから残る分担は、A「RF取得だけSoC、全復調FPGA」とB「Tだけ通常FIRをSoCへ移す」。Sは両案ともRF取得だけSoC。全体FPGA資源と同時WCETが未確定なので、指定された①性能→②通信→③採用では①未通過、正式割当0、採用0とする。9K構成全体の不可能性を証明した結果ではない。

基準HEADは `9a5b5d28d2350a312bf0d73d264ac5af6fe83dd6`。共通の[検算方法・全通信profile・一次資料](../control-only-method.md)と合わせて読む。本PRは見積もりの記録であり、受信機RTL完成や実機動作の報告ではない。

## 1. 処理分担候補すべて

Tの8段256通り、Sの6段64通りを[全所有者台帳](all-ownerships.json.gz)に保存した。304通りはFPGA→SoCの受信データ返送を要するので除外。許されるT9通り、S7通りは[全境界表](all-boundaries.md)、その63組すべての資源集計と判定は[全組合せ台帳](all-allowed-pairs.json.gz)。CPUが足りない行も省略していない。

| 比較対象 | T時のSoC | T時のFPGA | S時のSoC / FPGA | 位置付け |
|---|---|---|---|---|
| A：RFだけSoC | native16 MSa/s IQ取得、可逆梱包、指令実行、転送 | FIR/resample、同期/GI、FFT、等化、全interleave、Viterbi、RS、TMCC、TS | native40 MSa/s IQ取得・可逆転送 / FIR・同期・TC8PSK/BPSK/QPSK・frame処理・RS・TMCC・TS | CPU側に復調を追加しない比較基準。全体FPGA未成立 |
| B：Tの通常FIRをSoC | A＋同じ品質の通常FIR/resample | AからFIR/resampleを除く | Aと同じ | 低CPUモデルだけ残る予備案。高費用モデルはCPU超過 |
| T FIR＋同期以降をSoC | 全境界表の残り7通り | 各suffix | 各S候補と組合せ | 通信前でも低CPU103.018%以上。選択kernel模型では除外 |
| S FIR以降をSoC | 各T候補と組合せ | 各suffix | 全境界表の残り6通り | 通信前でも低CPU232.133%以上。選択kernel模型では除外 |

旧T FFT offload、S RSのBM/Omega/Forney offloadは今回使えない。FFT入力・syndrome・rootsを返す必要があり、指令ではないためである。FIRを通信都合で短くしたり、bitを落としたりしてBを救済しない。

## 2. 占有率とリアルタイム期限

以下は**未完成の旧stage予算の再加算**。物理メモリ、通信、CDC、arbiter、TMCC、全S変調、T階層contextを含む完成回路の占有率ではない。見積もりを満たす新回路が存在するとは認定していない。

| mode/分担 | logic /8640 | FF /6480 | BSRAM /26 | DSP18 /20 | CPU低/高・通信前 |
|---|---:|---:|---:|---:|---:|
| A・T | 7405（85.706%） | 5086（78.488%） | 24（92.308%） | 18（90%） | 31.953 /38.620% |
| B・T | 6653（77.002%） | 3550（54.784%） | 22（84.615%） | 10（50%） | 89.678 /123.435% |
| A/B・S | 6421（74.317%） | 4190（64.660%） | 14（53.846%） | 15（75%） | 76.758 /93.424% |

S旧台帳のselected-stage欄15 BSRAMと、元mode-profileの各stageを加算した14は一致しない。本表は後者の計算対象を明示し、全体の残り12 blockが自由だとは主張しない。corrected RS、保持buffer、別変調経路を入れた実装値を優先する。

T/Sは別imageなので資源は加算せず、同じ資源の最大値で容量を検査する。例えばAの旧stage envelopeは7405 logic、5086 FF、24 BSRAM、18 DSP。これはT image自体に余裕がほとんどなく、S imageの全機能も未計上という状態である。S3-N8R8はPSRAM8 MiB、**N16はPSRAMなし**。RF転送案は高速内部SRAMを使い、N8R8のPSRAMを計算/転送能力へ加算しない。

| 現存する実装証拠 | 資源と速度 | 今回の判断 |
|---|---|---|
| T直接受信＋正しいtraceback＋compact RSの部分top | 7311/8640 logic、16/26 BSRAM、101.48 MHz | 残り1329 logicにFIR/同期/FFT/等化/時間interleave/メモリPHY等が全て入る証拠なし |
| S直接受信＋TC8PSK＋全compact RS部分top | seed1 7515 logic、18 BSRAM、93.1532 MHz | 2667 cycles/CWには94.790172 MHz必要。**サービス率不足**。他seedも改善しない |
| 旧9K `mem-32acs-rsconst` | 105.41 MHz | 旧復号が独立no-noise試験で不合格。正常受信機の性能証拠に転用しない |
| PR7 unshared SDF FFT | 50 DSP18 | 9Kの20を超過。20Kでも48を超過した同じ実装。FFT方式全体の不可能性には一般化しない |

出典：[直接受信の部分実装](../s3-ordered-evaluation.md)、[PR7保存記録](../pr7-fft-archive/README.md)。部分topの資源を別topと足して完成配置値と呼ばない。

Tは2048/4096/8192点を259.875/519.750/1039.500 µsごとに処理する。T K7需要50.424242 MHz、Sの3-cycle metric需要86.58 MHz、S QPSK K7の保守需要101.01 MHz。RSはT64.730769 µs/CW、S28.135828 µs/CW。100 MHzでS QPSKの2-cycle K7を単純に実行する予算は足りない。S TC8PSKだけに対象を黙って狭めない。

FPGA PSRAMのT時間interleaveは5,690,880 B/8 MiB=67.841%。FFT/queue/係数は別。99 MHz・256 B burstの既存pin-modelのread/write合計299.929 MB/sを、散在interleaveの保証帯域にはしない。S3の3 bank方式は12,288 sampleごとT768 µs/S307.2 µsでserviceし、overshoot2000 sampleならpoll遅延上限T125 µs/S50 µs。core別実装と最悪割込みを含めた合格は未確認。

## 3. 境界情報と4. 全通信経路・余裕

↑はSoC→FPGA、↓はFPGA→SoC。

| 候補/mode | ↑受信データ | ↓ | 外部出力 |
|---|---|---|---|
| A・T | native IQ10可逆packed、40 MB/s | 選局/電源/開始停止等の指令のみ | FPGA serial TS、最大23.234700 Mbit/s |
| B・T | 同品質FIR後complex Q15、32.507937 MB/s | 同上 | 同上 |
| A/B・S | native IQ10可逆packed、100 MB/s | 同上 | FPGA serial TS、最大約52.17 Mbit/s |

全18 profileの説明・計算式は[共通方法](../control-only-method.md)。[通信台帳](bandwidth-catalog.json.gz)に、各速度で帯域に入る全subset、port別割当、残MB/s・残率、上下の経路を記録。[T/S raw固定配線の全19,203組](raw-route-pairs.csv.gz)も添付した。これは本数条件までの補助カタログであり、正式割当ではない。

| 代表的な帯域witness（↓UART別線） | ↑実効容量 | ↑必要量（設定指令0.01含む） | ↑残量/残率 |
|---|---:|---:|---:|
| A・T SPI2 Octal80 | 70.327658 MB/s | 40.01 | 30.317658、43.109% |
| B・T SPI2/3 Quad80 | 33.395842 | 32.517937 | 0.877905、2.629% |
| B・T SPI2 Octal80 | 70.327658 | 32.517937 | 37.809721、53.762% |
| A/B・S SPI2 Octal80＋SPI3 Quad80 | 103.723500 | 100.01 | 3.713500、3.580% |
| A/B・S SPI2 Octal80＋eMMC4 DDR40 | 102.018180 | 100.01 | 2.008180、1.968% |

SをOctal/Quadに等負荷率配分するAPI感度では、旧RF高費用条件を加えるとCPU超過になる。0.01 MB/s返送も同じSPIに載せる場合は別行のhalf-duplex再配分を使い、上表よりさらに0.01 MB/s分の容量を控除する。↑↓をそれぞれ満速で計算しない。

専用GPIOはT1 lane、S2 laneでそれぞれ設計能力101.800/203.601 MB/s、payloadに対する余裕61.800/103.601 MB/s。ただしSの順序保持が最大unit40,760 B→20 BSRAM相当を要し得る。全rawを外部PSRAMへspillするなら200 MB/s追加。基板の2 PLLで240 MHz samplerとPSRAM/復調clockを閉じることも未確認。**転送だけの大きな余裕を、受信機全体の余裕に読み替えない。**

SPI/LCD/eMMC/I2S、専用GPIO、低速指令経路、USB/Wi-Fi等の除外理由を全て共通方法へ記載した。信号劣化を伴うsoftware削減で通信候補を増やしていない。

## 外付NORによる切替条件

- 保存場所は**Tang Nano基板上の外付SPI NOR4 MiBのみ**。S3 Flash、FPGA内蔵Flash、ホストからの都度全bitstream転送を代替方式として採用しない。
- HEADの `s3_nor_images.py` のT/S/recovery各512 KiB slot案を照合。予約量1.5 MiB/4 MiB=37.5%。実受信imageのサイズ・CRCは未取得なので収容済みとはしない。
- 背景で外付NORを更新できることと、動作SRAMを無停止で切り替えられることは別。切替時はRF停止→DMA排出→TS無効化→外付NORから全再構成→epoch初期化→選局/lock→TS再開。
- MSPI strap、基板Flash配線へのアクセス、1.8 VのRECONFIG_Nに適切な電圧で接続する条件を確認する必要がある。完成基板の無改造で実行可能と未確認のまま書かない。
- 参考下限は512 KiB×8/24 MHz=174.763 ms/image。これは設計clockでの読み出し時間だけで、実image長、初期化、必要な再起動hop、RF relock、Flash erase/writeを含まない。切替所要時間の保証にはしない。T→S→recovery→Tの固定jump案ならS→Tは2 hopを要し、要求先任意jumpが無料で可能とはしない。

## 実施した静的完了条件確認と未達

| 確認した場所・方法 | 結果 |
|---|---|
| `all-ownerships` の全320件を走査、逆向きpayloadの有無とprefix列を独立比較 | OK：T9/S7、残り304件を除外。fail-fastなし |
| 旧CPU式を全320件で再現、FFT reorder二重計上を足し戻して比較 | OK：最大差約1.82e-12。訂正後もT FFT前段込みCPU超過 |
| stage資源を元profileから再加算、①はmaxで63組を集計 | OK：計算一致。**NG/未確定：完成回路の余裕** |
| 18 profileの全subsetを検査、controller/GDMA/方向/帯域保存則を検査 | OK：全555集合を走査。GPIO/電気STAは未確認 |
| S compact RSの必要clockと保存済みP&R値を比較 | NG：94.790172 MHz必要に対して93.1532 MHz |
| 外付NORのslot合計と動作制約を照合 | 容量計算OK。実image、strap、RECONFIG、復帰動作は未確認 |

**未達は「性能余裕内の採用案を提示すること」と「全候補の完成回路資源/WCETを確定すること」。** PR化は計算・除外根拠・未達をレビュー可能な形に固定する境界である。次の境界である成立確認まで進むには、9Kの全復調top、FIR/FFT/全変調FEC/階層context、メモリ・通信・切替を実装し直した上で測定する必要がある。これは今回の見積もり作成を超える受信機実装作業で、ここで完了したとは扱わない。実装可能な作業まで「実機がないため」とは分類しない。見積もりの記録を提出する品質は満たすが、採用決定の品質は満たさない。

再現コマンドと10件の検査内容は[共通方法](../control-only-method.md#再現と検査範囲)。計算結果は[summary.json](summary.json)。
