# ② N16R8の起動時連続確保を検証

N16R8だけで成立する案も許容する（2026-10-24追加条件）。①は変更しない。

前回のlate worker stack案は容量必要条件に合格したが、**既知の確保列をSDKと同じTLSFで再生するとmain stackの確保に失敗した**。これは全起動処理の再現ではなく、後述の省略を含む確保列の検証である。

## 実行した範囲

保存済みN16R8 ELF監査のheap寸法・TCB寸法を使用。Espressif TLSF commit `2867f6883a12920b1969ff9624c0ab0e4185c2ce` のソースを変更せず、32bitポインタ・size_tでcompileし、Unicornのx86 32bit実行機能でallocatorそのものを実行した。Xtensa CPUやESP-IDF全体をエミュレートしたものではない。標準Cライブラリの代替は出力・memcpy・memset・assertだけで、TLSFの割当処理は置き換えていない。

SDK commit `fcae32885b0296b32044cb99ecbdc50d98dddb83` のソースで、以下を確認した。

- `esp_system/startup.c`：constructor後にsecondary初期化。`esp_ipc.c`はconstructorでIPC×2を作る。
- `esp_timer/src/esp_timer.c`：secondary初期化でtimer taskを作る。
- `freertos/app_startup.c`：その後mainを作り、scheduler開始。late heapの有効化はmain内なので、それ以前の確保には使えない。
- `freertos_tasks_c_additions.h`：下向きstackはstack→TCBの順に確保。idleも`port_common.c`で同順。
- `heap_caps_init.c`と`heap_caps_base.c`：元のheap容量の昇順とcapability優先度で探索。S3は今回の要求でDIRAMをRTCより先に使う。
- `multi_heap.c`：対象DWARFのmulti_heap_info 20 Bを除いた領域にTLSFを作る。登録heap配列は対象DWARFのheap_t_ 36 B×領域数、下位heapから確保する比較を追加。
- 有効sdkconfigとXtensaのFreeRTOSConfig_arch.hでは、今回idle追加stack overheadは0。

全ソースのhashは[manifest](../../ci/s3_tlsf32_sources.json)、入力hash・省略項目・全16ケースの逐次記録は[result.json](result.json)、5 unittestは[tests.log](tests.log)。上流ソースはmanifestのcommitと相対pathから参照可能：
[SDK](https://github.com/espressif/esp-idf/tree/fcae32885b0296b32044cb99ecbdc50d98dddb83/components)／[TLSF](https://github.com/espressif/tlsf/tree/2867f6883a12920b1969ff9624c0ab0e4185c2ce)。

## 確保列の結果

late stack案・登録heap配列180 B込み。heap番号0＝下位DIRAM、1＝上位early DIRAM、2＝RTC。

| 確保後 | 下位の最大連続空き | 上位earlyの最大連続空き | RTCの最大連続空き |
|---|---:|---:|---:|
| heap登録配列 | 10,764 B | 5,516 B | 7,780 B |
| IPC×2のstack/TCB | 10,764 B | 2,236 B | 7,780 B |
| timerのstack/TCB | 6,664 B | 1,880 B | 7,780 B |
| mainの8,704 B要求 | **確保失敗** | **確保失敗** | **確保失敗** |

この時点の連続空きの合計は16,324 Bある。前回の「空き総量が正」の結果は変わらないが、それだけではmainが入らない。登録heap配列を省略した楽観ケースでも失敗する。

| worker stack配置 | main設定（SDK加算前） | 登録heap配列なし／あり |
|---|---:|---|
| 元BSS | 8,192 B | 両方main stack失敗 |
| 元BSS | 6,144 B | 両方idle0 stack失敗 |
| 元BSS | 4,096 B | 両方idle1 stack失敗 |
| 元BSS | 3,584 B | idle1 TCB／idle1 stack失敗 |
| late | 8,192 B | 両方main stack失敗 |
| late | 6,144 / 4,096 / 3,584 B | 6ケースすべて確保列通過 |

小さいmain設定は**感度分析のみ**で、実SDKを再リンクした値でも安全なstack high-waterの証明でもない。RF192 KiB、送信128 KiB、worker stack8 KiBはこの比較で削減していない。全16ケースを実行し、先行ケースの失敗で後続ケースを省略していない。

## 解釈の限界と次の実リンク

他のconstructor/libc/PSRAM登録/割込み/タイマ実装の確保・解放、heap_capsのhardware alignment wrapper、PHY/SPI runtime、late heap/DMA pool有効化は未再生。これらを省略するとheapの選択先も変わり得るため、今回の失敗を実起動の不可能性の一般証明にはしない。逆に確保列通過もboot成功ではない。

main stackを縮める案のほか、**stack・payload容量を維持してSDK heap関数をFlashへ配置する案**を実SDKリンクで比較する。`CONFIG_HEAP_PLACE_FUNCTION_INTO_FLASH=y` を明示するbuild optionと、N16R8のIRAM/Flash配置を順次比較するCIを追加した。新しい配置は有効sdkconfigでも検査する。SPI hot API/ISRのIRAM設定は維持する。Flash配置後のruntimeでcache無効中にheap関数が必要か、実行時間へ影響するかは別途検証が必要。

CIは1jobで2構成を逐次実行し、失敗しても次構成へ進め、全結果を保存する。同PRの古い同workflowだけcancelし、無関係なCIは停止しない。独自の秒数・分数による探索打切りは追加していない。

再現：

```sh
python -m pip install unicorn pyelftools
python ci/s3_tlsf32_replay.py
python -m unittest discover -s tests -p test_s3_tlsf32_replay.py -v
# ESP-IDF 5.5.1の環境で
python ci/s3_raw_probe_build.py --flash-mb 16 --late-stacks --heap-in-flash
```

現時点では正式採用0件。N16R8限定の許容は、内部RAMが増えたとの根拠にはしない。4項目の分担・資源期限・交換情報・全通信候補は[既存台帳](../partition-recheck-20261023/README.md)を継続し、実測WCET・全FPGA統合/STA・同時RF→TSは引き続き必要。
