# ② Tang Nano20K＋N16R8×2：現在の統合見積もり

2026-10-27。①は変更しない。**S側6/16 packing＋16KiB転送＋8word fillを進める。8word fillの実装・SDK確認に加え、準備を1反復1024wordへ分割した。平均CPUは追加管理費用を含む感度模型で評価する。一方、ownerの処理間隔とFPGAの速度・全段資源は未解決で、受信機の成立確認には至っていない。**

SoCはRF取得・可逆I10/Q10 packing・FPGAへの送信、FPGAは全復調とT/S独立TS出力を担当。N16R8×2限定で検討する。追加software間引き・有効bit削減は行わず、FPGA→SoCは選局・電源等の指令のみ。

## 1. SoC：実装した改善と最新の数値

[fill実装・実生成命令・SDK成果物](../s3-fill-unroll/README.md)。各volatile storeのbarrierと順序を残し、アドレス更新を8wordで共有した。折返し・端数・付帯費用まで含む命令数包絡は旧21574→**15362命令/bank**。削減率28.79%は命令数についての値で、実時間の測定結果ではない。

packingも最新SDKからCFGを再計数した。block45/run118/slow_pair173は維持、slice係数は213→223へ更新。実Cの11264/12288/12289/14288/14352 samples、開始位置0/16380、slice64/128/512/1024、各64bankの40条件×3構成で出力・経路保存則を確認。下表は1024word/反復への分割後（追加準備管理ΔEは直下に別計上）。512pair/slice、定常4長さを用いる。初回短bankを定常rateへ流用しない。

条件：240MHz×2、命令cycle係数α=1.1、SPI CPU active20µs/転送、未分類U0/U1=20/10 Mcycles/s。Sには40→30µs scanの追加費用1500cycle/回という**未測定の感度点**を含む。

| 構成 | core0 | core1 |
|---|---:|---:|
| T raw・8/16・32KiB・分割fill | 42.08〜44.06% | 26.18〜28.05% |
| S raw・5/16・16KiB・分割fill | 83.52〜87.02% | 80.07〜87.86% |
| **S raw・6/16・16KiB・分割fill** | **90.48〜94.70%** | **73.27〜79.94%** |

分割前はS6上端94.40%だった。分割後・ΔE未計上での追加scan費用予算は3025.55cycle/回。追加3000cycleという感度点ではcore0上端99.91%。追加scan費用と準備管理ΔEは別費用であり、同じ残余予算を二重使用しない。追加scan費用0・500・1500・3000とΔE=0・100・200・300をestimate.jsonへ保存する。いずれも実値が入る信頼区間や成立確率ではない。

### 平均CPUとは別に残る、ownerの処理間隔

| Sの分担 | core1 packing-only平均service上端/bank | 公開320µsから30µs collect待ちを引いた残り |
|---|---:|---:|
| 5/16 | 300.30µs | −10.30µs |
| 6/16 | 271.73µs | 18.27µs |

これは平均serviceからの設計予算であり、IRQ・古いjob待ち等を含む最悪応答ではない。5/16を平均CPUだけで第一案にしない。

[予算付き準備の実装と検算](../s3-budgeted-fill/README.md)で、owner内の7回のRF pollに**1反復合計1024word**の予算を共有させた。reclaimは1回、全7168wordが完了するまでprepared禁止、予算0でもRF監視を継続する。実Cで全16384開始位置・途中状態・期限失敗を検証した。

| 分割の影響 | 同期8word | 1024word/反復 |
|---|---:|---:|
| 1bankのfill命令数包絡 | 15362 | 15567 |
| 1反復のfill命令数包絡 | 15362 | 2265 |
| α=1.1のfill単独時間模型 | 70.41µs | 10.38µs |

呼出し増分を含めるとS6のcore0上端は**94.70%**。追加準備管理をΔE cycle/owner反復、毎秒33333.33反復と仮定すると、ΔE=100/200/300で**96.09/97.48/98.87%**。追加管理の残予算は約381cycle/反復。これは未測定費用の感度で、ΔE=0を実際の無償性とはしない。core1上端79.94%は不変。

**分割で連続fill量は減ったが、一定30µs scanを達成したとは認定しない。** 7反復の準備完了とbank解放・RF切替期限、SPI API/packing等を含む非一様なowner反復と有限bufferの整合が残る。1反復のfill単独10.38µsはowner全体の実時間上限ではない。

### 同じS候補構成のSDKメモリ確認

[SDK run 40518679493](https://github.com/kazuki0824/tangviterbi/actions/runs/40518679493)、commit `1d954f4`の共通・raw-only既定・S候補が成功。Sの実ELFが6/16・16384bytes・8word・1024word準備予算であることと新入口のIRAM配置を含む**59静的check**、fill命令列・literal・8 source identity等**12再確認**が成功。3構成の静的check合計は172。

Sのpack構造体440bytes、captureは160→168bytes。分割前と比べIRAM末尾は0x40388100→0x40388200、heap開始は0x3fcacf90→0x3fcad098。既知driver控除後の内部空き**上限**は16588→**16324bytes**（264bytes減）。準備管理の追加はメモリ上も無償ではない。未計上割当・断片化・実起動までの保証ではなく、128KiBの物理payload arenaを維持したlink結果である。

## 2. 通信と有限buffer

T raw40 MB/sはOctal、S raw100 MB/sはOctal＋Quad。T32KiB・S16KiBで、対応FPGA endpointのWRITE_BYTESを合わせる。通信内容は同精度の可逆I10/Q10 packing。

| 非直列化時間G=30µsという条件 | payload容量 | payloadとの差 |
|---|---:|---:|
| T・Octal | 74.519 MB/s | 34.519 MB/s |
| S・Octal＋Quad | 106.990 MB/s | 6.990 MB/s |

制御予約0.01 MB/sを使う場合は差から0.01を控除。G、CPU active、scan周期は別の量で、実測G=30µsを確認した値ではない。

[全scan位相検証](../s3-short-transfer-audit/README.md)では公開320µs・一定scan30µsの指定3列×全7200位相が128KiBに入り、最小残7872bytes。scan40µsでは交互列が9600位相中2772で超過、最大2040bytes。これらは指定列・一定間隔の模型であり、分割fillと非一様な処理間隔を持つ現runtimeへそのまま適用できない。位相件数を失敗確率とは扱わない。

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

[固定配置からの再配線2試行](../cursor-mask-fixed-router2/README.md)はcheckpoint復元のassertion／ALU位置制約エラーで配線前に終了し、新しいFmaxは得られなかった。速度改善を計上しない。元のcompatible-pair packerと計数instrumentationは保存source hashと一致する状態へ復元し、通常pack/placeからtiming weightを10→20へ変える試行と、weight10・seed2の試行を実行中。合法性検査は緩和しない。

T FIR移管は752logic・1536FF・2BSRAM・8DSP18を空ける代替。ただし保存QACC kernel＋準備書込みのみ＋旧非FIR/API予算で370.964〜403.472 Mcycles/s。準備書込み約2.081GB/s、gather読込み・展開・競合・core偏在・同品質係数契約が未確認。rawよりCPUを軽くする案として選ばず、FPGA容量を空ける代替として保持する。

## 4. 必須根拠の所在と採否

| 必須項目 | 所在・範囲 |
|---|---|
| 処理分担候補すべて | [全分担台帳](../partition-recheck-20261023/README.md)。宣言したT8段/S6段の16384組・320所有者、方向制約適合63組。未知の全アルゴリズムの網羅ではない |
| 資源占有率・期限 | 本文・estimate.json、[worker応答](../s3-worker-response/README.md)、[reclaim期限](../s3-reclaim-deadline/README.md)。平均占有率と最悪応答を区別 |
| 交換情報の種類 | 台帳の各境界に型・方向・速度。raw T40/S100 MB/s、T FIR代替はQ15複素32.507937 MB/s。FPGA→SoC payload禁止 |
| 全通信路候補と余裕 | 元台帳の18 profile・555有効集合と63分担の比較を維持。今回の転送長・費用を反映した経路は性能評価用の仮割当 |

性能・資源・期限の評価→合格分担への通信路割当→経路が非空のものを採用、という順序を維持する。正式な性能合格・通信路割当・受信機採用は0。

**現在の改善結果は「fillの命令数削減と準備の分割を実装し、平均CPU・連続処理量を条件付きで見積もった」。未完了はownerの時間配分と有限bufferの整合、FPGA速度と全段統合、実メモリ/RF連続取得・品質、T/S同時TSの確認。** 未測定項目を理由に条件付き数値を出さないことも、仮定を達成済みとすることもしない。

再現：`python -m experiments.s3_integrated_estimate`。現SDK CFG、実C経路計数、fill包絡、FPGA16候補、保存STA、FIR算術を再計算し、根拠hashをestimate.jsonに保存。値の幅は入力ケース・感度仮定によるもので、統計的信頼区間ではない。
