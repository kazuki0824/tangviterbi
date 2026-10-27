# ② Tang Nano20K＋N16R8×2：現在の統合見積もり

2026-10-27。①は変更しない。**S側6/16 packing＋16KiB転送＋8word fillを進める。fillは実装・SDK確認済みとなり、平均CPU見積もりは予算内へ改善した。一方、ownerの処理間隔とFPGAの速度・全段資源は未解決で、受信機の成立確認には至っていない。**

SoCはRF取得・可逆I10/Q10 packing・FPGAへの送信、FPGAは全復調とT/S独立TS出力を担当。N16R8×2限定で検討する。追加software間引き・有効bit削減は行わず、FPGA→SoCは選局・電源等の指令のみ。

## 1. SoC：実装した改善と最新の数値

[fill実装・実生成命令・SDK成果物](../s3-fill-unroll/README.md)。各volatile storeのbarrierと順序を残し、アドレス更新を8wordで共有した。折返し・端数・付帯費用まで含む命令数包絡は旧21574→**15362命令/bank**。削減率28.79%は命令数についての値で、実時間の測定結果ではない。

packingも最新SDKからCFGを再計数した。block45/run118/slow_pair173は維持、slice係数は213→223へ更新。実Cの11264/12288/12289/14288/14352 samples、開始位置0/16380、slice64/128/512/1024、各64bankの40条件×3構成で出力・経路保存則を確認。下表は512pair/slice、定常4長さの比較。初回短bankを定常rateへ流用しない。

条件：240MHz×2、命令cycle係数α=1.1、SPI CPU active20µs/転送、未分類U0/U1=20/10 Mcycles/s。Sには40→30µs scanの追加費用1500cycle/回という**未測定の感度点**を含む。

| 構成 | core0 | core1 |
|---|---:|---:|
| T raw・8/16・32KiB・8word fill | 41.96〜43.94% | 26.18〜28.05% |
| S raw・5/16・16KiB・8word fill | 83.22〜86.71% | 80.07〜87.86% |
| **S raw・6/16・16KiB・8word fill** | **90.17〜94.40%** | **73.27〜79.94%** |

S6/16の追加scan費用予算は3113.63cycle/回。追加3000cycleという感度点ではcore0上端99.61%。追加費用0・500・1500・3000と旧fill比較をestimate.jsonへ保存する。旧係数での直前値94.32%は最新SDKのslice増分を加えて94.40%へ訂正した。いずれも実値が入る信頼区間や成立確率ではない。

### 平均CPUとは別に残る、ownerの処理間隔

| Sの分担 | core1 packing-only平均service上端/bank | 公開320µsから30µs collect待ちを引いた残り |
|---|---:|---:|
| 5/16 | 300.30µs | −10.30µs |
| 6/16 | 271.73µs | 18.27µs |

これは平均serviceからの設計予算であり、IRQ・古いjob待ち等を含む最悪応答ではない。5/16を平均CPUだけで第一案にしない。

さらに現ownerは `poll_rf → s3_native_poll → fill(3072)＋fill(4096)` を同期実行する。同じ費用模型ではfillだけで約**70.41µs**を見込み、その間は同じownerのSPI reap/submit・collectへ戻らない。**平均CPUが100%未満でも、一定30µs scanを実現したことにはならない。** 次のSoC改善はfillの途中再開と1反復当たりの仕事量制限。その追加費用、全消去完了前のprepared禁止、reclaim順序、RF切替期限、非一様なSPI処理間隔を合わせて評価する必要がある。

### 同じS候補構成のSDKメモリ確認

[SDK run 40508948605](https://github.com/kazuki0824/tangviterbi/actions/runs/40508948605)、commit `ca8c06e`の共通・raw-only既定・S候補が成功。Sの実ELFが6/16・16384bytes・8wordであることを含む**57静的check**、fill命令列・literal・source identity等**9再確認**が成功。

同一commitのraw-only既定と比べ、pack構造体392→440bytes（+48）、DMA descriptorの2port合計432→240bytes（−192）。差引で既知driver控除後の内部空き**上限**は16444→**16588bytes**。IRAM末尾0x40388100、heap開始0x3fcacf90。未計上割当・断片化・実起動までの保証ではない。128KiBの物理payload arenaを維持する。

## 2. 通信と有限buffer

T raw40 MB/sはOctal、S raw100 MB/sはOctal＋Quad。T32KiB・S16KiBで、対応FPGA endpointのWRITE_BYTESを合わせる。通信内容は同精度の可逆I10/Q10 packing。

| 非直列化時間G=30µsという条件 | payload容量 | payloadとの差 |
|---|---:|---:|
| T・Octal | 74.519 MB/s | 34.519 MB/s |
| S・Octal＋Quad | 106.990 MB/s | 6.990 MB/s |

制御予約0.01 MB/sを使う場合は差から0.01を控除。G、CPU active、scan周期は別の量で、実測G=30µsを確認した値ではない。

[全scan位相検証](../s3-short-transfer-audit/README.md)では公開320µs・一定scan30µsの指定3列×全7200位相が128KiBに入り、最小残7872bytes。scan40µsでは交互列が9600位相中2772で超過、最大2040bytes。これらは指定列・一定間隔の模型であり、上の同期fillを含む現runtimeへそのまま適用できない。位相件数を失敗確率とは扱わない。

## 3. FPGA：全段予算と速度

旧全段配分から共有K7を置換した条件付き台帳。現在のtransportを含む全top合成・配置配線値ではなく、統合差分Δが残る。全8kernel×T FIR移管有無の16候補はestimate.json。

| 構成 | logic /20736 | FF /15552 | BSRAM /46 | DSP18 /48 | K7単体Fmax |
|---|---:|---:|---:|---:|---:|
| raw＋slotaddr | 20472 | 13189 | 46 | 34 | 156.764MHz |
| raw＋localshift | 21425 | 13364 | 46 | 34 | 224.266MHz |
| T FIR移管＋slotaddr | 19720 | 11653 | 44 | 26 | 156.764MHz |
| T FIR移管＋localshift | 20673 | 11828 | 44 | 26 | 224.266MHz |

raw＋高速localshiftはlogic689超過のため単純置換しない。slotaddrの台帳上の純増許容量はlogic264・BSRAM0。pairedはslotaddrよりlogic7多く、単体151.378MHzで劣る。他の保存trialも資源と速度の組合せで上回らない。未知の実装まで排除した結論ではない。

保存部分構成は152.091263MHz。最低152.626638MHzへ最長遅延0.023063ns、目標154.285714MHzへ0.093518nsの純短縮が必要。critical pathのRAM周辺routingは1.509ns＋1.344ns。この配線・近接配置を改善対象とする。単体Fmaxを全受信機へ流用しない。

[固定配置からの再配線2試行](../cursor-mask-fixed-router2/README.md)はcheckpoint復元のassertion／ALU位置制約エラーで配線前に終了し、新しいFmaxは得られなかった。速度改善を計上しない。元のcompatible-pair packerと計数instrumentationは保存source hashと一致する状態へ復元し、通常pack/placeからtiming weightを10→20へ変える試行を準備している。合法性検査は緩和しない。

T FIR移管は752logic・1536FF・2BSRAM・8DSP18を空ける代替。ただし保存QACC kernel＋準備書込みのみ＋旧非FIR/API予算で370.964〜403.472 Mcycles/s。準備書込み約2.081GB/s、gather読込み・展開・競合・core偏在・同品質係数契約が未確認。rawよりCPUを軽くする案として選ばず、FPGA容量を空ける代替として保持する。

## 4. 必須根拠の所在と採否

| 必須項目 | 所在・範囲 |
|---|---|
| 処理分担候補すべて | [全分担台帳](../partition-recheck-20261023/README.md)。宣言したT8段/S6段の16384組・320所有者、方向制約適合63組。未知の全アルゴリズムの網羅ではない |
| 資源占有率・期限 | 本文・estimate.json、[worker応答](../s3-worker-response/README.md)、[reclaim期限](../s3-reclaim-deadline/README.md)。平均占有率と最悪応答を区別 |
| 交換情報の種類 | 台帳の各境界に型・方向・速度。raw T40/S100 MB/s、T FIR代替はQ15複素32.507937 MB/s。FPGA→SoC payload禁止 |
| 全通信路候補と余裕 | 元台帳の18 profile・555有効集合と63分担の比較を維持。今回の転送長・費用を反映した経路は性能評価用の仮割当 |

性能・資源・期限の評価→合格分担への通信路割当→経路が非空のものを採用、という順序を維持する。正式な性能合格・通信路割当・受信機採用は0。

**現在の改善結果は「fillの実装・命令数削減・候補SDK配置を確認し、平均CPUを改善した」。未完了はownerの時間配分と有限bufferの整合、FPGA速度と全段統合、実メモリ/RF連続取得・品質、T/S同時TSの確認。** 未測定項目を理由に条件付き数値を出さないことも、仮定を達成済みとすることもしない。

再現：`python -m experiments.s3_integrated_estimate`。現SDK CFG、実C経路計数、fill包絡、FPGA16候補、保存STA、FIR算術を再計算し、根拠hashをestimate.jsonに保存。値の幅は入力ケース・感度仮定によるもので、統計的信頼区間ではない。
