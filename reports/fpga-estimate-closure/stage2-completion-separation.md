# 工程2-1：資源見積もり完了と20K収容可否を別軸で判定する

## 判定原則

- **declaration_checks_complete**：49項目の申告値とハッシュ・mappedセル・インスタンスの整合条件がすべて通過したか。**物理的に合格した証明ではない**。
- **estimate_complete**：申告整合に加え、資源レポート本文の独立検算と、全機能接続の独立検証が完了したか。現実装には後二者がないため、常にfalse。
- **declared_fit_status**：申告証拠からの \`unverified\` / \`fits\` / \`does_not_fit\`。仮想証拠でも値は変わるため、実機の合格根拠にはならない。
- **fit_status**：独立したレポート値・信号接続検証を終えた場合のみ上記判定を昇格する。現実装は常に \`unverified\`。
- **declared_resource_fit_candidate**：申告された条件が整合し、\`declared_fit_status=fits\` とされた候補。物理資源・接続・合法配置の独立認定ではない。
- **stage2_resource_fit_candidate**：独立検証で\`estimate_complete=true\`かつ\`fit_status=fits\`の場合のみtrue。現実装は未達のためfalse。
- **receiver_adoptable**：工程2だけでは常にfalse。後続の全期限・実機RF/TS・品質条件まで合格して初めて別途判定可能。資源超過による「見積もり完了」は「採用可能」を意味しない。
- **stage3_permitted**：工程2見積もりが完了した場合だけtrue。工程3では独立に全期限を検証する。資源不適合という結論も隠さない。

logic位置の容量判定はLUT/ALUの実測値に分散RAM（RAM16SDP4）1セル当たり4位置相当を加えた値も照合する。単にlogic値だけが20736以内でも実際の資源位置が上限を超える可能性がある。根拠は[Gowin mappedセル帰属](scan-and-k7-memory-attribution.md)。

不可能な配置でrouted netlistとtiming reportを必須にすると、実際に収容不能だと証明した設計を永久に「見積もり未完了」にする。これを改める。ただし容量不合格ルートで当該2ファイルをN/Aとできるのは、**同じ全受信機topについて容量超過が計測され、P&R失敗ログが存在してハッシュ照合に成功した場合だけ**。ログがない・過容量ではない・配線だけできない・ツールの異常終了などは未検証とする。

凍結済みのstage1 scope.jsonにある部分fixtureの値は全体計測へ昇格させず、変更しない。工程2-1は実際の20Kに収容できると判定する作業ではなく、今後の計測結果を誤って解釈しないためのゲート改修である。

## 静的監査で確認された証拠ゲートの限界（2026-11-08）

現行の `ci/fpga_estimate_stage2.py` は、`independent_report_values_verified=false`・`independent_instance_connectivity_verified=false`・`hardware_qualified=false` を明示する。証拠ファイルの存在・SHA-256一致、申告されたinstance名・各資源値・接続済み/機能済みフラグの整合を確認する。一方、**P&Rログやresource reportの本文を独立解析して、その数値が同一の完全RTL・実ネットリストに由来することまでは検証していない**。SHA-256はファイル同一性の検査であって、第三者によるデジタル署名・実装の真正性証明ではない。回帰試験で使う任意の文字列から作った仮想証拠でも内部フラグの合格系を通過するため、CI緑や `estimate_complete` 単独をハードウェア成立の根拠にしない。

完全RTLとP&R成果物の出所・合成ログの実数値・29ブロックの実際の接続関係の独立照合は残る。ここを閉じるまでは **`stage2_resource_fit_candidate` は検証器が申告証拠を受理した候補** として扱い、正式な資源適合性認定に昇格しない。ゲート試験を強くする際も既存の47条件をfail-fastで削らない。

## 必須証拠

全体RTLソース、実際の資源レポート、CST/SDRAM・PLL制約ファイルはSHA-256付きで必須。収容可能ケースはさらにrouted netlist＋timing reportを要求する。容量超過ケースは容量超過の実測値、根拠となるP&R失敗ログのSHA-256、legal_placement=false、2ファイルが作れなかった理由を要求する。

各必須機能はRTL instance名・resource owner・実際のソースファイルのSHA-256が必要。共有資源は同一の所有者へ割当て、二重計上不可。全29機能と全8資源区分、およびmapped-cellカウントと29インスタンス存在確認を含め、計49条件を**最後まで全件照合**する。診断workflowが緑でも結果JSONの\`estimate_complete\`を見なければならない。

## 回帰

\`python3 -m unittest tests.test_fpga_estimate_stage2_gate -v\` に次の仮想証拠ケースを追加している。

1. 実レポート未登録 → 未完了。
2. mapped-netlistのカウント不一致・必須インスタンス欠落・ハッシュ改変 → 申告整合NG。
3. 仮想全段接続＋仮想配置＋申告資源が上限内 → 申告整合はOK、declared_fit_status=fits。正式なestimate_completeはfalse。
4. 仮想容量超過＋整合する失敗ログ → 申告整合はOK、declared_fit_status=does_not_fit。正式なestimate_completeはfalse。
5. 過容量の測定がない失敗宣言 → 不合格。
6. 過容量ログを改変 → 不合格。
7. 物理上限超過なのに「合法配置」と申告 → 不合格。

**これはゲートの合格/不合格シミュレーションであり、実際の②受信機の計測を捏造するものではない。**
