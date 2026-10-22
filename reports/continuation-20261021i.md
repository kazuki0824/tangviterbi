# ②：重いのはTS直列出力より前段。配置失敗の集計診断

②はこの用途に対して余裕が小さい構成だが、SoC/FPGA双方が原理的に非力で不可能という証明ではない。
現FPGA実装の統合配置・clockは未達。S3側は実連続取得・搬出・WCETが未確認で、高費用CPUモデルは超過している。
①は停止を維持し、②の正式採用は0。

## どこが重いのか

| 段階 | 今回の設計条件・役割 | 現状 |
|---|---|---|
| S3-TのI/Q取得・可逆搬送 |16 MSps×20 bit＝320 Mbit/s＝40 MB/s |RFからの無欠落連続取得、搬出、WCET未確認 |
| S3-SのI/Q取得・可逆搬送 |40 MSps×20 bit＝800 Mbit/s＝100 MB/s |通常経路の帯域余裕2.00818/3.7135 MB/s、高費用CPUモデル106.6197/106.8042% |
| FPGA復調 |FIR、同期、TのFFT/等化/demap、S復調 |全段接続・精度・全体資源未確認 |
| FPGA並べ替え・復号 |時間/周波数等DI、T最大3階層＋S共有K7、RS |大量の中間値保持とSDRAM往復。K7はstallなしでも152.626638 MHzが必要 |
| FPGAのTS出力 |既存見積りのT23.234700/S52.17 Mbit/s |計75.404700 Mbit/s＝9.4255875 MB/s。出力payloadだけの算術では27/81 MHz serial目標に入る。実IOと最終TS期限は未検証 |

I/Q合計140 MB/sは上記TS payloadの約14.85倍。これにFPGA内部の並べ替え・復号の往復アクセスが加わる。
K7は拘束長7なので64状態を扱い、単に入力bitを出力端子へ送る処理ではない。
映像・音声コーデックの復号はこの受信機のTS出力目標には含めていない。
従って「TSの出力が重い」というより、「RF/IQから誤り訂正済みTSを作る全受信処理が重い」が適切。
TSだけを入力として受け取り転送する回路と、今回のRF→TS受信機は処理量が異なる。
FPGA→SoCは指令のみなので、中間値をSoCへ戻して後段を分担する救済は今回の許可条件に含まれない。

数値根拠：[既存処理分担・帯域表](control-only-20k/README.md)、[S3再監査](s3-input-source-audit-20261020.json)、[前回実装比較](continuation-20261021h.md)。
サンプルレートとI/Q幅は設計前提であり、実S3がそのRF信号を連続取得できた測定値ではない。

## 配置失敗を制御信号の総数だけで説明できるか

固定nextpnr commit `e2fe86b3ce6feaa3f09d8db5c0971c1cda3fc641` の
`assign_cell_info`、`incompatible_ffs`、`slice_valid`、`constrain_lutffs` を取得して照合した。
LSRはJSONのLSRというportではなく、SET/RESET/PRESET/CLEARから選ぶ。
同期set/reset等、backendが隣接配置を許す型は同じ互換群として数えた。

| 必要条件の集計 |前回heldearly＋同probe|onehot＋同probe|比較対象 |
|---|---:|---:|---|
| FF数 |8662|8662|15552 FF位置 |
| CLK/CE/LSR/互換型の群数 |268|272|群数自体の一律上限は置かない |
| 制御群ごとの2枠切上げ＋RAM blocker |10452|10452|15552位置 |
| FF＋ALU−最大共有数＋RAM blocker |12858|12854|15552 FF/ALU用位置 |
| 通常配置で最後に失敗したFFと互換な群の大きさ |163|163|singletonではない |

制御群の2枠切上げでは、奇数群152個ぶんの空き位置を楽観的に数える。
別の式では、同一ALU SUMへ接続できるFFを最大366個として、
onehotの8662 FF＋2920 ALU−366共有＋273 RAM×6＝12854位置を必要下限とする。
2つの下限は**足し合わせない**。それぞれ異なる制約の緩和であり、共通の配置を構成した結果ではない。
LUT位置下限19404/20736も引き続き必要条件だけ。

この集計では総容量超過が出ない。従って「FF制御群の総数が原因」「FF総数が足りない」と断定する根拠は得られなかった。
逆に、各下限が容量内でも、carry chainの位置、隣接型、LUT/FF結合、配線等を同時に満たす配置は保証しない。
実配置の拒否理由別カウンタや失敗時配置dumpは前回ログにないので、局所制約と探索アルゴリズムのどちらが支配的かは未特定。
最後に失敗したFFが163個の互換群に属することも、実配置場所があった証明ではない。

[監査結果とhash](placement-control-audit/result.json)／[2 unittest](placement-control-audit/tests.log)
／[監査コード](../ci/gowin_control_capacity_audit.py)。
固定版backendの取得元：
[gowin.cc](https://github.com/YosysHQ/nextpnr/blob/e2fe86b3ce6feaa3f09d8db5c0971c1cda3fc641/himbaechel/uarch/gowin/gowin.cc)
／[pack_luts.cc](https://github.com/YosysHQ/nextpnr/blob/e2fe86b3ce6feaa3f09d8db5c0971c1cda3fc641/himbaechel/uarch/gowin/pack_luts.cc)。取得ソースも同梱。

## 現在のボトルネックと未完了

前回の[全一覧](continuation-20261021h.md#現在残るボトルネック未完了)を維持する。
統合合法配置・全体資源・clock、全受信stageの精度と接続、descriptor/cold-fill RTL、全条件の長期・動的期限、
S3無欠落取得/搬出/WCET、pin/PHY/独立clock同期、SDRAM IO STA、RF→TS実機検証が残る。
今回の集計通過を配置問題解消として扱わず、TS payload出力帯域を新しい未達原因として追加もしない。

## 今回の区切りAと次のB

Aは、処理量の内訳を説明し、固定backendと保存netlistに対してFF制御・ALU共存の集計診断を終え、PRへ保存した地点。
次のBは、固定版toolchainを復元し、配置器へ拒否理由別の診断を追加して同netlistを実行し、失敗箇所の局所制約を特定する地点。
作業領域の自動整理で旧toolchainは消えたが、公開成果物からの復元を不可能とは扱っていない。
Aで返すのは、保存netlistだけで確定できる必要条件の検算を完了し、次が計測機能を加えた配置器での動的診断へ移るため。
Bまで続ける選択は可能で、許可待ちではない。今回は原因を裏付けないRTL変更を追加せず、否定できた説明と未特定部分を確定する境界を選んだ。
この集計には独立した境界条件unittestを付けたが、合法配置や受信機全体の品質を確認したわけではない。全依頼は未完了。
