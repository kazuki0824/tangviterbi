# ② raw packing：連続区間の境界判定をまとめる

従来のworkerは8sample/20bytesごとに64bit出力位置、arena番号、入力位置、境界・alignmentを再計算していた。`s3_parallel_pack.c`を変更し、安全な連続block数を残slice・入力bank末尾・出力arena末尾の最小値として一度計算する。内側では`pack_eight`、二つのpointer更新、loop判定のみを繰り返す。既存のsource/payload所有権、持越し、境界slow path、slice終了時の時計とDONE公開順序は維持する。

fast pathの既存条件は少なくとも1blockを保証する。最初の出力が4byte整列なら20byteずつ進めても整列を保つ。sourceは8wordずつ進め、run長で折返しを避ける。run末尾では外側で再計算するので、次のarenaやinput wrapへそのまま突き抜けない。期限確認頻度は元と同じslice単位であり、run長を増やすためにmax_pairsを緩めてはいない。

[target compile監査](target/results.json)では、O2の定常caller loopは6命令、Osはstackへの退避・復帰を含む11命令。pack_eightはどちらも39命令。合計はO2が45命令/8sample＝5.625命令/sample、Osが50命令/8sample＝6.25命令/sample。理想1命令/cycleならT90/S225（O2）、T100/S250（Os）Mcycles/s。これは長い連続runの反復部分のみで、run算出・slice選択・slow path・clock・終了公開・memory待ち・割込みを除く。旧8 cycles/sampleのWCETを証明せず、旧owner-budgetの未分類残額をこの数字で差し替えない。targetはfreestanding objectで、SDK全体の配置結果でもない。

[境界試験](tests.log)は実C＋UBSanで、入力開始位置9種、出力位置10種、prefix有無、worker区間開始2種、長さ7種、slice長6種＝15120条件を検査。独立した20bit連結基準と出力全域を比較し、書いてはいけない領域が不変であることも確認。既存の2worker並行、DMA逆順完了、queue失敗、stalled worker、時計/期限の試験も実行した。

既存SDK CIのpath filterにparallel_packと共有packing headerがなく、この変更だけでは再buildされないため追加した。同じworkflowで新境界試験も実行する。SDKのIRAM/heap結果はこのcommitのCIで再確認が必要で、旧残量を新実装の確定値として使わない。

次に必要なのは、run初期化・slow path・各sliceの実行回数を、実際のbank長とworker分担へ対応させた費用集計。その後に共通時計、RF poll、SPI APIとのcore別期限を閉じる。①とFIR比較の結論は変更しない。

## 実Cの経路回数を各workerへ対応させる

[計数script](../../ci/s3_pack_path_audit.py)はproductionファイルを変更せず、一時copyのrun開始とslow pairへcounterだけを追加してホストで実行する。[harness](../../experiments/s3_pack_path_probe.c)は実際のaccept・clocked step・collect・take・completeを使用し、各bankの出力全byteを独立した連続20bit列と比較する。単なる分岐条件のPython模写ではない。計数copyのhashとproduction hashも[結果](path-counts.json)に記録した。

bank長12288/12289/14288、先頭0/16380、slice64/128/512/1024 pairの24条件を各64bank実行。12288の場合は出力arena offsetの全周期を覆う。他の長さでは64bankの有限試験であり全周期ではない。奇数長は実acceptの持越しを通る。workersは順次実行、DMAは即時完了、時計は常に0であり、実時間schedule・RF品質の検証ではない。空workerへのpoll、割込み、実機のbank長分布はこの計数外。

例：12288sample/bank、先頭0、512pair/slice、現在の等分packing：

| 1worker当たり | T /秒 | S /秒 |
|---|---:|---:|
| 連続run開始 | 8300.781 | 20751.953 |
| 8sample block | 999511.719 | 2498779.297 |
| slow pair | 1953.125 | 4882.813 |
| slice | 7812.5 | 19531.25 |
| clock callback | 15625 | 39062.5 |

64bankで1workerのblockは49128回、runは408回。境界判定のまとまり数は約120.4分の1だが、処理時間が120.4倍速いという意味ではない。先頭16380の入力wrap条件ではworker0のslow pair回数が増えるため、先頭0の費用を全caseの上限に使わない。

下記の実SDK命令列の反復部分45命令/blockを理想1命令/cycleとした寄与は、上記Sの1workerで112,445,068.359 cycles/s。240MHzから残る127,554,931.641 cycles/sは、run初期化・slow pair・slice管理・clock・RF・SPI・割込み・stallをまだ払っていない額である。[全24条件×T/S×workerの係数表](path-budget.json)では次の式として未計測項を分離した。

`worker費用 = 45×block回数 + R×run回数 + P×slow pair回数 + H×slice回数 + C×clock回数 + 所有するRF/SPI等 + stall`

R/P/H/Cはそれぞれのcycle費用。Hはbodyとclockを除いたslice処理と定義し、二重計上を避ける。45も実WCETではないので、stall等の上限なしにこの式を保証値へ変えない。旧8cycles/sample模型から引いた未分類残額を、この式のRF費用として確定扱いしない。

実C出力一致・pairs保存・clock回数の24チェックに加え、全条件被覆、独立したslice回数式、slice短縮時の呼出し増加を確認する[3 unittest](path-tests.log)に合格。次はR/P/H/CとRF/SPIの実装対応を埋める。各coreの期限確認が完了したわけではない。


## SDK CIの結果を回収

[run 40114080196](https://github.com/kazuki0824/tangviterbi/actions/runs/40114080196)は成功。対象commitはaf66386で、成果物のpacking source hashと現行sourceの一致も確認。[provenance](sdk-provenance.json)、[ELF/map/config/logと静的監査](sdk/)を保存。共通40＋raw専用45＝85静的checkが合格。

共通構成はIRAM末尾/heap開始が各256 B増加した。raw専用構成は `_iram_end=0x40387800`、`_heap_start=0x3fcac540` で前回と同じ。コードが増えても整列を含む配置境界が同じ場合があり、共通構成の増分をrawへ一律適用しない。[既知動的費用](runtime-memory.json)を再実行した19チェック、[限定したSPI ISR配置](isr-placement.json)の26チェックも合格。較正中15,740 B/定常17,612 Bは既知費用控除後の**上限**であり、全起動確保・断片化を含む利用可能量の下限ではない。TLSF起動順の再生と実bootは今回新たに実行していない。

実SDKはperformance最適化設定。リンク済みELFの[step](sdk-step.dis)と[packing](sdk-pack.dis)から、caller反復6＋packing39＝45命令を確認した。[要約](sdk-loop-summary.json)。前回のfreestanding O2に対応する回数で、Osの50命令をこのSDK実行列の値として使わない。[費用係数の再現script](../../ci/s3_pack_path_budget.py)も保存。

成果物は依然link-only probeであり、RF/worker/SPIの実taskを起動した受信試験ではない。今回閉じたのは前回変更のSDK静的配置確認と有限条件の経路回数。R/P/H/CとRF/SPI等の費用、各core deadlineは未完。

## run・境界・slice管理の命令数を埋める

[分岐先から再decodeする監査](../../ci/s3_pack_cfg_audit.py)を追加し、固定したSDK ELFの実際に到達できる命令と分岐を取得した。[CFG](cfg/cfg.json)、[読みやすい命令一覧](cfg/reachable.txt)、[計数結果](cfg/results.json)。単純な線形objdumpではpaddingからdecodeしたため分岐先が別命令の途中に見える箇所があった。これを放置せず、関数入口・条件分岐の両方・jump先から読み直した。実装の不正命令ではなく表示の問題であり、既存packing本体39/反復45の値は変わらない。

sourceで回数を制限している4つのloop（3bank走査、block反復、5byte書込み、slice内dispatch）のback edgeを取り除くと、残りが非循環になることを確認した。slice管理・run管理では互いに排他的なbranchもすべて足すため、次は**宣言した成功経路・visit条件における保守的な命令数集計**であり、実時間上限ではない。

| 単位 | 命令数の係数 | 含む範囲 |
|---|---:|---|
| 8sample block | 45 | caller反復6＋pack_eight39 |
| run開始 | 118 | slice内位置計算・境界判定・run初期化/後処理。slow側の排他branchも含む保守値 |
| slow pair | 173 | 上記118＋5byte loopの11命令×5 |
| slice | 213 | step_implのbody外150＋bank走査追加2回×17＋clocked wrapper29 |

`命令数集計 = 45×block + 118×run + 173×slow pair + 213×slice`

run項は全bulk反復を除き、slow項はbyte loopを別に加算する。slice項はrun/slow bodyを除く。clock callbackへのcall命令は含むがcallee内部は含まない。pack_eight内部は45へ含むため別途足さない。実taskによるwrapperの呼出し・空job poll・RF/SPI・interrupt/context spill・pipeline/cache/bus待ちは別。分岐回数は前節の実C計数24条件に対応するもので、全てのRF入力量分布を検証したわけではない。

12288sample/bank、512pair/slice、先頭0なら、各workerはT47.959/S119.899 M命令/s以下という集計になる。先頭16380ではworker0がT48.802/S122.005へ増える。これに全命令1cycleという理想仮定を置けば同じ数値のMcycles/sとなるが、**保守的な命令数を数えたことは、1命令1cycleという仮定を保守的にするものではない。** 実行時間保証とは区別する。[96ケース](cfg/results.json)。

CFGの内部edge閉包、命令領域の非重複、padding誤decodeの回帰、ELF hash、領域分割と時計待ち未確定の扱いを[3 unittest](cfg/tests.log)で確認。実機又は完全なCPU emulatorでこの命令列を実行した試験ではなく、CとCFGの完全な形式的同値証明でもない。

### 共通時計候補の内部も確認

同じELFの `esp_timer_get_time`、`systimer_hal_get_counter_value`、`systimer_ticks_to_us` を調べた。通常のSDK初期化で換算function pointerへ後者を登録することも[pinned source](cfg/timer-source.json)で確認。callback候補の命令数は初回成功なら40命令、counter更新待ちの追加反復ごとに3命令、値整合性の再読出しごとに6命令。さらにMMIO等の待ち時間、callback adapterの費用が必要になる。

更新待ち・再読出し回数の上限をまだ得ていないため、40cyclesを時計のWCETとして代入しない。現在のnative取得のcore別cycle時計と同じepoch/単位だとも扱わない。共通時計への統合にはdeadline・bound・RF pollを同じ時刻基準へ変換する実装と検証が必要で、このAPIを呼ぶだけで契約が満たされるわけではない。

今回、以前R/P/Hとして未算入だったcaller処理の**命令数係数**を埋めた。残るのは命令・MMIO待ちの費用、共通時計とRF/SPI担当処理の統合、各coreの期限。受信機採用は増えていない。

## RF担当coreのsentinel費用

[次bank準備のSDK命令数と位相条件](native-prepare/README.md)を追加。公称S入力ではfill bodyだけで116.667 M命令/s。旧API仮定と現在の等分packingを足した条件付きcoordinator模型は251.215 Mcycles/sとなり、余裕ありと扱えない。命令訪問数の保守性・API未測定のため、不可能の証明にも使わない。

## sentinel連続区間化の実装

[全開始位置の機能試験とtarget object](native-fill-optimized/README.md)。各wordのmask/address計算を区間開始へ移し、bodyは5→3命令。公称Sで46.667 M命令/sを削減。SDK全体の配置確認と、phaseを含む期限検証は別に必要。

## 共通時刻への接続経路

[RF期限とworker比較の共通epoch対応](../s3-common-clock/README.md)を実装。64-bit絶対時刻のまま受渡し、時計異常時停止を試験。ハードウェア時計の精度/待ち時間と実task scheduleは未完。
