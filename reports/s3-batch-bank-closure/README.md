# ②：32 KiB案のcore別・内部RAM・bank寿命の具体化

**32 KiBへ設定変更するだけでは、既存firmware/RTLは成立しません。** 前回の96.477%は2core合計の感度計算で、既存core0集中構成には適用できません。今回、同じCPU模型をcore別へ展開し、旧SDKメモリ境界とbank寿命、現行通信形式を確認しました。単なる設定変更案を除外し、並列packing・raw-onlyメモリ再配置・可変長通信を伴う再設計仮説へ具体化します。全方式不可能の判断でも、探索停止でもありません。

[全入力hash・全18有限条件・全CPU/RAM/blackout条件・47チェック](results.json)／[実行ログ](run.log)／[6件のunittest](tests.log)。今回のデータは既存PR #10の32 KiB感度計算を補うもので、RF→TS実機や新たなFPGA配置配線の証拠ではありません。

## core別の必要条件

既存 `s3_ordered_constraints.py` はcore0をRF poll/preparation/packing/SPIの所有者、core1をT FFT workerとしています。現 `s3_capture_bridge.c` は単一FIFOと単一packerを使用し、2coreが並行で同じbankを消費できる実装ではありません。

| S・32 KiBのCPU配置仮説 | core0 | core1 | 意味 |
|---|---:|---:|---|
| RF高費用448.4375 Mcycles/sとAPIを既存core0へ集約 | 192.953% | この仕事の割当なし | この費用模型では不成立。実機CPU測定値ではない |
| RF仕事を理想的に半分ずつ、APIはcore0 | 99.529% | 93.424% | 未計上core0余裕0.471%。分割可能性未証明 |
| RF仕事を理想的に半分ずつ、Octal/Quadを別core所有 | 97.460% | 95.493% | 次に検討する配置。RF poll/prepare等を本当に均等分割できるとは未確認 |

APIをcore0へ集める場合、RF仕事のcore0分担は208.4375～225.350098 Mcycles/sに収める必要があります。合計480 Mcycles/sだけの検算ではこの条件が隠れます。Tの同じsingle-owner模型は79.682%で、Sと同じ失敗にはなりません。

2coreで並列化するなら、raw bankの読み出し区間、packing途中の2 sample/5 byte境界、出力順序、両worker完了前のbank再利用禁止を実装する必要があります。単一packerへの同時呼出しは解決策ではありません。448.4375という集約値だけから個別taskのWCETや分割可能な比率は導けず、新しい配置は未採用です。

## 内部RAMの必要条件

保存SDK `s3-runtime-control-union-evidence/results.json` の起動後・4 KiB DMA pool控除後の内部空き**上限**は25,908 Bです。128 KiBを空きheapへ追加するだけでは105,164 B不足します。これは旧FFT/RSを含むSDK配置の評価で、raw-only firmware全部の不可能性ではありません。

| 回収する既存領域 | 32 KiB×2面×2portの確保後、残り上限 |
|---|---:|
| なし | −105,164 B |
| 旧packed ring 32 KiBを置換 | −72,396 B |
| 旧ring32 KiB＋不要になるFFT/RS用2面64 KiB＋FFT係数16 KiB | **9,524 B** |

最後は再リンク前の算術上限です。worker、SPI driver、descriptor、PHY、fragmentation、DMA可能な連続領域は未確定。回収候補の領域がDMAへそのまま使えると仮定しません。2個の32 KiB slotやringを除去した後の新link mapと起動allocatorの検算が必要です。N8R8/N16R8のPSRAMを内部DMA RAMとして二重計上しません。

## bank寿命と保持量の有限モデル

保存CのTHRESHOLD=12288、LATE=2000、prepare予算20000 cyclesを用いました。S40 MSa/sではbank周期307.2 µs、モデル上の消費期限は公開後

`2×307.2 − 20000/240 − (1024+2000)/40 = 455.466667 µs`。

RF高費用模型を理想的に2分割すると1bank処理287 µs、期限余裕168.466667 µsです。これは実測上限ではありません。bank境界の取得長変動、実IRQ、DMAメモリ競合を含みません。

32 KiB・API20 µs・4096bankの**楽観的な完成時刻モデル**では、送信完了順が逆転しても連続した領域だけをretireした結果、最大ring保持120,832 B、完了済み順序逆転データ32,768 Bでした。128 KiBには収まりますが、64 KiB ringはこのモデルでも不足します。これは共有ring容量モデルで、各port固定2面の実装保証ではありません。

遅延200 µsを追加すると487 µsとなり、bank期限違反を検出しました。API60 µs条件はqueueだけ通ってもCPU予算が超えるため、総合必要条件を不合格にします。全18条件の後続検査を省略せず保存しました。tail（32 KiB未満）もbyte保存則に含めています。

モデルは到着bankの全packing完了時にデータを公開し、CPUの実行順をスケジュールしていません。完成時刻の一律遅延はストレス条件であり、実際にその遅延を吸収できるCPU配置の証明ではありません。stream中の連続流入・FPGA側skew保持の厳密最大値にも転用しません。

Sのpoll許容遅れは2000/40=50 µs。仮に8 cycles/sampleなら32 KiB相当13,108 sampleの一括packingは436.933 µsで超過します。256 sampleのsliceなら8.533 µsで、他のblackoutへ41.467 µsを残します。ただし8 cycles/sampleは感度条件であり現packerのWCETではなく、slice間pollとbank prepareの時間配置が別途必要です。

## 既存通信形式の実装障害

- `s3_wire_make()` はbytes==4096以外を拒否します。実Cをコンパイルして4096成功・16384/32768拒否を確認しました。
- `s3_spi_prepare_pages()` は4096 Bごとのheader/transactionを作ります。SPI3はcapacity1で、Octal SCTの仕組みをそのまま使えません。
- `rtl/s3_spi_rx.sv` はpayload終端を4096 B、カウンタを14bitに固定しています。32 KiB単一transactionを受け取る回路ではありません。

したがって8ページを指定するだけでは前回の1API/32 KiB模型になりません。C header、driverの転送長、FPGA parsing、page guard・保持・順序復元を一貫して変更するか、4 KiB framingを維持した別のdescriptor/送信方式を費用再計算する必要があります。今回それらのRTL/SDKを未検証で書き換えてはいません。

## 静的完了条件確認と次の作業

| 確認対象 | 方法と判定 |
|---|---|
| CPU集約/分割の保存 | 有理数で各coreの仕事を加算、集約値との一致を全4条件検査：OK。single-owner S成立：NG |
| 内部RAM | 保存SDKの30,004 B上限を照合しpool4,096 B控除、回収3条件×batch2条件を評価：旧配置NG、回収後の物理配置は未確認 |
| bank期限・ring | 18条件を全件実行。ring上限・期限超過の判定とbyte保存を照合：モデル整合OK、期限違反条件はNG |
| 現Cの32 KiB送信 | 実Cの4 KiB正例と16/32 KiB負例を実行：設定変更だけの対応はNG |
| FPGA parsing | s3_spi_rxの固定終端・14bitカウンタを確認：既存回路の32 KiB対応はNG。今回RTLシミュレーションなし |
| 受信機採用 | 全FPGA性能・core別WCET・物理通信が未達：正式割当0、採用0 |

次はraw-only firmwareの新link map/allocatorと、2coreのbank所有・packing区間・送信完了の契約を結びます。その後でdriver/FPGA受信形式を変更します。FPGA側152.09 MHzの速度未達、全stage/精度/全体資源、DI descriptor/cold-fill、全到着条件、SDRAM IOと実機RF→TSも残ります。

今回Aは前回の「32 KiB化」について、既存構成へそのまま適用する案をCPU/RAM/通信形式の3点で否定し、成立に必要な再設計条件を保存した地点です。次のBはraw-only linkと並列packing所有権の実装検証です。Aで返す理由は、単なるbatch設定の変更という前提が崩れ、次の作業がfirmware構成と通信契約の再設計になるためです。Bまで継続する選択は可能で、時間上限・承認拒否による中断ではありません。今回の仮説検証範囲としては整合性を確認しましたが、採用案確定という全体目的は未完了です。

再現：

```sh
python experiments/s3_batch_bank_closure.py
python -m unittest discover -s tests -p test_s3_batch_bank_closure.py -v
```
