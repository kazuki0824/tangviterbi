# ② 固定配置からの再配線試行

2026-10-27。旧部分構成152.091263MHzの配置を保ち、router2で配線を改善する試行。旧回路・全段予算を速い別kernelへ置換しない。

同じnextpnr基底commit e2fe86b3、同じGW2A-18C chipdb hashを確認したが、保存JSONの直接復元はroute開始前に `array2d.h:78` のassertionで終了した。Gowinの `notifyBelChange` は `fast_logic_cell` にアクセスする一方、その初期化は `prePlace` 内にあり、`--no-place` での保存BEL復元ではその初期化を通らない。配線・STA結果は得られていない。

代替として保存BELを全て位置制約へ変換し、通常のprePlaceを通す方法も実行した（[結果](../cursor-mask-fixed-router2-replay/result.json)）。こちらはALU1上のC2L dummy cellの位置制約を受理せず終了。保存routed JSONのcell/parameterを調べると、pack段階からのcluster制約はJSONへ保存されていない。保存packedとroutedの共通cellはtype/parameter一致だが、blocker除去・passthrough追加もあるため、routed JSONをそのまま未配置入力として扱えない。

どちらも回路の速度不足・資源超過を新しく示す結果ではない。保存STA152.091263MHzを据え置き、FPGA改善量を0として統合見積もりへ反映する。次の有効な試行には元の互換pair packerから通常pack/placeを再実行するか、backendのcheckpoint復元処理を直して同一回路・配置の復元を検証する必要がある。合法性検査を無効化して速度だけを報告しない。

実行にwall-time打切りは置いていない。2試行ともツール自身のエラーで終了した。command/result/logを保存。全受信機のP&Rではない。
