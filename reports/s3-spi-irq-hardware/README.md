# ② IRQ原因対応の下位SDK経路と時間上限の不足

2026-10-27。固定IDF fcae32885b0296b32044cb99ecbdc50d98dddb83のHAL/ESP32-S3 LLを追加取得し、URL/SHA-256付きで保存した。interrupt allocatorは既存保存sourceのhashを照合した。runtimeと①は変更しない。

## 実装で確認した順序

1. 初期化のspi_hal_initはtrans_done interruptをenableし、softwareでdoneをsetする。CPUへのIRQはdriverがINTRDISABLEDで確保している。従って初回IRQの原因を「実転送完了だけ」としてはいけない。既存モデルではREQのwakeが初回の有効化を覆う。
2. spi_new_transはspi_hal_setup_transを先に呼ぶ。setup_transはspi_ll_clear_int_statによりdma_int_clr.trans_done=1を書き、以前のdoneをclearする。
3. spi_hal_user_startはspi_ll_apply_config→spi_ll_user_startの順。前者はcmd.update=1を書き、while(cmd.update)で設定反映を待つ。後者がcmd.usr=1を書いて開始する。完了判定はdma_int_raw.trans_doneの読取り。
4. bg control callbackはesp_intr_enable/disableへ進む。通常の非shared・外部source経路は、共通spinlockを取得してesp_rom_route_intr_matrixへ対象CPU/source/IRQ番号（disableならINT_MUX_DISABLED_INTNO）を渡す。SPI trans_done自体をここでclearしない。

これで形式モデルのstart/complete/pendingの根拠となるレジスタ操作まで特定できた。ただしW1Cの反映、cmd.updateの解除時間、interrupt matrixの伝播、CPUのlevel IRQ認識・再入防止までをSDKのC本文だけから証明したことにはならない。レジスタへ書くことと、その後のhardware状態遷移を区別する。既存の `hardware_refinement_proven=false` を維持する。

## 時間上限へ追加すべき根拠

| 項目 | 実装上の所在 | 必要な根拠 |
|---|---|---|
| IRQ allocator共通lock | esp_intr_enable/disableのportENTER_CRITICAL_SAFE(&spinlock) | 他coreの同じlock利用と保持時間・取得待ち |
| 設定反映待ち | spi_ll_apply_configのwhile(cmd.update) | 通常動作・対象clock条件でhardwareが解除するまでの上限 |
| pending原因の対応 | done clear/setとIRQ matrix切替 | 旧levelの残留や再通知を含む各entryの原因対応 |

同一core配置(0,0)で除外できるのは該当SPI queueのcross-core競合である。IRQ allocatorのlockはqueueごとでなく共通なので、別coreの他API利用まで自動的に除外しない。通常SPI ISRの入口disableに1回、転送を開始してexitでenableするとさらに1回、この共通lockを取得する。ownerのREQ後enableが必要な場合も1回。実際の回数と他IRQの干渉を二重計上せずISR cost Cとownerの通常反復へ入れる。

cmd.update待ちにはsource上のソフトウェア反復上限がない。これは実際に無限待ちになるという証拠でも、候補を不可能とする根拠でもない。hardware上限が未取得という意味。CAS attempt数や有限状態モデルの遷移数を、この待ちのcycle数に置き換えない。

## 検証

12 source/hash/経路anchorチェック成功（audit.json）。固定allocatorのesp_intr_enable/disable実関数をそのまま抽出してhostコンパイルし、非shared外部sourceでCPU0/1の各routeについて共通critical entry/exit各1回、route引数を確認した。既存REQ/形式モデル試験を含め6 unittest成功。criticalとROM matrix関数はshimであり、競合・hardware伝播・実行時間は試験していない。

source anchor検査はCFG証明ではない。今回も実機C、H/S/W/Rは未確定で、性能合格・正式通信路割当・採用0。次の必要証拠は上表のhardware/仲裁の上限と原因対応であり、形式モデル側に都合のよい時間定数を追加して解決したことにはしない。

再現:

```sh
python -m ci.s3_spi_irq_hardware_audit
PYTHONPATH=tests python -m unittest test_s3_spi_irq_routing test_s3_spi_request_enable test_s3_spi_irq_envelope -v
```
