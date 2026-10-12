# S3-N16R8＋Tang Nano 9K：指定順で進めた1〜6の検証

2026-10-12。T/Sは排他的、同じSoCファームウェアと固定配線、FPGAは基板外付けNORの別image。
追加のソフトウェアdecimation／requantizationは行わない。

**指定順に容量・部分実装・期限を評価したが、全体性能を通過した分担はまだ0件。**
通信の探索結果は残し、性能未確認の分担へ正式割当・採用は行わない。
未実装の受信段を実機確認待ちに置き換えてはいない。

| 順序 | 実施した作業 | 結果／次を成立させるための不足 |
|---|---|---|
| 1：旧6の前提＋旧5の物理条件 | N16R8、固定Octal/Quad配線、GDMA、NOR容量／strap／RECONFIG条件を再確認 | 配線witnessあり。stock完成基板そのままのMSPI切替は不可。外部IO STA、RF dumpのPHY互換性、実boot未確認 |
| 2：旧3の同時メモリ＋旧1/2の粗い予算 | SDK起動時空き上限、2 worker stack/TCB、native RF＋2 mode slot＋RSのtarget ABIを検算 | 追加2×2 KiB workerは容量不合格。main再利用＋1 workerもdriver前上限1,020 Bしかない |
| 3：旧1 CPU／旧2 FPGA、旧3更新 | 既存CPU費用を維持し、直接BSRAM受信回路を実装・vector照合。T/S partial topを合成・配置配線。T SIMD＋S RS同一SDK link条件追加 | T partialは90 MHzで通過。S split／all-RSの測定実装は期限不合格。SIMDとsolverのtarget WCET、全受信top、同時SDK unionの結果は別の未完了項目 |
| 4：旧4の各core／共有メモリ／buffer | 144個のcore配置・費用感度、RF poll期限、4 pageの保持上限を所有者台帳へ結合 | core移動を含む仮説と現在のcore0 serviceを区別。RPC/IRQ/実driver/同一frameのjoint期限未確認 |
| 5：旧5の正式通信割当 | 全320分担の境界情報・資源根拠・既存通信catalog参照を追跡し、performance-first gateを実装 | 全体performance未確定のため割当対象0。探索catalogの帯域余裕を採用数に読み替えない |
| 6：旧6の最終T/S固定構成 | 共通配線／slot union／NOR3 image／停止・drain・epoch・lockの契約を照合 | 実受信T/S image、SoC scheduler、driverとNOR切替の結合が未完了。最終構成の採用未確定 |

## 同時メモリ

元SDK証拠はHEAD `e8cc725` の `native-direct-phy-simd`。
RF/FFT workerのコードと予約はリンク済みだが、RS code unionと実worker起動は含まない。
起動時heap空き**上限**7,512 Bから4,096 B internal DMA poolを差し引くと3,416 B。
追加taskにはtarget StaticTask_t 340 B＋stack＋最低8 Bの2 allocation headerを計上する。
main taskのstackは既存SDK起動時検算に含まれる。

| 宣言したtask構成 | 追加容量下限 | driver前の空き上限 | 判定 |
|---|---:|---:|---|
| 新規2 task、各stack 2,048 B | 4,792 B | −1,376 B | この構成は容量不合格 |
| mainをRF側として再利用、新規1 task stack 2,048 B | 2,396 B | 1,020 B | 容量必要条件のみ。実driver・call-chain未計上 |
| 新規2 task、各stack 1,024 B | 2,744 B | 672 B | 小stackの安全性未確認。採用しない |

RS slot使用量はhost sizeofではなくS3 ABIの30,688／25,344 B。
各32,768 Bのslotに収まるが、T DMAがdrainする前のRS上書きは禁止。
これはT/S排他的な**data area**共用の条件であり、T/Sのcodeを別々にリンクしてよい条件ではない。
新しいCI profile `native-direct-phy-simd-rs` はSIMD workerとRS codeを同時に保持し、
実map／ELF／startup upper boundを採る。結果取得前は従来の3,416 Bを両搭載の空き容量と断定しない。

## FPGA：native IQをそのまま運ぶ別実装

`s3_spi_direct_bridge`はSPI2 Octal＋SPI3 Quadから4×4 KiB BSRAMへ直接受信する。
physical PSRAM controllerを使わず、既存page guard／epoch／ACK／順序制御を保持する。
最後のwordがconsumerに受理されるまでpageは解放しない。faultはepoch resetまでsticky。
これはRF用D711入口。FFT復路やRS RPCを含む受信機ではない。

独立した整数oracleでI10/Q10の5 B／2 sample packingを作り、40 page／65,536 sampleを
実SPI波形→CDC→BSRAM→IQ unpack後に全照合した。2 portの異なる完了順、sink stall、
D71B readの無視、誤epochのpoison、reset後のstale禁止も合格。
送信側の4 page creditはtestbenchの契約で、実S3 credit senderを実装済みとはしない。

以下はOSS CAD Suite2026-10-04、同じdevice/CST、narrow LUT、seed1（追加seedは記載）。
FECはsynthetic inputに接続した部分共配置で、RF→FEC→TSの全鎖ではない。

| 部分実装 | routed logic位置／8,640 | 占有率 | BSRAM／26 | MULT18／20 | routed core fmax | 設定clock／判定 |
|---|---:|---:|---:|---:|---:|---|
| T：直接受信＋Viterbi traceback＋compact RS | 7,311 | 84.62% | 16 | 0 | 101.48 MHz | 90 MHz、CAD通過 |
| S：直接受信＋TC8PSK＋syndrome/Chien/Forney | 6,993 | 80.94% | 16 | 2 | 63.06 MHz | 90 MHz、不合格 |
| S：直接受信＋TC8PSK＋全compact RS、seed1 | 7,515 | 86.98% | 18 | 2 | 93.15 MHz | 99 MHz、不合格 |
| 同seed2 | 7,508 | 86.90% | 18 | 2 | 85.76 MHz | 99 MHz、不合格 |
| 同seed3 | 7,523 | 87.07% | 18 | 2 | 84.59 MHz | 99 MHz、不合格 |

logic位置はrouted LUT4＋ALUで数える。packed blockerをALUと二重計上しない。
pack-onlyの楽観的FF共有下限はT7,266、S split6,974、S all-RS7,482で、routed値と別。
各result JSON、生成top、clock/CST、合成／P&R logを
[証拠directory](s3-direct-stream-evidence/)に保存した。失敗seedも保存する。

S RS rateは35,541.872 CW/s、deadline28.1358 µs。現compact RSの2,667 clocks/CWには
94.7902 MHz以上が必要で、seed1の93.1532 MHzでも足りない。
S splitはBM/Omega offload、全RSはSoC solver不要という異なるmicroarchitecture。
両者の未確認／失敗を全てのRS実装へ一般化しない。
FIR／同期／interleaver／T FFT return／受信鎖のretention・correction・TS接続／credit sender／外部IO STAが
欠けており、T partialの余白1,329位置も全受信機の自由資源ではない。

## CPU、各core、bufferの期限

旧200 cycles/pageと20 µs active/APIを混同しない。[前のAPI感度](s3-link-cpu-sensitivity.md)を保持。
平均費用は測定WCETではない。144 profileではpacking単独所有者をcore0へ固定し、
prepare／API／controlのcore配置を変える。現在のcapture serviceはcore0。
他coreへ費用を移した表の合格は、その移動を実装した証拠ではない。

Tは8192点500/513 µsの仮定と4/6/8 cycles/sample packing、SはFFTなしを比較した。
Sで6 cycles/sampleなら40 Msamples/s×6=240 Mcycles/sとなり、単独packing ownerだけで
core0を占有する。平均2 core空き容量へsolverを置く前に、この配置を変更する必要がある。
逆に4 cycles/sampleという仮定の合格は、実target packingがその速度という証拠ではない。

native bankは12,288 sampleでT768 µs／S307.2 µs。切替overshoot2,000 sampleの
poll遅延限界はT125 µs／S50 µs。tile内WCETに加え、service／IRQ／driver滞在時間を合わせて
この期限を守る必要がある。2 core FFT stage barrier中もserviceを呼ぶ契約は既存workerにある。

直接BSRAM readerの理想上限は90 MHzで4 B／3 clocks=120 MB/s。
S native100 MB/sを運べるという算術だけではstallを隠せない。
4 page=16,384 Bの容量を100 MB/sで割った163.84 µs（T409.6 µs）は、
完全空bufferから全容量を利用できる場合の理想的な無service時間上限。
page commit待ち・2 port予約・現在の占有量を含む実保証値ではない。
continuous sink／real credit／FEC backpressureを結ぶ前にjoint期限を通したとはしない。

T Mode1/2/3最短GI周期259.875／519.75／1,039.5 µsを全て追跡。
以前のraw＋FFT結果Octal固定／FFT入力Quad固定は、Mode1/2でOctal平均時間が
104.265%／100.417%となる。今回のBSRAM回路追加だけではその割当問題は解消しない。
SIMD workerも8192点固定なので、Mode1/2の実装が未済。

## 候補と通信路を追跡する成果物

[ordered result JSON.gz](s3-ordered-evaluation/results.json.gz)はT256＋S64の全320分担を保持する。
各行に所有者、全境界情報、旧CPU上下費用、stage resource根拠、whole-resource/WCETの未知、
通信catalog keyと探索件数、正式割当／採用状態を記録する。
RS subpartitionは元catalogを参照し、今回のwhole-stage列挙へ混ぜない。
CPU screenで通信未探索の行の件数は`null`であり、通信路0件と誤表示しない。

全探索通信路と各portの上下MB/s・半二重競合・pin/GDMA・spare MB/s／%／gap余裕は
[元の検算catalog](s3-partition-audit/estimate.json.gz)に保持する。
今回の正式割当は「performance=trueの分担にだけ通信路を割当て、非空なら採用」の
gateで別管理。性能未知のまま探索帯域に通るpathを採用しない。

最終固定構成はOctal/Quad共通配線、mode slot共用、NOR T/S/recovery各512 KiBを
4 MiB中に配置する条件まで。実imageなし。R17のMSPI strap変更とR18/pin9の1.8 V
RECONFIGアクセスが必要で、通常headerだけで切替完了とはしない。
Background Programmingはこの基板外付けNORだけに限定する。
既存`Switch`契約のstop→drain→reconfig→image identity→fresh epoch→tune/lock→RF/TS enableを
独立試験しているが、実S3制御とFPGA identity／NOR bootに結ぶ作業は残る。

ローカル検証：既存を含むS3 120 unittest（363.792 s）、追加ordered gate 3 unittestが合格。

再現：

```sh
PYTHONPATH=tests python -m unittest -v test_s3_ordered_evaluation test_s3_spi_direct_bridge
python experiments/s3_ordered_constraints.py --output reports/s3-ordered-evaluation/constraints.json
python ci/s3_direct_stream_evidence.py --mode T
python ci/s3_direct_stream_evidence.py --mode S
python ci/s3_direct_stream_evidence.py --mode S-all-RS
python ci/s3_direct_stream_evidence.py --mode S-all-RS --seed 2
python ci/s3_direct_stream_evidence.py --mode S-all-RS --seed 3
python experiments/s3_ordered_evaluation.py
```

**残る実装上の入口：** SIMDとRS同時SDK linkの結果を容量へ反映し、main再利用も含む
実task構成／stack／driver live allocationを閉じる。次にRF/packing/API/FFT/solverのtarget費用と
実core配置を対応させ、FIR等の全鎖と保持／TSを接続する。そこまでの性能条件が通ってから
全mode・全messageの通信割当と最終T/S切替を確定する。
`complete_estimate=false`／`performance_stage_completed=false`／`receiver_adopted=false`。
