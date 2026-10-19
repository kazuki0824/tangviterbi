# 2026-10-18 次の統合順の更新

追記：[統合SDRAM serviceの面積監査](sdf-sdram-service-budget.md)で本体3357 logic、残予約超過1126、更新全体予算21598/20736を確認。旧予約込み予算を現実装が収まる証拠には使わない。

[内部clock統一監査](common-clock-audit.md)を追加。59904 B buffer/CDCを先に追加せず、共通154.286 MHzとメモリPHY条件を先に検証する。135 MHz共通案は現K7能力不足。154.286 MHz候補は換算した時間設定でSDRAMのデジタル試験を通過したが、PHY・全client期限・全体P&Rは未達。buffer寿命はclock統一でも別途必要。

# ② 上流depunctureの接続と、保持場所の具体化

2026-10-18。`rtl/shared_k7_depuncture_stream.sv`に4個の既存depuncture回路を接続し、各系統の符号率・パンクチャ位相・途中のX soft値を独立に保持する。続く共有K7のFIFO・S:T=2:1仲裁・保守slot・grant registerは維持する。

**depuncture込みの部分回路は157.678970 MHz、154.285714 MHz目標を通過。** 実SDRAM/controller・CDC・PLL・受信frontend・全S変調/TMCC・共有RS・TSまでの統合ではない。完成受信機の性能合格・正式経路割当・採用は0。

## 接続契約

入力は、系統タグ付きの受信済み8-bit soft値をX→Yの順に渡す。`in_valid && in_ready`以外では消費しない。パンクチャされて送られなかった位置は回路でzero-weight erasureへ復元し、8-bit soft値は変更しない。3階層T＋Sの各レジスタを分離したため、ある系統のXを受けた直後に別系統へ切り替えても混ざらない。

`rates`は各context 3 bit、0=1/2、1=2/3、2=3/4、3=5/6、4=7/8。global reset解除後の最初の立上りで設定し、それ以降は内部に保持する。5〜7は当該contextのfaultとなり入力を受理しない。符号率変更・再選局は現在global resetを要し、context別の動作中epoch切替は未実装。

完成soft pairの仲裁には、後段FIFOごとの`context_ready`を用いる。満杯のcontextを飛ばし、受け入れ可能なcontextのpairを渡す。初版の単純RR選択では、満杯Tを選んだままSまで待たせ得たため修正した。このmaskは**FPGA内部の流量制御**であり、FPGA→SoCへの受信データ返送ではない。出力backpressureは従来どおり未対応で、次段は全out_validを受ける必要がある。

## 実測と予算

| 部分回路 | logic位置 | FF位置 | RAM16SDP4 / BSRAM | Fmax MHz |
|---|---:|---:|---:|---:|
| 前回FIFO・仲裁まで | 6128 | 2892 | 244 / 4 | 160.230728 |
| depuncture初版、満杯maskなし | 6496 | 3035 | 244 / 4 | 156.911972 |
| depuncture＋満杯mask | 6464 | 3035 | 244 / 4 | 157.678970 |

GW2A-18Cでの使用不能周辺位置も計上：logic=LUT4＋ALU＋4×RAM16SDP4、FF位置=DFF＋6×RAM16SDP4。最終版の実DFFは1571、DSPは0。seed 1、固定テスト端子。PLL、外部delay、実基板負荷は含まない。

前回から336 logic・143 FF位置増、裸coreから累計769 logic・354 FF位置増。既存統合予約から消費し、残りの未実装分予約は**2231 logic・1646 FF位置・13 BSRAM**。予約込み混合全体予算は20472/20736 logic・13189/15552 FF位置・46/46 BSRAM・34/48 DSPのまま。無料追加ではなく予約の減少であり、全体P&Rではない。上流保持/controller等が残予約を超えればその超過も加算する。

[全CAD証拠](shared-k7-depuncture-evidence/)には初版と最終版のRTL/制約/log/JSONを保存。ツール再取得直後のABC実行パス不一致は環境修正後に再実行し、回路の速度未達としては数えていない。

## 上流保持：18-bit pairへの展開をメモリの後に移せた

これは追加再量子化・間引きではない。通信路で送られなかった消失位置をメモリへ保存せず、必要なときに補うだけで、送られたsoft値は全bit保持する。

`experiments/k7_soft_retention.py`でMode 1/2/3、2/4/6 bits/carrier、全5符号率の45組を検算した。最大T symbolは受信soft値**29952 B**。7/8の26208 stepへ18-bit pairとして展開すると58968 Bなので、展開前に保持するほうが小さい。混在階層でも13セグメント合計の最大は全セグメント6-bit時を超えない。この容量計算は全到着位相の期限証明ではない。

具体的な次の接続候補は、SDRAMへ**2×29952＝59904 BのT soft出力buffer**を割り当て、古いsymbolの読み出し中に次symbolを書けるようにすること。まだ実アドレスへ割り当てていない。8-bitの全量spillを新設するなら追加read＋writeは最大**57.627706 MB/s**。既存time-deinterleave領域から直接読める場合も、読み終えるまで元ring位置が上書きされないことを示す必要がある。寿命を証明せず同じアドレスをaliasして追加費用0にはしない。

S QPSK側の最大受信soft値は57.72 MB/s、Tとの合計86.533853 MB/s。単一soft portの154.285714 MHzに対する平均入力量は収まるが、depunctureによるstep増加、T burst、各FIFO満杯、実memory grant遅延を含む期限保証は未完。前回の18-bit pair直入れ到着モデルの遅延値を、この新しい接続の保証値として流用しない。

[容量・byte/s検算](shared-k7-depuncture-evidence/retention.json)。59904 Bを確保するだけではSDRAM実装の完了にならない。全clientのアドレス所有権・ring寿命・refresh・競合・CDCを含むtraceへ接続し、T再利用期限とS入力非欠落を検証する作業が残る。

## 検証・再現

新規試験は5 epoch×4 context×512 step＝10240 step。全5符号率の独立符号化列をsoft単位でランダムに切り替え、全metric/枝選択を無限精度oracleと照合。初期状態不明の収束64 bits後は元bit列とも一致。FIFO満杯時の待機、無効符号率、部分X/Yとqueueを汚した後のresetを含む。さらに受入可能なcontextが満杯contextに妨げられないことをassertし、その状況への到達も検査する。

既存stream試験2件も回帰確認し、ローカル3 test methodsが成功。CI成功とは別。現在のRTLに合わせてstream単体CAD harnessは未使用のcontext_readyを内部接続として扱う。旧測定RTLは各旧証拠のsnapshotで保持しており、当時のsource hashを現在版へ書き換えていない。

```sh
python -m unittest discover -s tests -p 'test_shared_k7*stream.py' -v
python ci/shared_k7_depuncture_evidence.py --output build/k7-depuncture-ready
python experiments/k7_soft_retention.py
python experiments/nine_k_recovery_frontier.py
```

SoC/FPGAの処理境界・native I10/Q10転送・全経路台帳は変更なし。①については[9K専用の再設計方針](9k-recovery-plan.md)を追加。今回の20K部分測定を9Kの成立証拠には使わない。
