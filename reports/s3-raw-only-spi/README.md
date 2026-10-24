# ② N16R8：raw専用SPIでheapのIRAM配置を維持する比較

[前段](../s3-spi-isr-placement/README.md)で、heap Flash＋SPI ISR IRAMは固定SDKの依存条件に反することが判明した。この比較はheapをIRAMへ戻し、使用しないSCT/polling APIへの参照をraw専用アダプタから除くことでRAMを回収する。N16R8のみ成立する案を許容し、①は変更しない。

## 実装と比較条件

`S3_RAW_ONLY_SPI=1`をraw diagnosticのtargetへ定義する。raw専用openは従来page/SCT経路を拒否し、queue/reapは通常の`spi_device_queue_trans`/`spi_device_get_trans_result`だけを使う。closeもSCT/polling停止処理を除く。defaultの共通版は維持する。pの不整合なSCT/polling状態はraw専用queue/reapで停止する。

SDK自体のSPI ISRにはSCTの分岐が残るため、「ELFにSCTコードが一切ない」という主張ではない。5個の公開driver entry pointがELFから消えることを実リンク監査で検査する。driverの正常raw状態でSCTが無効である条件は維持する。

比較はN16R8、late worker stack、NVS保存なし・起動時完全較正・PLL追従あり。main設定8 KiB、worker 8 KiB、RF192 KiB、送信128 KiBを保持。SPI2 Octal/SPI3 Quad 32 KiB送信、無損失I10/Q10 packing、T/S sample rateは変更しない。heap/ISRともIRAMに置き、heap Flashやlock ISRの独自selectは使わない。

build commit `bbef9790719d36f1ed1af9f46432c29ec98b135e`。[実SDK比較CI run 40094373890](https://github.com/kazuki0824/tangviterbi/actions/runs/40094373890)。比較対象は専用化なしと専用化ありの2構成。比較CIは成功し、38＋43＝81静的チェックが合格。[実ELF/map/config/log](sdk/)、[artifact digestとheap symbolの配置](provenance.json)を保存した。`heap_caps_malloc/free`、`multi_heap_malloc/free`も実ELF上でIRAMにある。両構成のbuild logに前段のSPI/heap依存条件警告はない。

| heap IRAM・NVSなし | 共通SPI版 | raw専用版 |
|---|---:|---:|
| `_iram_end` | 0x40388600 | 0x40387700 |
| `_heap_start` | 0x3fcad350 | 0x3fcac440 |
| 内部RAM回収 | — | 3,856 B |
| 元main 8,704 Bの既知確保列（登録recordあり/なし） | 2/2失敗 | 2/2通過 |
| 24個のSPI関数＋2設定の配置監査（専用版） | — | 26/26合格 |
| SPI/heapのSDK依存条件 | 適合 | 適合 |
| 専用版の較正中の残量上限 | — | 15,996 B |
| 専用版の較正後の残量上限 | — | 17,868 B |

回収3,856 BはIRAM終端差3,840 B＋他static差16 B。main/worker stack、payload等の`result.json`サイズは一致する。専用版ELFでは`spi_device_queue_multi_trans`、`spi_device_get_multi_trans_result`、`spi_device_polling_start/end`、`spi_bus_multi_trans_mode_enable`が消えた。コードの削減であり、ソフトウェアのデシメート・再量子化ではない。

[既知起動再生](startup-replay.json)は対照8＋専用8の16ケースを継続実行。専用版8/8が通過。元main容量の結果は上表で、残りはmain設定を変えた未ビルドの感度分析であり、stack削減案を採用していない。[配置監査](isr-placement.json)は当該SDK依存条件にも適合。全ISR call graphの証明は依然false。

[動的費用台帳](runtime-memory.json)は19チェック合格。SPI2/3既知要求2,464 B、PHY較正一時1,904 B/mutex84 B/較正後timer32 B、最小allocation headerとDMA pool追加管理費400 Bの同じ寿命モデルで再計算した。残量は未計上のstartup/PHY内部・断片化等を除く上限で、実利用可能量の保証ではない。

**今後の優先候補はこのraw専用・heap IRAM構成とする。** heap Flash＋独自lock selectの分岐は比較証拠として残すが、当該依存条件違反を受け入れなければ進めない状態は回避できた。これを受信機全体の性能合格や正式採用へ昇格しない。

## 実行した機能試験

- 通常版とraw専用版それぞれのC descriptor/所有権試験。双方のSPI hostで32 KiB descriptor、完了前の再利用禁止、timeout、無効prepare後の送信禁止を確認。raw専用ではlegacy open拒否も確認。
- 既存4/8lane有限RTL試験を再実行。正常系各65,536 Bと、length/epoch/途中切断/末尾過剰の各負例。4 unittest methodすべて合格。[bulk-tests.log](bulk-tests.log)。末尾過剰で先行page commitが残るためepoch停止が必要な制約は継続。
- 共通版の並列packing/native handoff/SPI adapterの3 unittestが合格。[parallel-control-tests.log](parallel-control-tests.log)。追加raw専用SPI adapter試験も合格し、逆順完了、queue失敗時のpayload保持を確認した。

最初のRTL再試行はiverilog欠落で実行できなかったが、Ubuntu packageを作業ディレクトリへ展開した後に全対象を実行し合格した。[環境記録](test-environment.json)。このホスト試験はS3の実時間性能や実RF品質を測定していない。

配置監査の回帰試験6 unittestも合格した（[ログ](../s3-spi-isr-placement/tests.log)）。元Flash lock不足、明示lock配置後も残るSDK依存条件違反、raw専用の当該依存条件適合を区別する。

## 未完了

全startup確保/解放、PHY内部heap、間接callとデータ配置を含む全ISR条件、実task/common clock・core別WCET、全FPGA資源/STA・同時RF→TSは未完了。必要条件を満たすだけで採用に昇格しない。[全候補と全通信路](../partition-recheck-20261023/README.md)の性能→通信路→採用の順序を維持し、正式採用0件。FPGA→SoCは指令のみ、追加softwareデシメート・再量子化なし。

今回の保存境界は、見つかったSDK依存条件の誤評価を訂正し、それに依存しないraw専用構成で実リンク・既知起動確保列まで確認した時点。単に未測定を理由に探索を止めず、別構成を実装して比較した。次はこの同じ構成で全startup/PHY内部確保と実task/common clock・WCETを閉じる必要がある。保存は全依頼の完了ではない。

```sh
python ci/s3_raw_probe_build.py --flash-mb 16 --late-stacks --no-phy-nvs --raw-only-spi
python ci/s3_spi_isr_placement_audit.py --profile reports/s3-raw-only-spi/sdk/n16r8-late-stacks-no-phy-nvs-raw-only-spi --output build/raw-only-isr.json
python ci/s3_tlsf32_replay.py --tlsf-source build/tlsf --input-root reports/s3-raw-only-spi/sdk --profile n16r8-late-stacks-no-phy-nvs --profile n16r8-late-stacks-no-phy-nvs-raw-only-spi --output build/raw-only-startup.json
```
