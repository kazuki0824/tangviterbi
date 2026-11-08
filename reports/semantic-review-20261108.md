# 2026-11-08：研究PR統合後の設計参考情報に対する意味論レビュー（途中監査）

> これは時点付きの監査記録であり、新しい設計値の正本ではない。設計の現在条件は[資料索引](design-reference-index.md)、実験値と根拠は各原資料とハッシュ付きの元成果物から辿る。

## 対象と確認方法

- 統合対象は① #8→#11、② #9→#10→#12。内容が一致しない並行追加文書を解消し、予定統合ツリーのパス保存・主な文書リンクを静的に確認した。
- #12時点のMarkdown **192ファイル**について、未完了/採用/不成立/過去のマージ方針などの語を横断点検。重要な主資料と判定器・その回帰テストは本文まで読み、設計前提・測定根拠・実装との相違を追加で確認した。ただし **192ファイルを全行、人手相当の意味論検査で承認したのではない**。#8停止監査、#11 traceback比較も個別に読んだ。
- ソース全件の個別検査、実機のRF→TS、全段P&R/STA、SDK実機WCETは未実施。GitHub APIを通じてファイルを読み、ローカルclone・実ターゲットでの全テストは実行できていない。

## 設計に対する意味論上の判定

| 対象 | 現在言えること | 主な根拠と留保 |
| --- | --- | --- |
| ① 9K | 具体的な複合置換はlogicおよびK7速度が未達。全方式の原理的不可能性は未証明 | [停止監査](9k-stop-audit.md)、[再設計方針](9k-recovery-plan.md)。停止監査内のDraft/非マージは2026-10-19当時の運用履歴に過ぎない |
| ① traceback | 比較用RTL・有限機能検証は研究成果。採用可能な9K実装・合法P&R・期限達成は未証明 | [#11の比較](https://github.com/kazuki0824/tangviterbi/pull/11)、[比較資料](https://github.com/kazuki0824/tangviterbi/blob/study/9k-traceback-ip-comparison/reports/9k-traceback-ip-comparison.md) |
| ② 20KとS3×2 | I10/Q10・T16/S40 MSa/sを元に研究。外部RF前段・全機能接続・物理制約・実RF/TSは未達 | [分担と境界](20k-dual-s3.md)、[計測精算](fpga-estimate-closure/stage2-reconciliation.md) |
| ② FPGA資源 | 旧予算 20472/20736、差分代入後 20726/20736、保持付き別案 22002/20736 は**同じ統合ネットリストではない**。10logicの旧見積り余白は採用余裕ではない | [精算](fpga-estimate-closure/stage2-reconciliation.md) |
| ② FPGA pin | 現状の診断topは46本／ヘッダ34本（12本超過）。計画上の34本は電気・クロック可能配置・CST適合をまだ証明しない | [pin予算](fpga-estimate-closure/pin-budget.md) |
| ② 部分RAM合成 | no_scan: LUT/ALU 19779、RAM16SDP4 273。1 RAM=4位置として **20871/20736、135超過**。これは全段の資源否決ではなく部分topのスクリーニング | [scan差とセル所有](fpga-estimate-closure/scan-and-k7-memory-attribution.md) |
| SoC側 | 条件付き正常ループ期限・SDK配置の調査が存在するが、周期PHY割込み・mem/MMIO stall・RF品質・全taskのWCETは未確定 | [S側queue](s3-queue-owner/README.md)、[全SoC見積り](receiver-integrated-estimate/README.md) |

## この監査で修正した意味論上の誤り・混同

1. **分散RAMを容量合否から落としていた。** `ci/fpga_estimate_stage2.py` にLUT/ALU＋RAM16SDP4×4の実位置換算を追加。20736境界、超過によるrouted拒否、容量超過の仮想証拠の3回帰を追加。ただしlogic計数とRAMセルの二重計上は許さないという計測契約を維持する。
2. **工程2の資源適合を受信機正式採用としていた。** `receiver_adoptable` を工程2のみでは常にfalseとし、別に `stage2_resource_fit_candidate` を出力。工程3以降の期限と実機品質を飛ばさない。
3. **証拠ハッシュを、レポート値の独立検証や署名と混同できた。** `independent_report_values_verified=false`、`independent_instance_connectivity_verified=false`、`hardware_qualified=false` を明示。ハッシュ照合は同一性検査であり、報告本文の数値の真正性や全機能接続を確認していない。
4. **#8の「Draftのままマージしない」が現行判断に見えた。** 当時の運用上の判断として明記し、研究成果の保存と回路の技術的な不成立を分離。
5. **並行PRで異なる文書が上書きされうる。** #8の9K新停止判断と#10の後続K7/SDRAM評価を両立するよう#9/#10/#12の文書を調停し、資料索引を新設。

## 続行監査：工程2の意味論的な偽陽性対策

- **49項目へ拡張**：従来の47項目に、Yosys mapped JSONのprimitive countと全29機能のinstance存在確認を追加。LUT/ALU・FF・BSRAM・RAM16SDP4・DSP・PLLの計数が宣言値と不一致なら拒否。不明なmapped primitiveも捨てずに不合格とする。元の47項目と新2項目は最後まで列挙する。
- **独立検証ではない**：mapped JSONと `full-top-proof.json` を同時に捏造できるため、cell count一致だけでnetlistが実配置された真正な受信機だとは認定しない。インスタンス名の存在もデータフロー・各ブロックの機能実装を証明しない。
- **正式な完了と申告整合を分離**：仮想証拠が49項目合格しても `declaration_checks_complete=true`・`declared_fit_status=fits/does_not_fit` という申告内整合にとどめる。現行の独立レポート数値検証と独立信号接続検証が欠けるため `estimate_complete=false`、`fit_status=unverified`、`stage2_resource_fit_candidate=false`、`receiver_adoptable=false`、`stage3_permitted=false` を維持する。申告された候補は `declared_resource_fit_candidate` に別記する。
- **反例回帰を追加**：mapped値の相違、29インスタンスの欠落、netlistハッシュ改変、未知primitive、LUTRAMの容量境界・容量超過、合格宣言のみの反例をテストする。テスト用の合成JSONはCAD実測の証拠にならない。
- **CIの異常終了を成功として隠さない**：`fpga-estimate-stage2.yml` は49項目のJSON全列挙と未完了状態を確認する。正常に未完了を報告するケースのみCI成功とし、クラッシュ・条件未列挙・JSON不正を不合格とする。最新HEADの実行結果は別途確認する。
- **設計上の基準変更はなし**：I10/Q10・T16/S40 MSa/s・20Kピン34本上限・全工程2未完了という制約を変更していない。元の不成立/未検証の測定値も残す。

## 残る意味論上の検証責任

- **重要・未完了：** `full-top-proof.json` の自己申告boolean、stage instance名、資源値が実際の全段RTL・mapped netlist・nextpnrログの本文に対応することの**独立検査**。現ゲートはファイル存在・SHA-256一致を扱うが、報告値を独立抽出しない。仮想テストが「fits」を返しても実ボードの証明ではない。
- **重要・未完了：** 全29機能を同一回路として実接続したこと、共有資源の一意帰属、論理資源・SRAM/SDRAM・ピン数・PLL/CDC・物理タイミングの同条件証拠。
- **重要・未完了：** ①②の全RTL・C・Python・workflow、各計測artifactとの行単位・データフロー単位の完全な意味論監査。文書の用語横断走査はこの監査の代わりではない。
- **重要・未完了：** 最新HEADのCI結果。CI緑でも物理不適合や未実装を合格へ変更しない。

**現時点の判定：** 研究成果を正しい注記付きでmainに残すための意味論的修正を実施したが、全ソースと全証拠を独立検証した「意味論的レビュー完了」の認定はまだ不可。特に#12の資料は、工程2未完了・受信機正式採用不可を保持する。
