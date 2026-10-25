# ② 共通時計の接続・量子化補正・読取り待ち評価

2026-10-25。対象は依頼の手順1/2のみ。①と実task schedule（手順3）には進まない。

## 実装した接続

SDK public API `esp_timer_get_time()`（pinned IDF 5.5.1ではSYSTIMER counter0）を使う `s3_timer_clock` を追加した。新規timer割込み・周辺回路・heap・共有可変状態・spinlockを追加しない。SDKの初期化済み時計を両coreから読む。受信中はsleep、counter再設定、debug haltを行わない前提。native MMIO callbackが切替を完了する契約と、RF境界検出自体の実機妥当性は既存の別確認事項。

`esp_timer_get_time()`をµs整数qとすると、adapterは `U=(q+1)*240` を返す。単位は1/240 MHz、epochはSDK起動時で、誤差幅E=240。この値はCPUのCCOUNTではなく、同じ時間単位に換算した上端値。clock契約は **U−E ≤ 時計が観測した時刻 ≤ U**。負値・乗算overflowはUINT64_MAXとして失敗する。

- `s3_pp_native_start_timer` がnativeへcallback/contextとEを設定する。
- 両workerは `s3_pp_step_timer` を使用する。内部では `s3_pp_step_clocked_quantized` が同じcallback/Eを使う。
- coordinatorのcollectにも `s3_timer_clock(NULL)` を渡す。workerからcapture.nowを読む必要はない。
- SDK link probeは新start/worker/clockを保持する。probe自体はRF/PHY/SPI/tasksを起動しない。

旧APIはE=0の正確な合成時計や従来の単core模型向けに残す。`s3_pp_native_start_clocked` / `s3_native_start_sink_clocked` はclock_error引数を追加した。未補償µsを旧E=0経路へ渡してはいけない。

## 安全側の時刻比較

切替前に取得したUから `switch_earliest=U−E` を保存し、切替後の時計上端を `switched` として保存する。前後のcallback間に切替処理が完了する契約なら、実切替時刻はこの区間内にある。poll入口の既存読出しを切替前側として使い、専用の追加読出しは設けない。

| 判定 | 使用する量 | 安全側になる理由 |
|---|---|---|
| settling最小待ち | `now_upper−switched−E ≥ 16*cpp` | 現在の下端から切替の上端を引くので、実経過を過大評価しない |
| bank age上限 | `now_upper−switch_earliest ≤ (16384−128)*cpp` | 現在の上端から切替の下端を引くので、実経過を過小評価しない |
| bank期限 | `switch_earliest + 2*THRESHOLD*cpp − 20000 − (1024+LATE)*cpp` | 切替後の遅い時刻を起点にして期限を延ばさない |
| worker開始前 | `now_upper + bound < deadline`（減算で検査） | 開始観測時刻を早く見積もらない |
| worker終了後 | `finished_upper < deadline`かつ`finished_upper−started_upper+E ≤ bound` | 終了の遅れと量子化によるelapsed過小評価を検出 |

callbackの**採時点からreturnまで**、最後の確認からDONE公開までの費用は、この区間のEに含めない。Eは量子化幅であって全callback WCETではない。これらは呼出し処理のWCET/boundへ別計上する必要がある。今回、この未確定費用を0と仮定して性能合格にはしていない。

例えばSの16 samples待ちは0.4µs。切替0.99µs→次観測1.00µsの例では、未補償µs差は1µsだが、補正後の最小経過は0以下となり受渡しを許可しない。待ちの増加は処理遅延であり、IQの間引き・再量子化・欠落を許可する変更ではない。

## 検証

`tests/s3_timer_clock_host.c` は実SDK adapter（esp_timer_get_timeだけをmock）、実native、実packingを使用。240通りのµs内位相×721経過値×T/S＝346080ケースで、早すぎるsettling許可がないこと、期限を実切替より後ろへ延ばさないことを検査。age上限、負値/overflow、worker量子化幅込みのbound境界、開始前期限も確認。

既存受渡しは旧/正確な共通/µs量子化共通×T/S×正常/worker停止の12ケースへ拡張。正常は各80 banks、全送信byteを独立期待列と照合。時計異常時のRF停止・SELECT復元、accept前後、既存pthread/SPI lease/deadline/fillを含む合計9 unittest成功。host時計は合成、実時間測定ではない。ログは quantized/tests.log。

## 読取り待ち時間の評価結果

根拠は[固定SDK source](source-provenance.json)とTRM v1.8 §11.4.1/§11.4.3/§11.5.1。source snapshotをsourcesへ保存した。

1. `esp_timer_impl_get_time`→`systimer_hal_get_counter_value`がUPDATEを書き、VALUE_VALIDを待つwhileを実行する。
2. low/high/lowが整合するまでdo/whileを繰り返す。SDKはISRからの再読出しをこの処理の理由としている。別coreも同じcounter snapshotを更新できる。
3. TRMはUPDATE→VALID待ち→値読出しの手順を指定するが、確認した該当節にUPDATE完了の最大cycle数はない。SDK sourceにも有限の最大反復回数はない。
4. 旧SDK実命令列で確認した追加反復費用はready待ち3命令、整合性再読出し6命令。ただし1命令1cycleやMMIO待ち0を上限として使わない。新adapterと新SDK配置の費用は再確認する。

したがって、**量子化補正を含む接続は実装済みだが、clock読取りWCETの有限な数値上限は未証明**。これはハードウェアが通常無限に待つという主張ではない。上限を導くには、UPDATE/MMIOの最大応答時間と、ISR・他coreによるsnapshot更新/割込みの到来・実行時間制約が必要。現在の資料・実装だけから数値を創作しない。任意回数で打ち切るtimeoutも追加していない。失敗停止を加えるだけでは、必要な連続受信が成立する証明にはならないためである。

手順2の完了条件「安全な共通時刻判定」に対して量子化の誤判定は解消したが、全callback所要時間まで含む保証は残る。**手順2全体の完了とは報告しない。** 実行順序・IRQ予算の仮定を必要とする部分は手順3との依存として明記し、今回は手順3の実装を追加しない。

## 手順1：前回6e689acのSDK確認

[SDK CI 40195029323](https://github.com/kazuki0824/tangviterbi/actions/runs/40195029323)成功。共通40＋raw専用45 check、capture stateは144→152 B、raw専用heap開始0x3fcac648。成果物をsdk-beforeへ保存。新ELFでメモリ台帳19check、限定SPI ISR配置26checkも成功（JSON参照）。これは量子化補正追加**前**の結果で、新コードの配置は別途確認する。

[RF共存診断40195029317](https://github.com/kazuki0824/tangviterbi/actions/runs/40195029317)も成功し、前回の依存ヘッダ漏れは解消した。一方、receiver functional closureのnew-components jobはpyelftools未導入とS3_ROM_ELF未設定で2件エラー。workflowへ固定pyelftoolsと、IDF tools.json指定ROM archive（SHA256照合後rev0 ELFのみ取得）の準備を追加。該当6 unittestはローカルで成功。試験をskipしていない。今回コードのSDK/CI結果は追記する。
