# ② 64bitカウンタ比較・桁上がりの費用監査

保存S ELFのtake/completeを、上位32bit一致という分岐制限を外して監査。take成功包絡55命令、empty30命令は不変。completeは8lease退役を上限に全分岐を展開し、従来144から153命令の包絡へ変更した。最後に不要なslot確認をする実現不能経路も許す保守的包絡で、実測増加9命令の主張ではない。

上限8回の根拠は8leaseで各退役時に別slotをFREE化すること。64bit全体のオーバーフローは除外し、下位32bit桁上がりと上位word不一致は許す。実Cの全完了順序を、8種類の開始番号・1〜全leaseで検算。S16KiBは369864例、T32KiBは264例。順序違いの完了、重複完了拒否、prefixだけの退役、payload位置を確認した。実C機能検算とXtensa命令包絡は別々の根拠である。

REAP_DONEを469→479cycleへ置換し、同じ費用をCPU台帳と時刻に一度だけ課した。24順序×3分担×3準備予算を100bank評価し、Sで通過した条件とT現行順序は4000bankでも確認。slice512、stall0%、その他の費用は旧台帳と同一。owner並べ替え後の制御命令費用は190cycleという同一模型のまま。

|系統|準備語|100bank通過順序/24|4000bank通過/実施|最長到達bank|
|---|---:|---:|---:|---:|
|T 8/16|1024|24|1/1|4000|
|T 8/16|2048|24|1/1|4000|
|T 8/16|3072|24|1/1|4000|
|S 5/16|1024|0|0/0|41|
|S 5/16|2048|6|0/6|344|
|S 5/16|3072|0|0/0|79|
|S 6/16|1024|0|0/0|3|
|S 6/16|2048|2|0/2|609|
|S 6/16|3072|0|0/0|61|

残るwindow例外・追加lock/ハード待ち・メモリ競合・アプリ差分を解消したわけではない。全SoC計上完了・正式採用とは認定しない。結果は [runtime.json](runtime.json)、命令根拠は [instructions.json](instructions.json)。

再現：`python -m ci.s3_counter_envelope --toolchain ../toolchain/xtensa-esp-elf`、`python -m unittest tests.test_s3_counter_envelope`、`python -m experiments.s3_counter_runtime`。
