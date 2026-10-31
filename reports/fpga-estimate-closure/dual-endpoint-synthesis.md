# 工程2追試：T/S物理SPI endpoint同時合成（部分測定）

[GitHub Actions run 41207826622](https://github.com/kazuki0824/tangviterbi/actions/runs/41207826622) の `synth` jobにより、`experiments/dual_s3_spi_endpoints_area_top.sv` で `s3_spi_runtime_endpoint` の T(`IMAGE_ID=0`) と S(`IMAGE_ID=1`) を**同じ20K netlistで**Yosys `synth_gowin -family gw2a -nowidelut` へ投入し、終了コード0、`check -assert` に到達した。

| 指標 | 合成結果 | 判断 |
|---|---:|---|
| LUT＋ALU | **3899** | 未配置（logic physical sitesではない） |
| FF | **2478** | 未配置 |
| mapped BSRAM | **27/46** | endpoint 2系統の合成値 |
| RAM16SDP4 | **0** | このnetlist |
| DSP | **0** | このnetlist |

対象は **既存のRF/FFT/IQ制御を含むSPI endpoint実装**であり、②の受信機仕様で禁止されたFPGA→SoC復調データ返送には使用しない。このプローブが保持する不要なIQ返送機能とFFT返送portは、資源削減した②専用実装の費用ではない。現行②の同時T/S接続と機能が一致する保証はない。共通top内の他回路と資源共有・重複する可能性もあるため旧46/46 BSRAMへの単純追加をしてはならない。ルーティング、物理I/O、CDC、外部SDRAM、全受信top、全段の処理期限は未検証である。

**新しい確認済み事項:** 2個のendpointインスタンスを同時に合成でき、その部分集合の合成資源を取得した。

**次の必要作業:** ②で使わない返送経路を取り除いた受信専用の物理endpointを具体化し、実装済みFFT/K7/SDRAMと接続する。整合する単一topで面積を精算し、全29項目の未計上を閉じる。ここまで工程2は未完了。工程3へ進まない。
