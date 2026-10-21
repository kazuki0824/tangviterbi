> 続報：[実タイルDMAの値・期限・配置配線・接続資源と現制約](continuation-20261021c.md)。以下は前回時点の結果。

# ②：3バッファ時間DIの所有権と実アドレス試験

①停止、正式採用0を維持。これは②全方式の不可能性証明ではない。
日付は作業上の日本時間。試験対象は最大Mode3、I=4、13 segments。
6個の既存8-bit soft値を保持する。追加の再量子化・間引きはない。

## 所有権と容量で確認できたこと

16 symbolの期間bで、scratch b%3へ入力、(b-1)%3を変換、(b-2)%3から出力する。
変換は16 carrier×16 symbol×6 bytes＝1536 bytesのtileを全て読んでから、
carrier別ringのwrite/readを行い、同じscratchの同じ位置に戻す。
これにより変換前の未読tileを上書きしない。役割交代には**全処理の期間内完了**が必要。

96遅延クラス、最大380 symbol遅延、64 blocksのPython値・所有権試験は成功。
独立時刻式でcold fillの無効値と有効値を照合した。実RTLでのcold fill処理は未実装。
ring 6344832＋scratch 479232×3＝7782528 bytes。
既存T spill 59904、S frame77952、FFT16384を引いた残容量は451840 bytes。
1536-byte tileは別途FPGA内部記憶として必要。全回路のBSRAMへ収まるという証明ではない。
4buffer配置の11008-byte超過を、この3buffer配置の問題として継承しない。

[所有権試験](t-time-three-buffer-schedule-test.log)、
[配置と要求列モデル](../experiments/t_time_three_buffer_schedule.py)。

## 実controllerへのアドレス列投入

既存BL8 controller（refresh事前判定版）と6-client arbiter、SDRAM pin-commandモデルを使用。
初期化完了から16 symbol＝2566080 clocksの1期間を計測。
入力・出力は各symbol冒頭に要求をreleaseし、symbol末尾を期限とした。
変換は期間冒頭release、期間末尾期限。入力/出力14976件ずつ、変換63336件。
T spill29952、S背景17152、FFT32768件を競合ケースへ追加した。

| 条件 | 変換完了clock | 変換の期間超過 | T spill期限違反request数 | 判定 |
|---|---:|---:|---:|---|
| 時間DIのみ、変換内部待ちゼロ | 1357289 | 0 | 対象外 | 宣言期限通過 |
| 時間DIのみ、byte逐次処理 | 3165008 | 598928 | 対象外 | 不合格 |
| 競合あり、変換内部待ちゼロ | 3213576 | 647496 | 24035 | 不合格 |

競合時のT spillは2696995で完了、個別symbol期限に対する最大遅れ325637。
入力・出力・S背景・FFT proxyは、この1期間では宣言期限違反0。
単独のbyte逐次処理ケースでは、転置とring読書きに合計1966848 clocksを直列追加した。
既存reader/writer RTLそのものを接続した試験ではなく、1 byte/clockの処理費用モデルである。

[実行結果・source hash](t-time-three-buffer-controller.json)、
[全ログ](t-time-three-buffer-controller-test.log)。unittestのOKは実験が完走した意味であり、
JSONのdeadline不合格を合格へ変えない。

**適用範囲:** T時間DIは実配置由来のアドレス列。SとFFTは旧fixture由来の要求数と
合成アドレスで、実stageの到着列ではない。T spillもK7本体へは接続していない。
全requestのwrite値は0であり、ここで時間DI値を検証したとは言わない。
データ値・所有権のPython試験と、実controllerの期限・プロトコル試験は別々。
batch100の1期間であり、全ring位相・全I・全modeの長期保証ではない。
要求元は抽象queueで、実入力の保持容量・backpressure契約も未実装。
release時刻の指定を、実際の到着や保持量の証明と扱わない。
周波数は154.285714 MHzを仮定したcycle換算であり、このtopの配線後達成値ではない。

## 連続要求をまとめる仲裁の追加実験

FFT client5の優先順位は維持し、背景clientは最大8要求の間、同じclientを優先する。
対象clientが要求を出していない場合は他clientを選べる。request/responseの所有権は
従来と同じく完了まで固定。既存のmask、停止、所有権試験に加え、8回での交代と
途中FFT割込み後の残り回数を検査して成功した。

8要求版で、時間DI完了は2794389 clocks、超過228309へ改善したが未達。
T spillは2540989で完了し、個別symbol期限違反も0へ改善。
これは変換内部待ちゼロの結果なので、byte処理を速くするだけではこの構成を合格にできない。

[8要求版結果](t-time-three-buffer-lease.json)、[ログ](t-time-three-buffer-lease-test.log)、
[仲裁機能試験](sdram-client-arbiter-lease-test.log)、[所有権・仲裁source hash](t-time-three-buffer-ownership-evidence.json)。

同条件で背景連続要求数を増やした結果：

| 最大連続要求 | 時間DI完了 | 期間超過 | T spill期限違反request数 |
|---:|---:|---:|---:|
| 1（従来） | 3213576 | 647496 | 24035 |
| 8 | 2794389 | 228309 | 0 |
| 32 | 2733480 | 167400 | 0 |
| 128 | 2723362 | 157282 | 0 |

32→128の改善は10118 clocksに留まる。この試験では全て不合格。
[32要求結果](t-time-three-buffer-lease32.json)、[128要求結果](t-time-three-buffer-lease128.json)。
要求数の変更だけで全ての案が不可能だと一般化しない。

### 要求選択と発行を同じcycleにする案

128要求版に、SELECTで選んだ要求をそのcycleにcontrollerへ提示する変更を加えた。
受理されなければISSUEへ移り所有権を固定する。応答消費までは次の要求を発行しない。
停止時の所有権、全subset/cursor、FFT割込み、128回での交代の3機能試験は成功。

変換内部待ちゼロでは、時間DI完了2546560、期限余裕19520 clocks（約0.761%）。
全clientの宣言期限違反0。従来の仲裁案の期限違反を、この案にも残っていると記載しない。
ただし、これは要求列だけのスクリーニング合格であり、実転置処理を含む期限合格ではない。
実データのtile gather/scatter・ring端数整列、実入力保持、配線後clock/面積は未確認。
組合せ選択経路が延びるため、帯域改善をclock改善と読み替えない。

[直接発行結果](t-time-three-buffer-direct.json)、[ログ](t-time-three-buffer-direct-test.log)、
[機能試験](sdram-client-arbiter-direct-test.log)。

### 実処理時間を加えた条件：まだ不合格

直接発行版で、各BL8の準備/消費時間をceil(bytes/処理幅) clocksとして直列追加した。
待ち時間ゼロ条件の合格をそのまま採用しないための費用感度試験。

| 転置・ring処理幅 | 追加処理clock総数 | 時間DI完了 | 期間超過 |
|---|---:|---:|---:|
| 4 bytes/clock | 491712 | 2925302 | 359222 |
| 32 bytes/clock | 63336 | 2597286 | 31206 |

両条件とも時間DI以外の宣言期限違反0。32 bytes/clockでも1.216%期間超過。
これらは幅を持つ実RTLを実装した測定ではない。端数整列・tileのbanking/port費用が
このモデル通りになる保証もない。処理をメモリ要求と重ねる方式は除外していないため、
この不合格は全ての転置方式の不可能性証明ではない。

[処理幅比較の結果・hash](t-time-three-buffer-wide.json)、[ログ](t-time-three-buffer-wide-test.log)。
今回のcontroller比較は9条件（宣言期限通過2、不合格7）。
実データの転置と先読み・二重保持を含むproducer実装が、次の具体的な検証対象となる。

## 現在残る成立上の障害と確認不足

「実測/モデルで未達」と「未実装/未確認」を区別する。未確認を物理的な不可能性とは呼ばない。

| 対象 | 現在の問題 | 解消に必要なもの |
|---|---|---|
| 実FFT＋共有K7の処理速度 | 最良146.2202 MHz。現K7は追加stallゼロでも152.626638 MHz必要 | 状態・survivor経路等の改善と統合P&R。FIFO追加だけでは平均不足を解消しない |
| 時間DI・SDRAM競合 | 直接発行の要求のみは通過。処理時間を入れると32 bytes/clockモデルでも31206 clocks超過。実転置RTL未接続 | 転置並列化・アクセス/仲裁改善と実stage到着条件での期限検証 |
| FPGA全体資源 | 20015 logic/20736、44 BSRAM/46等は未実装stageをallocationで置いた混合診断 | 全stage/接続/tile/PHYを実装・統合して再合成。残721 logicを確定余裕と扱わない |
| 未完成の受信処理 | FIR、同期、TMCC、等化/demap、実T/S DI、RS、TSまで一貫接続していない | 機能・数値精度・規格条件を含む全経路実装と独立oracle照合 |
| 長期・動的条件 | 全mode/rate/階層/位相、実到着包絡、RS burst、選局再同期、出力停止未検証 | 安定queue、状態隔離、reset/flush、最終TS期限の検証 |
| S3のCPU・内部帯域 | S通常2経路はCPU高費用モデル106.8042%/106.6197%。無欠落取得とDMA共存のcore別WCET未確認 | 実搬出実装・計測。専用GPIO方式もCPU占有と受信回路が未確認 |
| SoC/FPGA物理経路 | 34/34信号の算術配置まで。20K実ピン、搭載負荷、独立clock、lane同期未確認 | 具体pin割当、PHY/CDC契約、buffer/CRC費用、実測。内部共通clockのCDCを未解決扱いしない |
| SDRAM電気的タイミング | pad/tri-state/PLL位相/min-max制約が不足、実IO STAなし | メーカー制約を反映したtopとsetup/hold検証。cycleモデルだけでは不可 |
| RFと実機 | 必要占有帯域・C/N、外部変換、S3全量取得、RF→TS品質が未確認 | 対象実機とRF入力を用いた無欠落・誤り率確認 |

前二回の根拠：[全体/CPU/IO](continuation-20261020.md)、[K7と時間DI](continuation-20261020b.md)。
①は停止したまま。①の試した最良候補の棄却と、9K全方式不可能の証明は異なる。

## 現ボトルネックとして扱わないもの

service/reader/K7だけのclock不足（156.739807 MHzで解消）、共有K7状態保存回路の不存在、
一般名だけのdepuncture/soft/hard、全通信路の帯域不足、過去のCAD timeout/Push障害。
これらを現在の障害一覧へ戻さない。今回の3bufferのモデル上の容量・所有権も解消済み範囲に入るが、
実RTLへの実装と期限成立は未完了のままである。

## この検証の区切りと未完了

今回のAは「3bufferの論理所有権・容量と、実アドレス＋仲裁変更の有限比較を完走し、
処理費用を隠して合格にしていない状態で結果を固定する」点。
次のBは「tile転置・ring端数整列・request発行を実RTLとして接続し、実データ、
実処理遅延、面積、配線後clockを同じ構成で検証する」点である。
Bへ進めるソフトウェア上の作業は残っており、実機不足だけを未完了理由にしない。

Aで一度返すのは、抽象producerの速度仮定を増やす探索から、実装を伴う別の検証へ
切り替わる判断境界として選んだからである。Bまで続行する選択も可能であり、
外部障害によって強制停止したという意味ではない。品質面で妥当と考える範囲は、
この有限比較の再現性と不合格/条件付き通過の明示まで。依頼全体を完了したとする根拠にはならない。

その後も、実FFTのclock改善、全復調・復号経路、全条件長期期限、S3実装とWCET、
物理pin/SDRAM STA、RF実機検証は未完了。①は停止維持。正式採用0。
