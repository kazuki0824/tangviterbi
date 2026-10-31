# ② 単一未完了転送でのSPI ISR外側ループ

2026-10-27。前回監査で未確定だった `spi_intr` の外側do/whileについて、現在のraw構成に限定した回数上限を検算した。runtimeを打ち切り回数付きに変更したわけではない。①も変更しない。

## 条件付きの結論

| ownerと当該hostのISR | 外側ループの最大周回数 |
|---|---:|
| 同一core | 1 |
| 別core | 2 |

条件は、当該SPI hostに登録deviceが1個、bus acquireを使わず、API ownerが1個、各portの未完了転送が1件、当該ISRが再入しないこと。他task/ISR/supervisorが同じdeviceへqueue/reapしないことも必要。rawのactiveフラグはqueue前に立ち、成功したreap/complete後にのみ下がる。ownerはこのフラグが下がるまで次を送れない。

完了ISRは外側loopより前に旧転送のdescriptorをret_queueへ返す。別coreのownerはそれを回収し、同じISRの終了前に次の転送を1件enqueueできる。ただしその次の転送が完了するのは後続ISRなので、この外側loop中に2件目のreplacementを送り続けることはできない。同一coreのownerはISR中には実行しない。

## 2周となる理由

SDKはqueueから転送を取得できた周に `wip=true` でbg_exitへ進み、無条件で外側loopを終了する。取得できない周ではPENDをclearし、REQ/PENDが残らなければ終了する。別coreのownerがその前後でenqueue→REQ公開を行うと、emptyを見た後にREQを見て1回retryできる。その次の周には既にenqueue済みの1件を取得して終了する。enqueueがREQ公開より先であることが重要である。

「SDK一般で2周」「全loopが2周」「2周なら一定cycle」とはしない。複数device、他publisher、bus acquire等を加えれば、この導出は適用できない。

## 実施した検算

REQ/PEND、queue状態、producerのenqueue前/REQ公開前/完了状態、ISR各操作を状態として、全割込み位置のinterleavingを探索した。REQ snapshot、PEND set、REQ clearを別操作として扱い、その間へのproducer介入も列挙。保守的な初期状態16条件、合計223状態（各初期状態の集計なので重複を含む）で最大2周。同一coreとしてproducer介入を除外すると全条件1周。

探索は固定の最大周回数で打ち切らない。到達状態の再訪を検出した場合は有限上限の証明失敗として例外にする。今回の抽象状態グラフにcycleはなかった。

さらに保存済み固定SDKから `update_pend_core`、`spi_bus_lock_bg_check_dev_req`、`bg_exit_core` の実C関数本体を抽出してコンパイル。REQ/PENDの全4状態とwip条件について、bit移動・出口条件を確認した。atomicを逐次shimへ置換したhost試験なので、XtensaのCAS再試行やメモリ時間の検証ではない。関数本体とモデルの全動作が形式的に同値であるとの主張でもない。

関連7 unittest成功（tests.log）。実packing/native/SPI adapterの既存機能試験も含む。全実機スケジュールやCI成功とは区別する。

## 時間上限へ残るもの

外側loopの回数について未知を一つ減らしたが、各周内のatomic RMW、queue critical section、descriptor設定、割込み前後の遅延、メモリ/DMA競合のelapsed上限は残る。従って2周を2cycle等へ換算しない。前後処理費用＋各分岐の周回費用をcore別の応答時間へ課金するための根拠である。

割込みaffinity (0,0)では両hostとも1周条件、(0,1)/(1,0)では片方に2周条件、(1,1)では両方に2周条件を用いる。ただしcore0へ集約するとRF処理への割込み干渉が増えるので、これだけで配置を採用しない。

性能合格・正式割当・採用は0。数値の時間上限、全到着列、RF ABI、SoC全メモリ、全FPGA fit/STAは未完了。

再現:
```sh
python -m experiments.s3_spi_isr_rounds --output build/spi-isr-rounds.json
PYTHONPATH=tests python -m unittest test_s3_spi_isr_rounds test_s3_spi_lock_primitives test_s3_parallel_pack -v
```
