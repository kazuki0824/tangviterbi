# 第一候補の実装・期限監査

対象は `S3-T-00c/v2 + S3-S-000/v0`、通信は SPI2 Octal80 + LCD16 40 MHz に固定する。
PR #4 の `82ac49bef066f7c468898ba60f21b599ba5ef447` を親とする。
**全体実装と全体処理期限の確認は未完了。受信機として採用できる証拠はない。**
今回追加したものは第一候補専用の検算器・回帰試験・再実行CI・実装監査であり、完成受信機RTL/ファームウェアではない。
以前の「第一候補」は条件付き帯域・段階別コスト見積もりに基づく実装検討の優先順位であった。
その順位は、全体収容やリアルタイム動作が確認済みであるという意味ではない。
今回の共配置結果を受け、第一候補という順位も再評価が必要である。部分topの配置失敗から
全9K構成の不可能性まで一般化できないが、この案を採用可能として他案より優先する根拠は失われた。

## 固定する処理分担

| モード | S3-WROOM-1U-N16R8 | Tang Nano 9K |
|---|---|---|
| ISDB-T 6 MHz / 13セグ | RF capture、FFT、等化・デマップ | FIR、同期、時間デインターリーブ、Viterbi、RS、TS |
| 従来ISDB-S 28.86 Mbaud | RF captureと無損失native I10/Q10 packing | FIR、同期、TC8PSK、フレームデインターリーブ、全RS、TS |

TとSは同時実行しない。切替方式は外付けSPI NOR内の複数bitstreamからの選択だけを許す。
RSのS3移動、SHIFT24への変更、ソフトウェアによる追加デシメーション/再量子化はこのPRの対象外。
TのRFは32-bit native capture wordを16 MS/sで保持、Sは40 MS/sの20-bit native sampleを情報損失なく詰める。
TのLLRはデマッパ出力契約の各8 bitであり、帯域不足対策の追加再量子化は行わない。

## 実装監査

| 必須部分 | 現在の証拠 | 未完了部分 |
|---|---|---|
| S3 capture / packing | native capture、bank bridge、IQ10 packingの既存部品 | O+LCD16同時DMA、T raw32の全受信接続と連続運転 |
| T FFT | scalar Q15 tile reference (`s3_fft_tiles.c`) | 実S3カーネル、等化・デマッパ、キャリア/TMCC制御、競合込みWCET |
| T Viterbi / RS | 独立した演算器と試験 | T全レート、インターリーブを通した接続・TS出力 |
| S TC8PSK / RS | SHIFT22 folded metric、22ACS、コンパクト全RSの独立試験 | FIR/同期、フレームデインターリーブ、連結FEC/TSの適合試験 |
| 外部メモリ | 実PSRAM PHY/queueとSPI memory bridgeの検証top | 全インターリーブのメモリ配置・競合・期限、外部I/Oタイミング |
| 通信 | Octal SPI受信、LCD16受信と4096-byte頁試験、頁管理 | 実S3 LCD DMAとの接続、Octal上り、全ポート同時ピン割当、CDC/全流量スケジューラ |
| モード切替 | NOR関連の個別試験 | 2つの完成画像、切替時所有権/リセット/再捕捉を含む連結制御 |

`s3_memory_fec_benchmark.sv` は **独立LFSRによるFECと実メモリ通信の共配置top**。
FEC入力はRFから復調・デインターリーブされた符号語ではない。
元のtopのピン配置はOctal+Quadだった。今回、検証用Quad受信をLCD16受信に
置き換えた共配置topも追加した。ただしLCD16の頁試験と共配置はS3 DMA接続や全受信機のピン収容証明ではない。
合成/P&Rが成功しても、この表の未完了欄は消えない。

## 処理期限

| 検査 | 必要条件 | 判定の範囲 |
|---|---|---|
| S TC8PSK / 3 clocks per symbol | 86.58 MHz以上 | 演算器のレート条件。全入力鎖/メモリ/出力期限は未確認 |
| S RS / 2667 cycles、1エンジン | 保守的到着35,541.872 codewords/sに対し94.790172 MHz以上 | 90 MHzでは平均サービス不足。99 MHzでは計算上1.196434 µs余裕 |
| S RS / 90 MHz、2エンジン | 各エンジンの割当間隔とバッファ期限を確保 | 元の段階別見積もりはこの2エンジン分を計上。今回の99 MHz検証は1エンジン構成 |
| T Mode3 GI1/8 | 8192 samples / 1039.5 µs | FFTだけでなく等化/デマップ/往復通信/待ちの完了期限は未確認 |
| RF capture | T 64 MB/s、S 100 MB/sを連続保持 | S3のCPU使用率モデルはWCETではない。実DMA/IRQ/メモリ競合は未確認 |

Sの28.135828 µsは既存見積もりを踏襲した203-byte分母の保守的arrival contract。
独立RSシミュレーションで262符号語の修正と最大2667 cycles、異常入力・dirty resetを確認した。
99 MHzという指定値を、配置後に達成したクロックとして扱ってはならない。
1エンジンのサービス不足は、2エンジンや別の全FPGA-RS実装まで不可能とする証明ではない。

## 上下通信と条件付き帯域

4096-byte payload、SPI header 10 bytes、20 µs/batch + .25 µs/page、LCD header 16 bytes + 8 µs/pageを仮定。
OctalはRF 3頁batchとIQ上り1頁batchの占有時間を別々に課金し、上下を合算する。
LCDは下り専用。29通信信号という見積もりはRF入力や制御を含む完成ピン配置ではない。

| モード/情報 | Octal下り MB/s | Octal上り MB/s | LCD16下り MB/s |
|---|---:|---:|---:|
| T RF native32 | 27.684877 | 0 | 36.315123 |
| T GI除去後Q15 IQ | 0 | 31.522848 | 0 |
| T 4992 carrier × 6 × 8-bit LLR / symbol | 0 | 0 | 28.813853 |
| S RF lossless20 | 50.492314 | 0 | 49.507686 |

T各port占有94.449736%、S各port占有71.795814%。Tの余裕はOctal RF換算3.903371 MB/s、LCD3.827253 MB/s。
Sは同19.835344/19.448543 MB/s。これらは連続平均レートのminimax配分であり、
整数頁のdeadline付きスケジュール・バンク再利用・LCD/SPI DMA競合を証明するものではない。
TSはFPGAから外へ出す前提であり、S3経由のTS出力帯域は含めない。

## 資源の扱い

過去モデルの第一候補2行を `reports/s3-first-candidate-sizing-model.json` に保存した。
Tの上側FF見積もり6458/6480、Sの上側logic見積もり9214/8640、FF6990/6480であり、
単なる低側stage合計を全受信機の収容証明に使えない。
Sの元モデルは90 MHz・RS2エンジンであり、99 MHz・RS1エンジンの今回の部分共配置とは構成が異なる。

| 元の段階別モデル | T 下側–上側 | S 下側–上側 |
|---|---:|---:|
| S3 CPU / 2 × 240 MHz | 68.94–93.35% | 76.76–93.42% |
| logic-site estimate / 8640 | 5874–7202 | 7830–9214 |
| FF / 6480 | 4474–6458 | 5262–6990 |
| BSRAM / 26 | 7 | 17 |
| DSP18 / 20 | 9 | 15 |

これは平均負荷と部品コストのモデル。合計CPU使用率から各coreの締切やDMA競合は証明できない。

固定SHIFT22、folded metric、22ACS、全RS1エンジン、実PSRAM/SPI bridge、constant RRで99 MHzを検証する。
この狭LUT mapped netlistのpack後logic-site必要下限は8570/8640 (99.189815%)。
これはFF共有を楽観的に見積もった必要下限であり、70箇所を完成回路の空きとして扱えない。
前段FIR/同期・デインターリーブ/TS・LCD16/上り/制御はこのtopに含まれない。
P&R timeoutは収容不能の証明ではない。詳細とseed別終了理由は共配置reportに保存する。
初回seed 1/2/3はすべて私が設定した120秒でplacement timeout、routed Fmaxは取得できなかった。
120秒が配置完了に十分という根拠はなく、その打切りを検証の停止点として扱ったのは不適切だった。
再検証で `--pnr-timeout 0` とし、同一Octal+Quad netlistのseed 1/2/3はそれぞれ
配置器自身の `Unable to find legal placement for all cells` で終了した。
反復13/11/8まで進み、経過時間による中断ではなく、受信処理のdeadline missでもない。
生ログとSHA256を `reports/s3-first-candidate-unbounded-pnr.json` と付属logに保存した。
LCD16置換後の部分topは配置前の必要logic-site下限が8628/8640 (99.861111%)。
残る12箇所を完成回路の余裕とはみなせない。seed 1/2/3はいずれも配置器自身の
同じ合法配置エラー（exit 125）で終了し、Fmaxは得られなかった。
合成source/制約/資源auditが同一であることを確認し、2回の起動による3 seedの結果を
`reports/s3-memory-fec-compact-b1-rs-acs22-q15-folded-rr-lcd16.json` にまとめた。
seed別の生ログは `reports/s3-first-candidate-lcd16-seed{1,2,3}.log`。
この共配置測定は一つの合成netlistについての必要条件であり、別RTLの最適化まで否定しない。
Actionsのjob上限はサービス側の6時間とし、これに到達した場合も受信処理のdeadline missとは扱わない。
検証スクリプト自体が配置失敗時にもJSON保存後に0で終了するため、CIはそのJSONの
`exit_code` を明示的に読み、失敗時にjobを赤にする。
共配置netlistのFF 3784/6480、BSRAM 12/26、DSP18 2/20はpack時の値であり、完成受信機の占有率ではない。
seed 2/3は同一合成netlistを再利用して個別に実行し、コマンドと終了理由をreportに保存した。

## 再実行

OSS CAD Suite 2026-10-04を使用。配布archive SHA256:
`8a4708629b0f0afd5a1835aca8b44d224fec5f6e544c5fd22a060ea5514f83c9`。
この環境では配布wrapperがABCを`lib/yosys-abc`から起動しようとする問題があり、
ローカルの同パスを同梱`bin/yosys-abc`にリンクして修復した。RTL変更ではなく起動環境修復。

```sh
python3 -m unittest discover -s tests -p test_s3_first_candidate.py -v
python3 -m unittest discover -s tests -p test_s3_rs_compact.py -v
python3 -m unittest discover -s tests -p test_s3_lcd16_rx.py -v
python3 ci/s3_psram_benchmark.py --folded-metric --rr-table --lcd16 --core-mhz 99 --seeds 1 2 3 --pnr-timeout 0
python3 experiments/s3_first_candidate.py --partial reports/s3-memory-fec-compact-b1-rs-acs22-q15-folded-rr-lcd16.json --output reports/s3-first-candidate.json
```

`all_receiver_implemented=false` / `all_deadlines_verified=false` / `receiver_adopted=false` / `safe_to_flash=false` を維持する。
全体確認を終えるには上記未完了実装を実際に接続し、全topの配置配線・外部I/O・S3 WCETとRF→TS適合試験を完了する必要がある。
実機未測定だけが残っている状態ではない。

## 第一候補の再選定

旧モデルで「帯域・平均CPU・段階別資源・必要クロック」を満たした候補の順位は暫定値に戻す。
旧第一候補のmapped部分topが配置できないため、現時点で9K/S3の新しい第一候補を指名できない。
これは9K/S3のすべての分担が失敗したという件数判定でもない。
元のN16R8台帳640表現行と経路割当を再読し、旧モデルで性能と通信路の両方が残った
Sは `S3-S-000/008/020/028`（いずれもlossless20）の4分担、Tは70表現行だった。
旧モデルではT/Sの共通port集合を持つ組が280あったが、これは接続受信機の成功数ではない。
入力台帳のSHA256、各分担の資源・CPU・上下経路の再検算値は
`reports/s3-first-candidate-reassessment.json` に固定する。

| S分担 | S3への移管 | 旧CPU低–高 / 2core | O+LCD16最大占有 | 現部分8628位置＋旧未実装段の単純加算の超過 |
|---|---|---:|---:|---:|
| S-000 | なし | 76.76–93.42% | 71.80% | 1116 |
| S-008 | frame deinterleave | 97.81–123.49% | 83.37% | 860 |
| S-020 | TS | 76.76–93.42% | 82.49% | 1052 |
| S-028 | frame deinterleave、TS | 97.81–123.49% | 94.06% | 796 |

最後の列は旧段見積もりFIR552、同期256、frame deinterleave256、TS64を
**現在の部分topに独立に足した感度計算**で、再合成した別分担の物理下限ではない。
S-008/028の高費用CPU見積もりは総容量を超え、低費用でも余裕は2.19%だけ。
S-020はTSを移しても未実装FIR/同期/インターリーブが残り、TSの往復流量が増える。
どのS分担も完成回路の配置とS3 WCETを通過していない。

T-00c/v2の旧高費用資源はlogic7202/FF6458、O+LCD16最大占有94.45%。
T-08c/v2はTSをS3へ移してlogic7074/FF6330になるが、元の共通FPGA端子へTSを戻す
経路ではO+LCD16が99.10%に達する。S3からTSを直接出す別出口は元の割当と
別途GPIO/端子/期限を検証する必要があるため、T-08cを新第一案とはしない。

RSの一部をS3へ移した別の90 MHz部分topは8226位置で配置に成功し、core 93.214 MHz。
ただしFPGA枝距離をSHIFT24へ変えた構成であり、元のSHIFT22と品質同等とは未証明。
旧未実装段1128を独立に足すと9354位置、714超過という感度計算になる。
S3側RSの競合込みWCETも未確認で、この案も第一候補には昇格できない。

再選定時は候補ごとに両モードの接続回路・実通信ピン・外部RAMを含めた別bitstreamを作り、
配置配線後のクロック、S3の競合込みWCET、頁単位の上下転送期限を通過条件とする。
今回の収容問題が出たのはSの共配置topなので、Sの処理分担とビットストリームを先に再測定する。
T/Sは同時実行せず別画像へ切り替える契約であり、両者のFPGA資源を合算しない。
次の実装検証では、Sの64 KiB RF/PSRAM transport bridgeを小さいcredit付き頁バッファへ
変更できるかを、無損失・最悪休止・ページ順序・受信側所有権とともに調べる。
現bridgeの面積を削る可能性はあるが、代替設計の完成面積や期限を先取りして成立とは判定しない。
どれも満たさなければ「成立が確認された9K候補は0」と報告し、未検証案まで不可能とは数えない。

### 2頁BRAMによるS部分構成の実測

`rtl/s3_bram2_memory_bridge.sv` でOctalとLCD16の4096バイト頁を無再量子化で
受ける2頁BRAMを試作した。逆順に届く2頁と受信側の休止をシミュレーションで確認した。
同じfolded metric、22ACS Viterbi、全RSの**独立駆動**部分topに共配置すると、
狭LUT pack後の必要logic-site下限は7134/8640（82.57%）となり、旧部分topの
8628から1494減った。seed 1は合法配置・配線まで進んだが、core Fmax 79.94 MHzで
要求99 MHzに届かない。Octal 145.52 MHz対80 MHz、LCD16 157.06 MHz対40 MHz。
律速はViterbi経路メトリックの加算後の差分比較。
同じ12ビット符号判定を4+4+3ビットの借りで分割した別試作は7346位置、
core Fmax 62.85 MHzとなり、改善できなかった。
両者とも配置は成功したが、処理期限は不合格である。

旧未実装段の見積もり1128位置を7134へ単純加算した8262という値は
**完成回路の物理占有率ではない**。producerへのcredit返却、連続頁の最悪休止、
RFからTSまでの接続、S3競合込みWCETを未検証のまま、この部分試作を新第一候補にはしない。
合成・配置配線の再現スクリプト、ピン・クロック制約、計測値とログSHA256は
`ci/s3_bram2_benchmark.py` / `experiments/s3_bram2_{pins.cst,clocks.py}` /
`reports/s3-bram2-prototype.json` に記録した。
