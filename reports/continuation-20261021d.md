# ②：時間DIバッファ共有・整列回路の比較

①は停止維持。完成受信機・正式通信路の採用は0。以下は実装候補の比較であり、②全方式不可能の証明ではない。

## 比較の目的と保持契約

前回の部分回路21358 logic超過と、実DMAの15832 clocks超過を出発点とした。
全候補は48-bit/sample（6個の8-bit soft値）を保持する。追加間引き・再量子化はない。
外部SoC通信路、データ方向、分担は変更していない。

| 案 | 変更 | 追加の制約・時間 |
|---|---|---|
| shared | LOAD行とRING scatterの768-bit保持を共有 | 両phaseは排他。先読み用write_bufferとtile内wbuf/rbufは維持 |
| shared256 | shared＋背景仲裁の連続割当128→256 | FFT優先は維持。他clientの期限も同時検査。一般的なstarvation保証なし |
| halfword | shared＋位置合わせと組立てのshiftを16-bitへ統一 | 96-byte組立て16→48 cycles。SDRAM転送との重なりは実測 |
| direct＋grace | direct＋時間DI leaseのみ最大2 cyclesの空白を待つ | FFT優先維持、他clientの全宣言期限も検査 |
| direct | prefix除去後のread_buffer下位768-bitをtileへ直接渡す | scatter受理までread_buffer再利用禁止。bypass/LOADは共有input_bufferを使用 |

同一tileのLOAD完了後にRINGへ移るため、行入力と遅延結果の保持は排他的。
一方、現在の列をSDRAMへ書きながら次列を読み出すので、tile出力保持とwrite_bufferは
同時生存する。単に両者をaliasしてよいとは判断していない。
read_bufferは最大4 BL8＝128 bytesを保持し、2-byte単位のprefixを除く。
directではその結果が既に連続96 bytesであることを使い、再組立てを省く。
tile内部のwbufが受理時にコピーした後だけ、次のring読出しを許す。
BSRAM数は全案でtile用2個のまま。ポート数を増やした前提は置いていない。
ブロックpayloadレジスタは旧4864 bit、shared/halfword/directは4096 bit
（input 768＋write 768＋read 1024＋tile wbuf/rbuf各768）。制御・同期read q等は別。
同じ4096 bitでも書込み・shiftの選択回路が違い、logic数は同じにならない。

## 測定結果

| 案 | 単体合成logic | 単体配線後logic / FF | 単体MHz | FFT/K7接続pack logic |
|---|---:|---:|---:|---:|
| 前回固定case | 9496 | 10729 / 5213 | 175.438599 | 21358（103.00%） |
| shared | 9486 | 10539 / 4445 | 149.009094 | 21406（103.23%） |
| halfword | 8603 | 10320 / 4447 | 164.771805 | 20427（98.51%） |
| direct | 7726 | 8245 / 4442 | 178.986938 | 19597（94.51%） |

容量20736 logic。各単体BSRAM2/DSP0、接続pack BSRAM18/DSP6。
shared/halfword/direct接続pack FF位置は11234/11236/11231（RAM blocker込み）。
sharedの単体clockは未達、halfword/directは通過。接続packは配置配線完了の意味ではない。

| 案 | 完了clock | 期限に対する余裕clock | 他5clientの違反 |
|---|---:|---:|---:|
| 前回固定case | 2581912 | −15832 | 0 |
| shared | 2581912 | -15832 | 0 |
| shared256 | 2579708 | -13628 | 0 |
| halfword | 2594974 | -28894 | 0 |
| direct | 2577870 | -11790 | 0 |
| direct-grace | 2559092 | +6988 | 0 |

**direct＋graceは、この有限競合条件の全宣言期限を通過。** 時間DI余裕6988 clocks＝0.2723%。
最後のFFT proxy完了は2566013 clocksで期間端まで67 clocksしかなく、全条件の余裕保証ではない。
graceを含む接続packは19353 / 20736 logic（93.33%）、FF11233、BSRAM18、DSP6。
旧候補の622枠超過と今回条件の時間DI期限超過を、この候補の現障害として残さない。

仲裁の所有権、停止、全subset/cursor、quota、FFT優先、2-cycle上限、途中復帰の4 unittestも通過。
旧「次clientへ待ちなし」契約の試験は一度失敗。旧ログを保存し、所有権検査を維持したまま
仕様上の待ち時間を明記し、別途その上限を直接検査した。

### 同一構成の統合配置配線

直接版（graceなし）のheap配置は、有限期限を通過したgrace版を優先するためCtrl-Cで中止（130）。
その中止を配置不可能やhost容量不足とは扱わない。

期限通過したgrace版では、同じ合成netlistを再利用して次を試した。

| 配置方式 | 結果 | 読み取れること |
|---|---|---|
| SA、seed1 | −11、初期配置中に異常終了 | tool異常終了。原因未特定。速度不合格ではない |
| heap、seed1、cell-placement-timeout 10000 | 125、DFFREの合法配置を129593回試して失敗 | この探索条件で配置未完了。全方式の配置不可能証明ではない |
| heap、control-set処理無効、設定1000 | 130、意図的に中止 | 設定方向を取り違え試行上限が1295928へ増えたため、ログを確認して修正 |
| 同上、設定1000000（表示上限10000） | 125、DFFPの合法配置を10001回試して失敗 | 短い上限で同じ制御信号処理との関係を限定的に切り分ける |

heap失敗セルは`dut.memory.service.controller.initialized_DFFRE_Q`。
control-set無効では`dut.k7.s_tc8_mode_LUT3_I0_1_F_DFFCE_CE_Q_DFFP_Q`で停止した。
どちらも配線完了・統合Fmaxはなく、control-set処理だけが原因と特定したわけではない。
600秒のwall timeoutではなく、placerの探索上限到達。自動承認レビューの失敗ではない。
packの19353という集計だけを、合法配置・配線・clock成立の証拠として使わない。

## 検証範囲

全期間試験は312 tiles、119808出力word、29796 writeのaddress/payloadを独立oracleで照合。
実SDRAM controller、仲裁、pin-commandメモリモデルを通す。
各回路案にはI=1・全96遅延クラス・全偶数byte offset 0..30の短い試験も行う。
他5clientの宣言期限も確認する。unittest成功は値の一致であって期限合格とは限らない。

S/FFT競合負荷は要求proxy、全tile/config供給はtestbench。任意の過去メモリ値を用いるので、
cold-fill有効性、全mode・階層・実到着列の長期保証ではない。
FFT/K7接続の資源測定は別試験であり、受信経路全体の機能試験ではない。
単体配置配線には観測probeがあり、資源表はこれを分離する。
pack-only値を配線後値やFmaxに読み替えない。

## 現在のボトルネックと未確認事項

「実測で不合格」と「まだ保証できていない事項」を区別する。

| 対象 | 今なお残るもの |
|---|---|
| FPGA全体clock | direct＋graceの同一構成は統合配置配線をまだ通過していない。従来実FFT/K7統合の最良146.220200 MHzは、現K7の追加stallなし最低152.626638 MHz、設計154.285714 MHzへ未達。今回の単体clockを流用できない |
| 時間DI | direct＋graceの今回有限競合期限は通過。ただし全体descriptor生成・3buffer交代・cold-fillのRTL接続、全条件長期保証は未完了 |
| 全FPGA資源 | 部分回路の容量判定と全受信機収容は別。未実装stage・PHY・descriptor・接続費用を含む完成netlistがない |
| 復調・復号の完成度 | FIR/同期/TMCC/等化/demap/完全なT・S DI/RS/TSまでの一貫した実装・精度検証が未完了 |
| 長期・動的期限 | 全mode/I/rate/最大3階層/位相、実stageの到着包絡、RS burst、選局再同期、停止・reset契約、最終TS期限を未検証 |
| S3 CPUと取得 | 通常SのOctal＋Quad/Octal＋eMMC高費用モデル106.8042%/106.6197%で超過。専用GPIO含むcore別WCET、無欠落全量取得・可逆packing・DMA/IRQ競合は未実測 |
| 通信路の成立 | S通常経路の帯域余裕3.7135/2.00818 MB/sは算術値のみ。20Kピン割当、負荷、実PHY、独立clockの同期・lane整列・保持量が未確認 |
| SDRAM IO | pad/tri-state/PLL位相/min-max制約を含むsetup/hold検証なし。周期6.481481 ns−access5.4 ns＝1.081481 nsをsetup余裕とは扱わない |
| RF・実機品質 | 必要帯域/CN、外部変換/LNB、実S3連続取得、RF→TS誤り率・無欠落は未確認 |

**現在の障害から除外するもの:** service/reader/K7だけのclock未達、共有K7状態回路の不存在、
3bufferの容量・モデル所有権未検証、実tile転置回路の不存在、全データが要求モデルだけという説明。
これらは既に解消した範囲で、全受信機完成とは区別する。direct＋graceでは今回有限条件の時間DI期限超過と部分回路pack資源超過も解消した。

## 未完了・中断点

今回のAは、保持方式3案と仲裁2案を実データ・期限・資源で比較し、
有限期限と部分資源を通過するdirect＋graceを得た上で、統合配置の試行結果まで記録した地点。
全依頼の完了ではない。上表の全体RTL、全条件期限、S3/WCET、PHY/IO、RF実機確認は残る。

次の合理的なBは、DFFRE/DFFPの合法配置失敗をnetlist/制御信号/配置制約へ切り分け、
同一構成の配置配線とclockを確定し、global descriptor・3buffer交代・cold-fillを接続して
もう一度データと期限を検証する地点。

Aで返す判断は、値・有限期限・pack面積の比較から、合法配置を得るための原因調査へ
作業の性質が変わったため。この時点で測定済みと未確認を区別して記録・共有する選択をした。
Bへ取り掛かること自体が禁止されている、ユーザーの追加許可が必要、という理由ではない。
今回の改善と採用不可の範囲を判断する証拠は揃えたが、受信機完成や全ボトルネック解消という
品質には達していない。①停止、正式採用0、②全方式不可能は未証明のまま。

## 証拠へのリンク

- 全期間値・期限：[shared](t-time-tile-dma-shared-full.json)、[shared256](t-time-tile-dma-shared256-full.json)、[halfword](t-time-tile-dma-halfword-full.json)、[direct](t-time-tile-dma-direct-full.json)、[direct＋grace](t-time-tile-dma-direct-grace-full.json)。各`.log`も保存。
- 全offset：[shared](t-time-tile-dma-shared-offsets.json)、[halfword](t-time-tile-dma-halfword-offsets.json)、[direct](t-time-tile-dma-direct-offsets.json)。
- 単体配線：[shared](t-time-tile-dma-shared-route/summary.json)、[halfword](t-time-tile-dma-halfword-route/summary.json)、[direct](t-time-tile-dma-direct-route/summary.json)。
- 接続pack：[shared](shared-receiver-fft-tile-shared-pack/packed-budget.json)、[halfword](shared-receiver-fft-tile-halfword-pack/packed-budget.json)、[direct](shared-receiver-fft-tile-direct-pack/packed-budget.json)、[grace](shared-receiver-fft-tile-grace-pack/packed-budget.json)。
- 仲裁追加試験：[新契約](sdram-client-arbiter-grace.log)、[旧契約での失敗](sdram-client-arbiter-grace-old-contract.log)。
- 直接版配置中止：[理由とhash](shared-receiver-fft-tile-direct-route/placement-stop.json)。
- graceのSA異常終了：[summary](shared-receiver-fft-tile-grace-route/summary.json)。
- graceのheap再試行：[summary](shared-receiver-fft-tile-grace-heap/summary.json)。
- control-set無効試行：[設定誤りによる中止](shared-receiver-fft-tile-grace-noctrl/summary.json)、[修正後](shared-receiver-fft-tile-grace-noctrl-bounded/summary.json)。
- [機械集計・追加hash](continuation-20261021d.json)。

各結果はsource SHA256、コマンド、tool versionまたは固定された既存測定系への参照を持つ。
FPGA測定はOSS CAD Suite 2026-10-04、GW2AR-LV18QN88C8/I7、seed1。
