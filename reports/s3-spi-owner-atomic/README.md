# ② owner側REQ公開のCAS再試行上限

2026-10-27。前回の[実ELF監査](../s3-spi-atomic-path/README.md)を使い、owner側に残っていた競合回数を検算した。runtimeと①は変更しない。

## 結果と適用範囲

**REQ公開1回あたり失敗CASは保守的に最大4回、成功を含むattemptは最大5回。cycle上限ではない。** 単一SPI host/device、単一owner、各port outstanding 1件、bus acquireなし、ISR非再入、受信中にdevice登録/解除・lock初期化をしない条件。二つのhostのstatusは別なので、この回数にもう一方のstatus変更は足さない。もう一方のIRQが奪う時間は別途必要。

この上限は同一core・別coreの両方を覆うが、最小上限ではない。同一coreのISR中にownerは走れず、複数の変更が1回の比較までにまとまる場合もある。実スケジュールで4失敗が到達可能とは主張しない。

## 導出

ownerのORが成功するまで、このownerはREQをまだ公開していない。別ownerも存在しないので、その間REQを0から1にするwriterはいない。ISRは既存REQをPENDへ移す `update_pend_core` と、queueが空ならPENDを落とす `clear_pend_core` だけでstatusを更新する。LOCK/WEAK_BG等はこの正常経路では変更しない。

REQがあればISRはPENDを立て、その後REQを落とす。非再入なのでREQを落とす前に別ISRが同じ移動を開始することはなく、REQが落ちた後は新しいREQ公開がない限りPENDを立て直せない。従ってPENDを立てる変更は最大1回、REQを落とす変更も最大1回。PENDを落とす変更は、既存PENDに対する1回と、その後立ったPENDに対する1回を保守的に許す。

値が変わる書込み列は `clear PEND → set PEND → clear REQ → clear PEND` の部分列で覆える。ownerの開始がISRの途中でも、先頭の操作を省いた部分列に含まれる。ISRがDMAを開始して終了し、後続の完了ISRへ進んでも、REQの再公開前である限りこの回数は復活しない。値を変えない書込みは比較値CASの失敗を増やさないため列から除いてよい。

実ELFのS32C1I helperは失敗時に返された実値を次の比較元にする。1回失敗するには前のload/失敗後に少なくとも1回の値変更が必要なので、最大4変更から失敗は最大4回。最初のload等を除くloop本体は1 attemptあたり6命令で、最大30命令となるが、これを30 cycleとは扱わない。

## 検証と限界

`experiments/s3_spi_owner_atomic.py` はREQ/PENDの初期4状態と書込み列の16部分列、計64条件を探索する。ownerのload、失敗後の実値再利用、成功までの各境界にISRの書込みを挿入し、任意の再試行回数で探索を打ち切らない。抽象列には到達不能な組合せも含める。`result.json` はその過大近似の結果であり実行時間測定ではない。

固定SDKの実Cから抽出するprimitive試験に `clear_pend_core` を追加し、全REQ/PEND状態の変更と戻り値を確認した。既存ISR回数・ISR側CAS試験と併せて7 unittest成功。SDK全体と抽象モデルの形式的同値証明ではない。新しいELFを生成したり、前回の16バイナリチェックを再実行した結果ではない。

これでこの条件下のowner側status CAS回数は有限上限を持つ。しかしS32C1I/メモリのelapsed、queue/watchdog critical待ち、IRQ遅延・干渉、公開遅延HとSPI応答S/W/Rの数値上限は未確定。RF ABI、全到着列と継続動作、全FPGA fit/STAも未証明。性能合格・正式通信路割当・採用は0のまま。

再現:

```sh
python -m experiments.s3_spi_owner_atomic --output reports/s3-spi-owner-atomic/result.json
PYTHONPATH=tests python -m unittest test_s3_spi_owner_atomic test_s3_spi_atomic_interference test_s3_spi_isr_rounds test_s3_spi_lock_primitives -v
```
