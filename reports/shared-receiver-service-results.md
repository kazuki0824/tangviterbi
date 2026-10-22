> 2026-10-20更新：refresh判定の事前登録で、このservice/reader/K7部分は156.739807 MHzとなり目標を通過した。以下の153.49 MHz未達・事前登録未実装という記述は以前の比較履歴。現状は[継続検証](continuation-20261020.md)、[更新台帳](shared-receiver-service-budget.json)を参照。全受信機の合格ではない。

# ② SDRAM controller RTL・T reader・共有K7の同時接続

**②全体は未確定。成立確認済み分担・正式通信路割当・採用は0。** core単体・理想メモリ機会の試験から進め、同じ回路上でSDRAM controller、T reader、TC8/binary共有K7、S保持FIFOとT/S入力選択を接続した。シミュレーションと部分P&Rであり、実基板の動作確認や全受信機・ESP32-S3の成立確認ではない。

## 実装した比較対象

1. [元readerの統合版](../experiments/shared_receiver_service.sv)。既存T readerは32-byte応答をbyte単位でcacheへ展開する間、controllerへ応答を保持させる。新しい[S FIFO](../experiments/s_input_fifo.sv)は256×32-bitのblock RAM＋prefetch headで、headを含め256要素。binaryは下位8 bit、TC8は内部Q15 IQ16×2を保持する。T/S入力選択はS:T=2:1、stall中の選択を固定。
2. [256-bit退避版](../experiments/shared_receiver_service_buffered.sv)。[reader](../experiments/t_soft_reader_buffered.sv)がwhole BL8を256-bitレジスタへ取り込み、controllerの応答を先に解放する。その後に元と同じ3×64-byte cacheへ展開する。追加sample削減・bit削減はない。
3. [退避＋T2語FIFO版](../experiments/shared_receiver_service_elastic.sv)。readerとK7入力選択の間へ2×10-bit（context2＋soft8）の保持を追加。readyはoccupancyだけで決まり、同時popによるfull bypassを設けず、K7 ready→reader cache countの長い組合せ経路を切る。

4. [ready直結を除いた版](../experiments/shared_receiver_service_isolated.sv)。256-bit退避版を基に、[depuncture](../experiments/s3_depuncture_isolated.sv)の入力readyを `!out_valid` の保持状態で決め、output-readyからの同clock bypassを除く。前pairの消費と次soft入力を同時に行わないので、値は保存されるが受付間隔が延びる。T2語FIFOはこの版には加えない。全5符号化率の独立pair oracleと統合期限を再検査する。

5. [要求metadata登録版](../experiments/shared_receiver_service_metadata.sv)。ready直結除去版の[arbiter](../experiments/sdram_client_arbiter_metadata.sv)で、既存SELECT edgeにaddress21＋write1を登録する。ISSUE/RESPONSEの周期・所有権・round-robin規則を変えず、payload256とDQM32はproducer保持のままとする。登録値はreq_valid時のみ有効で、無効時の値をresetする回路は加えない。

全版で同じclock/reset、T3＋S同時稼働、S binary/TC8、元のdepuncture/soft/cost精度を維持。mode/rate変更はglobal reset、Sだけの独立retuneと出力backpressureは未実装。試作はexperiments内で、既存の生産用RTLを変更しない。

S FIFOをtestbench内の未課金保持として扱うことをやめ、今回の測定回路へ含めた。T response32 BとT FIFO2語も各版の実費に含める。BG各producerのrequest保持、実FFT・interleaver・復調出力の保持はまだ実装されておらず、今回の追加保持と同じものとみなさない。

ready直結除去の[単体試験](../tests/test_s3_depuncture_isolated.py)は全5符号化率・全puncture位相の2100 pairを、任意8-bit soft値とerasureの独立期待値へ照合した。output stall中のpair安定性と不正rate拒否も確認した。

## データ・プロトコル検査

[比較unittest](../tests/test_shared_receiver_service.py)、[T2語版unittest](../tests/test_shared_receiver_service_elastic.py)。[比較結果JSON](shared-receiver-service-test.json)、[T2語版JSON](shared-receiver-service-elastic-test.json)、[ready直結除去版JSON](shared-receiver-service-isolated-test.json)。[metadata登録版JSON](shared-receiver-service-metadata-test.json)も含め、各版でS binaryとTC8を別のglobal reset epochとして検査した。

- T Mode 1、1/5/7 segment、各7/8、2 symbol。T softは各symbol 576/2880/4032 B、合計7488 B、平均28.813853 MB/s。
- 初期symbolをcontroller RTL経由で書いてからt=0にcommitする。以降は次symbolのwrite完了後にのみcommit。実T spill write 3 symbol×234＝702 BL8（初期prefillを含む）、T readは2 symbol×234＝468 BL8。最初に読んだ物理bankを3番目のsymbolで実際に再使用し、liveが解放されるまでwriteを待つ。
- 40095 clocksごとにFFT2048 sample、T time-interleave proxy523、S frame proxy186、management proxy82 BL8をreleaseする。2 period、FFT合計4096 sample。FFTのouter cache契約はread+1/write+6、最短13 clocks/sample。実FFT演算や実interleaverの到着traceではなく、有限合成sourceである。
- Sはbinary soft57.72 MB/sまたはTC8 28.86 MSymbol/sの有理数均等到着。実S interleaver burstは未接続。S sourceがreadyを待つ間もwordを保持する。
- 独立したSDRAM pin-command decoderがACT/PRE/READ/WRITE/REF/MODE、CL=3・BL8・DQMを反映したメモリを持ち、open row、DQ競合、宣言cycleのtRCD/tRP/tWR/tRFC/refreshを検査する。T soft値14976 Bを全量既知入力へ照合し、出力済み復号bitも先頭64以後を既知情報列へ照合。TC8はB0/B1両方。これはIO遅延・電気・PHYの実機検証ではない。
- traceback出力をACS直後で打ち切らず、末尾に2000 clocksを与える。64-bit bank単位の出力数を検査し、有限列の未確定末尾を全量出力済みとしない。binary時の未使用B1は比較しない。

[S FIFO単体試験](../tests/test_s_input_fifo.py)は3372 wordを独立accepted-word列と照合し、256要素満杯・output stall時の安定性・複数回のpointer周回・完全drainを確認した。

[arbiter cycle miter](../tests/test_sdram_client_arbiter_metadata.py)は、producerがreadyまで要求を保持する契約で旧版と登録版を20,000周期比較した。要求3,288件、応答3,287件、途中resetによる処理中断を含み、ready/valid・応答先・有効要求metadata/payload/DQMが全周期一致した。[実行log](sdram-client-arbiter-metadata-test.log)。

## clock単位の有限期限

以下の期限は**154.285714 MHzで動作できるという条件下の診断契約**。各T symbolのACS完了と次symbol writeは40095 clocks以内、FFTは1/2 periodの40095/80190以内を調べる。Sの最後の入力直後に全ACSが空になることは要求せず、遅延と有限保持を区別する。commitのtestbench上の1-cycle遅れを実装の失敗として数えないよう、要求をhandshake予定edgeの前に出す。

| 版 | S mode | 最大T ACS遅延 | FFT 1 period完了 | FFT 2 period完了 | 診断期限超過 |
|---|---|---:|---:|---:|---:|
| 元reader | binary | 39372 | 40885 | 81231 | 2 |
| 元reader | TC8 | 35182 | 39862 | 79523 | 0 |
| 256-bit退避 | binary | 38922 | 37107 | 76635 | 0 |
| 256-bit退避 | TC8 | 26230 | 36935 | 76461 | 0 |
| 退避＋T2語 | binary | 38922 | 36994 | 76630 | 0 |
| 退避＋T2語 | TC8 | 26230 | 36935 | 76461 | 0 |
| ready直結除去 | binary | 38916 | 37038 | 76501 | 0 |
| ready直結除去 | TC8 | 26230 | 36935 | 76461 | 0 |
| metadata登録 | binary | 38916 | 37038 | 76501 | 0 |
| metadata登録 | TC8 | 26230 | 36935 | 76461 | 0 |

metadata登録版の記録した全trace値はready直結除去版と一致し、T/Sデータoracleも通過した。転送周期を増やした改善ではない。

ready直結を除いたdepunctureの、下流stallがない場合の必要処理clockはsoft数＋pair数である。S binary最悪7/8は57.72＋50.505＝108.225 Mclock/s、T最大は28.813853＋25.212121＝54.025974 Mclock/s。各contextは独立回路である。共通soft入力需要は86.533853 MB/sだが、調停やstallを含めた有効能力の証明ではなく、必要条件の検算にとどまる。

元readerはbinary同時処理時にFFT期限を790/1041 clocks超過し、不合格。whole response退避でこの有限例の超過を解消した。T2語版のT最小余裕は1173 clocksで、S FIFO最大はbinary22要素、TC8 1要素。いずれも256要素以内。T sourceのbank寿命とS hardware FIFO容量はこの試験列で確認したが、全位相・長期運転・実burst・TS最終期限は未確認。

初回試験ではbinaryの未使用B1を数値として読み、ACS直後に終了して遅延出力を待たなかったため、testbenchの検査が失敗した。検査対象と終了条件を修正してから上の比較を全版で実行した。元readerのFFT期限超過は検査修正後も再現している。

## CADと資源台帳

各版の[元reader CAD](shared-receiver-service-evidence/summary.json)、[退避版CAD](shared-receiver-service-buffered-evidence/summary.json)、[T2語版CAD](shared-receiver-service-elastic-evidence/summary.json)、[ready直結除去版CAD](shared-receiver-service-isolated-evidence/summary.json)、[metadata登録版CAD](shared-receiver-service-metadata-evidence/summary.json)。seed 1、同じ1874-FF probe、GW2AR-LV18QN88C8/I7、目標1080/7 MHz。source hashとcommandを保存する。scan1497＋capture364＋digest13 FFとそのpassthrough/digestだけをprobe費用として分離し、capture D側logicを本体へ課金する。

CADの最終数値と混在台帳は[再計算JSON](shared-receiver-service-budget.json)を参照。台帳は旧19891 logicからservice/reader3854と共有TC8 stage7468を一度だけ除き、joint netlist実費を足す。独立TC8の3208をさらに削除しない。FF/BSRAM/DSPも同じ所有権で置換する。

**他stageはallocation、他の未実装接続費用は0の混在診断値であり、全受信機の収容・P&R・資源下限ではない。** 元2231 logic予約は既にservice/readerへ置換済み。BG producer保持等を無料・実装済みと扱わない。BSRAM予約を未実装項目と相殺しない。

## 目標clockの判定と残る経路

| 版 / seed | joint logic位置 | joint FF位置 | BSRAM / DSP | 出力reportのFmax MHz | 154.285714 MHz |
|---|---:|---:|---|---:|---|
| 元reader / 1 | 11479 | 5113 | 6 / 2 | 128.915817 | 未合格 |
| 256-bit退避 / 1 | 11561 | 5370 | 6 / 2 | 125.344696 | 不合格 |
| 退避＋T2語 / 1 | 11518 | 5392 | 6 / 2 | 121.565773 | 不合格 |
| ready直結除去 / 1 | 11491 | 5370 | 6 / 2 | 153.491943 | 不合格 |
| 同じRTL / 2 | — | — | — | 未確定 | 600秒で計算未完 |
| metadata登録 / 1 初回 | 11569 | 5394 | 6 / 2 | 134.390533* | 配線未完 |
| metadata登録 / 1 再実行 | 11569 | 5394 | 6 / 2 | 134.390533 | 不合格 |

元readerの実行はexit 1で、ログにRouting complete記録がない。出力reportの128.915817を成功した完走結果とは扱わない。元の比較3版は配線完了後にclock条件でexit 1となった。**有限試験のclock数が期限内でも、実時間の性能合格ではない。**

T2語FIFOだけでは長いready経路がFIFOのread pointer制御へ移り、改善しなかった。mapped source位置を追うと、depunctureの保持状態やK7入力FIFOのcountから上流保持へ戻る経路だった。ready直結除去でこの経路を短くし、seed 1の最長経路はSDRAM arbiter owner→要求metadata選択→controller stateへ移った。必要周期6.481481 nsに対しreport経路6.515000 nsで、約0.033519 ns不足する。

ready直結除去版を台帳へ置換すると `19891−3854−7468＋11491＝20060 / 20736 logic`、残676。FF位置12120/15552、BSRAM44/46、DSP34/48。ただし上記の混在診断条件があり、clock未合格で採用しない。同じRTL・pin・目標clockでseed 2を追加検算したが、nextpnrの600秒上限でexit 124となり、配線完了reportは得られなかった。[seed 2 evidence](shared-receiver-service-isolated-seed2-evidence/summary.json)。これは計算未完であり、資源超過・完走後のclock不合格・②全方式の不可能性とは別である。RTLとprobeのsource hash一致を再計算scriptで検査している。

現在の最高reported Fmaxは153.491943 MHz。目標との差は0.793771 MHz、約0.5145%。**統合clock合格は0で、性能合格・通信路正式割当・採用へ進めない。**

22-bit metadata登録案は実装・検算したが**不採用**。初回はexit 1、明示ERRORなし、Routing complete記録なしで終了したため、出力reportの134.390533 MHzを最終配線値とは扱わなかった。同一RTL・collector・seed・pin・clockで再実行し、今度は配線完了、clock不合格のERRORと正常終了記録を確認した。[初回CAD](shared-receiver-service-metadata-evidence/summary.json)、[再実行CAD](shared-receiver-service-metadata-retry-evidence/summary.json)。再実行でも134.390533 MHzで、source hashの一致を台帳生成時に検査する。初回終了の原因は断定しない。

登録版のjoint費用11569 logic・5394 FF位置・6 BSRAM・2 DSPを置換すると、混在診断値は20138/20736 logic（97.116%、残598）、12144/15552 FF位置（78.086%、残3408）、44/46 BSRAM（残2）、34/48 DSP（残14）。ready直結除去版に比べlogic＋78、FF位置＋24で、22 bitという信号幅だけでは周辺の再合成・配置費用を表せない。有限試験が同周期で通ってもclockを改善せず、旧版を置き換えない。

配線後の最長経路は `controller.refresh_age` →加算/比較・request受付制御→ `controller.state`。report周期7.441000 ns、必要6.481481 nsに対し0.959519 ns不足。[pin/P&R JSON](shared-receiver-service-metadata-retry-evidence/pnr.json)に始点・終点・delayを保存する。22-bit登録だけで全経路を解決できるという仮説は棄却する。

次はcarry比較がrefresh_due・飽和・faultのどの述語を共有しているかをmapped netlist上で確定する。その上で検証する余地があるのは、最高153.49 MHzのready直結除去版を基点に、refresh受付用の判定を1 clock先のcounter値から事前登録し、元の閾値・refresh周期・受付禁止周期と完全一致させる案。登録版の余分な22-bit費用を引き継ぐ案ではない。counterの加算と比較から受付/FSMへ至る実測経路に対応するが、まだ実装・同周期性・資源・clock未検証でありcreditを与えない。閾値前後、refresh reset、初期化、応答stallを旧controllerとcycle単位で照合してから統合CADへ進む。

探索を打ち止めとする根拠は現時点ではないが、成立する別案を確認したという意味でもない。refresh判定を含む残る経路対策が資源・目標clock・実期限を満たさず、測定根拠のある改善も残らなければ、この共有構成の救済を打ち切る。②全方式の不可能性とは区別する。

## 情報・通信経路と未達

要求された全候補・資源期限・情報境界・上下経路と帯域余裕は、[ownership](control-only-20k/all-ownerships.json.gz)、[448 variant台帳](folded-t-evidence/budgets/20k-all-variants.json.gz)、[情報境界](control-only-20k/all-boundaries.md)、[帯域catalog](control-only-20k/bandwidth-catalog.json.gz)、[raw経路全組合せ](control-only-20k/raw-route-pairs.csv.gz)、[制約付き組合せ](control-only-20k/all-allowed-pairs.json.gz)に残す。今回の特定構成の実費を、未検証の全variantへ無条件適用しない。

SoC→FPGAはnative I10/Q10（T40 MB/s、S100 MB/s）、FPGA→SoCは指令のみ。内部Q15 IQ/8-bit soft/9-bit costは既存FPGA復調契約で、通信都合の追加softwareデシメート/再量子化を行わない。代表の算術上の余裕はT Octal80で30.317658 MB/s、S Octal80＋Quad80で3.7135 MB/s、逆指令UARTで0.09 MB/s。実S3の連続取得・転送・WCET、端子・配線成立を確認した値ではない。

性能が成立した分担を先に確定し、その後に実現可能経路を割り当て、経路0でない候補を採用する順序を維持する。現在の正式採用は0。①は停止したまま。
