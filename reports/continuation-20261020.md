# ②の継続検証（2026-10-20）

①はユーザーの停止指定を維持し、PR8を変更しない。②だけを扱う。
完成受信機の成立・正式通信路割当・採用は引き続き0。
**service/reader/K7部分は156.74 MHzで通過したが、実FFT統合後の最高は146.22 MHzで目標154.29 MHz未達。**
今回の5件のCAD比較は全て配線完了。全結果とsource hashは[集計JSON](continuation-20261020.json)に記録した。
全受信機実装・全条件期限検証・実ピンSTA・実S3測定まで完了したという報告ではない。

## 入力・転送の根拠の再監査

[ESPARGOS/esp-sdr](https://github.com/ESPARGOS/esp-sdr)の
`main/common/ring_capture.c`（blob `02d38877e02a4ef19526895d21b86ce3e5fd5a41`）と
`main/targets/esp32s3/receiver.c`（blob `6c9bf0b685d9b59fc5214bece56e040f8ca1c5c5`）を確認。
3個の64 KiB SRAM bankを回す連続取得実装は存在する。
ただし上流は処理遅れ時のwork破棄とUSB queue満杯時のframe破棄を許し、
ring動作中は割込みを止める。したがって連続取得実装の存在だけでは、
全量無欠落パッキング・SPI/GPIO送信・ドライバIRQ共存を証明できない。
ローカルadaptationは割込みを止めないため、上流の実績をそのまま移植先のWCETへ転用できない。

T/Sの取得SRAM書込みは64/160 MB/s、可逆packed出力は40/100 MB/s。
12288 sampleごとのbank切替周期は768/307.2 µs、2000 sampleの遅れ許容は125/50 µs。
これは取得回路、CPUによる読出し・packed書込み、GDMA読出しが共存する問題である。
PSRAM容量が増えても、それだけでこの内部メモリ競合を解消しない。
さらにsample rateの指定は、RF/アナログfilterがISDB-Sの必要占有帯域と信号品質を通す証明ではない。外部周波数変換・LNB電源も別途必要。

既存native capture・RF pump・schedule closureの8 unittestを再実行して成功。
[ログ](s3-input-source-audit-test.log)はホストモデル検証であり、実S3の測定ではない。
[機械結果](s3-input-source-audit-20261020.json)。

### 前の説明で落としていたCPU制約

以下は既存カタログを再計算した値。CPU low/highは費用感度モデルでありWCET上下限ではない。

| Sの通常周辺機器経路 | payload＋設定需要 | 帯域余り | driver込みCPU low/high |
|---|---:|---:|---:|
| SPI2 Octal80＋SPI3 Quad80 | 100.01 MB/s | 3.713500 MB/s | 90.1376 / **106.8042%** |
| SPI2 Octal80＋eMMC4 DDR40 | 100.01 MB/s | 2.008180 MB/s | 89.9531 / **106.6197%** |

帯域だけでなく**高費用CPU条件も不合格**。前の回答で「帯域に入る候補・実機未確認」だけと
説明したのは不十分だった。これは専用GPIOや別の効率的実装の不可能性を示すものではない。
通常経路はT10＋S16＋TS6＋指令2＝34/34信号で、物理割当・clock入力・搭載負荷も未検証。
専用GPIOもT1 lane＋S2 laneで34信号だが、240 MHz CPUからの送出費用、同期受信回路、
独立S3 clockとの関係を実証していない。算術カタログを正式経路に昇格させない。

## refresh事前判定：既存部分回路のタイミング未達を解消

棄却したmetadata登録版ではなく、従来最良のready直結除去版へ適用した。
`refresh_age == REFRESH_CYCLES-33`の時点で次cycleのrefresh_dueを登録し、
MODE/REFRESH/resetでは元と同じedgeで消す。要求受理や転送に追加cycleを入れない。
精度、puncture/erasure、FIFO容量、refresh間隔は変更しない。

論理上は帰納的にも一致する。reset/MODE/REFRESHでageとflagはともに0へ戻る。
それ以外でageは初期化後に1ずつ増え、上限で飽和する。閾値N=REFRESH_CYCLES-32に対して
age=N-1のedgeだけでflagを立て、その後は次のresetまで保持するため、各edge後の
flagは常にage>=Nと等しい（許可parameterはREFRESH_CYCLES>=64）。
この説明は論理等価性であり、配置配線の遅延保証とは別。

旧controllerとのcycle miterは全出力とrefresh_dueを比較。
period 64/1203/65535、row/bank変更、応答stall、途中reset、refreshを妨害した飽和・faultを検査。
それぞれ要求912/1482/16978件を受理した条件で一致した。
binary/TC8の結合試験もデータoracleに一致し、記録したtrace全値は従来最良版と一致。
[試験ログ](shared-receiver-refresh-predecode-test.log)、[結果](shared-receiver-refresh-predecode-test.json)。

| 部分回路 | logic（RAM blocker込み） | FF位置 | BSRAM/DSP | 配線後MHz | 目標154.285714 MHz |
|---|---:|---:|---:|---:|---|
| 従来ready直結除去 | 11491 | 5370 | 6/2 | 153.491943 | 未達 |
| refresh事前判定 | 11474 | 5371 | 6/2 | **156.739807** | **通過** |

[CAD証拠](shared-receiver-refresh-predecode-evidence/summary.json)。同じ固定toolchain、seed1、probe。
この部分回路の混合見積りはlogic20043/20736（余り693）、FF12121/15552、BSRAM44/46、DSP34/48。
他stageは依然allocationであり、この数字は全体実装の収容証明でも下限でもない。

## 到着の偏りを増やした結合試験

従来最良版へ、Sの同じ平均レート・同じ総sample数を64 clock単位でまとめて渡す条件を追加。
binary/TC8それぞれphase0/31、計4条件。全T softと復号bitをoracleへ照合し、
T bank再使用・refresh期限・既存FFT模擬アクセス期限も検査した。

| S | phase | S外部backlog最大 | S FIFO最大 | 最大T ACS遅延 | FFT 1/2期間完了 | 診断期限超過 |
|---|---:|---:|---:|---:|---|---:|
| binary | 0 | 24 | 31 | 38911 | 37028 / 76558 | 0 |
| binary | 31 | 24 | 32 | 38920 | 37080 / 76596 | 0 |
| TC8 | 0 | 12 | 9 | 26232 | 36951 / 76461 | 0 |
| TC8 | 31 | 12 | 9 | 26220 | 36935 / 76461 | 0 |

[全結果](shared-receiver-arrival-sweep-test.json)、[ログ](shared-receiver-arrival-sweep-test.log)。
これは2 symbolの有限条件。実S interleaverの到着包絡、全位相、長期queue安定性の証明ではない。

## 実FFTを含めた統合

`experiments/shared_receiver_fft.sv`で、従来のFFT外部delay模擬要求を実際の
`shared_sdf_fft`のread/writeへ接続した。Mode3だけでouter cacheを予約する。
FFT出力は独立したbin/data/validとして取り出し、まだ等化器・demapへは渡していない。
これはRFからTSまでの直列接続ではない。

同じ1890-FF観測probeで次を測定した（旧serviceのみのprobeは1874 FF）。
各probeのFF/passthrough/digestを分離するが、観測D側のlogicは本体へ課金する。

| FFT統合版 | logic | FF位置 | BSRAM/DSP | 配線後MHz | 判定 |
|---|---:|---:|---:|---:|---|
| 旧controller＋旧arbiter | 14039 | 6776 | 16/6 | 132.996414 | 未達 |
| refresh事前判定＋旧arbiter | 13947 | 6777 | 16/6 | 124.347183 | 未達 |
| refresh事前判定＋metadata登録 | 14175 | 6801 | 16/6 | **146.220200** | 未達 |
| 上記＋reader beat冗長更新除去 | 14079 | 6801 | 16/6 | 139.198212 | 未達 |

旧controller版の最長経路はBG要求addressからcontroller state、7.519 ns。
refresh事前判定版はreader read_bankからbeat、8.042 ns。
metadata併用版は共有K7内部からsurvivor保存側、6.839 ns。
したがって、service部分の156.74 MHz通過をFFT統合後にも適用してはいけない。
reader beat更新除去はlogicを96減らしたが、146.22→139.20 MHzへ悪化し、速度改善案として採用しない。
FFT統合の現最良版の混合診断値は20015 logic、12049 FF位置、44 BSRAM、34 DSP。
残りlogic721という値にも未実装stage/接続の費用不確定がある。全受信機を収容できるとは判定しない。
[基準CAD](shared-receiver-fft-evidence/summary.json)、[refresh版](shared-receiver-fft-refresh-evidence/summary.json)、
[metadata併用版](shared-receiver-fft-metadata-refresh-evidence/summary.json)、
[beat更新除去版](shared-receiver-fft-beat-hold-evidence/summary.json)。

FFT＋連続Sの機能試験は8192点×3出力frame＝24576 binが独立整数oracleに一致。
S出力175192 bitのうち先頭64 bitを除いて既知zero符号列に一致した。
初回300秒はhost実行timeoutで判定未完。進捗を記録して900秒上限で再実行し、310.305秒で成功。
初回timeout logも保存し、回路の実時間期限違反と混同しない。
[結果](shared-receiver-fft-test.json)、[ログ](shared-receiver-fft-test.log)。

metadata＋refresh版には、T3のzero-codeword soft bufferを234 BL8で実controllerから書き込み、
commit後にFFT・T3 reader・Sを並行動作させる接続試験も追加した。
FFT全24576 bin、各T contextの既知zero出力、Sの既知列を検査して成功。
この初版のT検査はcontext出現と値の検査であり、完全出力数の保証とは分ける。
[結果](shared-receiver-fft-t3-s-test.json)。

readerのIDLEでの`beat<=0`は、resetまたは最終UNPACK edgeで既に0となり、
IDLE/REQUEST/RESPONSEの間は変わらないため冗長である。この条件を除く実験も追加した。
2 symbolの従来binary/TC8試験では全データとtraceが従来版と一致した。
[結果](shared-receiver-beat-hold-test.json)。この版のFFT統合試験ではT出力数も
384/2432/3456 bitと照合し成功した（[結果](shared-receiver-fft-t3-s-beat-hold-test.json)）。
Tのtrellis stepは504/2520/3528で、64-bit出力bankとtraceback待ちにより有限列の出力数は
`(steps//64-1)*64`となる。末尾の出力待ちをTS再生完了と扱わない。
有限T buffer試験であり、実T time interleaverや連続全階層到着ではない。

## SDRAMの実ピンタイミング監査

[DS226-2.7E](https://cdn.gowinsemi.com.cn/DS226E.pdf) 2.2.1でQN88のSDR SDRAMを確認。
64 Mbit、32-bit、166 MHz、access time5.4 ns、4096 refresh/64 ms。
154.285714 MHzの周期6.481481 nsから5.4 nsを引いた残りは1.081481 nsだが、
これをsetup余裕と呼ばない。実IO・clock経路、setup、skew、jitterがまだ含まれない。
hold側はmin data-valid条件も必要。

[メーカーIP guide](https://www.gowinsemi.com/upload/database_doc/281/document/5d280116bebab.pdf)
6.2も高速時の位相調整を要求する。現在はSDRAM pad/tri-state/PLL位相を持つ実topと
対応するmin/max制約がないため、物理STAを完了できない。
既存pin-commandモデルはcycle単位のプロトコル検査であり、電気的setup/hold検査ではない。
不明なdelayを0として合格させない。[換算と不足入力](sdram-io-timing-audit-20261020.json)。
refresh1203 clocksは約7.797 µsで、公称4096/64 msより頻繁。今回の比較では変更していない。

## 完成までの未完了範囲

- 実RF front end、同期、TMCC、等化/demap、実T/S interleaver、RS/TSまでの全stage統合。
- 実stageから導いた到着契約、全mode/rate/階層、選局時のreset範囲、出力停止時の扱いと長期期限。
- S3実実装の連続取得・全量搬出・core別WCETとDMA競合、実GPIO割当・受信PHY。
- 実SDRAM padとPLLを含むSTA、実基板でのRF入力からTS出力までの検証。

これらは完了していない。全体統合の未実装部分を「実機だけが必要」とは分類しない。
今回の部分回路の成功を受信機全体の成功へ拡張しない。

## 作業完了範囲と残作業の区別

| 依頼項目 | 今回実施したこと | まだ完了していないこと |
|---|---|---|
| S3入力・転送根拠 | 上流ソース監査、既存packer hash検算、通常経路CPU再計算、8ホスト試験 | 実S3の無欠落全量搬出、RF帯域/CN、GPIO経路実装・WCET |
| FPGAタイミング改善 | 5 CAD条件、controller同周期miter、refresh改善でservice部分通過 | 実FFT統合版の目標clock達成 |
| 到着・競合検証 | binary/TC8の64-clock batch到着4条件、T3/S/FFT接続のデータ照合 | 実stage到着包絡、全mode/rate/位相と長期queue保証 |
| 全体統合 | 実FFTをサービス/reader/K7へ接続して測定 | FIR/同期/TMCC/等化/実interleaver/RS/TSを含む受信機全体の実装と統合 |
| SDRAM実ピンSTA | メーカー仕様確認、cycle→ns換算、必要制約の不足を特定 | 実pad/PLLとmin/max制約を持つtopでのSTA |
| 実機測定 | 完了とは扱わない | この環境に接続した対象基板がなく未実施 |

「全て完了」ではない。全体統合など、こちらで引き続き実装できる作業も残る。
実機がないことを全ての未完了理由にしない。現在のFFT統合版はclock未達であり、
これを通過していない状態で通信路正式割当や採用へ進まない。
①全方式・②全方式の不可能性を証明したという結論でもない。
