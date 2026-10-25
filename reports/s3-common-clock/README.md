# ② 共通絶対時刻をRF期限とpackingへ渡す経路

2026-10-25。従来のnative取得APIは、coordinator coreの32-bit cycle countを受信開始時の0へ延長していた。この値を、別coreのcycle countやSDK起動時起点のesp_timer時刻と比較してはいけない。

今回 `s3_native_start_sink_clocked` と `s3_pp_native_start_clocked` を追加。呼出し側が渡した64-bit common clockの絶対値を維持して、RF bankのnow/deadlineを生成する。両workerの既存 `s3_pp_step_clocked` に同じcallback/contextを渡せる。単位は既存native演算に合わせて1/240 MHz。追加のper-core時刻延長状態、clock lock、動的確保はない。旧32-bit APIは既存の単core模型向けに残し、今回の共通clock経路ではio.cyclesをNULLにできる。

**ハードウェア共通時計の実装・精度・待ち時間の確認まで完了したわけではない。** 今回実装したのは、実CのRF→bank期限→worker比較を同じepoch/単位で動かす接続経路と異常時処理。FreeRTOS実taskはまだ起動しない。raw SDK link probeの保持対象をclocked startへ変更し、そのコードと追加stateをSDK全体で検証する。

## 時計異常と所有権

callbackのUINT64_MAX、native内での逆行、deadline加算可能範囲を超える値をCLOCK_FAULT=8としてRF停止・SELECT復元。poll内の各時計読出しの後でfaultを確認し、失敗値を使ってbank acceptや成功returnへ進まない。accept後の最終読出しで失敗した場合は、既に渡したbankを取り消さずRFを止める。worker/DMAの所有権は維持し、停止・再初期化は既存のquiesce契約に従う。

`UINT64_MAX - 2*THRESHOLD*cpp`までを時計値の許可上限とする。これは固定の運用timeoutではなく、実際のdeadline加算がuint64 overflowしないための算術条件。開始時にも検査する。

## 確認したこと

- 実nativeと実packingを通した既存host受渡し試験を、旧時計/共通時計×T/S×正常/worker停止の8ケースへ拡張。共通時計の開始値は2^40を超え、下位32-bit境界も横断する。io.cyclesはNULLとし、callbackの絶対値とcapture.now一致を確認。正常時はそれぞれ80 banks、全送信byteを独立20-bit期待列と照合。
- 時計読出し失敗を起動の2点、poll入口/末尾、SELECT切替後、accept前/後へ注入。RF停止・SELECT復元、accept前失敗なら未受渡し、accept後失敗なら受渡し済みであることを確認。逆行と算術上限の両側も確認。
- 既存のpthread packing、SPI lease、clocked deadline、native capture、全開始位置fillを含む合計8 unittest成功。UBSan有効。これらの時計は合成で、callback/packing/storeの実時間を測定していない。
- 実native/parallel adapterをS3 GCC14.2 O2・最小SDK宣言stubでobject compile成功。SDK link・メモリ配置・命令数は今回の追加後に再確認する。直前の204.776 Mcycles/sやメモリ残量を新コードの成立保証に使わない。

## 1µs時計をそのまま接続しない理由

`esp_timer_get_time()*240`なら単位だけはそろうが、nativeのsettling判定は16 samples。Sでは96 cycles=0.4µs、Tでは240 cycles=1µsである。例えばSで切替が0.99µs、次観測が1.00µsなら、実経過0.01µsでも切捨てµs差は1µsになり、0.4µsを待ったと誤判定し得る。入力が常にこの位相になるという主張ではなく、無補償接続が安全でない反例。

したがって、このAPIへ無補償のµs時計adapterは追加していない。次は実際の共通clockの分解能・読出し誤差・SDK内の更新待ち/整合性再試行の上限を確認し、必要ならsettling/age/worker deadlineを安全側へ補正して接続する。時計関数の公称命令数をWCETと扱わない。その後、RF準備開始位相・packing slice・SPI送信・割込みを含む実task scheduleを評価する。通信路の正式割当・採用は性能条件の成立後。①は変更しない。

再現: `python -m unittest tests.test_s3_native_clock tests.test_s3_parallel_pack tests.test_s3_native_capture tests.test_s3_parallel_deadline tests.test_s3_native_fill`。
