# S用RSのFPGA→S3復調データ返送：禁止理由の再監査

**結論：シンドローム転送量が大きすぎて全経路で不成立、とは証明されていない。** ただし現在のRS部分移管の実装は、通信・CPU・FPGA資源・同一batch期限を合わせた受信機成立の証拠が0件。PR #8の**指令のみ**制約は維持し、以下を禁止解除の根拠ではなく比較証拠として保存する。

旧台帳 [s3-partition-audit](../s3-partition-audit.md) と [API感度](../s3-link-cpu-sensitivity.md)、[Forney面積](../s3-rs-forney.md)を用いる。コード：[`experiments/s3_rs_reverse_policy_audit.py`](../../experiments/s3_rs_reverse_policy_audit.py)、試験：[`tests/test_s3_rs_reverse_policy_audit.py`](../../tests/test_s3_rs_reverse_policy_audit.py)。出典の多くは**仮定模型**であり、実S3の実行時間やPHYを測っていない。

## 量と実際のボトルネック

S RS保守到着率は **35,541.871921 CW/s**（28.135828 µs/CW）。204 CW/batch は5.739709 ms。4096 B/page、旧Octal80+Quad80リンクはRFだけで100 MB/s使用、モデル実効容量合計103.7235 MB/s。以下の「RPC込み総量」はpaddingを含めた *平均転送量の和* であり、半二重・batch順序・burst間隔の証明には使わない。旧台帳はそれとは別にport単位の方向別負荷・APIを割り当て、S-2/3/4の複数のwire witnessを列挙した。

| 案 | S3での処理 | RPC往復 MB/s | RF+RPC単純和 MB/s | 旧port別帯域必要条件 | 決定的な残問題 |
|---|---|---:|---:|---|---|
| S-0 | なし（FPGAで全RS） | 0 | 100 | 一次条件は存在 | FPGA全体fit/clockとS3 RF/WCETが未確認 |
| S-1 | 全RS | 14.986 | 114.986 | 旧Octal+Quadでは不足 | 既存scalarはRSだけで784.054 Mcycles/s > S3全480 Mcycles/s |
| S-2 | BM/Chien/Forney | 1.427 | 101.427 | 通過する割当あり | 旧scalar Chien 6,528 cycles/CWは楽観RF控除前の残3,139 cycles/CWを超える |
| S-3 | BM/Omega | 2.141 | 102.141 | 通過する割当あり | 低RF+API模型で残1,288～1,317 cycles/CW。FPGA Forney付き旧mapped netlistは**9,426/8,640位置** |
| S-4 | BM/Omega/Forney | 2.855 | 102.855 | 通過する割当あり | 低RF+API模型で残1,216～1,293 cycles/CW。保持込み既存部分topは90 MHz未達 |

とくに S-3 は生I/Q転送100 MB/sに対するRPC**2.141 MB/s**であり、「帯域が極端に大きい」という説明は不正確。RPCは小さいとはいえ、低残帯域（旧S-3でport割当別 **1.338～1.583 MB/s**）やコア占有・credit・同一batch期限を無視できない。

BM/Omegaについてhost検査で観測された **421回GF乗算呼出し・16回除算/CW** は、Xtensa最悪CPUサイクルではない。1,288～1,317 cycles/CWを超えるかは実kernel/WCETの測定を要する。CPU high RF費用模型では他の計算に充てる残予算が負となる。S-3のForney面積不合格は当該netlistの反例であり、Forneyなどのあらゆる別実装の不可能性ではない。

## 結論の論理区分

- 「Sのシンドローム転送は帯域自体が常に不可能」＝ **否定**。選択portにS-2/S-3/S-4の必要条件を満たす例がある。
- 「現行S-2/S-3/S-4のRS部分移管が完成受信機として成立済み」＝ **否定**。CPU/core別deadline、同一batch RPC、credit/CW保持、FPGA全体P&RとSTAに合格したものは0件。
- 「逆方向を指令のみにする方針」＝ **設計方針として合理的**。逆向き情報・回路内状態保持・プロトコル・タイミング保証が不要になり、分析対象の範囲が明確になる。ただしこの制約が唯一の完成可能案を残すことや総ハードウェア性能最良は未証明。
- 「逆方向を許せば必ず9K受信機が成立」＝ **否定**。既存RS部分移管は他の必要条件で不合格又は未知。

## 次の検証条件と優先順位

指令のみのPR #8は維持する。逆方向データを許す別の比較として、まずS-3のBM/Omegaを**同じI10/Q10品質と既存のリンク資源を保ったまま**再評価する。最初のゲートは、BM/OmegaのS3用最適化実装を本当に1,288～1,317 cycles/CW内に収められるかの同時WCET、および旧Forney付きnetlistの786 logic位置超過を（精度悪化なしで）解消する実測。続いて方向別RPCの最悪batch遅延／RFバンク保持／DMA, IRQ, queue／9K物理P&R/STAを検証。これらを通過しなければ、S-4（4回RPC）を優先しない。

`experiments/s3_rs_reverse_policy_audit.py` はS-0～S-4のページ・平均・残CPU比較を出す。比較計算は確認済みの数値の再構成で、独立したCPU/RTL実装を生成するものではない。**receiver_adopted=falseに相当する状態は不変。**

### 静的完了条件

1. S-0～S-4の全ケースを省略せず、RF100 MB/sとRS35,541.871921 CW/sを共通の分母に用いる。
2. 往復の*有用payload*と*page padding込み*を区別し、RPCを含む合計100～115 MB/sを再計算する。方向別半二重・時刻保証は未達と明記。
3. S3低/高RF感度、API控除後cycle予算、既存S3 GF回数・FPGA下限を別扱いとし、合格を捏造しない。
4. 指令のみを外した経路はPR #8の正式候補として昇格しない。
5. 全体FEC/TMCC/TSと同時実装・PHY・実機WCET・合法配置STAが未達であると記録する。

再実行：`python experiments/s3_rs_reverse_policy_audit.py` と `python -m unittest discover -s tests -p 'test_s3_rs_reverse_policy_audit.py' -v`。

**品質境界：** 現時点で行ったのは既存一次資料の比較とモデル・試験コードの追加であり、CAD・実S3アセンブリのWCET・通信PHYを測定していない。計算の静的確認と受信機性能の合格は別。
