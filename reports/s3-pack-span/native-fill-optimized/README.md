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

raw-only SPI workflowへnative sourceと新試験のpathを追加し、既存の共通/raw専用2構成のSDK build・link監査へこの変更を通す。ローカルobject確認2チェックと7 unittestは成功。SDK CIの結果と再検算は下記。配置/heap/IRAMは旧結果を新sourceへ流用しない。

再現: `python -m ci.s3_native_fill_target --toolchain build/fir-target/xtensa-esp-elf --output reports/s3-pack-span/native-fill-optimized`。


## SDK link結果を確認

[raw-only SPI placement run 40192845126](https://github.com/kazuki0824/tangviterbi/actions/runs/40192845126) はproduction commit `176653a216363191004efc17390e4aafebec7126`で成功。共通40＋raw専用45＝85静的check成功。artifact 12598732910のZIP SHA256は `2a00f43e2ffed941c28131683134c85d07da130301865a0894b8934073a7e278`。ELF/map/config/build logをsdk以下に保存した。

`ci/s3_native_fill_sdk_audit.py`で8チェック成功: artifact内ELF hash、native/packing source hash、packing主要3関数の旧SDKとのバイト列・アドレス一致、SDK fillの3命令bodyと25命令の関数形を確認。実SDKのfill cloneは69 bytes、0x40377408。前節のobjectだけで得たbody/区間費用を、同じproductionのSDKでも確認できた。packing内部の以前のCFG集計は同一命令列へ適用できる。callback先・メモリ待ち・呼出し元全体の実時間は引き続き別。

raw専用の `_iram_end` は0x40387800→0x40387900、`_heap_start` は0x3fcac540→0x3fcac640。共通構成の両境界は前回と同じ。raw専用はalignment込みで内部heap開始が256 B進む。メモリ台帳19チェックと限定SPI ISR配置26チェックを新ELFで再実行して成功。fresh vectorsの場合の既知動的費用控除後の**残量上限**はSPI初期化17480 B、PHY較正15484 B、定常17356 B。未計上起動費用・断片化・TLSF replay・実bootはこの結果で解消していない。

別の[RF共存診断run 40192845047](https://github.com/kazuki0824/tangviterbi/actions/runs/40192845047)は8 profileすべてで `s3_transport.c` が `s3_iq10_block.h` を見つけられず停止した。リンク容量の判定に達していない。診断用コピーの依存ヘッダ漏れを修正し、workflowのpathにも追加した。実copy-listをASTから読み、そのコピー先でtransportをhost構文検査して成功。SDKでの再実行結果は別途確認する。「全CI成功」とは報告しない。

### 期限検証へ引き継ぐ数値

fill clone全体の安全側包絡21574命令を1命令/cycleと仮定し、他の処理を無料にした場合、S入力は3596 samples進む。前回の開始位相条件のbody-only値8314に代わり、fill-clone-onlyの最遅writtenは10692となる（14288−3596）。実際にはINDEX観測からfill開始まで、bank callback内部、次INDEX/SELECTまで、割込み等をさらに差し引く必要がある。早期準備を含む実task scheduleと共通clockはまだ未統合で、10692を本番の固定許可値として追加していない。
