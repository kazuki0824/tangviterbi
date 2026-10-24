> 続報：[N16R8のSPI/PHY動的確保とNVS保存なし構成](../s3-runtime-memory/README.md)。全runtime成立の証明とは区別して費用を更新。

# ② N16R8の起動時連続確保を検証

N16R8だけで成立する案も許容する（2026-10-24追加条件）。①は変更しない。

**N16R8でheap関数をFlash配置にすると、全バッファ・stack容量を保ったまま内部RAMを6,912 B回収でき、既知の起動確保列も通過した。** 実SDKリンク2構成・74静的チェックが合格。全boot・runtime性能・全受信機の成立は未確認。

前回のlate worker stack案は容量必要条件に合格したが、既知の確保列をSDKと同じTLSFで再生するとmain stackで失敗した。その問題を具体化し、SDK設定だけを変える改善案を比較した。これは全起動処理の再現ではなく、後述の省略を含む確保列の検証である。

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

全ソースのhashは[manifest](../../ci/s3_tlsf32_sources.json)、入力hash・省略項目・全16ケースの逐次記録は[result.json](result.json)、6 unittestは[tests.log](tests.log)。上流ソースはmanifestのcommitと相対pathから参照可能：
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

## 同容量のFlash配置：実SDKリンクと新ELFでの再生

[CI run 40090916387](https://github.com/kazuki0824/tangviterbi/actions/runs/40090916387) は成功。commit `dd04a00c9e3b283a2cda53780cd835f031339fd5`、ESP-IDF commitは前回と同じ。生成物のZIP digestをGitHub記録と照合し、[provenance.json](provenance.json)へ保存した。両構成の実ELF/map/config/build logは[sdk](sdk/)以下。

| N16R8、late worker stack | heap関数IRAM（対照） | heap関数Flash |
|---|---:|---:|
| `_iram_end` | `0x40388600` | `0x40386b00` |
| `_heap_start` | `0x3fcad388` | `0x3fcab888` |
| 下位early heapのraw容量 | 11,384 B | 18,296 B |
| 起動前の容量余裕上限（前段の必要条件） | 3,736 B | 10,328 B |
| 既知driver控除後の総余裕上限 | 15,380 B | 21,972 B |
| 元のmain 8,704 Bを含む既知確保列 | mainで失敗 | idle×2まで通過 |
| 静的チェック | 37/37 | 37/37 |

余裕上限には全runtime確保を含まず、実利用可能RAMと断定しない。heapが16 KiBを越えることでTLSF管理領域が増えるため、raw回収6,912 Bと容量余裕の改善6,592 Bは異なる。

Flash案のmain直前の最大連続空きは下位13,264 B、上位early1,880 B、RTC7,780 B。main stack/TCBとidle×2を確保した後は1,476 / 812 / 7,780 Bが残る。RF192 KiB、送信128 KiB、worker stack8 KiB、main設定8 KiBはいずれも維持した。検証用の小さいmain設定へ変更せず、元の容量で通過する。

新旧CI生成物についても2配置×4main設定×heap登録配列有無＝16ケースを再生し、[ci-placement-replay.json](ci-placement-replay.json)へ保存。Flash案は8ケースすべて通過。保存済みターゲットELFのDWARFからheap_t_・multi_heap_info・control_tの寸法を再抽出し、入力ELF hashも検証している。ホストの64bit型寸法を代入していない。

## 解釈の限界とFlash配置の条件

他のconstructor/libc/PSRAM登録/割込み/タイマ実装の確保・解放、heap_capsのhardware alignment wrapper、PHY/SPI runtime、late heap/DMA pool有効化は未再生。これらを省略するとheapの選択先も変わり得るため、今回の失敗を実起動の不可能性の一般証明にはしない。逆に確保列通過もboot成功ではない。

main stackを縮める案のほか、**stack・payload容量を維持してSDK heap関数をFlashへ配置する案**を実SDKリンクで比較した。`CONFIG_HEAP_PLACE_FUNCTION_INTO_FLASH=y` を明示するbuild optionと、N16R8のIRAM/Flash配置を順次比較するCIを追加した。新しい配置は有効sdkconfigでも検査した。SPI hot API/ISRのIRAM設定は維持する。SDKのheap/Kconfigは、cache無効中のIRAM ISRからheap APIを呼ばないことを条件としている。SPI masterソースではSCT完了ISRがfreeを呼ぶが、今回のrawはSCT無効。通常のqueue/reapではDMA適合buffer＋MANUALフラグにより一時bufferの追加確保を禁止し、pre/post callbackも設定していない。これにより当該SPI経路の条件を絞ったが、他ISR/PHYを含むruntime全体のcache無効時call graphと実行時間は未検証。Flash配置の採用はその確認を条件とする。

CIは1jobで2構成を逐次実行し、失敗しても次構成へ進め、全結果を保存する。同PRの古い同workflowだけcancelし、無関係なCIは停止しない。独自の秒数・分数による探索打切りは追加していない。

再現：

```sh
python -m pip install unicorn pyelftools
python ci/s3_tlsf32_replay.py
python -m unittest discover -s tests -p test_s3_tlsf32_replay.py -v
python ci/s3_tlsf32_replay.py --input-root reports/s3-startup-order/sdk --profile n16r8-late-stacks --profile n16r8-late-stacks-heap-flash --output reports/s3-startup-order/ci-placement-replay.json
# ESP-IDF 5.5.1の環境で
python ci/s3_raw_probe_build.py --flash-mb 16 --late-stacks --heap-in-flash
```

現時点では正式採用0件。N16R8限定の許容は、内部RAMが増えたとの根拠にはしない。4項目の分担・資源期限・交換情報・全通信候補は[既存台帳](../partition-recheck-20261023/README.md)を継続し、実測WCET・全FPGA統合/STA・同時RF→TSは引き続き必要。

今回の保存境界は「容量を維持した改善案の実リンクと既知確保列通過」まで。全起動確保・PHY/driverの残額・実task/common clock・core別WCET・全FPGA/実機検証は残る。実機なしでできる部分もあり、採用確定・探索終了・依頼全体完了とはしない。N8R8で同じFlash配置を検証していないため、N8R8を排除する結果でもない。
