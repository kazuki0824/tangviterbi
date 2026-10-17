# 続行結果：共有FFTの実装・部分配置配線とGPIO保持上限

**FFTを仮の予算から実回路へ進めた。①②の受信機全体の採用は引き続き0件。**
`shared_sdf_fft.sv` は全13段で4個の実数乗算器を共有する。Mode 1/2/3は同じ回路のmode入力で選択し、mode変更時に状態をresetする。①のT/S切替を別の方法へ変更したものではない。②でもT/S同時という条件を維持する。

## 1. 何を実装し、何を検証したか

- 13 slotの巡回schedule、6 clockの演算pipeline、段ごとのdelayと保持、共有Q1.16係数ROM、固定小数点の丸め・飽和、bin番号・frame末尾を実装。
- 最大delayだけ外部へ出すhybridと、全delayをBSRAMに置くresidentを同じRTLのparameterで比較。外部delayは**予約付き理想同期RAMポート**であり、SDRAM/PSRAM PHY・burst cache・仲裁は未実装。
- FFT入力は通常復調のcomplex Q15。全sample・全binを保持し、旧独立DIF整数oracleとbit exact一致。通信都合の追加間引き・再量子化はない。NumPyのDFTとも誤差を照合。
- 4枚の連続した非ゼロframeを入力し、先頭3枚の全出力を比較。4枚目も実データで、frameごとのzero tailやresetを挿入しない。最後の未完pipelineをそのまま終了する試験であり、4枚目の全出力を検証したとはしない。
- Mode 1/2/3、resident/hybrid、backpressure、full-scale飽和、tone、RAM内容を残したMode 1↔3 resetを含む11 unittest合格。待ちなしでは入力・出力の間隔が常に13 clocks。

## 2. FPGA資源と期限

OSS CAD Suite 2026-10-04、Yosys `0.69+190/0e8336b4e`、nextpnrは各JSONに実versionを記録。すべてseed 1。topは入力刺激と出力signatureを持つ**FFT単体の測定用回路**。logic位置は配置後のLUT4＋ALUであり、合成LUTだけではない。係数ROMのDPX9BもBSRAMへ含める。

| FPGA / FFT | logic位置 | FF | BSRAM | DSP18 | 目標MHz | 配置配線後MHz | 判定 |
|---|---:|---:|---:|---:|---:|---:|---|
| 9K hybrid | 2,747 /8,640（31.79%） | 1,502 | 10/26 | 4/20 | 108 | 109.493 | 部分回路の目標通過 |
| 9K hybrid・110 MHz試行 | 2,747 | 1,502 | 10 | 4 | 110 | 109.493 | 目標不合格を保存 |
| 9K resident | 2,703 | 1,471 | 18/26 | 4/20 | 110 | 91.158 | 目標・必要持続率とも不合格 |
| 20K hybrid | 2,729 /20,736（13.16%） | 1,502 | 10/46 | 4/48 | 162 | 222.568 | 部分回路の目標通過 |
| 20K resident | 2,717 | 1,471 | 18/46 | 4/48 | 162 | 197.200 | 部分回路の目標通過 |

[全5条件の生ログ・数値](shared-sdf-evidence/)を保存した。配置前の楽観Fmaxを最終値として使わない。全条件に端子位置は付けたが、測定用の26端子割付であり受信機の配線図ではない。外部I/O delay、基板PLL生成、実メモリ、全受信機のSTAを通過したという意味ではない。P&R終了codeが0でもErrorや完了記録を確認する。

| T Mode | GI1/32周期 µs | 持続完了間隔 clocks | 108 MHz時 µs /余裕 | 162 MHz時 µs /余裕 |
|---|---:|---:|---:|---:|
| 1・2048 | 259.875 | 26,624 | 246.519 /13.356 | 164.346 /95.529 |
| 2・4096 | 519.750 | 53,248 | 493.037 /26.713 | 328.691 /191.059 |
| 3・8192 | 1039.500 | 106,496 | 986.074 /53.426 | 657.383 /382.117 |

上表は**持続処理間隔**。初回frameの全出力までのレイテンシではない。Mode 3の連続飽和入力試験では最初のframe完了が213,057 clocks、以降106,496 clocksごと。OFDMの実到着形状・後段保持・TSまでの遅延契約は別途必要。

有効区間8.126984 Msamples/sを停止なく受ける条件は105.650794 MHz以上。108 MHzでは演算占有97.825%、余裕2.175%、GI込み平均では94.860%。162 MHzでは65.217%、GI込み63.240%。特に①は理想RAMでの通過にすぎず、メモリ待ちを少し追加するだけで不足し得る。試験のbackpressure条件では値と順序を検証したが、任意のstallでも期限を満たすとはしない。

hybridの外部delay需要はMode 3平均63.045695 MB/s、有効区間65.015873 MB/s。選択時のreadyは、次clockのread要求への同期応答と選択から6 clocks後のwriteを予約する契約。実外部RAMへ直結してこの契約を満たすと仮定しない。prefetch/writeback cacheと他clientを含む待ち時間評価が必要。

## 3. 全分担への反映と採用判定

旧320所有者をすべて残し、FFTをFPGAへ置くTの128行にhybrid/residentの2実装を与え、**448実装付き候補**を作った。逆方向制約を満たすものはT12＋S7＝19境界、T/S **84組**。SoC側の費用・やり取りする情報・転送速度は変えず、各行から既存の帯域カタログを参照する。

| 更新台帳 | 読める全境界表 | 全所有者付き実装 | 全許可組合せ |
|---|---|---|---|
| ① | [19境界](shared-sdf-evidence/updated-9k/boundaries.md) | [448行](shared-sdf-evidence/updated-9k/ownership-variants.json.gz) | [84組](shared-sdf-evidence/updated-9k/allowed-pairs.json.gz) |
| ② | [19境界](shared-sdf-evidence/updated-20k/boundaries.md) | [448行](shared-sdf-evidence/updated-20k/ownership-variants.json.gz) | [84組](shared-sdf-evidence/updated-20k/allowed-pairs.json.gz) |

これはFFT測定値と旧stage見積もりを混ぜた**置換予算**。結合回路の合成結果でも、任意の実装に対する面積下限でもない。測定用回路の費用も含む保守的な比較であり、それを黙って引いて余裕を作らない。

| 置換対象 | logic | FF | BSRAM | DSP18 | 今回の判断 |
|---|---:|---:|---:|---:|---|
| ① T・RFだけSoC、hybrid | 9,496（109.91%） | 6,332 | 16 | 18 | 旧stageのFFT 656 logicを実測2,747へ置換すると予算超過。未計上回路も残る |
| ① T・通常FIRをSoC、hybrid | 8,744（101.20%） | 4,796 | 14 | 10 | 置換予算超過、さらにSoC高費用模型123.435% |
| ② 旧共有RS B・hybrid | 20,681（99.73%） | 13,512 | 46/46 | 34 | 空き55 logic・0 BSRAM。未実装cache/CDC等を加えた余裕は未成立 |
| ② 旧共有RS B・resident | 20,669（99.68%） | 13,481 | 54/46 | 34 | BSRAM超過 |

①のT/Sはmax、②は同時加算という規則を全84組で再検査した。②の共有RS Bは共有を含む別予算なので、単純stage加算とは別欄で置換する。Sの全変調、Tの階層context、FIR/同期/等化/TMCC、全メモリ・入力・TSの結合は未完。S部分回路のRS速度不足もこのFFT変更では解消していない。

したがって、指定手順の性能→通信→採用では引き続き性能未通過、正式通信割当0、採用0。FFT単体を改善できたことを全体採用へ昇格しない。

## 4. GPIO二laneの保持量を分解

前回の40,760 Bは「後続unitを丸ごと保存する方式」の費用。必ずその全量が順序逆転する、という下限ではない。今回、固定eSpDR sourceの全length 15,360～16,288・全alignment 0～15、計14,864ケースを使って、**順序逆転分だけ**を計算した。

S40で、framing・capture管理・fragment gap合計が3,000 CPU cycles/unit以内という未測定条件を置く。最大serviceは95,729 cycles＝398.870833 µs、隣接unitの最小到着間隔384 µs、同一coreは768 µs。従って追い越せるのは次の1 unitだけで、最大重なり14.870833 µs。後続laneを実際より早い「開始時に40 B、以後91 cyclesごと40 B」で包絡すると、**packed 1,600 B、32-bit IQへ展開後2,560 B**までとなる。

| S40への追加条件 | 順序逆転packed上限 | IQ32上限 | 注意 |
|---|---:|---:|---|
| 上記3,000 cycles以外の遅延なし | 1,600 B | 2,560 B | 2 KiB/blockなら1/2 blockの算術最小値 |
| さらに10 µsの開始遅延、または10 µs後段停止 | 2,640 B | 4,224 B | 元の3,000 cyclesとは別に加算 |
| 追加開始遅延・後段停止が各10 µs | 3,680 B | 5,888 B | mapped RAM数ではない |
| 遅延上限なし | 未確定 | 未確定 | 小FIFOへの置換を認めない |

[機械可読の全条件](shared-sdf-evidence/gpio-reorder-bound.json)。S80では上記最大serviceが同一coreの最小到着間隔を超えるため、この単純な包絡証明を流用できない。S80の不可能性の証明でもない。

この上限は入力の平滑化、CDC FIFO、checksum検証完了まで全unitを保留する方式、FPGA front-end処理能力を含まない。元の可逆データを保ったまま保持量を減らせる設計条件を示しただけで、S3 WCETやTang上のGPIO受信回路を実測したわけではない。**全raw spill200 MB/sが不可避とはしないが、0 MB/s追加で受信機が成立するとも扱わない。**

## 5. 検証結果と次の境界

FFT 11件、GPIO包絡5件、候補更新・入力hash・資源集計6件、旧見積もり回帰10件、**合計32 unittest成功**。fail-fastなし。全448行・全84組を走査し、CPU/境界情報を変えていないこと、採用へ誤昇格しないことを確認した。5条件のP&Rには不合格2条件も残す。ログ・入力hashは[証拠一式](shared-sdf-evidence/)に置く。

前回の「FFT本体の資源・連続演算が未実装」は、今回「共有FFT単体の実装・部分P&R通過」へ進んだ。残りは次のとおり。

1. hybrid outer delayの実burst cache・メモリcontrollerとの接続、T時間deinterleave/S frame/入力保持と同時の期限。
2. 全復調・全変調/階層FEC/TMCC/TS・I/Oの実回路を結合した資源削減とSTA。①は上記T予算超過、②はほぼ無余裕を先に解消する。
3. S3の管理時間・最大skewを実firmwareへ落とし、内部RAM/Flash起動・RF連続取得との共存を検査。今回の3,000 cyclesはWCET認定していない。
4. Tang完成基板のGPIO/clock/電気条件、①の外付NOR複数image・strap・再構成動作、実RF帯域/CN/BER。

今回の区切りは、実装済みブロックを機能・資源・部分タイミングまで検証し、その結果を**全候補の見積もりへ戻した**点。未実装のPHYや受信機全体まで成立済みとして進める品質には達していない。上記1～3の設計・実装作業を「実機がないための保留」に置き換えてはいない。

## 再現

リポジトリrootで、OSS CAD Suite 2026-10-04をPATHへ設定する。

```sh
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s tests -p test_shared_sdf_fft.py -v
python -m unittest discover -s tests -p test_gpio_reorder_bound.py -v
python -m unittest discover -s tests -p test_shared_sdf_update.py -v
python -m unittest discover -s tests -p test_control_only_estimate.py -v
python ci/shared_sdf_evidence.py --board 9k --pnr --frequency 108 --output build/shared-9k
python ci/shared_sdf_evidence.py --board 20k --pnr --frequency 162 --output build/shared-20k
# residentは --resident を追加。9K 110MHz試行も不合格のまま保存。
python experiments/gpio_reorder_bound.py --output build/gpio-reorder-bound.json
python experiments/shared_sdf_update.py --board 9k --output build/updated-9k
python experiments/shared_sdf_update.py --board 20k --output build/updated-20k
```

置換台帳は保存済みCAD証拠を入力にする。新しい測定値へ切り替えるときは、元のsource hash・scope・生ログを伴って証拠を更新する。CIの大量起動を避け、今回のCADと32件の検査はローカル実行。GitHub Actionsが緑になったという報告ではない。
