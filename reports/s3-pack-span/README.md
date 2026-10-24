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
