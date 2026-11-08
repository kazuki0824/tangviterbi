# 工程2：RF page creditを既存status照会へ同梱する実装候補

## 目的と制約
Tang Nano 20KのJ5/J6計34 signal上限の下では、従来のT/S各3bit `RF_credit_gray` を外部専用信号に割り当てられない。現実験topはSPI2+SPI3×2（32pin）＋TS×2（6pin）＋event（2pin）＋credit×2（6pin）＝46pinで不適合。T側SPI3を消しても40pinで不適合。

そこで `s3_spi_control` の既存32-byte状態snapshot内、`flags` word [7:5] に `RF_credit_gray[2:0]` を持たせる。従来flags [4:0]、status magic、image/epoch、IQ_offset、nonce、build_tag、checksumの配置とCRCではないXOR整合式は保つ。
- FPGA status snapshotはcoreで `RF_credit_gray` を採取し、チェックワードも同一状態を組み込む。
- S3 `s3_control_decode` は `flags&31` を従来のflagsとし、`credit_gray=(word3>>5)&7` を別の項目へ復元する。余剰[31:8]を非ゼロなら不正として拒否する。
- 従来4-bit Quadおよび新8-bit Octalに同一構造を適用。statusを読むまでの伝搬と、CS/epoch/nonce/ACKを別の有効な仕組みとして保持する。
- これによって**FPGA側に既に存在するcreditカウンタの値を既存statusで表現する回路経路を実装した**。ただし外部creditピンの消去とS3側フロー制御の切替はまだ未実施。

## 未成立の点
1. 新Octalを物理SPI2で使うT専用endpoint、実S3制御adapter、既存Octal SPI2送信との相互排他は未接続。
2. 各S3のcredit取得間隔と必要なpage再利用期限を同一状態機械で検証していない。3-bit Grayをstatus照会で取得しても、read完了が遅ければRF page ringは満杯になる。query頻度・CPU処理費用と100 MB/sのS側の余裕は未検証。
3. フロー制御をstatusへ移しただけではイベント2本をどのタイミングで使うか決定できず、34pin実CST・PLL/IO STAは未完成。
4. 現行 `s3_spi_runtime_endpoint` の独立credit出力とT側Quad端子は引き続き存在する。現`dual_s3_spi_ingress_only_area_top`を34pin合格と認定しない。
5. `s3_spi_rx`既定4KiBと実S3の16/32KiB通信の不一致、全ISDB復調top・資源・期限は未解決。

## 試験と採否
FPGA Quad制御の既存テスト、Octal追加テスト、host status decoderテストを同じCIで実行する。`tests/s3_control_host.c`のスナップショットにRF-credit=3を入れ、low flags=5が不変か確認する。新Octalの初期reset・command/epoch等のテストが緑にならない間は採用しない。

**工程2は未完了であり工程3へは移行しない。**
