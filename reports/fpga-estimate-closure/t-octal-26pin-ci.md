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
