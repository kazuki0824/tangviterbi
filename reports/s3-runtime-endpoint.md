# RF/FFT/IQ/statusの未実装接続を追加

2026-10-12。Tang Nano 9K完成基板とS3-WROOM-1U-N16R8、T/S排他切替。
`e6d9797` のlink-only保存証拠の後続。全受信機の完成を示すものではない。

| 以前の未実装 | 今回の実装 | 確認した範囲 |
|---|---|---|
| FPGA FFT戻り入口、RFとの保持・競合 | 4×4 KiBの共有BSRAM、RF/FFT独立順序cursor・独立held出力、2 port token parser | RFを17語で停止してもFFT16ページが完了。32ページの全語、同じoffsetの異なるstream、20-bit sequence wrap、stall中不変性 |
| 実identity／epoch／enable／IQ-ready | SPI3 D71C/D71D/D71EのRTLと実SPI driver C。core request/ACKによるcoherent snapshot、nonceとchecksum、実CSR ACK | SPI波形とC境界試験。core停止中の繰返しqueryは古いsnapshotを新しいACKと誤認しない。request DMA終了をCSR ACKとみなさない |
| RF/FFT/IQ/controlを一つのendpointへ接続 | `s3_spi_runtime_endpoint`：共有pool、RF retirement、IQ ping-pong、status、epoch resetを結合。TのQuad書込みparserは使わない構成 | 80 MHz SPI/90 MHz coreの実RTLでRF5ページ＋FFT2ページ＋IQ2ページを並行転送し全byte照合、mute/drain/fresh epoch検証。DSPは未接続 |
| 毎IQページのready問い合わせ | 2-bit Grayの公開ページ数と` s3_iq_credit `。2不変pageの制限を利用しoffset/epochを照合して一度だけ消費 | 10,000ページ、modulo4 wrap、2ページ同時公開、unstable retry、epoch/offset/過剰公開fault |
| RF creditとFFT用空きの両立 | RF creditを3-bit modulo8へ拡張。S最大4、T最大2未消費RFページ。Tは共有4ページのうち2ページをFFT返送用に確保 | 400ページの実pump/ring/driver境界試験。GPIOをDMA完了の代用にしない |
| Quadのpolling終了待ちによるRF処理停止 | RF開始前にSPI3を専有取得。固定IDF 5.5.1のHALと同じdone predicateを先に確認し、未完了ならpolling_endを呼ばず戻る | actual CをSDK境界shimで検証。polling_end(0)はSDKの厳密`>`判定で次tickまでspinし得るため、0だけを非blockingの根拠にしない |
| native packerの不要なmask | low20-bitと同じ結果になる狭いbitfield抽出へ変更 | native payloadのbit一致。固定S3 GCC14.2 O2/O3でhelper43→39命令、8読出し5書込み。WCETではない |

信号の追加software間引き・再量子化はない。SPI silicon、実FreeRTOS、GPIO電気的CDCはhost shimでは確認できない。

## 配線と上下メッセージ

従来のOctal SPI2／Quad SPI3の18本を維持する。追加線は以下。

| 方向・意味 | ESP GPIO | FPGA package pin | レベル |
|---|---|---|---|
| FPGA→SoC RF consumer retire Gray[0:2] | 38,39,41 | 55,56,57 | 3.3 V |
| FPGA→SoC IQ page publication Gray[0:1] | 42,47 | 37,38 | 3.3 V |

GPIOは同じIN1 register一回のreadで各counterを採取する。連続2回安定性確認は電気的CDCの証明ではない。
GPIO42/47はこのN16R8 moduleで使用できる線。FPGA37/38のmicroSD機能と共用できない。
新CSTのpackage pin割当と3.3 V bankは前提、実配線と外部IO setup/holdは未検証。
旧SDA/SCL55/56をstream中に併用しない。

TのSoC→FPGAはOctal native RF（40 MB/s）と全FFT bin返送、FPGA→SoCはQuadの全IQページ。
SのSoC→FPGAは両port native RF（合計100 MB/s）、RS split案では別途RPC request/replyと符号語保持が必要。
共通controlはQuadで10-byte request header、queryだけ32-byte reply。wire時間はquery1.05 µs、command0.25 µs。
1 kHz queryならQuad使用率0.105%／42 kB/sで、API/CS gap/IRQ費用は別。
現pipelineはcontrol clientを保持するが受信中の周期queryを自動実行しない。IQ公開はGPIOを使う。
帯域に収まる必要条件でも、全core期限・buffer期限を満たした正式割当とはしない。

## 資源の証拠

`ci/s3_runtime_endpoint_evidence.py`を追加。上記のconnected endpointと既存FECを同時合成する。
FECは独立synthetic input、IQはsynthetic producerであり、FIR/sync/equalizer/interleaver/TSは含まない。
生成top、実CST、clock constraint、source hash、synth/pack/P&R logを保存する。
最小サイト数はpack済みnetlistについての下限、routingの実使用数ではない。

| 部分構成 seed1 | 最小サイト / 8640 | 配置配線の結果 |
|---|---:|---|
| T endpoint＋Viterbi＋RS | 8216（95.09%） | 180秒limit。fit/timing不明 |
| S endpoint＋TC8PSK＋split RS演算 | 測定中 | 測定中 |
| S endpoint＋TC8PSK＋全RS | 8857（102.51%） | 217サイト超過。今回のmapped netlistを却下 |

Tの最低424サイトの余白は未実装DSPが収まる証明ではない。
S all-RSの失敗も、別実装・別分担の全否定にはしない。
旧direct-only endpointの合格値を新connected endpointの合格に流用しない。

## 未完了の理由と範囲

| 項目 | 現在 | 残る依存・必要な作業 |
|---|---|---|
| SDKの同時code/data/stack/driver | 新Cをruntime32 probeとCIへ追加 | 変更後の実SDKリンクとmapを再検算する。旧18,080 B gapは変更後の値ではない |
| 全受信top | **未実装** | FIR、同期、equalizer/demap、全interleaver、FEC連結、TMCC、符号語保持/補正、TS。実機待ちと分類しない |
| CPU/通信/buffer joint schedule | **未完了** | 全DSPと実API費用を含むイベント試験。既存36条件は仮定を使う必要条件で、新creditの保証ではない |
| NOR切替の実driver binding | 一般C state machineと実status clientを実装済み、binding未完了 | RECONFIG_Nの1.8 V level shifter、外付けNORからbootするT/S/recovery image、実tune/lock driver。background programmingは基板外付けNORだけ |
| 実機が必要な確認 | 未取得 | native RF dump互換性/品質、各kernel/API/IRQ WCET、stack high-water/PHY heap、共有SRAM競合、GPIO/SPI電気timing、NOR boot、連続TS |
| 正式採用 | 0 | 全体性能確認→全messageの通信割当→非空候補採用を維持。未評価候補は不可能や通信路ゼロとは書かない |

この追加で残作業全体が完了したとは記載しない。
`complete_estimate=false` / `receiver_adopted=false` / `safe_to_flash=false`。
