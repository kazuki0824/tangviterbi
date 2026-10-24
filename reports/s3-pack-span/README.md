# ② raw packing：連続区間の境界判定をまとめる

従来のworkerは8sample/20bytesごとに64bit出力位置、arena番号、入力位置、境界・alignmentを再計算していた。`s3_parallel_pack.c`を変更し、安全な連続block数を残slice・入力bank末尾・出力arena末尾の最小値として一度計算する。内側では`pack_eight`、二つのpointer更新、loop判定のみを繰り返す。既存のsource/payload所有権、持越し、境界slow path、slice終了時の時計とDONE公開順序は維持する。

fast pathの既存条件は少なくとも1blockを保証する。最初の出力が4byte整列なら20byteずつ進めても整列を保つ。sourceは8wordずつ進め、run長で折返しを避ける。run末尾では外側で再計算するので、次のarenaやinput wrapへそのまま突き抜けない。期限確認頻度は元と同じslice単位であり、run長を増やすためにmax_pairsを緩めてはいない。

[target compile監査](target/results.json)では、O2の定常caller loopは6命令、Osはstackへの退避・復帰を含む11命令。pack_eightはどちらも39命令。合計はO2が45命令/8sample＝5.625命令/sample、Osが50命令/8sample＝6.25命令/sample。理想1命令/cycleならT90/S225（O2）、T100/S250（Os）Mcycles/s。これは長い連続runの反復部分のみで、run算出・slice選択・slow path・clock・終了公開・memory待ち・割込みを除く。旧8 cycles/sampleのWCETを証明せず、旧owner-budgetの未分類残額をこの数字で差し替えない。targetはfreestanding objectで、SDK全体の配置結果でもない。

[境界試験](tests.log)は実C＋UBSanで、入力開始位置9種、出力位置10種、prefix有無、worker区間開始2種、長さ7種、slice長6種＝15120条件を検査。独立した20bit連結基準と出力全域を比較し、書いてはいけない領域が不変であることも確認。既存の2worker並行、DMA逆順完了、queue失敗、stalled worker、時計/期限の試験も実行した。

既存SDK CIのpath filterにparallel_packと共有packing headerがなく、この変更だけでは再buildされないため追加した。同じworkflowで新境界試験も実行する。SDKのIRAM/heap結果はこのcommitのCIで再確認が必要で、旧残量を新実装の確定値として使わない。

次に必要なのは、run初期化・slow path・各sliceの実行回数を、実際のbank長とworker分担へ対応させた費用集計。その後に共通時計、RF poll、SPI APIとのcore別期限を閉じる。①とFIR比較の結論は変更しない。
