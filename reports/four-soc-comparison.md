# 4 SoCの最良候補を検討するための比較台帳

2026-10-11。**仮説としての候補比較を開始できる。最良案の確定・採用は未達。**
比較検討そのものに、全受信機の完成を前提としない。検討中の費用モデル、実装した
回路の証拠、未確定事項を追跡し、部分共配置から成立済み第一案へ飛躍しない。

## 復元と対象

元HTML version 24とCP-SAT評価archiveを復元した。
HTML SHA256 `ce9a0b99692dfff79e5627b4337ebeab284b12d879a3eb5f00cbf38281fd4f67`、
archive SHA256 `ed61fba2b22af9bd1cb9c2eac9145542c69c27cf0a9c53d3f9fae3fa76a59d0d`。
固定入力に、元のownership ledgerとmode cost profilesの全行を保存する。
CPU stage費用を独立に加算し、S3の既計上RF費用を一度だけ加え、7040 profile全部の
保存値と一致することを確認した。ACS lane数をCPU cycle費用として足さない。

| 元の対象 | T所有者 | S所有者 | 費用profile数 | 型番・メモリの扱い |
|---|---:|---:|---:|---|
| C5-WROOM-1U | 256 | 64 | 1280 | PSRAM variant未指定。追加PSRAMを搭載済みとしない |
| S31-WROOM-3U-N16R16V | 256 | 64 | 1280 | 元資料の16 MiB PSRAM／CPU費用前提を保存。現行SDK実装未検証 |
| S3-WROOM-1U-N8R8 | 256 | 64 | 2560 | 本来の対象。PRのN16R8 link profileは容量別の参照証拠 |
| C61-WROOM-1U-N8R2 | 256 | 64 | 1920 | 元資料の2 MiB PSRAM／CPU費用前提を保存。現行SDK実装未検証 |

4 SoCの各T256×S64、計**65536所有者pair**を、low/high費用×100/125 MHzの
4 scenarioで再計算した。計**262144 pair record**。RF表現の代替は7040 profileに
全て残す。所有者分担は有限集合であり、全microarchitectureの集合ではない。

S3 N8R8とN16R8は公式datasheet v1.8のTable 1-2で、それぞれ8/16 MB Quad flash、
ともに8 MB Octal PSRAM。Section 3.2により双方ともIO35/36/37はPSRAMに使用される。
内部SRAMは512 KBで共通。ただしflash容量とpartitionのSDK検証を省略しない。
N16R8のELFがリンクしただけでN8R8受信機の完成としない。
[Espressif公式datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)。

## 現在の条件への変更

旧資料はT/Sを一つの共有bitstreamに収める条件だった。現在の許可条件はT/S排他的に
別imageを外付けNORからreloadする。新台帳では各modeのselected-stage資源を集計し、
pairの必要な容量を資源ごとに`max(T, S)`とする。各stageのmaxを足した共有netlistや、
TとSの同時占有を使用しない。旧資料のS31最良案・条件付き49案などは転記しない。
固定基板配線のunion、両modeのPHY、停止/drain/resetと復旧、NOR image容量、常駐
softwareと同時live memoryは別の未確定項目であり、max計算だけで閉じたとしない。

FIR/sync/FFT/復調/interleaverの旧FPGA費用は設計scenarioで、測定上限・必要下限ではない。
FECも旧anchorであり、現在修正したRSやTC実装の全topとは対応しない。
旧3502 clocks/CWのRS仮定を、現在測定済みの限定RS実装と混ぜない。
CPUはscalar analogue、理想的なcore分割、driver追加前の費用を含む。
low/highは厳密な楽観下限・保証上限ではない。

## 比較軸と判定

全7040 profileでCPU平均、selected FPGA資源とstage clock仮定を表示し、同じscenario内で
logic/FF/BSRAM/DSP/CPU利用率のPareto frontierを求める。通信路未割当の**モデル上の
比較対象**であり、実現可能性による候補削除や採用順位ではない。RF表現を安いCPU値だけに
固定せず全代替を保持する。frameとburstを含む通信費用のない順位を最良順位にしない。
scenarioごとの件数と全frontier witnessは[summary](four-soc-comparison/summary.json)に保存。
screenを通るpairも通らないpairも全台帳に残る。high scenarioでC61が0でも、C61全体の
実現不能と判定しない。

全profileの`whole_resources`、`per_core_WCET`、`communication_assignment`は`null`。
未計上の回路・memory・IRQを0にしない。performance確認前の通信仮説は採用根拠にしない。
現在のS3部分RTL、scalar不合格、SDK map、bounded workerの証拠は
[完了条件](pr4-estimate-completion.md)と対応付け、当該実装のみに限定して使用する。

| 条件 | 現在 | 次に満たす内容 |
|---|---|---|
| 仮説比較を始める | 満たす | 対象、全所有者、全費用profile、別image条件、比較軸、未知と証拠の範囲を固定済み |
| 最良を確定する | 未達 | 比較を変える未知の資源・各core期限・memoryを閉じ、性能通過案の通信路を1経路以上確認 |
| 実受信機を採用する | 未達 | 独立RF→連続TS、WCET、PSRAM PHY、固定配線、NOR切替の検証 |

これによりPR5の「部分回路を成立済み第一案へ昇格」の判断を繰り返さず、PR4で
最良候補の検討を進められる。見積もり完了・最良確定を宣言するには残りの条件が必要。

## 再現

```sh
python -m unittest discover -s tests -p test_four_soc_comparison.py -v
python experiments/four_soc_comparison.py
```

1280分担の欠落・重複、CPU費用の欠落・二重加算を拒否する。
別imageではstageごとのunionでなくmode全体のmaxを用いる反例も検査。
全台帳を再生成して固定reportと比較し、未知が性能合格や通信採用へ昇格しないことを確認する。
入力・出力hashと元資料hashを保存し、同じ入口をCIへ追加。
2.3 MBの全pair出力は上記コマンドで再生成する。固定入力とsummaryをPRに保持し、
再生成した全出力のhashが記録値と一致することも検査する。

`hypothesis_comparison_ready=true` / `best_candidate_certifiable=false` /
`complete_estimate=false` / `performance_stage_completed=false` / `receiver_adopted=false`。
