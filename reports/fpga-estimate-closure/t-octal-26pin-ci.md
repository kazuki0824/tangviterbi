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
