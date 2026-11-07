# ② SPI割込みの発生数：有限モデルと応答時間への接続

2026-10-27。形式手法の利用許可を受け、有限状態モデルの全到達遷移を検査し、任意長の実行列に適用できる帰納的不等式を作った。runtimeと①は変更しない。実装全体の形式検証ではない。

下位経路の追補：[HAL/LLとIRQ allocatorの照合](../s3-spi-irq-hardware/README.md)。初期doneのsoftware set、開始前clear、設定反映待ち、IRQ matrix切替の共通spinlockを確認。hardwareの時間・原因対応の証明は残る。

## 証明したもの

状態は outstanding / started / REQ published / DMA completed / pending IRQ cause / deferred enable の6変数。1 outstandingを維持し、REQ公開前のDMA開始・完了も許す。REQ公開とDMA完了は各転送1回、公開後の条件付きenable処理と完了の両方を経てからreapして次をenqueueする。IRQ原因は1 pending bitへ合流し、IRQ entryが消費する。開始・reapとISRの詳細な順序制約は緩めており、実機では到達しない列も含む。

到達20状態・44遷移を全探索。`F = published − completed`、`Ψ = pending + deferred − F` として、各遷移で次を検査した。

`IRQ entry数 − 2 × DMA完了数 + ΔΨ ≤ 0`

全到達状態で `−1 ≤ Ψ ≤ 2`。任意個の遷移について加算すると中間のΨが消え、**任意の観測区間で IRQ entry数 ≤ 2 × DMA完了数 + 3** となる。探索深さや実行秒数による打切りはなく、有限グラフ全体の閉包と全edgeの証明書を `result.json` へ保存した。長さを決めたシミュレーションだけから無限継続へ一般化していない。

区間中のREQ公開数を単純に完了数+1とはしない。区間開始前にDMA完了済み・REQ未公開なら、その遅れた公開と次転送の公開が同じ区間に入り、完了0回でも公開2回となる。試験にこの列を含めた。

## 実装照合で訂正した点

前版6b5f009ではREQ公開とwakeを同じ遷移にしていた。しかし固定SDKのreq_coreはatomic ORの戻り値を保存し、その古い値が0なら後でbg_enableする。ORとenableの間にISRが入り、さらにDMA完了/IRQ entryを経る可能性を、同一操作として畳み込んではいけない。

このため公開時はdeferred=1とし、後続のfinish requestで必要ならpendingを立ててdeferred=0にする。途中のIRQ entryはpendingを消費してもdeferredは消費しない。単一ownerがAPI return前にreap/次submitをできない制約も加えた。前版モデルでの証明自体はそのモデルについて有効だったが、実装への適用根拠は不足していた。前版もrefinement未証明としており、実機成立判定は行っていない。

新しいΨで全edgeを再検証すると、範囲は依然−1〜2なので上限式は変わらない。固定SDKのreq_core本体を抽出してhostコンパイルし、OR直後にstatusをISR相当の操作で変更するhookを入れた。初期REQ/PENDの4状態×hook有無の8条件で、現在値ではなくOR前の値によりenableが決まることを確認。これは実req_coreの分岐確認であり、hookの実機到達性や時間の証明ではない。

## 実装との対応と未証明の前提

| モデル | 固定実装で対応する箇所 | 残る条件 |
|---|---|---|
| 1 outstanding | s3_parallel_spi.cのactive/busy、reap後の次submit | 他owner・他device・lifecycle操作なし |
| publish | spi_device_queue_transのenqueue後、spi_bus_lock_bg_request / req_core | 成功経路のREQ公開1回 |
| start / complete | spi_new_transのspi_hal_user_start、SPI転送完了 | 偽完了・中断再開・SCTなし |
| wake | req_coreからbg_enable、spi_bus_intr_enable | 同じ原因から無制限にentryしない |
| IRQ entry | spi_intr / spi_bus_lock_bg_entry | 非再入、無関係な共有IRQ・spurious entryなし |
| reap | get_trans_result成功後にactiveを解放 | queue API return前の再submitなし |

固定spi_master.cはbg controlをspi_bus_intr_enable/disableへ登録する。ISR入口でdisableし、転送を開始した場合はbg_exitでenableする。ownerのREQ公開も必要時にenableする。この構造をモデル化したが、IRQハードウェアのlevel/enable動作まで含む実装→モデルの形式的refinement証明は未完了。特に**各entryをREQ公開またはDMA完了に由来するpending原因へ対応付けられること**を適用条件とする。この条件が確認できるまで、証明済み実機IRQ上限として採用しない。`implementation_refinement_proven=false` を出力する。

## 時間モデルへの接続

同じhostのDMA完了間隔の下限をLとする。32 KiB、command16 bit＋address64 bit、全phaseをmultiline、80 MHz、1 outstandingという既存の条件から、8laneはL=98334 CPU cycle、4laneはL=196668 cycle（240 MHz）。これは物理転送完了同士の間隔に使う。queue API return後の残り時間の下限には使わない。

長さRの区間に入る完了数は保守的に `1 + floor(R/L)` 以下。区間開始時に実行中のISRを追加1回分課金すると、hostごとのCPU処理要求は次で覆える。

`SPI IRQ処理要求 ≤ (6 + 2 × floor(R/L)) × C`

Cは、全normal ISR経路のexecution上限。入口/出口、queue、最大外側loop数、CAS、メモリ待ち等を含める。他のIRQに中断された時間を別eventとして足す場合、その時間をCへ重複計上しない。cross-core lock待ちを含めた有限Cもまだ得ていない。

`worker_event(lanes, C)` は既存worker responseの `burst=3, cost=2C, period=L` へ変換する。これは2 IRQ分をまとめた計算上のeventで、実IRQが必ず対で来るという意味ではない。C未入力・ゼロ等を拒否する。実値がないreportはC=nullのまま。

| SPI2/SPI3 ISR affinity | core0のSPI event | core1のSPI event |
|---|---|---|
| (0,0) | 両host分を加算 | なし |
| (0,1) | host0 | host1 |
| (1,0) | host1 | host0 |
| (1,1) | なし | 両host分を加算 |

raw task ownerはcore0。どの配置もここでは採用しない。Lのlane対応は実際のhost設定へ合わせる。通常反復の測定値にSPI IRQ時間を含めているなら、このevent追加との二重計上を避ける定義が必要。

## 検証結果と残り

全edge帰納式・遅延REQ/enableの例・固定SDK req_core本体・応答モデルとの式一致と境界値・既存worker試験を含む11 unittest成功。試験内のC=7 cycleはインターフェース検証用の架空値で、実機の推定値ではない。

これまで未入力だったSPI eventの**発生数の式を条件付きで具体化**した。残るのは実装とのrefinement、各hostのC、他IRQ/criticalの干渉、H/S/W/R等の実時間上限。RF ABI、全受信機の資源・全FPGA fit/STAも未完了。性能合格・正式通信路割当・採用0。

再現:

```sh
python -m experiments.s3_spi_irq_envelope --output reports/s3-spi-irq-envelope/result.json
PYTHONPATH=tests python -m unittest test_s3_spi_request_enable test_s3_spi_irq_envelope test_s3_worker_response -v
```
