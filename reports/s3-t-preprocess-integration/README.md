# T 側前処理の結合判定と証跡の復旧記録

**判定：今回の halfband 移管候補は、現状では正式採用できない。** 中断前に実行した結合モデルの結果は `MODEL_REJECT` だった。raw 入力の期限判定で継続処理が止まり、FPGA 側にも許容された 2 フレーム連続バーストを収容できない条件があった。同じ構造で比較した FPGA 実装では DSP 削減も得られなかった。

この判定の対象は、以下の具体的な実装・係数・費用モデル・転送条件である。ESP32-S3 で実現可能な T 側のあらゆる方式について、不可能と証明したものではない。

前段の検討は [T 側前処理の容量評価](../s3-t-preprocess-capacity/README.md) を参照する。本書は、その後に進めた native 入力、実 SDK、有限時間の結合モデル、残存 FPGA の検討結果を記録する。

## 1. 対象と判定条件

| 項目 | 今回の対象 |
|---|---|
| システム構成 | Tang Nano 20K と ESP32-S3 N16R8 を 2 台。T 用と S 用を分けて同時動作させる構成 ② |
| 今回の範囲 | T 用 S3 に前処理を移し、残る FPGA 処理と接続できるか |
| 入力と前処理 | 16 Mcomplex/s、1 ブロック 1,024 raw、31 tap・17 nonzero の Q15 halfband |
| S3 出力 | 8 Mcomplex/s、I16Q16、32 MB/s。1 ブロック 512 complex、2 スロット |
| core 0 / core 1 | core 0 が入力の展開と 32 出力、core 1 が残る 480 出力を担当 |
| 残存 FPGA | 診断用の 32 tap・64 phase、64/63 resampler |
| SPI の評価条件 | Quad 80 MHz、最大 40 MB/s、キュー深さ 2、16 KiB フレーム |
| 品質条件 | 元の受信品質を落とさないこと。今回の診断用係数を元方式の品質契約とは扱わない |
| FPGA → SoC | payload の逆送を使わず、control のみとする制約を維持 |

実 SDK の接続は費用評価のための暫定経路だった。Q15 出力の識別、FPGA 側の受信 parser と epoch の対応、および物理接続までを完成した受信経路として認定していない。

## 2. この復旧版で保存できたもの

コミット転送の中断後、作業ディレクトリが削除されていることを確認した。中断前には 142 ファイル、5,582,272 bytes をコミット対象として確定していた。現在は当初と同一の内容として 31 ファイルを回収し、111 ファイルは未回収である。対応関係は [復旧状況](recovery/recovery-status.json) に記録する。本節の区別は、以降の数値を評価する際にも適用する。

本書は残存した作業記録から新たに記述した報告であり、未回収の当初 README と同一内容・同一ハッシュだとは主張しない。

| 証跡 | 現在の回収状況と意味 |
|---|---|
| [当初の対象一覧](recovery/expected-artifacts.json) | 142 ファイル分のパス、サイズ、Git blob SHA、SHA-256 が残存。予定内容の識別に使う。ファイル本体の存在や検証完了を代替しない |
| 圧縮された FPGA 証跡 | baseline / residual、FIFO あり / なしの mapped JSON、合成ログ、routed JSON、計 20 個。当初の Git blob SHA を持つオブジェクトの tree 参照が成立 |
| 圧縮された SDK 証跡 | 設定、コンパイル情報、再ビルドログ、途中の診断資料、計 8 個。当初の Git blob SHA を持つオブジェクトの tree 参照が成立 |
| 復旧したソース | `native_adapter.c`、`tpre_runtime.c`、`tpre_runtime.h` の 3 ファイル。残存コピーから当初の SHA-256 に完全一致する内容を回収 |
| 最終 SDK ELF と最終 map | **未回収**。対応する圧縮 blob も確認できていない |
| 最終の費用・判定・監査 JSON | **未回収**。`runtime/costs.json`、`runtime/results.json`、`sdk/audit.json`、`validation.json` など |
| その他の新規ソース、テスト、CI | **未回収**。今回の回収物だけで当時のビルドと全テストを再実行できるとは主張しない |

復旧ソースは、不完全な実装を通常の実験経路へ接続しないよう、本報告の `recovered-source/` 以下に保存する。対応する当初のパスとハッシュは次のとおり。

| 当初のパス | SHA-256 |
|---|---|
| `experiments/t_preprocess_capacity/native_adapter.c` | `ccfcc45843e947eb82bb7016abfb8e0d66441a2c78f592f8a8580587d9a24cd7` |
| `experiments/t_preprocess_integration_probe/tpre_runtime.c` | `015ea011b206003699d78578174fb7a8d8b259246df3ea9c6aafb717fc64d31b` |
| `experiments/t_preprocess_integration_probe/tpre_runtime.h` | `b29698670ef202b9cacb9c51d05637776e7153eb2ae386703c000744e0254651` |

復旧したコードは [native_adapter.c](recovered-source/experiments/t_preprocess_capacity/native_adapter.c)、[tpre_runtime.c](recovered-source/experiments/t_preprocess_integration_probe/tpre_runtime.c)、[tpre_runtime.h](recovered-source/experiments/t_preprocess_integration_probe/tpre_runtime.h) を参照する。

SDK の `before-heap-flash-audit.json.gz`、`bss-overlap-build.log.gz`、`bss-overlap.map.gz` は途中段階の問題を記録した資料であり、最終 ELF・map や最終監査の代わりにはならない。`final-rebuild.log.gz` が残っていても、失われた最終バイナリを再取得したことにはならない。

**以下で「中断前」と記した実行結果と監査件数は、当時の作業セッションで観測した内容の記録であり、復旧後に同じ実行を再現した結果ではない。** 第5節の DSP・BSRAM 数については、保存された6つのネットリストから復旧後に再集計し、確認できた結果を別に示す。 最終 JSON や未回収ソースの内容を推測して作り直し、当時の原本として保存することはしない。

## 3. T 用 S3 の結合モデル：中断前の観測結果

当時の有限モデルは、native 入力とアダプター、halfband pipeline、実 SDK と同じ owner / worker の C 制御を接続して評価した。ホストでの所要時間を S3 の時間へ換算せず、対象命令列から組み立てた費用を処理・公開・DMA 所有権の各イベントに加算した。

この費用モデルを実機の WCET 認定とはしない。cache、MMIO、register-window 関連の遅延や割り込み・PHY 保守処理の全条件について、物理的な時間上限を確定したものではない。

最終構成では owner の 1 周に合計最大 2,048 raw の prepare を許し、1 poll あたりは最大 1,024 raw とした。owner は poll、reap、produce、poll、DMA reap、poll、DMA submit、poll、feed の 9 段階を回す。出力の READY / DONE 公開、raw バンクの返却、DMA の完了・reap は別々に扱った。

| 基準条件での観測値 | 結果 |
|---|---:|
| 要求した入力バンク数 | 4,000。20,000 バンクを要求した実行でも同じ早期停止 |
| 受け付けたバンク数 | **26** |
| 次の処理を受け付けられなくなった時点 | **5,001,048 cycle = 20.8377 ms**、240 MHz 換算 |
| その時点の残り期限 | **4,908 cycle = 20.45 µs** |
| 次の処理に宣言した上限 | **20,000 cycle = 83.333… µs** |
| worker の終了確認後の最終時点 | **5,008,380 cycle** |
| 入力の受け付け / 消費 | 326,262 / 313,344 raw |
| 生成 / reap した halfband ブロック | 306 / 305 |
| 完了した転送フレーム | 37 |
| 独立 oracle で照合した complex 出力 | 151,552 |
| 最大 core 0 step | 14,023 cycle = 58.429… µs |
| 最大 worker step | 14,983 cycle = 62.429… µs |
| 最大 poll 間隔 | 14,929 cycle = 62.204… µs |
| 停止時の状態 | adapter fault 4、task fault 5、native fault 0。RF 停止、worker 応答確認、DMA lease 維持 |

失敗したのは、残り 4,908 cycle では次の処理に宣言した 20,000 cycle の枠を確保できないという受付条件である。**20,000 cycle を、次の処理が必ず消費する実測時間や理想的な最低費用と解釈してはいけない。** この結果は、当該費用モデルとスケジュールの継続成立を棄却する。

既存の QACC / ACCX の下限評価と違い、この結合結果を「理想下限でも S3 の演算能力を超える」とする証明には使わない。また、raw の期限は core 0 が守る条件であり、worker に独立した 83.333… µs の raw lease を課して失敗させたわけではない。

当時は 27 シナリオを最後まで列挙・実行した。監査の PASS は、費用計上や所有権、異常時の停止、出力照合などの検査が成立した意味であり、受信が継続可能という PASS ではない。基準条件の容量判定は `MODEL_REJECT` のままである。

## 4. FPGA 側：許容バーストを受け切れない条件

中断前の診断では、64/63 resampler の前に 512 complex の FIFO を置き、バックプレッシャーのない SPI 入力を評価した。

| 入力条件 | 中断前の観測 |
|---|---|
| 16 KiB を 512 µs ごとに 8 フレーム | 32,768 入力、33,289 出力が oracle と一致。FIFO 最大占有 438 / 512 |
| 40 MB/s で 2 フレーム連続 | **4,817 番目の入力、482.105556 µs で FIFO に空きがなくなる** |
| 同じ速度で 8 フレーム連続 | 同じ時点で容量不足 |
| 2 フレーム連続を受けるための backlog | 872 complex、3,488 bytes |
| 8 フレーム連続を受けるための backlog | 3,479 complex、13,916 bytes |

周期的な入力を受けられた結果だけでは、キュー深さ 2 が許す連続バーストを受けられる契約にはならない。実 SDK が必ずこの連続波形を出すと証明したものではないが、それを禁止する送出ペーシング契約も確立していなかった。

想定した 154.285714 MHz、1 出力 17 cycle の処理能力を入力側へ換算すると約 35.735294 MB/s である。このモデルで 40 MB/s の連続入力を無期限に許すなら、有限 FIFO を大きくするだけでは解決しない。送出ペーシング、バースト上限、必要 FIFO 容量を同一の接続契約として定める必要がある。

## 5. FPGA 資源：今回の比較では DSP 削減がない

比較対象は、同じ構造の診断用 resampler に FIFO、scan probe、RAM 配置用の条件を加えた実装である。baseline は 16 → 512/63 Mcomplex/s の 32/63、S3 移管後の residual は 8 → 512/63 Mcomplex/s の 64/63 とした。

| 資源 | baseline 32/63 | residual 64/63 | 差 |
|---|---:|---:|---:|
| Logic positions | 1,181 | 1,305 | +124 |
| FF positions | 577 | 693 | +116 |
| BSRAM | 2 | 3 | +1 |
| DSP | **4** | **4** | **0** |

両者とも複素 tap を 1 cycle あたり 2 個処理する 4 DSP 構成であり、入力レートを半分にしたことが、この実装での DSP 数削減にはつながらなかった。これは表の比較範囲に対する結果であり、受信機全体の資源数や別構造の最適化余地を示すものではない。

**復旧後の再確認：** [資源の再集計結果](recovery/fpga-resource-recount.json)と[再現スクリプト](recovery/recount-fpga-resources.py)を追加した。baseline / residual の core-mapped、probe-mapped、routed の計6ファイルを実際に展開し、圧縮ファイルの SHA-256 が当初の manifest と一致することを確認した。全段階で `MULT18X18` は **4 → 4**、BSRAM は **2 → 3** だった。routed の各 DSP と BSRAM が別々の配置位置（BEL）を持つことも確認した。

この再集計は **6件すべて VERIFIED**。表の Logic / FF positions の換算、FIFO の時系列、STA、品質についてはこの確認に含めず、中断前の観測と未認定条件を維持する。再現コマンドはリポジトリのルートで次のとおり。

```sh
python reports/s3-t-preprocess-integration/recovery/recount-fpga-resources.py --repo .
```

対応する mapped / routed JSON と合成ログは、回収した 20 個の圧縮 blob に含まれる。ただし、RTL、係数生成器、最終の比較 JSON、配置配線ログなどは全体として回収できておらず、元と同じ実行を再現する材料は揃っていない。

## 6. タイミングと品質の未認定条件

### FPGA の表示 Fmax は採用根拠にできない

中断前の coverage 監査では、使用した GW2A-18C chipdb の 8 speed grade・37 variant に `MULT18X18` と `LUT1/2/3` のタイミング情報が欠け、該当経路が `TMG_IGNORE` になることを確認した。accumulator 160 FF と product 128 FF の D endpoint の記録も 0 だった。

このため、配置配線時に表示された約 450 / 502 MHz を datapath 全体の性能保証には使えない。4 構成の配置配線が完了したことと、目標周波数の物理タイミング成立は別の判定である。完全なモデル、または vendor STA で主要 datapath の coverage を含めて確認する必要がある。最終の `timing-coverage.json` 自体は未回収である。

### 診断用係数の良好な数値は元方式との品質等価を保証しない

元方式の係数、出力契約、許容 MER / C/N / BER の基準を特定できていなかった。今回の残存 FPGA 係数は診断用の cutoff 3.6 MHz、Kaiser β = 8.6 の設計であり、元方式の係数として扱えない。

中断前の診断計算では、cascade の ripple 0.005353 dB p-p、stopband 73.590067 dB、最大 image −90.465009 dBc などを記録した。192 件の整数計算照合と 768 件の FFT / 直接計算照合も通過した。しかし、これらは診断用 profile 内の計算確認であり、元の受信品質を維持したことの認定ではない。最終の品質 JSON・計算コードも未回収である。

## 7. 中断前に実行した検証と、今回の再検証範囲

次の件数は中断前の作業記録に基づく。最終監査出力がない状態で、復旧後に独立して確認し直した件数とは区別する。

| 検証 | 中断前に観測した結果 | 最終出力の回収状況 |
|---|---|---|
| native adapter 監査 | 16 PASS | 最終 `results.json` 未回収 |
| 実 SDK の静的監査 | 103 PASS | 最終 `audit.json` 未回収 |
| 費用・ソース・実ビルドの照合 | 393 PASS、0 FAIL、0 BLOCKED、`READY` | 最終 `costs.json` 未回収 |
| 有限結合モデルの監査 | 33 PASS、27 シナリオ。容量判定は `MODEL_REJECT` | 最終 `runtime/results.json` 未回収 |
| 回帰テスト | **28 / 28 PASS** | 新規テストと最終 `validation.json` 未回収 |
| FPGA stream 条件 | 20 条件中 18 PASS、2 件は上記 FIFO 容量不足 | 最終 summary と stream ログ未回収 |
| FPGA の CAD 実行 | 4 構成の配置配線完了。物理 timing 成立は未認定 | mapped / routed JSON、合成ログは回収済み |

28 件の回帰テストで実行したコマンドは次のとおりだった。この復旧版だけで新規テストを実行できるという案内ではない。

```sh
python -m unittest tests.test_t_native_adapter tests.test_t_preprocess_runtime \
  tests.test_t_fir_capacity_audit tests.test_s3_fir_qacc tests.test_s3_fir_accx -v
```

当時の SDK は ESP-IDF v5.5.1、commit `fcae32885b0296b32044cb99ecbdc50d98dddb83`、compiler は GCC 14.2.0 / esp-14.2.0_20241119 を使用した。最終 ELF の観測 SHA-256 は `1f0604f1afa9ddeac71d14b06252dda907496ea3376ec83216b410dc8f257574` だが、ELF 本体を回収して照合し直せていない。

途中段階の `costs.json` や `results.json` は一部残存したものの、当初 manifest の最終 SHA-256 と一致しなかったため、最終結果の代用品にはしない。今回の回収確認は、残存 source と予定 manifest の完全一致、および既存 Git blob の対応を対象にする。

## 8. 残る作業と正式採用の条件

中断前には native 接続、実 SDK のビルドと費用評価、同じ C 制御の有限モデル、残存 FPGA の評価まで実行を進めた。今回のコミットは、その判定と回収できた資料を保存するものであり、失われた 142 ファイル全体の納品や、受信経路の完成を宣言するものではない。

1. **再現可能な証跡を復元する。** manifest と一致する最終 source、ELF / map、監査 JSON、モデル、テスト、CI を回収する。回収できない部分を作り直す場合は、新しい版として識別し、新しい結果を保存する。
2. **T 用 S3 の期限条件を成立させる。** raw の受付、prepare、演算、SPI、割り込み・保守処理を含む費用とスケジュールを見直し、全条件を列挙する検査で継続処理を確認する。費用の恣意的な削減や停止直前で評価を終える方法では解決としない。
3. **S3 → FPGA の転送契約を閉じる。** 最大バーストとペーシング、必要 FIFO、実 parser と epoch を定め、許容される入力列で overflow が起きないことを示す。
4. **資源削減と FPGA timing の成立を確認する。** 比較する実装範囲を固定し、DSP が減る設計であればその差を示す。主要経路が欠落した Fmax 表示を採用条件に使わない。
5. **元方式との品質契約を確定する。** 元の係数・出力と受信品質の許容値に対し、候補の移管が条件を満たすことを確認する。

正式採用へ進めない理由は、物理機材が手元にないことだけではない。具体的な期限判定の不通過、FIFO の容量不足、今回比較での DSP 削減ゼロ、品質とタイミングの未認定が残っている。証跡を全て回収できたとしても、これらの判定条件を解消する追加設計と検証が必要である。
