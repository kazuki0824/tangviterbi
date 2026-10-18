# ② 現行SDF cacheの競合試験：仲裁で期限結果が変わる

2026-10-19 JST。現行`shared_sdf_fft`＋32 B `sdf_delay_cache`＋実`dual_sdram_burst`へ背景要求を追加した。**旧6転送FFTの代用品ではなく、現行FFTが実際に発行するread/write要求を使う。** 背景側は均等到着の合成負荷であり、実K7/deinterleave/S frame回路は未接続。

## 境界と背景負荷

154.285714 MHz、Mode 3、GI 1/32（160380 clocks/symbol）。1要求はBL8・32 B。背景の各源は有理数accumulatorで均等にreleaseし、1要求ずつ処理する。FFTの入力は常時validと、有効区間1215/64 clocks/sample・symbol周期160380 clocksのpaced条件で比較する。pacedの起点は初回cache準備後で、RF受信開始からSDRAM初期化中の入力を保存できる証拠ではない。

| 背景源 | 要求/symbol | MB/s | 今回の依存関係・配置 |
|---|---:|---:|---|
| T soft spill write | 936 | 28.813853 | 128 BL8の循環領域、未読overwriteを検出 |
| T soft spill read | 936 | 28.813853 | 対応write応答の後だけread可能 |
| T time-deinterleave相当 | 2091 | 64.369408 | 128 BL8を巡回、write/readを交互に実行 |
| S frame相当 | 744 | 22.903319 | 同上、領域を分離 |
| 管理予約 | 325 | 10.004810 | 同上、既存10 MB/s予約の切上げ |
| 背景合計 | 5032 | 154.905243 | FFT outer delayは別途実要求 |

背景の基準帯域は旧試験と同じだが、旧FFT 189.137 MB/sを投入しない。T readの消費cache/K7を接続していないため、write済みでreleaseされればreadする。T ringの128 BL8はこの試験用配置で、実必要容量ではない。deinterleave/Sの実scatter配置・burst依存関係、入力/出力frame stagingは再現していない。SoC側の追加デシメート・再量子化は導入していない。

仲裁はtestbench内。条件AはFFTを含む6源のround robin、条件BはFFT要求があれば次の選択で優先し、他は5源のround robin。処理中のBL8は中断しない。優先以外の条件は同一。request/responseの所有者を保持し、独立pin memoryとは別の要求側reference memoryで背景readも照合する。

queueは到着/完了カウンタで診断し、256未完要求を超えた最初の時刻を記録する。**256深さFIFOを実装してはいない。** 背景の期限指標はreleaseから1 symbolで、stage本来の期限を証明した値ではない。入力もtestbenchの4 frame配列で保持しており、測った最大滞留が実装済みFIFO容量を意味しない。

## 結果

| 仲裁・入力 | 後続frame間隔 clocks | 背景最大未完数（T write/read、TI、S、管理） | 入力最大滞留 |
|---|---|---|---|
| round robin・常時valid | 175474 / 175435 | 1 / 1 / 2 / 1 / 1 | pacedでないため対象外 |
| FFT優先・常時valid | 144560 / 142116 | 1 / 1 / 3 / 1 / 1 | 同上 |
| FFT優先・paced | 160381 / 160381 | 1 / 1 / 2 / 1 / 1 | 4 sample（16 B） |

round robinは常時validでも目標symbol周期160380 clocksを15094 clocks（9.41%）超え、このモデルで継続処理能力が足りない。FFT優先の常時validは最大144560 clocksで、観測差分15820 clocks（9.86%）。後者は競合下でも先の32 B cacheを検証候補として残せる結果だが、余裕を保証値にしない。

pacedの2間隔は目標より各1 clock長い。frame完了は346957 / 507338 / 667719 clocks、入力開始基準epoch=30978。各frameの提示開始からの遅延は315979 / 315980 / 315981 clocksで、短期の2 clock差を観測した。13 clock slotへの量子化の影響を含むため、これを無限の遅延増大とも、長期安定の証明とも判断しない。長期位相一巡と実frame期限の検証は残る。入力最大4 sampleは今回の測定値であり、4 sample FIFOで全条件十分とはしない。最大受理間隔4888 clocksにはGIが含まれる。

全3条件で背景の256未完超過なし、試験用1 symbol期限超過0、到着数＝完了数＋残件数を確認。試験終了時の残件をJSONに残し、全要求をdrainしたとはしない。FFT要求完了数の8192/8193の違いは4 frame入力後の次line先読みの完了有無を含む。非使用の余分な先読みも実トラフィックとして数える。

全条件で非零乱数4 frameを入力し、最初の3 complete frame・24576 binを独立整数FFT oracleと比較する。初期化、ACT/read/write/precharge/refresh、DQ collision、背景read値、T未読overwriteも検査する。PHY setup/holdは対象外。

## 判定の範囲と次の作業

常時valid条件のframe間隔は継続処理能力を見るもの。paced条件の隣接完了間隔にはjitterが入るため、単一間隔がsymbol周期を超えたかだけで失敗/成功としない。実際のreleaseから完了までの許容遅延、入力滞留の上界、後段の期限を合わせて決める必要がある。今回の3出力frameだけで長時間上界を証明しない。

有利な均等負荷でもround robinは不足したため、その仲裁条件を棄却する。FFT優先の通過を全条件へ一般化しない。次は実K7消費・deinterleave/S frame到着/アドレスを接続する。現状のtestbench仲裁を採用RTLへ移す際は保持容量と資源を計上し、全体P&Rで確認する。既存の20472/20736 logic・46/46 BRAM見積もりに新cacheが収まったとは未確認。

**現時点の正式採用は0。PHY、全体STA、S3 WCETも未達。①は変更なし。**

[再現unittest](../tests/test_sdf_cache_contention.py)／[全結果・source hash](sdf-cache-contention.json)。unittest 1 method・内部3条件が113.553秒で成功。unittestの成功はround robinの性能合格を意味せず、データ/command/集計の検査成功を指す。Icarus/vvpをPATHへ置き、repo直下で `SDF_CONTENTION_REPORT=reports/sdf-cache-contention.json python -m unittest discover -s tests -p test_sdf_cache_contention.py -v`。
