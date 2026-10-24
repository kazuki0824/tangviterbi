# ② N16R8：SPI/PHYの動的確保とFlash配置条件

**N16R8のheap関数Flash配置＋PHY較正データのNVS保存なし、を実SDKでリンクした。全バッファ・stack容量を保ち、既知の起動確保列8ケースも通過した。** SPI/PHYの未計上オブジェクトを追加して再計算したが、全runtime heap・実機boot・受信機の成立は未確認。N16R8のみ成立する案を許容し、①は変更しない。

## 追加構成と検証

[CI run 40091783736](https://github.com/kazuki0824/tangviterbi/actions/runs/40091783736)、commit `26c643e4d414e1d6649b040019ac509fd5bc866c`。IRAM heap、Flash heap、Flash heap＋NVS保存なしの3構成を逐次buildし、3×38＝114静的チェックが合格。SDKは前回と同じv5.5.1 commit `fcae32885b0296b32044cb99ecbdc50d98dddb83`。artifact digestをGitHub記録と照合し、[provenance.json](provenance.json)に記録した。

追加構成の実ELF/map/config/build logは[sdk](sdk/)以下。NVS保存ありの対照は[前段の生成物](../s3-startup-order/sdk/n16r8-late-stacks-heap-flash/)。今回再buildした対照の配置・容量も一致した。追加構成の起動再生は[startup-replay.json](startup-replay.json)で、元のmain 8,704 Bを含む8ケースが通過した。

| N16R8、heap関数Flash | PHY NVS保存あり | PHY NVS保存なし |
|---|---:|---:|
| `_iram_end` | `0x40386b00` | `0x40386b00` |
| `_heap_start` | `0x3fcab888` | `0x3fcab850` |
| 静的内部RAMの追加回収 | — | 56 B |
| 前段の起動後余裕上限（今回の追加費用を控除する前） | 23,668 B | 23,724 B |
| main / worker stack / RF /送信payload | 8 KiB設定 / 8 KiB / 192 KiB / 128 KiB | 同容量 |

`ESP_PHY_CALIBRATION_AND_DATA_STORAGE=n`では`esp_phy_load_cal_and_init()`が`register_chipv7_phy(..., PHY_RF_CAL_FULL)`を呼ぶ。較正を省略せず、起動ごとに完全較正する。PHY較正データのNVS読み書き依存がなくなり、今回のELFでは`nvs_open`等のNVS APIも除去された。PLL追従は維持。追加RAM回収は56 Bに留まるため、巨大なRAM改善とは扱わない。起動時間・較正の実RF結果は未測定。

## 動的確保の台帳

SDKソースの成功経路と保存済みELFのDWARFから抽出した型寸法を対応付けた。[NVSあり](with-phy-nvs.json)／[NVSなし](no-phy-nvs.json)。各19項目の条件確認、6 unittestが合格（[tests.log](tests.log)）。hostのsizeofをS3へ代入していない。

対象はSPI2/3各1device、queue_size=1、32 KiB送信、SCTなし、専用の非共有SPI割込み、PM/retentionなし、GDMA event callbackなし、PHY初回enable。GDMA group/pairを新規確保するこの構成の要求byte数であり、あらゆるdriver構成の上限ではない。割込みvector descriptorが既存の場合も別計算した。

| SPIの常駐オブジェクト（2port分） | 要求量 |
|---|---:|
| 従来計上：host/bus/DMA context/device、queue、TX/RX descriptor | 1,696 B |
| GDMA：group136＋pair28×2＋TX52×2＋RX56×2 | 408 B |
| bus lock64×2＋device lock12×2＋binary semaphore84×2 | 320 B |
| SPI IRQ handle8×2＋新規vector descriptor12×2 | 40 B |
| **合計** | **2,464 B（33確保）** |

descriptorは各方向9個×12 B、各portでTX/RX両方を確保。GDMA channel作成だけではevent interruptを登録しないため、GDMA ISR handleをSPI IRQ handleに重ねて計上しない。既存vector descriptorを再使用する条件ならSPI要求量は2,440 B（31確保）。共有IRQは別構成であり、ここでは未計上。

GDMA groupの先行確保136 B、既存pairの探索用28 Bは再使用時に解放される一時領域。これらを全後続段階へ常駐として足していない。一方、実際の断片化・探索時の確保順序まで再生したものではない。

PHY初回enableではlazy mutex84 B、較正data1,904 Bを確認。較正dataは`esp_phy_load_cal_and_init()`内で解放され、その後PLLタイマ32 Bが作られる。したがって、較正dataとタイマを必須の同時常駐量として加算しない。

| 段階（新規vectorの場合） | 既知の要求byte数 | 最小allocation header | NVSなし構成の残量上限 |
|---|---:|---:|---:|
| SPI2/3初期化後 | 2,464 B | 132 B | 20,728 B |
| PHY較正中 | 4,452 B | 140 B | 18,732 B |
| 較正data解放・PLLタイマ作成後 | 2,580 B | 140 B | 20,604 B |

残量上限は前段23,724 Bから表の費用とDMA reserveの追加管理費400 Bを控除した値。**実際に利用できる余裕の下限ではない**。PHY binary/ROM内部、logging/libcの別lock、他startup確保、実断片化、RF専用初期化は未計上。NVSあり構成についてはNVSオブジェクトも未計上なので、同じ表だけで成立とはしない。main stackは保持したまま計算しており、main終了による回収は仮定していない。

## DMA予約poolの二重計上を避けた補正

SDKは内部heapから4,096 Bを切り出し、新しいheapとして登録する。その4,096 B自体はDMA/内部確保に再利用できるため全量を再控除しない。

1chunkの場合、外側block header最小4 B、SDKの`end=start+size-1`と`end-start`登録による1 B、内側multi_heap/TLSF/sentinel/整列355 B、heap_t_登録record36 Bとそのheader最小4 B、合計400 Bを追加の利用不能量として控除した。poolが断片化して複数chunkになる場合の追加管理費、TLSFの要求丸めやその他align損失は未計上。この400 B補正で全allocatorを再現したとはしない。

## cache無効中のheap呼出し

`HEAP_PLACE_FUNCTION_INTO_FLASH`のSDK条件は、cache無効中のIRAM ISRからheap APIを呼ばないこと。

| 経路 | 確認内容と範囲 |
|---|---|
| 通常raw SPIのISR | SCT無効、pre/post callbackなし。通常完了経路でheap確保/解放を行わない。DMA一時bufferはMANUALフラグで禁止する。 |
| SCT完了ISR | `spi_post_sct_trans()`はfreeを呼ぶ。今回のcache-off候補ではSCTを使えない。 |
| PHY PLL追従 | esp_timerの既定TASK dispatch。callbackはtimer taskで既存PHY mutexを取得する。ISRとして扱わない。周期処理のWCET・RF bank期限への影響は未計測。 |
| Flash一時read buffer | `get_buffer_malloc`自体はIRAMにあるが、非ROM版APIではtemp確保はcache停止のstartより前、解放はendより後。IRAM配置だけを理由にcache-off違反と断定しない。 |
| libc lazy lock | 初回acquireはmutexを動的確保する。他ISRの未初期化lockやPHY binary/ROM経路まで閉じた証拠はない。 |

全ISR closureはまだfalse。SPI正常経路だけの確認を、全runtimeの安全性や連続受信性能へ拡張しない。

## 再現と残作業

ソースcommit・hashは[manifest](../../ci/s3_runtime_memory_sources.json)。各pathは[固定SDK](https://github.com/espressif/esp-idf/tree/fcae32885b0296b32044cb99ecbdc50d98dddb83/components)以下。PHYの動作変更は`esp_phy/Kconfig`と`esp_phy/src/phy_init.c`、費用はSPI/GDMA/lock/interrupt/esp_timerの各実装を根拠にする。

```sh
python ci/s3_raw_probe_build.py --flash-mb 16 --late-stacks --heap-in-flash --no-phy-nvs
python ci/s3_runtime_memory_audit.py --profile reports/s3-runtime-memory/sdk/n16r8-late-stacks-heap-flash-no-phy-nvs --output reports/s3-runtime-memory/no-phy-nvs.json
python -m unittest discover -s tests -p test_s3_runtime_memory_audit.py -v
```

①は変更なし。N8R8の同構成は未検証で、N8R8不可という結果ではない。[全分担・資源期限・交換情報・全通信候補](../partition-recheck-20261023/README.md)の制約は継続し、FPGA→SoCは指令のみ、追加softwareデシメート・再量子化なし。

今回の到達点はNVS非依存構成の実リンクと、SPI/PHYの既知確保・寿命・allocator費用の更新。実task/common clock、全startup/PHY内部確保、全ISR closure、core別WCET・全FPGA資源/STA・同時RF→TSは残る。ソフトウェアで進められる作業も残っており、依頼全体の完了・探索終了とはしない。正式採用は0件。

CIの重複待機を減らすためPR #10の旧headに限定して停止を試みたが、GitHub APIは403で拒否した。停止したとは扱っていない。最新の上記比較CIはその後成功した。
