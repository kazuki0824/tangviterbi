# ② Tang Nano20K＋N16R8×2：現在の統合見積もり

2026-10-28 JST。①は変更しない。**S側6/16 packing＋16KiB転送＋8word fillを進める。8word fillの実装・SDK確認に加え、準備を1反復1024wordへ分割した。平均CPUは追加管理費用を含む感度模型で評価する。一方、ownerの処理間隔とFPGAの全段統合は未解決（保存部分構成の速度は目標達成）で、受信機の成立確認には至っていない。**

SoCはRF取得・可逆I10/Q10 packing・FPGAへの送信、FPGAは全復調とT/S独立TS出力を担当。N16R8×2限定で検討する。追加software間引き・有効bit削減は行わず、FPGA→SoCは選局・電源等の指令のみ。

## 見積もり結果の要約

現在の推進案はT raw 8/16・32KiBとS raw 6/16・16KiB、N16R8を各1枚。下表のSoCは管理200cycle/反復も含めた同一感度条件で示す。実測値や成立確率ではない。

| 項目 | T側 | S側 | 判定・条件 |
|---|---:|---:|---|
| SoC core0占有率 | 44.86〜46.84% | 93.25〜97.48% | 管理200cycle・30µs反復の感度値 |
| SoC core1占有率 | 26.18〜28.05% | 73.27〜79.94% | packing命令模型＋未分類費用 |
| 必要payload帯域 | 40 MB/s | 100 MB/s | 同精度I10/Q10 |
| 仮割当通信路の容量 | 74.519 MB/s | 106.990 MB/s | G=30µsを仮定 |
| payloadとの差 | 34.519 MB/s | 6.990 MB/s | 制御予約0.01 MB/sは別控除 |

共有FPGAのraw＋slotaddrは**20472/20736 logic（98.73%）、46/46 BSRAM（100%）**という旧全段台帳からの条件付き値。部分回路の配置配線は**166.22MHz**で目標154.29MHzを達成したが、全段統合の速度・資源とは別である。

**見積もり上は平均CPUと仮割当帯域に入る条件がある。ただし処理間隔・buffer期限・全段FPGAを同時に満たす確認が未完了で、正式採用0。** S側core0の余裕は上端で2.52ポイントと小さい。判断を変える未確定費用は後段に明記する。

数値の全桁・根拠hashは [estimate.json](estimate.json)。実装改善の履歴より先に結果を確認したい場合はこの節を参照する。

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

[packing細分化の比較](../s3-owner-slice-tradeoff/README.md)では、256pairへ減らすと非空slice平均のケース上端は28.10→17.29µsになる一方、追加管理200cycle/反復込みのcore0上端は97.48→102.41%。64/128もCPU超過、1024は連続packingが長くなる。細分化だけで解決せず、512を維持して処理本体・SPI費用・スケジュールを改善する。平均slice時間を最悪時間とは扱わない。256pair案を管理200cycleの感度条件で平均CPU100%以内へ戻すには、他条件固定ならSPI CPU使用時間20→16.05µs/転送以下が必要。達成値ではなく改善目標の逆算である。

[SPI空振り確認の改善](../s3-spi-running-guard/README.md)：raw-onlyの転送中はSDK結果キュー確認を省くguardを実装。idleだけでは完了認定せず、従来のSDK完了結果でleaseを解放する。関連host試験と変更後SDKのT/S各59静的check・各12ソース/生成命令照合が成功。実ELFでも動作中のSDK呼出し省略とidle時のSDK回収経路を確認。削減時間は未測定で、上記CPU感度値を減額していない。 実命令比較ではwrapper込みで動作中49＋SDKキュー内部命令→38/40命令。idle未公開では逆に9/11命令増えるため、全経路の改善とはしない。256pair案は転送API20µs・管理200cycleを固定すると、追加scan費用805.544cycle/回以下が平均CPU100%境界。scan全体の達成値ではなく、残る改善目標である。

[通常RF監視の費用内訳](../s3-owner-quiet-path/README.md)：準備済み・非settlingの指定経路はRF監視1回189命令。7回＋2本の転送中SPI確認で1401命令、α=1.1なら1541.1cycle相当。collect・feed・owner制御等は別なので、追加scan1500cycleを保証上限とは扱えない。これは特定反復の部分費用であり、平均費用への置換には状態頻度と既存Uの重複整理が必要。CPU数値は今回据え置く。

[通常owner反復の追加集計](../s3-owner-iteration-path/README.md)：collect・feed・時計・制御を加え、inline化した2pollのwrapper重複28命令を除くと、指定2経路はpacking本体を除いて1572/1607命令。α=1.1では1729.2/1767.7cycle相当。この値を平均追加scan費用と**仮定**した感度計算ではS512 core0上端は**98.28/98.41%**、S256は**103.21/103.34%**。実平均の確認ではなく、上表の1500cycle条件を置換した成立認定もしない。その他経路・待ちと状態頻度の確認が残る。

### 同じS候補構成のSDKメモリ確認

[SDK run 40535137322](https://github.com/kazuki0824/tangviterbi/actions/runs/40535137322)、commit `9da570f`の共通・raw-only既定・S候補が成功。Sの実ELFが6/16・16384bytes・8word・1024word準備予算であることと新入口のIRAM配置を含む**59静的check**、fill命令列・literal・8 source identity等**12再確認**が成功。3構成の静的check合計は172。SPI guard追加後もS/Tのpacking係数45/118/173/223は変わらず、各4項目のCFG照合が成功。

SPI guard追加前後で下記メモリ値は不変。Sのpack構造体440bytes、captureは準備分割により160→168bytes。分割前と比べIRAM末尾は0x40388100→0x40388200、heap開始は0x3fcacf90→0x3fcad098。既知driver控除後の内部空き**上限**は16588→**16324bytes**（264bytes減）。準備管理の追加はメモリ上も無償ではない。未計上割当・断片化・実起動までの保証ではなく、128KiBの物理payload arenaを維持したlink結果である。

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

[配置配線の完了結果と検算](../cursor-mask-route-comparison/README.md)：保存部分構成は**166.2234MHz**へ改善し、最低152.6266MHz・目標154.2857MHzの両方を達成した。目標に対する周波数余裕は7.737%。logic site計数19658（基準比+31）、FF8673、BSRAM29。もう一方のweight20試行は152.9520MHzで、最低を超えたが目標には未達。入力netlist・backend source・chipdb一致と出力再計数等18checkが成功した。

この部分構成の速度不足は解消した。ただしRF endpoint・equalizer・interleaver・RS/TS・PHY等の全接続構成ではなく、scan/観測fixtureを含む。**166.22MHzを全受信機のFmaxとは扱わない。** 旧全段台帳の資源数・未接続段・現在のtransportとの差分を統合して再合成/配置配線する課題は残る。詳細成果物は [Actions run 40524351929](https://github.com/kazuki0824/tangviterbi/actions/runs/40524351929)。

[固定配置からの再配線2試行](../cursor-mask-fixed-router2/README.md)はcheckpoint復元エラーで終了。続くローカル通常配置配線も完了結果を取得できなくなり、停止原因は不明。その途中ログを成果とせず、Actionsへ移した完了結果を今回採用した。合法性検査は緩和していない。

T FIR移管は752logic・1536FF・2BSRAM・8DSP18を空ける代替。ただし保存QACC kernel＋準備書込みのみ＋旧非FIR/API予算で370.964〜403.472 Mcycles/s。準備書込み約2.081GB/s、gather読込み・展開・競合・core偏在・同品質係数契約が未確認。rawよりCPUを軽くする案として選ばず、FPGA容量を空ける代替として保持する。

## 4. 必須根拠の所在と採否

| 必須項目 | 所在・範囲 |
|---|---|
| 処理分担候補すべて | [全分担台帳](../partition-recheck-20261023/README.md)。宣言したT8段/S6段の16384組・320所有者、方向制約適合63組。未知の全アルゴリズムの網羅ではない |
| 資源占有率・期限 | 本文・estimate.json、[worker応答](../s3-worker-response/README.md)、[reclaim期限](../s3-reclaim-deadline/README.md)。平均占有率と最悪応答を区別 |
| 交換情報の種類 | 台帳の各境界に型・方向・速度。raw T40/S100 MB/s、T FIR代替はQ15複素32.507937 MB/s。FPGA→SoC payload禁止 |
| 全通信路候補と余裕 | 元台帳の18 profile・555有効集合と63分担の比較を維持。今回の転送長・費用を反映した経路は性能評価用の仮割当 |

性能・資源・期限の評価→合格分担への通信路割当→経路が非空のものを採用、という順序を維持する。正式な性能合格・通信路割当・受信機採用は0。

**現在の改善結果は「fillの命令数削減と準備の分割を実装し、平均CPU・連続処理量を条件付きで見積もった」。未完了はownerの時間配分と有限bufferの整合、FPGAの全段統合、実メモリ/RF連続取得・品質、T/S同時TSの確認。** 未測定項目を理由に条件付き数値を出さないことも、仮定を達成済みとすることもしない。

再現：`python -m experiments.s3_integrated_estimate`。現SDK CFG、実C経路計数、fill包絡、FPGA16候補、保存STA、FIR算術を再計算し、根拠hashをestimate.jsonに保存。値の幅は入力ケース・感度仮定によるもので、統計的信頼区間ではない。
