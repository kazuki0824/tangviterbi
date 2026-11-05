# ② N16R8：SPI割込みのbus lock配置を検算

N16R8のみ成立する案を許容し、①は変更しない。前段のSPI正常完了経路にheap呼出しがないことと、全呼出し先がcache無効中に実行できることは別条件である。保存済み実ELFを調べると、SPI ISR本体はIRAMでも、正常経路から呼ぶbus lockの6関数がFlashに残っていた。

## 元の実ELFで確認した不足

対象は[前段のNVSなしELF](../s3-runtime-memory/sdk/n16r8-late-stacks-heap-flash-no-phy-nvs/)。全24関数のaddress/sizeと26チェックは[before.json](before.json)。6関数と設定1件の計7チェックが不合格。他の18関数の配置確認は合格したが、これは全call graphの確認ではない。

| 関数 | 元のaddress |
|---|---|
| spi_bus_lock_bg_entry | 0x420246cc |
| spi_bus_lock_bg_exit | 0x4200fe9c |
| spi_bus_lock_get_acquiring_dev | 0x420246c0 |
| spi_bus_lock_bg_clear_req | 0x4200fefc |
| spi_bus_lock_bg_check_dev_acq | 0x420246f4 |
| spi_bus_lock_bg_check_dev_req | 0x4200ff48 |

`spi_intr()`からentry/exit、次transactionを取得する分岐から他4関数を呼ぶ。SCT完了のfreeだけを除外しても、この正常経路のFlash依存は残る。

固定ESP-IDF v5.5.1 (`fcae32885b0296b32044cb99ecbdc50d98dddb83`) の`spi_bus_lock.c`は、`ESP_SPI_BUS_LOCK_ISR_FUNCS_IN_IRAM`でこれらの配置を決める。従来ELFでは`SPI_MASTER_ISR_IN_IRAM=y`、`ESP_SPI_BUS_LOCK_FUNCS_IN_IRAM=y`だが、lockのISR用設定は無効だった。[固定ソースのhash](sources.json)。

**依存条件違反の訂正:** `esp_driver_spi/Kconfig`では`SPI_MASTER_ISR_IN_IRAM`は`!HEAP_PLACE_FUNCTION_INTO_FLASH`に依存する。一方`SPI_MASTER_IN_IRAM`がISR設定をselectするため、保存済みFlash heap構成は依存条件がfalseでもISR=yになり、元build logにこの警告がある（[抽出](before-kconfig-warning.txt)）。ISR側からlock ISR設定へのselectは有効にならなかった。従来の「SDKが許容するheap Flash配置」という記述は、heap配置option単独については存在しても、今回のSPI IRAMとの組合せのサポートを意味しない。この組合せをSDK依存条件に適合する構成とした評価を撤回する。新しいlockのselectも依存条件違反そのものを解消せず、検証対象の独自構成として扱う。

`SPI_MASTER_ISR_IN_IRAM`という名前だけでISR全体がcache-safeとは判定しない。さらにdriverが渡す`intr_flags`の`ESP_INTR_FLAG_IRAM`と、関数のリンク配置も別条件である。現transportはcallerの`pins->intr_flags`をコピーし、診断appはSPI初期化を実行しないため、実行時の割込み属性・core affinityはまだ未確定。非IRAM割込みならcache無効中に停止される側の期限検証が必要であり、この発見だけで通常cache有効時のSPI動作まで不可能とはしない。

対照として[heap IRAMの元ELF監査](heap-iram-control.json)は26/26配置チェックとSDK依存条件を通過する。ただし前段の既知起動確保列では元mainの連続確保に失敗した構成である。配置条件の合格と起動RAM条件の合格を異なる構成間で混ぜて成立としない。

## 配置比較

`--spi-lock-iram`を追加し、project KconfigからSDKの隠れたboolを`select`する。隠れたsymbolをsdkconfig.defaultsへ直接書いて有効になったと仮定しない。SDK sourceを改変せず、同じSDK、main/worker stack、RF192 KiB、送信128 KiB、完全PHY較正、PLL追従を保持する。

比較build commit: `548891953804cc12f34a69696a67e50daf6a01e7`。
[比較CI run 40093893957](https://github.com/kazuki0824/tangviterbi/actions/runs/40093893957)。4構成のlink・配置159チェック（38×3＋45）が合格。artifactのSHA-256をGitHub記録と照合した。[provenance](provenance.json)、[新ELF/map/config/log](sdk/)、[配置監査](after.json)を保存した。元対照3構成のIRAM/heap位置は前回と一致する。

| heap Flash・NVSなし | lock ISR設定なし | 明示selectあり |
|---|---:|---:|
| `_iram_end` | 0x40386b00 | 0x40386d00 |
| `_heap_start` | 0x3fcab850 | 0x3fcaba50 |
| 内部RAM追加費用 | — | 512 B |
| 24関数＋2設定の配置監査 | 19/26 | 26/26 |
| SDK依存条件への適合 | 不適合 | 不適合 |
| 既知起動確保列（main 8,704 B含む） | 8/8通過 | 8/8通過 |
| 較正中の既知費用控除後の残量上限 | 18,732 B | 18,220 B |
| 較正後の同残量上限 | 20,604 B | 20,092 B |

[起動再生](startup-replay.json)、[動的費用台帳](runtime-memory.json)。追加512 Bを控除した。残量は未計上費用を含まない上限であり、空きRAMの保証ではない。heap IRAM対照からの従来6,912 B回収にはlock helperのFlash移動も含まれていた。同じNVS条件ならlockを戻した純配置差は6,400 Bであり、6,912 Bすべてをheap関数だけの費用としない。

新build logにも同じ依存条件警告が残る。SDK依存条件の違反はこの明示selectで解消しない。実機bootや全ISRの証明を意味しない。

## 検証範囲

`ci/s3_spi_isr_placement_audit.py`は固定SDKソースで確認した24個のretained symbolと2設定を、実ELFのaddress/sizeで検査する。完全な逆アセンブルcall graphではない。欠落symbolとIRAM境界超過を独立に検出し、異常をまとめて報告する。6 unittestは、raw専用実ELFの依存条件適合、新ELFの配置合格とSDK依存条件違反の分離、heap IRAM対照の配置・依存条件合格、元ELFの既知不合格、複数異常の同時検出、部分配置合格を全体成立へ昇格しないことを確認する。

```sh
python ci/s3_spi_isr_placement_audit.py --profile reports/s3-runtime-memory/sdk/n16r8-late-stacks-heap-flash-no-phy-nvs --output build/spi-isr-before.json
python -m unittest discover -s tests -p test_s3_spi_isr_placement_audit.py -v
```

修正後も、間接call・literal/data配置・assert/error経路・他ISR/PHY binary/ROM・実行時IRQ属性・cache無効期間とRF bank期限の検証は残る。ヒープ関数のFlash配置を無条件に採用する根拠にはしない。全候補と通信路の台帳は[全分担の検算](../partition-recheck-20261023/README.md)を継続し、正式採用は0件。FPGA→SoCは指令だけ、帯域合わせのsoftwareデシメート・再量子化なし。

## 次の比較：raw専用SPIによるコード回収

`bbef9790719d36f1ed1af9f46432c29ec98b135e`で`S3_RAW_ONLY_SPI`のbuildを追加。raw専用ではlegacy openを拒否し、queue/reap/closeからSCT・polling API参照を除く。共通版は従来どおり保持。SDK sourceとバッファ・信号精度を変更しない。heapをIRAMに保持し、NVSなし・late stackで専用化の有無を比較する。対象ELFから5つのlegacy driver entry pointが消えることも確認する。[比較CI](https://github.com/kazuki0824/tangviterbi/actions/runs/40094373890)。[raw専用報告](../s3-raw-only-spi/README.md)で、heapをIRAMに保持したまま3,856 B回収し、元mainを含む既知確保列を通過した。以降はこちらを優先候補とする。
