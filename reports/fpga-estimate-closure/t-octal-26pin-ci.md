# ②工程2：10-pin T Octal制御/creditと26-pin T/S輸送の測定

- 対象PR #12、最新検証は [Actions 41368757400](https://github.com/kazuki0824/tangviterbi/actions/runs/41368757400)、HEAD `add6df522f0454fc393b4573e82a3ac350982ca9`。
- Tの`s3_spi_t_octal_control_endpoint`で、単一SPI2 OctalのCS/clock/8 dataがRF D711とCSR D71C/D71D/D71Eを共有。通信量や物理STAは未測定。
- Icarus `test_shared_octal_rf_control_credit`：実4KiB payload 1024word、byte一致、status snapshot/Gray credit、enable/stop/epoch処理 **PASS**。
- 単体Yosys Gowin mapped：logic LUT+ALU 1062、FF742、BSRAM9、DSP0。
- `dual_s3_26pin_transport_candidate` 同一mapped：logic LUT+ALU 3078、FF1941、BSRAM19、DSP0。
- transport信号：T Octal10、S Octal10 + Quad6 =26。未接続のTS6/event2を予約して34本。本数は必要条件だけ満たす。SDRAM PHY/TS IOやclock-capable pin mappingを合格と認定しない。
- 直前赤の原因：`token_ready_unused` の宣言位置がVerilog Icarusのoutput連結で未定義だった。宣言を使用箇所より前に移す最小修正を行い、同じ試験を緑にした。Yosys単体が合格していてもIcarus構造不良が検出される実例。

## 完了条件と未達

この構成の通信は4KiBページで、S3 raw-only送信側は16/32KiB条件。後段のFFT/K7まで含む全復調topの機能的な入力接続、FIR・同期・等化・DI、S全モード/TMCC、共有RS→TS、有限buffer/SDRAM、16/32KiB splitなどが未接続。S3側credit照会の頻度/時間/CPU費用、整合するhost transactionの実SDK運用、T/S+TSのCST/P&Rも未完了。

**工程2は未完了。工程3へ進めない。** 部分回路の資源値を旧全段予算に加算・二重控除しない。


## 2026-11-02：T 16/32KiB輸送候補

`rtl/s3_spi_t_octal_control_endpoint.sv` に `WRITE_BYTES`（4096/16384/32768）を追加。16/32KiB の場合、SPI2 Octal `s3_spi_rx` 受信から `s3_bulk_page_split` を経て、既存 `s3_pooled_page_store` の4KiB page保持へ実接続した。該当条件の `overflow` と `split_fault` は全受信faultに合流し、単にビット数を削減するものではない。

`tests/test_fpga_t_octal_endpoint.py` には4/16/32KiBのRF payloadをword単位で独立照合し、各pageのoffset/last、最後のGray credit、status、停止・epoch resetを検査するケースを追加した。既存の`tests.test_s3_bulk_page_pipeline`の16/32KiB二系統分割oracleも同一CIで再実行する。

**CIの新規結果が出る前は動作保証しない。** さらにSの接続・TMCC/slot、物理pin/STA、全FPGA復調・TS、SoC実転送・有限期限は未達。4KiBの従来緑をこの新しい長大フレームへ外挿しない。


## 2026-11-02：4/16/32KiB実行結果と8-page credit alias解消
- [Actions 41381422547](https://github.com/kazuki0824/tangviterbi/actions/runs/41381422547)（commit `bde7aa8f787b86697b0cdc0c8dbccb2749d277cc`）は全job成功。既存16/32KiB split/reorder oracle成功、T側4/16/32KiB共有Octal制御・RF・status creditの4試験成功、T単独/二系統mapped合成成功、artifact記録。
- `tests/test_fpga_t_octal_endpoint.py` の各テストで転送length、別実行ファイル名、Gray上位bit切り落としの誤判定を是正。32KiB受理8ページでは下位3bit Grayが0に戻るため、`s3_rf_credit` 16-bit累積退役値を状態word3[23:8]に追加し、C側`s3_control_decode`へ`retired_pages`を追加。
- Cの従来flags[4:0]は維持。S3の完了確認は原則、epochと単調増加するretired_pagesの差を用いる設計が必要。16bitでも一度の未観測周回65536pageは識別不能で、照会間隔の有限上限と再起動epochの検証が継続課題。
- 同一netlistの単独T Octal `WRITE_BYTES=32768` mapped LUT+ALU **1371** / FF **879** / BSRAM **9**。
- ②入力26pin transport候補（T=32KiB Octal、S=16KiB Octal+Quad）mapped LUT+ALU **3899** / FF **2315** / BSRAM **19**。各値はYosysであり実P&R/STAではない。
- 26 signal transport ＋6 signal TS予約＋2 event予約＝**34本（本数だけ）**。USB、clock-capable pin、BL616兼用、actual CTS/SDRAM、TS sink endpointはまだ全て検証未完。
- このCI成功はRF→FIR/同期→FFT/等化→DI→K7→共有RS→T/S TSの全段動作の証拠ではない。工程2の全資源計上も未完了。
