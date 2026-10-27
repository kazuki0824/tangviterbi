# ② SPI atomicの実バイナリ分岐とISR内再試行

2026-10-27。保存済みlauncher SDK ELF（SHA-256はaudit.json）を公式Xtensa toolchain esp-14.2.0_20241119で再解析した。toolchain archive SHA-256はe3e6dcf3d275c3c9ab0e4c8a9d93fd10e7efc035d435460576c9d95b4140c676。runtimeと①は変更しない。

追補：[owner側の検算](../s3-spi-owner-atomic/README.md)で、同じ正常経路条件下の失敗CASを保守的に最大4回とした。以下の「owner側未確定」は本監査時点の記録。elapsed上限は引き続き未確定。

## 実際に通る分岐

REQ公開は `__atomic_fetch_or_4`、REQ→PEND移動はORとANDを呼ぶ。これらは引数アドレスに0xc4000000を加えた32 bit値を0x01ffffffとunsigned比較する。すなわち0x3c000000〜0x3dffffffならfallbackの共通s_atomic_lockを取得し、それ以外ではS32C1I helperへ進む。

SPI bus lockは固定SDKで `MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT` により確保される。現在の内部RAM配置条件では上記fallback領域に入らず、SPI status更新はS32C1I経路を通る。従ってfallbackに存在するWAIT_FOREVER spinlockを、このstatus更新の通常経路へ誤って課金しない。ただしFreeRTOS queue lockやwatchdog lockも消えるという意味ではない。

OR helperのCASは0x40385ca6、後方分岐は0x40385cab→0x40385c9e。ANDは0x40385c8a、0x40385c8f→0x40385c82。各attemptは比較元保存、OR/AND、SCOMPARE1設定、S32C1I、戻り値保存、不一致分岐の6命令。初回load等は別にある。6命令を6cycleとはしない。

## ISR側に限る競合回数

前回の単一device/owner・1 outstanding・ISR非再入条件下では、当該ISR中にownerが同じstatusへ行う書込みはreplacementのREQ公開1回まで。IRQだけで値が勝手に変わるのではなく、他のwriterがそのメモリ値を変更した場合にS32C1Iの比較が不一致になる。

この1回の変更は、実行中のISRのどれか1個のRMWに最大1回の失敗を起こせる。失敗後はS32C1Iが返した現在値を次の比較元にする。別の変更がなければ次は成功する。従って**ISR全体で追加CAS attemptは最大1回**。同じcoreでownerがISR中に走らなければ、この相手による追加attemptは0回。

これは同一statusを更新する他writerがなく、S32C1Iの比較交換動作が前提通りという条件付きの回数上限。owner側のREQ更新には、並行ISRが複数のstatus更新を行い得るので、この「最大1回」を対称に流用しない。owner側の再試行上限は未確定のまま。

## 検証と残る時間根拠

実ELFの分岐・helper呼出し・CAS/後方edge・IRAM配置・内部確保を16チェックで確認。branch-aware disassemblyはreachable.json/txtに保存した。sourceのatomic API名だけで機械語を推定していない。

独立interleaving試験では2周分を過大に覆う6 RMWと、相手の1回のREQ公開を各read/CAS境界に挿入。初期値8条件についてISR全体の追加attempt≤1を確認。前回のISR外側loop/SDK実C primitive試験も含め4 unittest成功（tests.log）。host上の競合モデルであり実Xtensa計測ではない。

未確定なのはowner側の競合回数、S32C1I/メモリのelapsed、queue critical待ち、IRQ到達遅延と他IRQによる中断、DMA競合を含む全体応答。今回の16チェックと4試験を実時間の合格には置き換えない。性能合格・正式割当・採用は0。

再現:
```sh
python -m ci.s3_spi_atomic_audit --toolchain build/toolchain/xtensa-esp-elf --output build/spi-atomic-audit
PYTHONPATH=tests python -m unittest test_s3_spi_atomic_interference test_s3_spi_isr_rounds test_s3_spi_lock_primitives -v
```
