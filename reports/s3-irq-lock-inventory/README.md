# ② IRQ allocator共通lockの利用者とSPI_UPDATE資料確認

2026-10-27。前回の「他coreの共通lock利用」を固定source全体で具体化した。runtimeと①は変更しない。

## 共通lock利用者

固定intr_alloc.cから直接spinlockを取得する全関数を列挙し、11関数を確認。sourceのhashを既存manifestと照合した。

| 分類 | 関数 | 受信中の扱い |
|---|---|---|
| 予約・登録・解除等 | esp_intr_mark_shared / esp_intr_reserve / esp_intr_alloc_intrstatus_bind / esp_intr_set_in_iram / intr_free_for_current_cpu | 初期化後に実行しない条件を課す場合だけ除外可能。他componentも対象 |
| IRQ route切替 | esp_intr_enable / esp_intr_disable | SPI owner/ISR自身も利用。時間根拠が必要 |
| 非IRAM IRQ一括制御 | esp_intr_noniram_disable / esp_intr_noniram_enable | flash/cache操作等との関係を確認し、受信中に到達しない根拠または上限が必要 |
| 共有IRQ dispatcher | shared_intr_isr | **登録ISRを呼んでいる間もlockを保持**。他coreの共有IRQの全handler時間を無視できない |
| tracing付き非共有dispatcher | non_shared_intr_isr | CONFIG_APPTRACE_SV_ENABLE条件。今回保存ELFにはsymbolがなく、これを無条件に課金しない |

共有dispatcherは単に短いroute register操作ではなく、登録handlerを順に実行する。保存ELFにはshared_intr_isr（0x403763c0、57 byte）が存在する。ただしsymbolの存在は実際の共有IRQ登録や受信中の発火の証明ではない。全componentの登録一覧・affinity・発生条件が必要。

raw SPIのopen処理は呼出し元のpins構造体をコピーするため、intr_flagsをこの関数内だけでは固定していない。従来の非shared経路分析は**非shared設定を確認した場合の条件付き結果**である。受信中の他componentの共有IRQを含む登録一覧はまだ確定していない。全SPI ISRをcore0に置いても、core1の共有dispatcherがこの共通lockを保持する可能性まで消えたことにはならない。

## SPI_UPDATEに関する公式資料

[Espressif ESP32-S3 TRM](https://documentation.espressif.com/esp32-s3_technical_reference_manual_en.pdf)のRegister 30.1 SPI_CMD_REGを確認。SPI_UPDATEはAPB側からSPI module側へのレジスタ同期を指示するbitとされる。ダウンロードしたPDF全体をtext化してSPI_UPDATEを検索し、この表記は1箇所だった。確認した記載には同期完了・bit解除までの最大cycle数はない。PDFのSHA-256と参照箇所をtrm-source.jsonに記録し、PDF全文はコミットしない。

これは全公開情報に上限が存在しないという調査結果ではない。今回の資料から数値上限を得られなかった、という限定した結論。一般的な同期回路を仮定して2〜3 cycle等を代入しない。また同じregisterのSPI_CONF_BITLENはCONF stateの長さであり、その説明をSPI_UPDATEの解除上限へ流用しない。

## 判定への影響

未確定の「共通lock待ち」を、対象関数と実行条件へ分解した。残る確認は、受信中のIRQ登録/発生とclock/cache/lifecycle条件、その下でのlock保持・仲裁とSPI_UPDATE待ちの上限。新しい製品機能を追加したわけではなく、既存のISR時間Cに必要な根拠の具体化である。

sourceの11関数列挙、保存ELFのhashとwrapper symbolを再現スクリプトで確認。前回の実allocator関数試験を再実行し成功。有限状態の割込み回数上限を、このlockの時間上限へ置き換えない。性能合格・正式割当・採用0、hardware refinement未完了を維持。

```sh
python -m ci.s3_irq_lock_inventory
PYTHONPATH=tests python -m unittest test_s3_spi_irq_routing -v
```
