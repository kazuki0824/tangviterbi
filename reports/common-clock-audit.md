# 2026-10-19 仕様確認の更新

[一次資料との照合](sdram-spec-gate.md)：内蔵SDR SDRAMの166 MHz仕様とPLL数値範囲を確認。154.286 MHz案は公称周波数内。個別command timing・IO setup/hold・位相の確定は未達であり、物理合格ではない。

# 内部CDCを先に減らす：②のclock設計監査

2026-10-18。結論：135 MHzメモリdomainは必須条件ではない。演算とSDRAM controllerのuser側を154.285714 MHzへ統一する案を先に検証する。ただしPHYの実デバイスtimingを満たした証拠はまだない。実装済みCDCを除去して資源を減らした測定結果でもない。確定資源削減は0。

## domain別の判断

| 境界 | 方針 | 残る証明 |
|---|---|---|
| FFT/K7/RS/仲裁/controller user側 | 同一clock、必要な低頻度処理はclock enable。内部async FIFOを前提にしない | 全stage統合STA、競合・最悪期限 |
| controllerとSDRAMの端子 | 同一PLL由来の関連clockと位相調整を候補にする | メモリ速度grade、CL、setup/hold、出力/入力delay、PLL設定・配置 |
| 独立S3の送信clockとFPGA内部 | source-synchronous取込み後のCDCが残り得る | 各通信経路のclock関係と有限FIFO。周波数一致だけで同期としない |
| reset/PLL lock | 各domainの解除を同期させる | lock失敗・再選局・途中resetで旧データを混入しない |

Gowin [IPUG279-1.3E §6.2 pp18–19](https://www.gowinsemi.com/upload/database_doc/281/document/5d280116bebab.pdf)は、user interfaceをcontroller clockへ揃え、SDRAM側はsetup/holdを満たす位相を調整する構成を説明する。表8-1のGW2AR-18 controller Fmax≥160 MHzは、Tang Nano20Kの実メモリと今回の自作controllerを154.286 MHzで保証する値ではない。既存135 MHzも認定済みsilicon timingではなかった。

## clock案の比較

| 案 | K7能力（127/128の保守予約後） | 判断 |
|---|---:|---|
| 全内部135 MHz | 66.972656 Mstep/s | 需要75.717121 Mstep/sに不足。現K7では除外 |
| 全内部1080/7 MHz | 76.540179 Mstep/s | 算術上の残り0.823058 Mstep/s。PHYと統合期限を検証する候補 |
| 演算1080/7 MHz・メモリ135 MHz | 演算能力は上と同じ | 比較対照として残す。CDCの容量・資源・遅延を別計上 |

同じ27 MHz源、または周波数比8/7というだけではCDCを消してよい根拠にならない。PLLの関連clock関係を制約へ記載し、全経路を解析する。135 MHz案が落ちるのは現K7の処理能力であり、すべての回路方式の不可能性ではない。

## 時間設定を持ち越さない

[検算script](../experiments/common_clock_audit.py)と[JSON](common-clock-audit.json)は、従来の**仮定**の最小待ち時間を切り上げ、最大refresh間隔を切り下げて換算する。仮定をデバイス仕様へ昇格させない。

| 設定 | 旧135 MHz | 154.286 MHz候補 |
|---|---:|---:|
| 初期wait | 27000 cycles = 200 µs | 30858 cycles ≈ 200.006 µs |
| tRP/tRCD/tWR/tMRD | 各3 cycles | 各4 cycles |
| tRFC | 10 cycles | 12 cycles |
| refresh上限 | 1053 cycles | 1203 cycles |

旧27000を流用すると175 µs、旧tRFC=10は約64.815 nsまで短くなる。CL=3は保持したが、このclockでのCAS速度gradeは未認定。tMRDが仕様上cycle単位であっても、今回の4 cyclesは旧仮定時間を短縮しない保守的な試験設定である。

## 実行したデジタル試験

`rtl/dual_sdram_burst.sv`と`tests/test_dual_sdram.py`を既存履歴302d805から復元した。以前の集計にあるcontroller hashとは異なるので、旧135 MHzの帯域を比例拡大しない。同じ復元sourceで135 MHzの対照も再試験し、通過した。

`tests/test_common_clock_sdram.py`は154.286 MHz相当のclock、30858-cycleの初期化、独立command monitorとdata scoreboardを使用する。same-rowとMode3 FFT＋bank/row競合の2列、open/closed-pageの2条件で、計14848 requestsを検証。byte mask・全burstデータ・response stall・refresh期限も検査する。これは単一要求列の直列処理であり、同時全clientの期限保証ではない。

[154.286 MHz結果](common-clock-sdram.json)、[同sourceの135 MHz対照](common-clock-baseline-135.json)。154.286 MHz候補のrefresh最大間隔1197 cyclesは設定1203以内。open-pageのFFT混合列は388.218 MB/s、競合列253.085 MB/s。到着時刻・初期wait/stall条件が対照と異なるため、これを純粋なclock高速化率として比較しない。

## 保持領域・資源・次の合格条件

Tの29952 B/symbol、二重保持候補59904 Bはバーストとデータ寿命の問題であり、CDC除去だけでは消えない。既存ringからの直接読出しで重複を除けるかを、書込み・読出し・再利用時刻で検証する。追加全量spillの57.627706 MB/sも、aliasが証明されるまで無料扱いにしない。

混合予算20472/20736 logic、46/46 BSRAMは変更しない。未実装予約2231 logic/1646 FF位置/13 BSRAMから、未実装CDCの推定費用を架空に差し引かない。復元controllerを予算へ二重加算もしない。既存controller allocationとの置換差分は統合時に測る。

次は実メモリtiming仕様とPLL/PHY制約を確定し、共通clock controllerを全client仲裁へ接続、リング寿命・最悪refresh競合を検証してから全体P&Rへ進む。154.286 MHzの実メモリ条件が成立しなければ、二domain対照の費用を測る。単一clockを無理に採用するために信号品質を落とさない。FPGA→S3は指令のみ、native I10/Q10、正式採用0を維持。
