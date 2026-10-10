# S3/9K：RSの部分移管と90 MHz部分配置

2026-10-10。対象はTang Nano 9K＋ESP32-S3-WROOM-1U-N16R8、T/S実行時切替。
**受信機の採用は0件。`receiver_adopted=false`、`safe_to_flash=false`を維持する。**
追記：下記第4節のobject/配置検査に続き、実ESP-IDF linkとROM/起動メモリの必要条件監査も実施した。
追加後の実SDK結果は第4節末尾を優先し、object検査だけの古い到達点と区別する。
今回の進展は、実PSRAM受信経路とSの距離/TC8PSK/RS部分処理を一緒に配置し、
内部90 MHzとSPI各80 MHz制約に合格したこと。この時点のtopは全復調器・RPCのFPGA側・TS出力を含まない。

後続の[FPGA距離精度・RS応答検査](s3-fpga-precision-and-rpc.md)で、応答page検査と
90→27 MHzのdata FIFOを追加実装した。全RPCは未統合であり、追加後の面積・Fmaxは
後続レポートで判定する。下表の追加前topの値をそのまま転用しない。

## 1. 期限の検算と訂正

従来の52.17 Mbit/s÷188 Bから得た28.8288 µs/codewordは**TS平均**の値であり、
全区間のRS到着期限と同一視しない。
[ITU-R BO.1408-1 §5](https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-1-200204-I!!PDF-E.pdf)
では同期byteを伝送から省略してRS処理前に復元する方式がある。
[ITU掲載ISDB-S説明資料](https://www.itu.int/ITU-D/tech/OLD_TND_WEBSITE/digital-broadcasting_OLD/kiev/Presentations/saito/ITU%20Seminar%20ISDB-S%20001109.pdf)
の28.86 MSymbol/s・TC8PSK 2情報bit/symbolを用い、203伝送byte、TMCC/burstの空き時間を一切差し引かない上限を採る。

これは規格に書かれた厳密な瞬間到着波形ではなく、今回の保守的なサービス予算である。

| 項目 | 再計算 |
|---|---:|
| RS到着率の上限 | 28.86e6×2÷(203×8)＝35,541.871921 codeword/s |
| 1符号語のサービス予算 | 28.135828 µs |
| 専用CPU 1 core、240 MHzを全部使う場合 | 6,752.598753 cycles/codeword |
| 204符号語/batch | 5,739.708940 µs/batch |
| 旧compact RS 2667 cyclesに必要なclock | 94.790172 MHz |

CPU予算にはBM/Omega/Forney、CRC、page検査/作成、context管理と割込み競合も収める必要がある。
旧83.86 MHz FECは平均期限でも不合格であり、この訂正によって採用へ変わらない。
新90 MHz案は旧FPGA RS decoderを外すので、その94.79 MHz条件を適用しない。

## 2. 分担を列挙し、通信路で絞る

RFのnative I10/Q10は全量100 MB/sを転送する。追加のSoCデシメート・再量子化は行わない。
下表のCPUはRSについての分担。RF取込み/packing/SPI管理のCPU負荷は別途同時に存在する。
FPGAには別に同期、距離計算、TC8PSK、interleave、TS出力が必要で、未完のものがある。

| RS分担候補 | FPGAに残るRS処理 | FPGA→S3 | S3→FPGA | CPU期限の証明 | 帯域を満たす割当数 | 判定 |
|---|---|---|---|---|---:|---|
| CPUで全RS | coded block保存/TS取扱い | 受信204 B＋識別子等 | TS188 B＋識別子等 | 未証明 | 0/4 | 通信帯域で除外 |
| CPUでBM/Chien/Forney | syndrome、訂正適用 | 16 syndrome＋識別子等 | 最大8位置/値＋識別子等 | 未証明 | 4/4 | 実装研究候補、採用保留 |
| CPUでBM/Omega | syndrome、Chien、Forney、訂正適用 | 16 syndrome＋識別子等 | λ9 B、Ω16 B等 | 未証明 | 4/4 | FPGA Forney分割未実装、採用保留 |
| CPUでBM/Omega/Forney | syndrome、Chien、訂正適用 | syndrome、後段で最大8位置 | λ9 B、後段で最大8値 | 未証明 | 16/16 | 今回の実装対象、採用保留 |

性能未証明のものを通信帯域だけで採用しない。ユーザー指定の「性能→通信路→採用」に従い、
現時点の通信計算は条件付きスクリーニングであり、採用候補の確定ではない。

### この通信構成内で取りうる割当を全列挙

対象は既実装endpointの **O＝SPI2 Octal/80 MHz、Q＝SPI3 Quad/80 MHz**。
他の物理IFを含めた全探索とは主張しない。各portは半二重で、RPC送受信の占有時間を
RF転送の可能時間から引く。4 KiB page、16 B RPC header、別途80-bit SPI wire header。
API 20 µs、Octal SCT gap 0.25 µsを仮定する。20 µsは実機WCET未確認。
RF用Octalは3頁batch、RPC Octalは複数頁をまとめ、Quadは1頁ごとにAPIを計上する。
ready/credit通知を追加のSPI pollingなしで与える契約は未実装。
SPI polling/ack transactionを追加する設計では、その占有時間をさらに引いて再計算する。

| 候補 | 各stageのrecord長 | 204 recordでの頁数 | RPCのpadding込みMB/s |
|---|---|---|---:|
| 全RS | 208 / 192 B | 11 / 10 | 14.986126 |
| BM/Chien/Forney | 19 / 20 B | 1 / 1 | 1.427250 |
| BM/Omega | 19 / 29 B | 1 / 2 | 2.140875 |
| BM/Omega/Forney | 19 / 13 / 12 / 12 B | 1 / 1 / 1 / 1 | 2.854500 |

以下はwire/API占有も差し引いた**RF100 MB/sに対する残り余裕**。
上下の通信stage順は上表の順で、全RS/BM-Chien-Forney/BM-Omegaは↓↑、
BM-Omega-Forneyは↓↑↓↑（↓はFPGA→S3）。

| port割当 | 全RS MB/s | BM/Chien/Forney MB/s | BM/Omega MB/s |
|---|---:|---:|---:|
| OO | −10.037344 | +1.969507 | +1.337568 |
| OQ | −10.609142 | +2.132878 | +1.419253 |
| QO | −10.690828 | +2.132878 | +1.500939 |
| QQ | −11.262626 | +2.296250 | +1.582624 |

| BM/Omega/Forney port割当 | RF余裕MB/s | port割当 | RF余裕MB/s |
|---|---:|---|---:|
| OOOO | 0.215515 | QOOO | 0.378886 |
| OOOQ | 0.378886 | QOOQ | 0.542257 |
| OOQO | 0.378886 | QOQO | 0.542257 |
| OOQQ | 0.542257 | QOQQ | 0.705628 |
| OQOO | 0.378886 | QQOO | 0.542257 |
| OQOQ | 0.542257 | QQOQ | 0.705628 |
| OQQO | 0.542257 | QQQO | 0.705628 |
| OQQQ | 0.705628 | QQQQ | 0.868999 |

条件を満たす全24割当を100 batchのイベントモデルで検査し、RF ring予約最大40,960 B≤65,536 B。
各cycleのstageは**異なるbatch**で、CPU/Chienの完了を所定release時刻までに要求するpipelineモデル。
CPUをゼロ時間とした同一batchの直列往復ではない。実RF bankのburst、全PSRAM負荷、
CPU/ISRを結合したモデルでもない。API 40 µsの反例ではoverflowし、採用不可となる。
[全割当・式・event結果](s3-rs-offload-budget.json)、`experiments/s3_rs_offload_budget.py`に保存。

## 3. FPGA部分実装・資源・期限

新RS分割部品は、syndromeを8 clocks/byte、Chienを1位置/clockで処理する。
既存TC8PSKはcompact出力/B1、Q15契約下12-bit metric、32 ACSを使用。
距離回路は正確な3-clock共有であり、SoC側の追加再量子化はない。
PSRAM仲裁はround-robinの順序を変えず、動的剰余/加算を5個の定数priorityへ展開した。
160組のrequest/start位置を独立な巡回順序と比較して一致。

| 同時配置top | P&R結果 | ロジック位置 | 備考 |
|---|---|---:|---|
| 旧PSRAM＋全compact FEC | 合法配置未発見 | 必要下限8616/8640 | 配置余白24とは扱わない |
| RS分割、元の仲裁、99 MHz | seed1/2不合格、85.49/90.83 MHz | seed2 7631 | 99 MHz動作不可 |
| RS分割、定数仲裁、99 MHz | seed1/2/3不合格、92.41/89.57/91.73 MHz | seed3 7583 | 失敗を保存 |
| RS分割、定数仲裁、90 MHz PLL | seed1合格、core92.4129、SPI107.2156/150.9662 MHz | 5269 LUT4＋2324 ALU＝7593/8640＝87.88% | 3265 FF、10/26 BSRAM、2/20 MULT18X18、1/2 PLL |
| 上記へbyte訂正を追加 | seed1/2/3不合格、72.74/71.68/82.34 MHz | seed3 7954 | 追加前のFmaxを使わない |
| byte訂正＋syndrome末尾flagをregister化 | seed1/2は88.55/82.82 MHzで不合格、seed3でcore91.4495、SPI143.7814/131.3888 MHz合格 | 5598 LUT4＋2360 ALU＝7958/8640＝92.11% | 残り682位置。FPGA RPC等は未実装 |
| byte訂正＋22 ACS（3 clocks）、2-port登録版 | seed1/2/3全て不合格、77.15/70.81/75.48 MHz | seed3 5752＋1940＝7692 | 面積は266位置減るがSの速度不足、32 ACSを保持 |
| byte訂正＋4-port syndrome | seed1/2/3全て不合格、88.64/84.50/89.15 MHz | seed3 5602＋2356＝7958 | 12 BSRAM。採用せず2-port登録版を保持 |

このtopは実PSRAM受信経路と独立な合成負荷を同時配置したもの。
syndromeを仮のlocatorへ配線しており、正しいCPU RPCが存在するようには扱わない。
訂正追加前の未使用位置1047は、訂正＋末尾flag版で682へ減る。
FPGA RPC、符号語管理、完全復調、TS出力等をさらに収める必要がある。
外部IO/phase/CDCの全STAは未完で、上記内部FmaxはPSRAM信号品質の証明ではない。

| 90 MHz時の処理 | 供給能力・試験値 | 必要条件/残る限界 |
|---|---|---|
| 距離計算 | 30 MSymbol/s | 28.86に対して+3.95% |
| 32 ACS TC8PSK | 45 MSymbol/sのACS受入れ | 距離側が律速、全同期・interleave未接続 |
| syndrome | 11.25 MB/s、262独立符号語合格、stalls込み最大1640 cycles | 204×35541.871921＝7.250542 MB/s、1block28.135828 µs予算 |
| Chien | 264ケース、stalls込み最大224 cycles | 90 MHzで2.4889 µs。204符号語batchの連続処理は別途scheduler必要 |
| byte訂正 | 263 block/53652 B、stalls込み最大268 cycles | 90 MHz換算2.9778 µs。コード語buffer/TSの統合ではない |
| SPI→実DDR端子モデル→reader | 96頁393216 B一致、3.410734 ms（115.2878 MB/s） | このテストpatternで100 MB/s超。interleave等の追加メモリ負荷を含まない |

実PLLを90 MHz（27 MHz入力、IDIV2/FBDIV9/ODIV8、VCO720 MHz）に変更してP&Rした。
99 MHzのFmaxを読み替えただけではない。DDRモデルのcore/CKも90 MHz・90°で再検査した。
byte訂正回路は、全rootを検査してから204 Bを受け、末尾byteの受領完了まで次の設定を受けない。
4種の不正root設定、16回の途中reset、出力stallを試験済み。PSRAMへの訂正writeはまだ未実装。
末尾flag登録版は元のsyndrome回路と262 blockの全cycleでready/valid/結果が一致。
失敗seedを隠さず保存し、3番目のseedでの内部90 MHz合格として扱う。
さらに4-ROM並列版も実装し、262独立符号語で16 syndromeが一致、最大826 cyclesまで短縮した。
ただし全3 seedで90 MHzに届かず、BSRAMも2個増えるため今回の採用対象にしない。

## 4. S3実装と占有

`experiments/s3_rs_offload.c`のBM/Omega/Chien/Forneyは、独立符号化262パターンで
parityを含む204 B、全204の単独誤り位置、最大8誤りを照合した。
S3用GCC14.2.0（IDF5.5.1指定archiveのSHA256一致）で実ISAのobjectを生成。

| 版 | RS solver code/literal/rodata | RPC code/literal/rodata |
|---|---:|---:|
| Os | 1106 B | 1186 B |
| O2 | 1339 B | 1452 B |
| O3 | 5860 B | 2052 B |

**object compileであり、完成アプリのlink・IRAM配置・実CPU WCETではない。**
関数ごとのstackと逆アセンブルも保存。callee/RTOS込みの最大stackは未確定。
host時間をS3 cyclesへ換算しない。観測GF演算数も全入力のWCETとは扱わない。

BM/Omega/Forney分担のC RPCは4 KiB固定頁で実装済み。
CRC32、世代/batch、全204 recordのID/位置/空きbyteを検査してからcontextを更新する。
5 context、1020符号語で全204 Bの訂正一致、世代違い/重複/早期ack/CRC破損/不正rootを検査。
異常時はepochを停止する契約で、自動再送による重複適用をしない。

| 内部SRAM対象 | 使用量 |
|---|---:|
| 5 batch context（ABIをS3 compile時にもassert） | 5×7148＝35,740 B |
| GF tables/状態 | 2,832 B |
| CRC table | 1,024 B |
| 入出力page各1 | 8,192 B |
| 合計 | 47,788 B |
| S modeで仮に64 KiB FFT領域を再利用できた場合の残り | 17,748 B |

mode union、起動/RTOS/driver全同時allocation、DMA descriptor、stackは未link。
この残量を完成受信機の空きSRAMとは主張しない。
CPUの6,752.6 cycles/codewordは上記RPCのCRC等も含む予算で、達成確認はまだない。

### 離れたFFT領域への配置を具体化

旧ROM-safe案のFFT領域は連続64 KiBではなく、late slotと低位SRAM slotの各32 KiB。
`s3_rs_workspace.h/.c`で、TのFFT配列とSのRS領域を明示的なunionにした。
S3 objectから取り出したABI表（全Os/O2/O3で同じ）は次の通り。

| 使用領域 | slot内offset | bytes |
|---|---:|---:|
| slot0 context 3個 | 0 | 21,444 |
| slot0 CRC table | 21,444 | 1,024 |
| slot0 RX DMA頁（32 B aligned） | 22,496 | 4,096 |
| slot0 TX DMA頁（32 B aligned） | 26,592 | 4,096 |
| slot0 RS構造体合計 | 0 | 30,688 / 32,768 |
| slot1 context 2個 | 0 | 14,296 |
| slot1 GF tables/状態 | 14,296 | 2,832 |
| slot1第2 RX DMA頁 | 17,152 | 4,096 |
| slot1第2 TX DMA頁 | 21,248 | 4,096 |
| slot1 RS構造体合計 | 0 | 25,344 / 32,768 |

単体RPC検査の入出力各1頁に対し、workspaceはCPU処理中のDMA用に**入出力各2頁**を確保した。
padding込み使用56,032 B、2 slot合計の残り9504 B。union自体は各32,768 B、alignment 32 B。
この二重化でもCPU実時間と頁所有権を満たすschedulerの証明は別途必要。
100回の汚れたFFT領域からの初期化、5 contextの非重複、前後guard、DMA alignmentをhostで検査。
切替前のDMA drain/所有権移譲はcaller契約で、実RTOS driverには未結合。
このABI検査は、具体アドレスへ完成アプリを配置する最終link監査を代替しない。

### 実装したRPC wire契約

1 batch＝204符号語を1入力頁として扱い、record IDは0..203の昇順。
multi-byte整数はlittle endian。16 B headerは `RS`(2)、version(1)、kind(1)、epoch(2)、
record数(2)、batch番号(4)、CRC32(4)。CRCはISO-HDLCの反転多項式0xEDB88320、
init/xorout 0xffffffff、CRC欄を0と見なし4096 B全量を保護する。未使用tailは0を要求する。

| kind | record配置 | 方向 |
|---|---|---|
| 1 syndrome | ID16、status8、S0..S15の16 B＝19 B | FPGA→S3 |
| 2 lambda | ID16、status8、degree8、λ0..λ8＝13 B | S3→FPGA |
| 3 roots | ID16、count8、位置8 B、reserved8＝12 B | FPGA→S3 |
| 4 magnitudes | ID16、status8、値8 B、reserved8＝12 B | S3→FPGA |

statusは0/1。roots countは0..8または失敗0xff。位置は厳密昇順で0..203、
未使用位置/値・reservedは0。Forneyは渡された位置が実際のlocatorの根かも再検査する。
上流失敗/不正locatorで、部分的に計算した訂正値を公開しない。
contextはFREE→WAIT_ROOTS→WAIT_ACK→FREE、最後のackはresponse DMA完了後だけ許可。
重複、未知batch、古いepochの再送は拒否する。callerが次batchとepochを管理し、
epoch変更時は古いDMA/FPGA処理を止めてdrainする必要がある。この所有権管理自体は未結合。

### 実ESP-IDF link・IRAM・ROM・起動メモリの追加監査

ESP-IDF v5.5.1（fcae32885b0296b32044cb99ecbdc50d98dddb83）、固定RF source、
固定esp-dspを取得し、既存RF/transport/FFT予約へRS/RPC/unionを加えた実ELFを再生成した。
BM/Forney/RPCの主要6 APIと既存hot処理8 APIは実mapでIRAM内。
RF loop/RS workerは呼び出していないLINK用probeであり、完成firmwareの実行ではない。

この検査で、**union型を32 B alignedにしても、変数側のDMA_ATTRが4 B alignmentへ
上書きし、実slot1が0x3fc9bb84へ置かれる不具合**を発見した。
変数にも明示的なaligned(32)を追加し、再link・実ELFの4 DMA page住所検査・回帰試験を実施。
初回の不正配置は[棄却記録](s3-rs-link-evidence/initial-bad-alignment/rejection.json)に保持する。

| 実SDKで確認したもの | 修正後の結果 | 限界 |
|---|---|---|
| RF/SPI/FFT＋RS/RPC link | 成功、S3 ISA | 全worker/driverを動かすschedulerではない |
| slot1の実住所 | 0x3fc9bba0、32 B aligned | slot0は0x3fcf0000のlate領域、app_mainより前には触れない |
| S用4 DMA頁 | ELFから抽出したoffsetを実baseへ加算し、全て32 B aligned・予約内 | DMAを実行していない |
| RF予約手前の静的余白 | 29,512 B | runtime heapの空きとは異なる |
| 起動task/TCB/allocator後、DMA pool前の内部空き上限 | 19,312 B | 多めに見積もった上限。PHY/driver/追加worker/断片化をまだ引く必要がある |
| 4 KiB DMA poolの必要容量条件 | PASS | 起動・runtimeの十分条件ではない。poolを空き容量へ二重加算しない |
| ROM rev0との予約衝突 | なし | 実moduleのROM revisionは未確認 |
| 起動/配置監査の回帰試験 | 8件PASS、4 Bへずれた配置の拒否を含む | 実機起動試験ではない |

[SDK linkのsource hash・実住所・ABI](s3-rs-link-evidence/results.json)、
[環境pin](s3-rs-link-evidence/environment.json)、実ログと生成RF sourceを保存した。
今回閉じたのは「RSを加えた実SDK link/静的配置/起動必要容量」の検査で、
全RTOS allocation、native RF互換、CPU WCET、連続受信、全T/S切替は未完。

GitHub Actionsもcommit d9f1e3bで起動したが、raw APIの全jobが`steps=[]`、`runner_id=0`で失敗。
原因診断用check-run endpointはconnectorで非対応。これはローカル合成/実linkの失敗とは区別する。

## 5. 環境内で残る実装と、実機が必要な確認

| まだ環境内で進められるもの | 今回から残る具体物 |
|---|---|
| RS分割の統合 | FPGAのRPC頁codec/CRC、RFとは別のqueue、5 batch所有権/credit、符号語保存、訂正read/write、TS packet scheduler |
| S3 firmware | C RPCをSPI/SCT/status/RTOSへ結合、全workerを含む最終link/runtime SRAM監査、実機cyclesを記録する計測入口。部分RF/FFT/RSの実SDK linkとunion配置監査は今回完了 |
| 受信処理 | T/Sの同期・追従・TMCC・全interleave・descramble・TS選択、T FFT/SIMD/core間連携、規格波形との結合試験 |
| FPGA完成時の合否 | 上記全回路を含むP&R、IO/CDC/phase STA、PSRAM校正ロジックと全負荷のmemory deadline検査 |
| 切替/前段 | 外部NORのT/S/recovery実image、writer/RECONFIG/recovery driver、RF回路図/BOM/PCB |

これらは実機待ちではない。今回の部品試験に合格しただけで全作業完了とはしない。

| 今の環境では実施できないもの | 不足する実物・条件 | 合格条件 |
|---|---|---|
| S3 native RF連続取得 | N16R8実moduleとRF入力 | PHY直接初期化で16/40 MSps、全sample連続・bank破壊なし |
| CPU/GDMA/ISRのWCET | RF＋SPI＋RS/FFTを同時実行するS3 | 6,752.6 cycles/codeword等の全予算、API上限、buffer期限内 |
| 2 SPIの電気的動作 | 両基板/実配線/計測器 | Octal/Quad各80 MHzで無欠落、実gapが予算内 |
| PSRAM/clock/電源 | Tang Nano 9K実機、温度/負荷条件 | read/write/refresh競合、DQ/RWDS eye、電圧/jitter/温度条件を満たす |
| RF前段 | 選定後の変換/LO/filter/LNB給電回路、信号源等 | 帯域・image抑圧・雑音・直線性を満たす |
| NOR切替/復旧 | strap/1.8 V RECONFIG配線、programmer、電源操作 | T/S両方向、破損image/電源断時の停止と復旧 |
| full TSの実受信 | 完成実装、規格RF波形/実波、TS analyzer | T/Sとも既知TS一致、CC/CN/長時間/切替再捕捉条件を満たす |

Background Programmingは基板外付けSPI NORに複数imageを保存し切り替える用途のみ。
実機書込みもPR mergeも実施しない。

## 再現

```sh
python -m unittest discover -s tests -p 'test_s3_*.py' -v
python experiments/s3_rs_offload_budget.py > reports/s3-rs-offload-budget.json
python ci/s3_rs_offload_compile.py --cc /path/to/xtensa-esp32s3-elf-gcc
python ci/s3_psram_benchmark.py --rs-offload --rr-table --core-mhz 90
python ci/s3_psram_benchmark.py --rs-correction --rr-table --core-mhz 90
python ci/s3_rs_offload_evidence.py --test-log build/s3-rs-offload-all-tests.log
```

論理/タイミング証拠、失敗seed、host/target検査は`s3-rs-offload-evidence/`。
GitHub Actionsの失敗はstep情報が取れない限り原因を断定しない。ローカル結果をremote成功と呼ばない。

検証ログは全S3 unittest 68件（292.299秒）に加え、後から追加したsyndrome版を含む
4件とworkspace 1件を別途実行してすべて合格。4件のうち既存2件は重複実行である。
