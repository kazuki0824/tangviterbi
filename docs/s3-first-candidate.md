# 第一候補の実装・期限監査

対象は `S3-T-00c/v2 + S3-S-000/v0`、通信は SPI2 Octal80 + LCD16 40 MHz に固定する。
PR #4 の `82ac49bef066f7c468898ba60f21b599ba5ef447` を親とする。
**全体実装と全体処理期限の確認は未完了。受信機として採用できる証拠はない。**
今回追加したものは第一候補専用の検算器・回帰試験・再実行CI・実装監査であり、完成受信機RTL/ファームウェアではない。
以前の「第一候補」は条件付き帯域・段階別コスト見積もりに基づく実装検討の優先順位であった。
その順位は、全体収容やリアルタイム動作が確認済みであるという意味ではない。

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
| 通信 | Octal/Quad SPI受信部品、頁管理 | LCD16受信、Octal上り、固定ピン割当、CDC、全流量スケジューラ |
| モード切替 | NOR関連の個別試験 | 2つの完成画像、切替時所有権/リセット/再捕捉を含む連結制御 |

`s3_memory_fec_benchmark.sv` は **独立LFSRによるFECと実メモリ通信の共配置top**。
FEC入力はRFから復調・デインターリーブされた符号語ではない。
そのピン配置はOctal+Quadであり、本候補のOctal+LCD16のピン収容証明にもならない。
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
再検証では `--pnr-timeout 0` によりローカルの経過秒数による打切りを撤廃する。
Actionsのjob上限はサービス側の6時間とし、これに到達した場合も受信処理のdeadline missとは扱わない。
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
python3 ci/s3_psram_benchmark.py --folded-metric --rr-table --core-mhz 99 --seeds 1 2 3 --pnr-timeout 0
python3 experiments/s3_first_candidate.py --partial reports/s3-memory-fec-compact-b1-rs-acs22-q15-folded-rr.json --output reports/s3-first-candidate.json
```

`all_receiver_implemented=false` / `all_deadlines_verified=false` / `receiver_adopted=false` / `safe_to_flash=false` を維持する。
全体確認を終えるには上記未完了実装を実際に接続し、全topの配置配線・外部I/O・S3 WCETとRF→TS適合試験を完了する必要がある。
実機未測定だけが残っている状態ではない。
