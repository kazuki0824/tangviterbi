> 続報：[N16R8の起動時確保順序](../s3-startup-order/README.md)。容量通過のlate案も既知確保列ではmainの連続確保に失敗。容量検証と確保順序を区別する。

# ②：実ESP-IDFリンクとraw専用内部RAM配置（2026-10-24 JST）

**N8R8/N16R8とも実ESP-IDF 5.5.1でリンクできた。ただし元のBSS stack配置は、起動前の内部RAM不足で不合格。** 2workerのstack合計8 KiBをapp_main以降の領域へ移すと、送信128 KiB・stack容量を削らずに容量の必要条件を通過した。起動成功、全runtime heap、task scheduling、WCET、全受信機の成立は未確認。

①は変更しない。前回 `964ec99` の「実SDK未リンク」から、raw用実コード・SPI/PHY SDK call graph・task生成APIを含む診断ELFへ進めた。**性能合格→正式経路割当→採用は0→0→0を維持**する。

## 比較結果

| 構成 | 実SDKリンク・配置チェック | 起動前余裕上限：stack/TCB控除後 | allocator費用も控除した上限 | 容量必要条件 |
|---|---|---:|---:|---|
| N8R8、worker stackをBSS配置 | OK | −3,208 B | −4,384 B | NG |
| N16R8、worker stackをBSS配置 | OK | −3,208 B | −4,384 B | NG |
| N8R8、worker stackをlate領域へ移動 | OK | 4,984 B | 3,736 B | OK、十分条件ではない |
| N16R8、worker stackをlate領域へ移動 | OK | 4,984 B | 3,736 B | OK、十分条件ではない |

[全4構成の要約・検証記録](summary.json)／[監査の回帰試験](tests.log)。各構成の下に実ELF・map・有効sdkconfig・buildログをgzip保存し、`result.json`へhash、設定、全チェック、target ABI寸法、起動容量を保存した。

## 配置と起動の区別

共通のRF bank予約は `[0x3fcb0000,0x3fce0000)` の192 KiB。送信payloadは以下の128 KiBで、各32 KiBは連続・4byte整列している。

| 対象 | 実ELF／SDK予約の領域 | 容量 |
|---|---|---:|
| 下位送信buffer×2 | `[0x3fc9a1d8,0x3fcaa1d8)` | 65,536 B |
| 上位送信buffer0 | `[0x3fce0000,0x3fce8000)` | 32,768 B |
| 上位送信buffer1 | `[0x3fcf0000,0x3fcf8000)` | 32,768 B |
| 移動案のworker stack×2 | `[0x3fcea000,0x3fcec000)` | 8,192 B |
| worker TCB×2 | 通常BSS、`raw_task_tcbs=0x3fcacb40` | 680 B |

ESP32-S3 rev0 ROM ELFから取得した予約開始は`0x3fceee34`。上記予約との非重複を確認。実機のrevision/layout一致を確認したことにはしない。上位送信buffer1には32 KiB data cache設定が必要で、有効sdkconfigでも検査した。

SDKはmain task開始後にnon-OS startup stack領域をheapへ戻す。その前にmain・timer・IPC×2・idle×2のstack/TCBが必要になる。元配置はこの時点で容量不足なので、後から利用できるRAMを足して成立とすることはできない。

移動案はworker stackを`SOC_RESERVE_MEMORY_REGION`でheapから除外し、app_main後にだけtask生成APIへ渡す構成。stackをPSRAMへ移したり容量を削ったりしていない。raw取得・128 KiB送信payloadにも変更はない。

**移動案の3,736 Bは起動成功の証明ではない。** mainの必要stackは8,704 Bで、初期heapのraw容量だけ見ても連続確保候補は下位の`[0x3fcad388,0x3fcb0000)`だけ。上位early heapは5,904 B、RTCの楽観的容量も8,168 Bしかない。先行する確保と断片化を含む確保順序は未検証。SDKはheapのサイズ順・capability優先度でも選択するため、空き総量のみで代用しない。

## 起動後・driver費用

移動案の起動後内部RAM余裕上限は、確認したTLSF管理費用と起動task分を差し引いて17,076 B。DMA予約pool4,096 Bを他用途から除けば12,980 B。ただしpoolは実RAMの一部であり、DMA確保費用として二重に差し引かない。

実ELFのDWARFから型寸法を抽出し、SPI2/3の既知の動的確保を最低1,696 Bと数えた。

| 2port分の内訳 | 容量 |
|---|---:|
| host/bus context/DMA context/device | 848 B |
| 送受の結果・投入queueと1要素（各port 2 queue） | 416 B |
| 各port TX/RX DMA descriptor、各9個×12 B | 432 B |

この既知driver分を差し引いた総内部RAM余裕上限は15,380 B。GDMA channel/group、bus/device lock、interrupt handle、allocation header/alignment、PHY/calibration、他のruntime確保は含まない。したがって15,380 Bを「利用可能な余裕」と断定しない。前回9,064 Bの足し引きは旧FFT/RS firmwareの回収仮説であり、今回の新ELF寸法と混ぜない。

## 何を実行し、何を実行していないか

- SDK commit `fcae32885b0296b32044cb99ecbdc50d98dddb83`（v5.5.1）と指定submodule、Espressif GCC14.2.0を使用。host shimではなく実SDKでcompile/linkした。
- native capture、並列packing、bulk SPI、real SDK queue/reap、PHY初期化入口、2個のstatic task生成APIを保持。対象hot関数12個のIRAM配置を確認。
- app_mainは診断表示のみ。RF・PHY・SPI・taskを起動しない。task本体も通知待ちだけで、復調receiverや実runtime schedulerではない。pin map、tuner設定、共通clockのnative相対時刻への接続、poll周期・slice WCETは提供していない。
- task stackの4 KiB/coreは比較用の予約量。測定したstack high-waterや保証された余裕ではない。両比較で同容量を保って配置の効果を分離した。
- 4構成×36チェックを全件実施。配置・ROM非重複・設定・ABI・hot関数・build中source不変等を確認。**チェック合格と容量NGは区別**して記録。
- unittestは、実保存ELFで元配置NGと移動案の必要条件OKを確認し、ROM衝突・誤設定を同時注入して両方報告されることを検査。実機boot試験ではない。

作業ファイルは環境の自動整理で消えていたため、Push済みbranchを再cloneした。初回のSDK準備では実行属性と未取得submoduleの問題があり、修復・取得後に最終4構成をビルドした。これらを構成のRAM不足や停止理由として扱っていない。

## 再現

ESP-IDF 5.5.1の環境をexportし、同SDK toolsの`esp32s3_rev0_rom.elf`を指定する。

```sh
python ci/s3_raw_probe_build.py --flash-mb 16
python ci/s3_raw_probe_build.py --flash-mb 16 --late-stacks
python ci/s3_raw_probe_build.py --flash-mb 8
python ci/s3_raw_probe_build.py --flash-mb 8 --late-stacks
python ci/s3_raw_link_audit.py --build build/s3-raw-probe/n16r8-late-stacks/idf --rom "$S3_ROM_ELF" --output reports/s3-raw-sdk/n16r8-late-stacks
S3_ROM_ELF=/path/to/esp32s3_rev0_rom.elf python -m unittest discover -s tests -p test_s3_raw_link_audit.py -v
```

他の3構成もbuild/output名を対応させて監査する。4構成のソースhashと設定・SDK commitは各`result.json`内の`build`に記録。elftoolsはIDF Python環境の依存を利用する。

## 残作業と今回の保存境界

[全分担・全通信候補](../partition-recheck-20261023/README.md)、[通信機能](../s3-bulk-transport/README.md)、[並列packing/所有権](../s3-parallel-pack/README.md)は継続。FPGA→SoCは指令のみ、追加softwareデシメート・再量子化なし。全FPGA資源・STA・K7速度不足、動的期限、core別WCET、実PHY/SDRAM、同時RF→TSは未解決。

今回Aは「実SDK静的配置と起動容量の必要条件を比較し、元配置の不成立と移動案を示した地点」。Bは確保順序・残るdriver/PHY確保、実task/共通clock統合・WCET、全FPGA・実機検証。リンク成功だけで採用しない点は妥当。Aで依頼全体を完了とすることは妥当でなく、ソフトウェア側で進められるBも残る。今回の保存は強制打切りや探索終了ではない。
