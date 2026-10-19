# ② SDRAM burstのシフト化比較：両方向案は不採用

2026-10-19 JST。面積超過862 logicを受け、256 bit保持の可変beat選択を32 bitずつのシフトへ変更する案を検証した。**両方向シフト案は機能試験に成功したが、面積とFmaxが悪化したため採用しない。`rtl/dual_sdram_burst.sv`はa3cab3b時点の実装に戻した。**

| 案 | 本体直接合成 logic | 元との差 | 配置後本体 logic | probe Fmax MHz | 判定 |
|---|---:|---:|---:|---:|---|
| 元の可変beat選択 | 3325 | 0 | 3357 | 183.925 | 面積予算超過の基準 |
| readのみシフト | 3210 | −115 | 未測定 | 未測定 | 合成だけの削減候補、成立根拠にしない |
| writeのみシフト | 3600 | ＋275 | 未測定 | 未測定 | 面積削減案として不採用 |
| read/write両方シフト | 3488 | ＋163 | 3584 | 150.399 | 目標154.286 MHz未達、面積も悪化。不採用 |

readは各DQ wordを256 bit responseの上端へ入れ、右へ32 bit送る。8 beat後のword 0が下位になるよう、最終beatの組合せresponseも合わせて変更した。writeは各beatの先頭32 bitとDQM下位4 bitを出力してシフトする。外部のBL8順序、マスク、受理/応答契約を変えない案である。

両方向案は独立pin memoryによるデータ・マスク・refresh・応答停止のunittestを通過（1 test、2.625秒）。さらに実仲裁＋FFT/cache/controllerの常時valid/周期入力2条件で各24576 binが独立整数FFT oracleと一致（1 test、91.333秒）。frame完了時刻も基準と一致した。ただし物理Fmaxが目標未達なので、このclockで実機動作できる証拠にはならない。

readだけ/writeだけの分離案は合成まで。両方向案の機能試験やFmaxを分離案へ流用しない。115 logicの合成削減だけで、既存の862 logic超過および残未実装費用が解消したとは主張しない。次はread案の単独検証と、wide仲裁・cacheの選択/保持構造を含む、より大きな削減の根拠が必要。

シフトで可変選択を減らしても、全保持bitのload/shift選択が加わるため、この実装では自動的な面積減にはならなかった。面積の増減は表の実測値で判断し、回路の書き方だけから有利と決めない。

## 証拠と再現

- 両方向案：[controller snapshot](sdf-sdram-shift-evidence/controller.sv)、[CAD結果](sdf-sdram-shift-evidence/summary.json)、[FFT接続結果](sdf-rtl-arbiter-shift.json)。source hashの `rtl/dual_sdram_burst.sv` は試験時の変更版を指し、保存snapshotと同一hashである。現行RTLは元に戻したため、そのままでは変更版を再現しない。
- 分離案：[read合成](sdram-read-shift-probe/summary.json)、[write合成](sdram-write-shift-probe/summary.json)。各ディレクトリにcontroller.sv、synth.ys、合成log/netlistを保存した。repoの親ディレクトリから当該synth.ysをYosysへ渡す。
- 両方向案の再現は一時checkoutで保存snapshotを `rtl/dual_sdram_burst.sv` へ置き、`ci/sdf_sdram_service_evidence.py`、`test_common_clock_sdram.py`、`test_sdf_rtl_arbiter.py` を実行する。正規ブランチへ不採用回路を復帰させない。

全体見積もりは基準の21598/20736（862超過）のまま。①変更なし。外部push/PR更新は承認レビュー用モデルのcapacityエラーで未反映のため、この結果もローカル保存状態である。
