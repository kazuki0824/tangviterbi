# FPGA内の距離精度候補とRS応答検査

2026-10-10。Tang Nano 9K＋ESP32-S3-WROOM-1U-N16R8、T/S実行時切替。
この作業で受信機全体が成立したとは判定しない。`receiver_adopted=false`、`safe_to_flash=false`。

## 変更の範囲

RS部分移管の分担は[従来の見積もり](s3-rs-offload.md)を維持する。
FPGAはQ15距離、TC8PSK、RS syndrome/Chien/byte訂正、S3はBM/Omega/Forneyを担当する。
FPGA側へS3応答ページの検査を追加した。RPC全体の実装完了ではない。

native RFのI10/Q10、lossless packing、FPGAへの100 MB/s転送、Q15 symbol入力は変更しない。
新候補の丸めは**FPGA内の枝距離だけ**に適用する。転送帯域を収めるための
SoC追加デシメート・再量子化は一切追加していない。
枝距離を変更するため、旧SHIFT22と同じ復号性能とは扱わない。

## 演算上限と独立照合

Q15入力の全域に対し、投影差の幾何学的上限を求め、同じ丸めoffsetでの差を
`ceil(projection_difference / 2**SHIFT)`で抑える。171/133の7-symbol impulseが
作る枝ラベル差`3,1,0,3,3,2,3`について加算した上限を使う。
この上限がmodulusの半分より小さい幅を選ぶ。
これはその量子化器に対する正確なmodulo比較であり、量子化器同士の等価性証明ではない。

| FPGA COST_SHIFT | 枝距離最大値の上限 | 枝距離幅 | 合流する候補距離の差の上限 | 経路距離幅 | 半modulus |
|---:|---:|---:|---:|---:|---:|
| 22（従来） | 362 | 9 bit | 1964 | 12 bit | 2048 |
| 23 | 181 | 8 bit | 984 | 11 bit | 1024 |
| 24 | 91 | 7 bit | 492 | 10 bit | 512 |
| 25 | 45 | 6 bit | 248 | 9 bit | 256 |

- 各量子化器4145入力点、合計16580点で、独立した8点constellation計算と一致。
  Q15端点、全象限、ランダム入力、出力停止を含む。
- 新3候補は各3 epoch×2048 symbol×64状態＝393216状態を無限精度整数ACSと照合。
  合計1179648状態が一致し、同じ枝距離を受ける13-bit参照RTLとも毎clock一致。
- 入力停止、dirty reset、metric周回を含む。全Q15入力列をsimulationで網羅したという意味ではない。

再現：`experiments/s3_tc8psk_precision.py`、`tests/test_s3_tc8psk_precision.py`。

## 同じ雑音入力での復号比較

独立171/133 encoder、未知初期状態37、各条件16384 symbol。
4種類のRTLへ同じQ15入力を与え、先頭128 symbolを除き、各条件32384情報bitを照合した。
各条件1 seedで、trellisによる誤り相関がある。統計的同等性や規定C/N閾値は主張しない。
Es/N0は量子化前のsymbolエネルギーとAWGNから設定し、その後Q15へclampしている。

| 振幅（Q15 full scale比） | 設定Es/N0 | clampしたsymbol数 | SHIFT22誤りbit | SHIFT23 | SHIFT24 | SHIFT25 |
|---:|---:|---:|---:|---:|---:|---:|
| 0.65 | 無雑音 | 0 | 0 | 0 | 0 | 0 |
| 0.25 | 6 dB | 0 | 1887 | 1848 | 2041 | 2223 |
| 0.25 | 10 dB | 0 | 0 | 0 | 0 | 0 |
| 0.25 | 14 dB | 0 | 0 | 0 | 0 | 0 |
| 0.65 | 6 dB | 690 | 1996 | 2165 | 2013 | 2034 |
| 0.65 | 10 dB | 62 | 0 | 0 | 0 | 0 |
| 0.65 | 14 dB | 1 | 0 | 0 | 0 | 0 |

SHIFT24は振幅0.25/6 dBで従来より154 bit多く誤る。高いSNRでこの有限試験の誤りが
0でも、従来精度の代替として無条件採用できない。RF取得、同期、AGC、TMCC、RS、TSはこの試験に含まない。
再現：`ci/s3_precision_ber.py`。入力・出力・RTLのSHA256とB0/B1別誤りをJSONへ保存する。

## FPGAのRS応答検査

`rtl/s3_rs_rpc_guard.sv`は、S3から返る固定4096 Bのlambda（kind 2）とmagnitude（kind 4）を検査する。

| 検査・動作 | 実装した内容 |
|---|---|
| header | magic/version/kind、期待epoch/batch、204 records |
| CRC | ISO-HDLC、初期値/最終XORはFFFFFFFF、CRC欄12..15 byteを0として4096 B全体を保護 |
| 順序・形式 | 0..203のID、status、degree≤8、lambda定数項1、次数外0、最高次係数非0 |
| failed record | lambda/magnitudeを0とする。kind 4のreserved byteも0 |
| 長さ・pad | 4096 Bちょうど、unused tailは0。途中lastと末尾last欠落を拒否 |
| 停止 | 無受信gapのwatchdog、結果を受け取るまで保持、resetでdirty stateを消去 |
| 公開 | 最終結果が成功するまで外部staging pageをcommitしてはならない契約 |

95 page / 372868 byteの検査に合格。実C生成の正常・upstream失敗応答12 pageと
再確認1 pageだけを受け入れ、CRC破損、CRCを再計算した不正内容、長さ異常を拒否した。
result保持、timeout、dirty resetも検査した。registered payload-region版は、
同じ全試験で元の回路とready/valid/errorが毎clock一致した。
さらにheader/paddingの2の冪境界を明示的bit比較へ置き換え、mapperが生成した
不要な減算carry chainを避ける版も追加した。こちらも同じ全試験で毎clock一致した。

この回路はpayloadを保存しない。external staging、batchの所有権、root countに応じた
未使用magnitudeの追加検査、Chien/訂正との接続、epoch停止は未統合である。
失敗をackして次のcfgを受けられることは、受信機が同じepochで継続してよいという意味ではない。

90 MHzで1 byte/clock、4096 Bに45.511 µs（入力停止・前後handshakeを除く）。
既定gap上限16384 clock＝182.044 µsは設計値で、全体schedulerの保証値ではない。
RPCが2 portで同時到着する場合の合計wire peakは1台のchecker能力を超え得る。
PSRAM staging又は到着順序制御と、その遅延・帯域・creditを統合して検証する必要がある。

さらに、検査を27 MHzへ分離する候補として、90 MHzのstaging readerから
128×9 bit（data8＋last）の非同期FIFOを介するwrapperを実装した。
14 page / 54250 byte、writer停止65677 clock、CRC/identity/長さ異常、timeout、
両domainのdirty resetを検査し合格。正常pageの最大所要時間は151.892838 µsだった。
これはbackpressure可能な内部reader用であり、Octal80 MHzの無停止SPIを直接受ける回路ではない。
cfg/resultは27 MHz側に置き、90 MHz schedulerとのdescriptor/resultのCDCと所有権は未実装。
全page stagingもこの128-word FIFOで代用しない。
この27 MHz案では既定16384-clock gap上限は606.815 µsとなる。clockを変えたまま
90 MHz版の182.044 µsというwatchdog時間を流用しない。

27 MHzの理想処理量27 MB/sに対し、受信側RPC 2 page/batchの平均1.42725 MB/sは5.2861%。
2 pageの試験所要時間合計303.785676 µsは5.739709 ms/batchの5.293%。
この余裕を全アクセスのworst-case待ち時間へ変換するには、PSRAM仲裁とbatch schedulerの結合が必要。

## 合成・配置配線

固定OSS CAD suite 2026-10-04、GW1NR-LV9QN88PC6/I5、narrow LUT、core90/SPI2・3各80 MHz。
部分topはRF格納PSRAM経路、距離/TC8PSK、syndrome/Chien/訂正、必要に応じてRPC検査を同時配置する。
各workloadは独立入力で動き、RF→TSの結合回路ではない。
位置占有は配置後の**LUT4＋ALU**。配置前下限やLUT4単独とは区別する。

| SHIFT／構成 | 検査clock MHz | 最終配置の位置数・率 | FF | BSRAM | core Fmax（seed順）MHz | 判定 |
|---|---:|---:|---:|---:|---|---|
| 22／追加前 | — | 7958 / 92.11% | 3438 | 10 | 88.55 / 82.82 / 91.45 | 部分top合格 |
| 23／検査なし | — | 7656 / 88.61% | 3354 | 10 | 87.83 / 81.57 / 79.33 | 90 MHz不合格 |
| 24／検査なし | — | 7534 / 87.20% | 3270 | 10 | 85.47 / 93.98 | 部分top合格 |
| 25／検査なし | — | 7255 / 83.97% | 3186 | 10 | 78.79 / 87.02 / 85.66 | 90 MHz不合格 |
| 22／元の検査 | 90 | 未配置（下限8446） | — | — | 合法配置未発見 | 未証明 |
| 24／元の検査 | 90 | 8099 / 93.74% | 3442 | 10 | 77.60 / 71.78 / 76.48 | 90 MHz不合格 |
| 24／payload flag | 90 | 8078 / 93.50% | 3443 | 10 | 83.37 / 71.82 / 82.83 | 90 MHz不合格 |
| 24／bit比較追加 | 90 | 8076 / 93.47% | 3443 | 10 | 72.77 / 73.36 / 71.80 | 90 MHz不合格 |
| 24／FIFO分離 | 27 | 8226 / 95.21% | 3580 | 11 | 93.21 | 部分top合格 |
| 22／FIFO分離 | 27 | 未配置（下限8593） | — | — | timeout | 未証明 |

合格したSHIFT24/FIFO分離版は5980 LUT4＋2246 ALU＝8226位置（95.21%、残414）、
3580/6480 FF（55.25%）、11/26 BSRAM（42.31%）、2/20 MULT18、1/2 PLL、3 BUFG。
core93.2140、SPI2 252.9724、SPI3 204.2484、検査75.0356 MHzで、90/80/80/27 MHz制約に合格した。
残414位置は全復調器等を収める余裕の証明ではない。SHIFT22の元の検査版は180秒timeout後に
480秒上限で再試行して合法配置未発見。SHIFT22/FIFO版は180秒timeoutで、下限8593位置。
いずれも理論上不可能と断定しない。

同じseed集合1/2/3を設定し、最初の合格又は非timingの配置失敗で探索を終了する。失敗seedも保存する。
time limitは合法配置なしの証明ではない。実IO timing、CDC skew、PSRAM sampling eyeは未証明。
新しい実装を足すたびに、過去の単体又は部分topのFmaxを完成回路へ転用しない。

## 通信路と実時間予算への影響

枝距離はFPGA内部情報なので、今回の精度変更でSoC↔FPGAの情報種類・速度は減らない。
CPU BM/Omega/Forney案は、syndrome19 B、lambda13 B、roots12 B、magnitude12 Bを
各204 records＋header/padで4×4096 B/batchとする。
Octal80 SPI2とQuad80 SPI3への16通りの上下割当、RF込み帯域余裕
0.215515〜0.868999 MB/sは[既存列挙JSON](s3-rs-offload-budget.json)の条件付き値を維持する。
今回のguardはSPI polling等の追加取引を実装していないため、追加control通信を無料とは扱わない。

連続28.86 MSymbol/sの保守的期限は28.135828 µs/codeword、204 codeword/batchで5.739709 ms。
240 MHzの1 coreなら6752.598753 cycles/codeword。CRC/API/ISR等もこの中に収める必要がある。
CPU WCET、RPCの全stage所有権、coded-block PSRAM保存/訂正、TS出力は未証明であり、
bandwidthモデルだけで採用することはできない。

coreを90 MHzで動かす場合、距離回路は3 clock/symbolなので30 MSymbol/s、
28.86 MSymbol/s入力による稼働率96.2%、容量側余裕3.8%である。
配置後Fmaxが90 MHzより高くても、この固定PLL構成の処理速度をそのFmaxへ置き換えない。
各部品の既存単体試験でのsyndrome1640 clock、Chien224 clock、訂正268 clockは
それぞれ18.222/2.489/2.978 µs。全体待ち時間・memory競合・RPC往復を含む期限証明ではない。

## この環境でなお進める実装

| 未完了 | 今回進めた部分 | 次に必要な完成物 |
|---|---|---|
| FPGA RPC | S3応答のCRC/形式/epoch/batch検査、比較・timeout試験、90→27 MHz data FIFO | staging commit、descriptor/result CDC、syndrome/roots送信page生成、credit、5 batch所有権、Chien/訂正・PSRAM・TSとの結合 |
| 面積・実時間 | 3精度候補の理論上限・RTL照合・雑音比較・部分配置 | 精度を含む受信性能条件、全復調/通信を含む配置・STA、追加分の予算再計算 |
| S3実firmware | 以前の実SDK link、IRAM配置、DMA alignmentを保持 | RF/SPI/SCT/RS/FFT worker、2 core barrier、全runtime allocation、停止・再初期化 |
| T/S復調 | 既存の距離/FEC/メモリ部品を保持 | 同期/AGC/TMCC/deinterleave/descramble/TSを含む独立既知TSとの照合 |
| 実装設計・切替 | 既存pin案と外付けNORのみの切替制約を保持 | RF前段BOM/回路、IO校正/制約、T/S/recovery image、NOR driver・再構成/復旧 |

これらを実機待ちへ分類しない。今回で環境内の全作業が完了したわけではない。

## この環境だけでは実行できない確認

| 未確認 | 必要なもの | 合格条件 |
|---|---|---|
| S3 native16/40 MSps、PHY直接初期化 | N16R8実機、RF入力、diagnostic trace | 連続取得、正しいROM予約、bank欠落/上書きなし |
| RS/packing/FFT/ISRのWCET | RF・SPI・DMAを同時実行するS3 | 各期限と全core予算内、内部SRAM確保成功 |
| Octal/Quad80 MHzとPSRAM | 接続基板、計測器、温度/負荷試験 | bit誤りなし、refresh/read/write競合時も期限内 |
| RF前段と実受信C/N | 設計後のRF回路、T/S信号源、TS analyzer | 特性、規格波形への同期、既知TS一致、長時間無欠落 |
| NOR切替と復旧 | strap/1.8 V RECONFIG回路を含む実基板 | T/S切替、破損image・電源断からの復旧 |
| 電源・clock・温度 | 完成基板と測定器 | 同時動作時も電圧/jitter/温度条件内 |

GitHub Actionsのrunner未割当・step開始前失敗は別の外部サービス阻害である。
ローカル合成・simulationは実行済みだが、Actionsでの合成成功へ読み替えない。

## 再現・証拠

```sh
python -m unittest discover -s tests -p test_s3_tc8psk_precision.py -v
python -m unittest discover -s tests -p test_s3_rs_rpc_guard.py -v
python -m unittest discover -s tests -p test_s3_rs_rpc_guard_cdc.py -v
python ci/s3_precision_ber.py
python ci/s3_psram_benchmark.py --rs-correction --syndrome-ready --rr-table --core-mhz 90 --cost-shift 24
python ci/s3_psram_benchmark.py --rpc-payload-flag --syndrome-ready --rr-table --core-mhz 90 --cost-shift 24
python ci/s3_psram_benchmark.py --rpc-bit-ranges --syndrome-ready --rr-table --core-mhz 90 --cost-shift 24
python ci/s3_psram_benchmark.py --rpc-clock27 --syndrome-ready --rr-table --core-mhz 90 --cost-shift 24
python ci/s3_precision_evidence.py
```

[source hash・失敗seed・全数値](s3-precision-evidence/results.json)。PRはdraftのまま、merge/flashは行わない。
