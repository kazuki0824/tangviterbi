# ②：公式SDRAM参照設計を取得した結果

追記：[有限保持とK7供給条件の試験](k7-finite-retention.md)を追加。160 clocks/32 Bの仮想供給条件を次の接続候補とし、192 clocks条件は継続帯域不足・bank再使用失敗で除外した。実SDRAM仲裁・PHY合格ではない。

2026-10-19 JST。**②の探索を継続。参照設計の取得ではPHY認定を閉じられなかった。** ①のbranch/PRは変更しない。

## 取得・検算

[Gowin公式IPページ](https://www.gowinsemi.com/en/support/ip_detail/69/)から公開されている「SDRAM Controller GW2AR-18 RefDsign」の[archive](https://www.gowinsemi.com/upload/database_doc/2058/document/64f5457822ba5.rar)を取得・展開した。vendor IPの再配布はせず、archiveと主要ファイルのSHA256、計算値を[JSON](sdram-reference-audit.json)へ保存した。

再現：`python experiments/sdram_reference_audit.py ARCHIVE.rar EXTRACTED/SDRC_2AR18K`。この検算はファイル解析と有理数によるclock計算であり、vendor simulation/P&Rの実行ではない。

| 調査対象 | 確認した内容 | 今回への意味 |
|---|---|---|
| Readme | 対象GW2AR-18LV7LQ144C | QN88C8/I7への直接の実装保証ではない |
| PLL RTL | 50 MHz、IDIV_SEL=15、FBDIV_SEL=52 | 50×53/16＝165.625 MHz |
| 同梱SDC | 20 ns入力、両generated clockは3倍 | 150 MHz指定。PLL RTLと15.625 MHz不一致 |
| PLL生成設定 | 出力目標166 MHz、許容差2% | 165.625 MHzと整合。SDC側の150 MHzとは異なる |
| 端子timing | このSDCにはinput/output delay指定なし | メモリsetup/holdをこのファイルだけで認定できない。専用tool内部の扱いは別途確認が必要 |
| simulation | DUT、FPGA primitive、controller netlistを使用 | 独立したSDRAM timing modelは収録ファイルの調査で見つからなかった |
| IP設定 | embedded controller、device ID、IO挿入設定 | メモリのtRCD/tRP/tRFC等の保証値一覧にはならない |

SDC周波数に対するRTL計算値の差は10.416667%。このarchiveの保存済みtiming結果を、そのまま165.625 MHzや今回の154.285714 MHzの証拠に昇格しない。SDCの位相指定とPLLの出力接続も移植時の再確認対象であり、位相をコピーするだけの修正は行わない。

[Sipeed公式example](https://github.com/sipeed/TangNano-20K-example/tree/e23949a0a77381b94960cbc4e97a7c5e5ba8d222)も確認した。`nestang/src/sdram.v`は54 MHzを既定値とする非burst controllerで、コメント上の設定上限は66.7 MHz、CL2を使用する。180°のSDRAM clockの例は今回のCL3・154.286 MHz・BL8 PHYのSTA保証ではない。ここから低速時の待ちcycleを移植しない。

## 判定と続行先

今回得られたのは「公式archiveを未取得」という不足の解消と、流用できない理由の特定である。**対象QN88の詳細memory timingとPHYは依然未確定**。現自作controllerの4/12 cycle等は旧仮定を保った条件であり、保証値に更新していない。

PHYの合格判定には対象device向け生成IP/実装制約・メーカーの詳細timing、またはそれらに基づく実機評価が必要。このarchiveのみで満たせるという探索経路はここで終了する。公開資料に存在しないと一般化はしない。

②の次のデジタル探索は、既存の仮定付きBL8 controllerに対する**T soft値保持・K7供給の有限buffer/仲裁**に移す。29952 B/symbol、二重保持59904 Bをまず独立allocationとして計上し、寿命が証明できるまで既存ringとのaliasで差し引かない。全量spill時の追加read/write 57.627706 MB/sを含め、Sとの競合でK7が供給不足にならないかを検査する。平均帯域やbacklogged traceの単体速度をdeadline保証として流用しない。容量超過・供給不足ならこの保持方式を落とす。PHY未確定のまま全受信機を合格にはしない。

資源混合予算20472/20736 logic・46/46 BSRAM、残統合予約2231 logic/1646 FF位置/13 BSRAMは据え置き。今回新しいRTL/合成/P&R結果はなく、確認済みCDC削減0、正式性能合格・通信割当・採用0。native I10/Q10、FPGA→SoC指令のみ、帯域都合のsoftware品質低下禁止を維持する。
