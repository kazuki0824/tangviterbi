# ② sentinel書込みを連続区間化

2026-10-25。`s3_native_capture.c::fill` の各wordでのring mask/address計算を、ring末尾までの連続区間ごとの計算へ移した。折返し後はbank先頭から続ける。write順序、volatile、末尾memw、bank callbackの1回呼出し、reclaimしてからwriteする順序を維持。poll分割・core配分・時計・RF境界条件は変更していない。追加decimate/再量子化はない。

## 機能確認

実際のproduction Cをincludeしてprivate fillを呼ぶhost testで、全16384開始位置×7長さ（0,1,2,3072,4096,16384,16385）、非正規化開始位置1件、計114689ケースを検証。独立した距離式で全wordの期待値、未変更領域、bank前後guard、callback回数を確認した。productionでは最大16384 wordsだが、複数周回も元実装どおり処理する。UBSan有効。

既存native capture・parallel packing・clocked deadlineも含む7 unittestが成功。host時計には実write時間を代入しておらず、受信速度/期限の証明ではない。

## targetコンパイル

GCC14.2 esp-14.2.0_20241119、ESP32-S3設定、O2で**実ファイル全体**をcompile。SDKヘッダの宣言だけを最小stubで与えたobject確認であり、SDK全体のlink結果とは区別する。stub/flags/source hashをtarget.jsonに保存。compilerが非zero長のproduction呼出し向けに作ったfill cloneを確認。

| 項目 | 旧SDK | 今回object |
|---|---:|---:|
| wordごとのbody命令 | 5 | 3 |
| 次bankの7168 wordsのbody | 35840 | 21504 |
| 公称Tのbody命令/s | 46.667 M | 28 M |
| 公称Sのbody命令/s | 116.667 M | 70 M |
| bodyのみ理想240MHz、1命令/cycle | 149.333 µs | 89.6 µs |

新loopは `memw, s32i.n, addi.n`。各volatile store前のbarrierを除去していない。clone内は1呼出し9命令＋13命令/区間＋3命令/word、2呼出し・合計2〜4区間として21548〜21574命令（4区間は安全側の包絡値）。bank callback内部、caller、バス競合、割込みは別。旧SDKはbodyだけを比較しており、関数全体が正確に40%高速化したという主張ではない。

同じ公称S条件で、旧packing CFG119.898682 M命令/sとAPI仮定14.649902 Mcycles/sを保持し、今回fill clone全体上限21574命令/bankを理想換算するとcoordinatorは **204.776449 Mcycles/s**。従来の条件付き251.215から改善するが、残る約35.224 Mcycles/sを使用可能な実測余裕とは扱わない。異なるbinaryの部分結果を合成した参考模型で、他のRF、clock、IRQ、MMIO待ち、SPI競合、非公称bank長はまだ未検証。

89.6µsでもSのLATE相当50µsより長い。前回記載した開始位相条件は引き続き必要。早期準備・lease・packingを合わせたscheduleと共通時計統合は未完。今回だけで正式な性能合格/通信路割当/採用へ進めない。①は変更しない。

## SDK全体の確認

raw-only SPI workflowへnative sourceと新試験のpathを追加し、既存の共通/raw専用2構成のSDK build・link監査へこの変更を通す。ローカルobject確認2チェックと7 unittestは成功。SDK CI結果は別途確認する。配置/heap/IRAMは旧結果を新sourceへ流用しない。

再現: `python -m ci.s3_native_fill_target --toolchain build/fir-target/xtensa-esp-elf --output reports/s3-pack-span/native-fill-optimized`。
