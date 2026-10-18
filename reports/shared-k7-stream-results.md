> 続行：[depuncture接続・満杯context回避・上流保持の検算](shared-k7-depuncture-results.md)。以下は前回の接続時点。

# ② 共有K7への入力FIFO・仲裁・保守スロットの接続

2026-10-18。前回の4 context K7を実際のFIFOとschedulerへ接続した。主実装は `rtl/shared_k7_stream.sv`、内側の復号回路は `rtl/shared_k7_context.sv`。T最大3階層＋S BPSK/QPSKの独立状態を保持する。S TC8PSKは従来どおり別回路。

**接続後の部分回路が154.285714 MHz目標を通過。完成受信機の正式採用は0のまま。** FIFOへ入る前の全信号処理・実SDRAM・depuncture・CDC・PLL・RS/TSはこのtopに含まない。①9Kへの収容・速度は測っておらず、①の未達は変わらない。

## 入出力とスケジューラ

- 内部入力は `in_valid/in_ready/in_context/soft0/soft1/erasure`。各contextに16語×18 bit、計1152 bitの分散RAM FIFO。8-bit soft値2個と2-bit erasureをそのまま保存し、量子化も間引きもしない。
- 同一clockの単一入力port。`valid && ready`のときだけ受理する。上流はreadyが0なら未受理語を保持する必要がある。満杯のFIFOから同時に取り出す場合もreadyの再提示は次clock。RF源自体を止められると仮定せず、上流保持を別途必要とする。
- `WEIGHTED=1`が選択版。通常はSに2 slot、T全体に1 slot。Tの3階層内はround-robin。空のclassの枠は他方へ渡す。`WEIGHTED=0`の4者round-robinも機能比較に残す。
- 128 slotに1回をデータなしの保守slotへ予約。保守対象は4 contextを巡回する。空きslotでも巡回を進め、入力が止まったcontextのtraceback/出力を進める。データ処理slot中も同じcontextのtracebackは進む。
- reset直後は4個の初期化slot。次grantを前slotの第2clockで用意し、context/word/validをregisterで保持する。FIFO→仲裁→ACSの長い組合せ経路を分割し、定常時は2 clocks/stepを維持した。
- 出力はcontextタグ付きbit列。出力backpressureはなく、後段は全out_validを受ける必要がある。global resetではFIFOも破棄し再初期化。context単独の再選局/epoch更新とdepuncture位相管理はまだ外部課題。

これらはFPGA内の接続で、FPGA→SoCへの復調データ返送を追加するものではない。

## 配置配線と資源予約の消費

同一20K device、seed 1、固定テスト端子、154.285714 MHz目標。PLL/外部I/O delay/実基板負荷は含まない。

| 構成 | logic位置 | FF位置 | 分散RAM macro / BSRAM | Fmax MHz | 判定 |
|---|---:|---:|---:|---:|---|
| 4者RR、直接接続 | 6144 | 2867 | 244 / 4 | 138.542526 | 速度未達 |
| S:T=2:1、直接接続 | 6134 | 2869 | 244 / 4 | 147.775970 | 速度未達 |
| S:T=2:1、grant登録 | 6128 | 2892 | 244 / 4 | 160.230728 | 部分通過 |

logicはLUT4＋ALU＋4×RAM16SDP4、FF位置は実DFF＋6×RAM16SDP4。選択版の実DFFは1428、DSPは0。使用不能になる周辺位置を引き続き計上する。宣言順を修正する前の登録試作も `registered-prototype` に保存した（6132 logic、156.006241 MHz）。最終版のRTL/測定は `weighted-registered`。

前回の裸core 5695 logic/2681 FF位置から、接続後は**433 logic/211 FF位置増、BSRAM増0**。

この追加分を既存の統合予約3000 logic/2000 FF位置から使い、残る未実装分の予約は**2567 logic/1789 FF位置/13 BSRAM**になる。したがって予約込みの混合予算は20472/20736 logic・13189/15552 FF位置・46/46 BSRAM・34/48 DSPのまま。**追加回路が無料という意味ではなく、予約を433/211消費した結果**。上流T保持・memory controller等が残りの予約を超えれば全体予算も増える。完成受信機の実測値ではない。[検算](shared-k7-stream-evidence/budget.json)。

## 時間予算と到着バースト

154.285714 MHzに対して、保守slot予約は0.78125%。残るデータ処理能力は76.540179 Mstep/s。従来のT＋S需要75.717121 Mstep/sとの差は0.823057 Mstep/s、全clock比では1.066926%。**これは平均量の必要条件であり、全modeの期限合格ではない。**

全FIFOが非空なら、T全体に最低25.513393 Mstep/s、Sに最低51.026786 Mstep/sを配る。局所的なhead待ちは保守slot込みで保守的に22 clocks以下、FIFO末尾は先行16語の処理を待ち得る。これはreadyで受理した後の保証で、上流待ちを含まない。各contextへのidle service間隔は最大1024 clocks。未完traceback/出力を進められるが、まだ受理していない将来のtrellis情報を生成するものではなく、有限入力の末尾を完全復号するflush符号も追加しない。

`experiments/shared_k7_stream_schedule.py`で、Tは1039.5 µsごとに26208 stepを一括提示、Sは50.505 Mstep/sで均等到着する仮説を8 symbol分再生した。T階層配分は13/0/0と1/5/7の2例。上流は無制限store、単一portへの供給は理想的なwork-conserving RR。実FFT/SDRAMの到着traceではない。

- 単純RRではS側上流の最大待ちが8365語／12480語となる。
- 重み付き配分ではS側上流の最大待ちは1語／9語、局所FIFOは2語／9語。Sの観測最大遅延は約0.0584／0.2009 µsまで減る。
- Tの最終ACS完了は到着から最大約1006.697 µs。次symbolまで約32.803 µsしか残らず、これはTS期限ではない。後段traceback/RS/TSやmemory待ちを含む保証は残る。
- どちらでもTのburst自体は残る。局所FIFO64語だけでは26208語の一括到着を保持できない。18 bit/stepなら1 symbolで58968 B（3 B配置なら78624 B）。既存memory内のデータをそのまま段階的に読む構成で重複copyを避けられるか、実アドレス/寿命/帯域で検証する必要がある。

18-bit展開済みpairを新しく全量spillしてから読むなら、Tだけで約113.454545 MB/sの追加read+write、3-byte配置なら約151.272727 MB/sになる。既存202.802 MB/s等へ無条件加算して合格にも、既存保持と同一とみなして0にもできない。depuncture前のsoft値を保持し読出し時にerasureを補う方法も含め、実SDRAM/cache統合で所有範囲を確定する。

[到着モデルの全数値](shared-k7-stream-evidence/schedule.json)。この2例を全Mode/GI・全階層配分・全位相の最悪到着証明と呼ばない。レビューの[平均帯域だけで合格しない条件](https://github.com/kazuki0824/tangviterbi/pull/9#discussion_r4303343179)と[共有K7の最悪同時schedule条件](https://github.com/kazuki0824/tangviterbi/pull/9#discussion_r4303343190)は未完として維持する。

## 検証と残る接続

最終RTLはRRと重み付き配分の2件を試験。各3 epoch×4 context×512 step、計12288 stepの全64 metric/枝選択を独立無限精度oracleと照合した。任意soft/erasure、全5符号率を含む独立符号化列、未知開始状態、連続バースト、FIFO満杯による待機、途中reset、データ/保守slotの飢餓検出、出力bit照合を含む。直接接続版も別ログを保存。いずれもローカル検証でありGitHub CI成功を意味しない。

再現:

```sh
python -m unittest discover -s tests -p test_shared_k7_stream.py -v
python ci/shared_k7_stream_evidence.py --output build/k7-stream-final
python experiments/shared_k7_stream_schedule.py
python experiments/shared_k7_stream_budget.py
```

失敗した直接接続版も生成RTL・制約・合成/P&Rログ・JSONを保存。最終版のsource hashと測定RTL一致を確認する。各旧構成のCAD再現には、そのフォルダのdut.sv.gzを展開しsynth.ys/command.jsonの作業パスを置換する。

次の対象は、上流の保持/depunctureと実SDRAM/cacheの結合で、この入力契約を実到着に対して満たすこと。その後も全clock/PLL・他receiver stage・S3 WCET・物理配線・RF品質・同時TSの既存ゲートは残る。境界の情報と全通信経路台帳は変更していない。T40 MB/s/S100 MB/sのnative I10/Q10、逆方向指令のみ、追加softwareデシメート/再量子化禁止を維持し、正式性能合格・通信割当・採用は0。
