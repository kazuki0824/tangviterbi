# T前処理候補のSDK接続・リンク検証

このディレクトリは、保存されたネイティブ処理・halfband pipeline・実行制御Cを、新しく再構成したSDK接続へ結び付けた**実際のESP32-S3リンク結果**である。過去に失われたELFの復元を主張しない。`app_main` は保持ポインタと配置情報を表示するだけで、RF、PHY、SPI、タスクを起動しない。したがって、この検証結果は受信機の実機動作、ハードウェアWCET、元の受信品質の証明ではない。

今回のビルド後に実行した [audit.json](audit.json) は **202 PASS、0 FAIL、0 BLOCKED**。ソース・設定・成果物のハッシュ、対象ABI、固定メモリ配置、起動・停止手順、CP3と割り込みの条件を独立に列挙した。監査器の異常入力試験4件もPASSした。費用算定と有限実行モデルは隣接する `runtime/` の別の検証であり、このSDK静的監査のPASSを処理容量のPASSへ読み替えない。

## 固定した入力と実際の出力

| 項目 | 今回の値 |
|---|---|
| ESP-IDF | v5.5.1、`fcae32885b0296b32044cb99ecbdc50d98dddb83` |
| GCC | 14.2.0、`esp-14.2.0_20241119` |
| Xtensa配布物SHA256 | `e3e6dcf3d275c3c9ab0e4c8a9d93fd10e7efc035d435460576c9d95b4140c676` |
| ROM ELF配布物 | `20241011` |
| ROM配布物SHA256 | `921f000164a421c7628fbfee55b173384aafaa51883adc65cd27bf9b0af9e9a9` |
| SoC構成 | ESP32-S3、16MB flash、8MB Octal PSRAM、CPU 240MHz、PSRAM 80MHz |
| 入力・halfband | T入力16MSps、halfband shift10、I16/Q16診断出力 |
| 提供するsymbol ELF | 605,456 bytes、gzip 232,149 bytes |
| 提供ELFの展開後SHA256 | `41a01f1a76c3879f0b3757f2bd2b307d0f9977655c3e9ce293562dcf7f5f821c` |
| 完全なdebug ELF | 4,954,564 bytes、gzip 1,645,806 bytes、7分割 |

公式配布物は実際に取得して上表のSHA256と一致することを確認した。IDFの再帰submoduleは固定commitへcheckoutしている。`idf-submodules.txt` と `python-packages.txt` が実際の環境を記録する。今回のローカル環境ではCMake 3.30.2、Ninja 1.11.1.4を使用した。

[provenance.json](provenance.json) は、27個のリポジトリ内コンパイル入力・ヘッダ・ビルド設定、full sdkconfig、提供物、完全ELFの分割片をSHA256で結び付ける。`configured_project_version` はCMakeに記録されたアプリケーションのバージョン、`source_head_at_packaging` は包装時点のGit HEADである。同時に別の報告をコミットしている場合は一致するとは限らない。実際のコード識別にはコンパイル入力のハッシュを使う。

`t_preprocess_integration_probe.elf.gz` は完全ELFから `objcopy --strip-debug` だけを行ったもの。`.symtab` を保持し、全allocated sectionのアドレス、サイズ、型、フラグ、内容を完全ELFと比較して一致を確認した。debug ELFは `full-elf.parts/part-000` から順に連結し、gzipを展開して得られる。各片は最大240,000 bytes。監査は各片を独立に確認してから連結後の整合性を確認するため、最初の片が欠けても後の6片の判定は残る。

## SRAMとDMAの配置

| 用途 | 予約範囲または実測サイズ |
|---|---|
| RFの3 bank | `[0x3fcb0000, 0x3fce0000)`、3×64KiB |
| 上側DMA arena 0 | `[0x3fce0000, 0x3fce8000)`、2×16KiB |
| 上側DMA arena 1 | `[0x3fcf0000, 0x3fcf8000)`、2×16KiB |
| 下側DMA arena | `tpre_lower_frames[4][16384]`、明示した16-byte alignment |
| 遅い時点で使うSRAM | `[0x3fce9720, 0x3fcee940)`、21,024 bytes |
| pipeline | `0x3fce9720`、実測8,528 bytes |
| adapter | `0x3fceb870`、実測4,288 bytes、予約4,304 bytes |
| task stacks | `0x3fcec940`、`0x3fced940`、各4,096 bytes |
| SDK接続状態 | 実測232 bytes |
| runtime / native capture | 実測244 / 168 bytes |
| StaticTask_t / SPI transaction / clock | 実測340 / 40 / 24 bytes |

SDKの実際のリンク値は `_data_end=0x3fcaa64c`、`_bss_end=0x3fcab5a8`、`_iram_end=0x40386800`。RF領域との静的な重複はない。遅い時点で使う領域は `SOC_RESERVE_MEMORY_REGION` でallocatorから除外し、app_mainに到達した後の一度だけ初期化する。Cのゼロ初期化に含まれないため、adapterを明示的にゼロ化してから `hbnative_init` を呼ぶ。初期化を試みたフラグは、そのゼロ化より先に立てる。

これらは固定予約とリンク時配置の確認である。実際のstack high-water、全アプリケーションのheap、バス競合、DMA進行の証明を含まない。rev0 ROM末尾の領域は今回のlate reserveに含めない。

main componentだけに `-mno-disable-hardware-atomics` を適用する。SDK接続の初期化は対象オブジェクトとDMA frameの先頭・末尾が内部メモリであることを確認する。他のSDK componentにはPSRAMのatomic workaroundを残す。`-fno-tree-slp-vectorize` はscalar unpackの不要な展開を抑えるためにmainへ適用し、実際の命令列はリンク後に再確認する。

## 実装した起動と停止

SDK接続は、8個の16KiB内部DMA frame、pipeline、adapter、runtime、native captureを所有する一回限りの実行を対象とする。呼出側はこれらとstack/TCBの分離、および実行・停止処理が終わるまでの寿命を確保する。SPI3はQuad80MHz、送信キュー深さ2。80MHzの実際の選択値もAPIで確認する。`0xd711` と16-bit command／64-bit addressは診断用の通信envelopeであり、正式な受信機のパーサ契約を採用したものではない。

workerをcore1に作成してからownerをcore0に作成する。各taskはRF-offで共通clockをcalibrateし、CP3 warmupを実行する。workerがtick sleepを終えて常時awakeのgateに入ったことをownerへ通知した後、ownerが再calibrateしてRFを開始する。実測したclock errorをruntimeへ渡す。

**owner priority23、worker priority21、timer priority22は費用モデルの呼出側設定**である。一般のlaunch wrapperがこの値を固定・強制しているという意味ではない。PHY tracking timerは保存設定でcore1、周期1,000ms。PHYのhardware busy待ちには、この検証で確立した時間上限がない。

呼出側は実際の元TWDT設定を渡す。受信中はidle taskの監視を外し、終了時に元設定を復元する。専用taskは自身のTWDT購読を削除してから終了する。通常のfeed確認はtimeoutの半分の間隔でresetを行う。初期化例のtimeoutは5,000msであり、実行モデルのcadenceもこの設定に対応する。

停止時はRFを止め、workerのpayload操作が終わるまで待ち、SPIの完了を最大キュー深さ分だけ非blockingで回収する。queue errorではDMA leaseを保持し、poisonedを立てる。timeoutで再利用可能と見なす処理、free、restartは実装しない。**`stopped[]` はpayload quiescenceであり、task deletion、CP3所有権の解放、全DMA完了を保証しない。**

## CP3とキャッシュの成立条件

`tpre_pie_warmup` の実体は `entry; ee.zero.qacc; retw.n`。FreeRTOSのlazy coprocessor exceptionを通じてtaskのCP3 contextを所有させ、CPENABLEを手動で書き換えて回避しない。固定SDKのCP3保存領域は208 bytes、alignment16。通常のISR entryは、今回の設定でCPENABLEをクリアしない。SPI/tick ISRのrootにPIE命令がないことを監査し、費用算定はその呼出先も個別に扱う。他のISR/NMIがPIEを使用しないことは別途必要な統合条件である。

今回の実際のリンク配置は次の通り。

| 関数 | アドレス | section |
|---|---|---|
| `spi_intr` | `0x4037932c` | `.iram0.text` |
| `spi_bus_lock_bg_entry` | `0x420244f8` | `.flash.text` |
| `spi_bus_lock_bg_exit` | `0x4200e4c4` | `.flash.text` |
| `spi_bus_lock_bg_check_dev_req` | `0x4200e570` | `.flash.text` |
| `spi_bus_lock_get_acquiring_dev` | `0x420244ec` | `.flash.text` |

**受信中はflash cacheが有効であることを仮定する。** `SPI_MASTER_IN_IRAM`、`SPI_MASTER_ISR_IN_IRAM`、`ESP_INTR_FLAG_IRAM` だけから呼出先全体のcache-off安全性を結論できない。`HEAP_PLACE_FUNCTION_INTO_FLASH` と `esp_driver_spi/Kconfig` の依存関係により、今回の実物には上表のflash helperが残っている。Kconfigの警告を隠して、全経路がIRAMにあるとは扱わない。根拠は [audit.json](audit.json) の `cache_placement` と固定IDFの `components/esp_hw_support/spi_bus_lock.c`、`components/esp_driver_spi/Kconfig`。

## 再現コマンド

公式ESP-IDF v5.5.1と再帰submoduleを取得し、固定コンパイラ、esp32ulp、ROM ELF、IDFのPython依存を用意した環境で実行する。以下の大文字はローカルの対応する絶対パスに置き換える。

```sh
python experiments/t_preprocess_integration_probe/build_probe.py \
  --idf IDF --toolchain XTENSA_ROOT --idf-tools IDF_TOOLS --python-env VENV \
  --config reports/s3-t-preprocess-integration-v2/sdk/sdkconfig.gz \
  --output build/t-preprocess/sdk

python ci/t_preprocess_sdk_audit.py \
  --idf IDF --toolchain XTENSA_ROOT \
  --elf build/t-preprocess/sdk/t_preprocess_integration_probe.elf.gz \
  --config build/t-preprocess/sdk/sdkconfig.json.gz \
  --provenance build/t-preprocess/sdk/provenance.json \
  --output build/t-preprocess/sdk/audit.json

python -m unittest tests.test_t_preprocess_sdk_audit -v
```

builderは `IDF_TARGET=esp32s3` を明示し、指定したfull sdkconfigから初期化する。出力先を変えても入力設定を失わない。ビルドに失敗した場合はELF包装へ進まない。`--no-build` は成功済みのローカルbuildを包装するときだけ使用する。包装対象は明示した一覧に限定し、前回の余った分割片は削除する。

監査はfail-fastにしない。ソース27項目、コンパイル単位11個、設定、全分割片、ABI、配置、ライフサイクル条件をそれぞれ記録する。入力自体の欠落／破損はFAIL、そこへ依存して判定できない条件はBLOCKEDとし、独立して確認できる後続条件は続行する。4件の回帰試験は、全入力欠落、最初の分割片欠落、最初のソース不一致、不正JSONを実際に与えてこの挙動を確認する。
