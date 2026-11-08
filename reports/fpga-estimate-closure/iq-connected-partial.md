# 工程2：実SPI 2系統→I10/Q10復元の結合と、FFT/K7部分統合の共存

基準: PR #12の commit `58bc56b5dd41b17772704bf83ef08bcab40004a2`。
証拠: [GitHub Actions run 41276164352](https://github.com/kazuki0824/tangviterbi/actions/runs/41276164352)。

## 実装と機能試験

`experiments/dual_s3_iq_ingress_joint_fft_area_top.sv` でT/Sの`s3_spi_runtime_endpoint`出力を、各独立`s3_iq10_unpack`入力へready/validで直接接続した。RF_valid/RF_ready/RF_data は実回路信号であり、架空のdemodulatorを入れない。stream_enableとfaultに基づく各epoch reset境界を設け、連続フレーム途中ではunpackerをresetしない。内部FFT/K7は別のCADスキャン刺激で駆動するため、復調の端から端までの接続とは主張しない。

`tests/dual_iq10_unpack_tb.sv` は2独立経路、各4096個のI10/Q10（=8192サンプル合計）、各2560個の32-bit転送word、8192byte/系統、2つの4096byte source pageを貫通する連続ビット列を作る。別の数学的bit oracleと検算し、異なる入力valid/出力ready停止列、word末尾の20-bit境界を検査した。Icarus/vvp: **PASS**（ビット誤りなし、source/consumer deadlockなし）。この試験はSPI PHYやページendpointそのもののサイクル動作を検証するものではない。

## 一体合成資源測定

前段 `dual_s3_ingress_joint_fft_area_top` と同じFFT/SDRAM/K7部分、同じ既存SPI 2系統を維持し、アンパッカーを実結合。Gowin GW2A向け Yosys `synth_gowin -family gw2a -nowidelut` + `check -assert` 成功。

| 測定項目 | 前段（未接続IQ） | 今回（IQ実接続） | 差 |
|---|---:|---:|---:|
| mapped LUT＋ALU | 13,591 | **14,109** | +518 |
| mapped FF | 9,189 | **9,327** | +138 |
| mapped BSRAM | 35 | **35** | 0 |
| mapped RAM16SDP4 | 273 | **273** | 0 |
| DSP18 | 6 | **6** | 0 |
| 暫定logic位置換算（LUT＋ALU＋4×RAM16SDP4） | 14,683 | **15,201/20,736** | +518 |

**15,201は配置配線後の合法site数ではない。** 今回の各sample実出力だけではシステム全体で同時処理が成立するとは認定できない。過去の全段予算`20,472/20,736`と単純加算・差引きしない。BSRAM35/46も実回路の全memory footprintではない。

## 残存する工程2の最終必須条件

未接続: T/S FIR、同期/シンボル抽出、T FFT→等化/demap→時間DI、S inner decode/フレームDIと動的TMCC/slot、shared K7→shared RS→TS×2、producerの有限保持/creditと二系統入力のCDC、PLL/SDRAM PHY/基板IO・pin fit。既存FFT/K7はCAD harness起動であり、上記機能の代替として扱わない。

したがって**工程2未完了**。全必須機能の同一top接続、資源所有権一意化、P&Rによる20K収容・各資源計測が揃うまで工程3へ進まない。

## 今回の証拠の使い方

- 旧endpoint比較は［dual-endpoint-synthesis.md］(dual-endpoint-synthesis.md)
- 今回の実結合部分合成はCI artifact `dual-iq-connected-partial-area` 内`result.json`・`iq-bit-oracle.log`・`yosys.log`
- 異なるscopeの部品の資源差を同じfull-top測定と呼ばず、工程2台帳へ実配線済みの証拠として追加する
