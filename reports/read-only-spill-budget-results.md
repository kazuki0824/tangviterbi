# ② T spill読出し専用化とrefresh幅縮小：追跡値20726、残り10 logic

2026-10-19 JST。前回の回転cache＋固定mask版は、同じpipeline観測境界で全体追跡値20999/20736、263 logic超過だった。T spill readポートの実際の役割に合わせた特殊化と、refresh期限カウンタの幅縮小を検証した。

**機能検査とprobeの154.285714 MHz目標を通過したため、この2変更を部分実装へ採用した。更新追跡値は20726/20736、残り10 logic。ただし残未実装部分の追加費用を0とした値なので、完成受信機の収容や成立を示すものではない。正式採用は0のまま。**

## 変更と比較

| 版 | 本体直接合成logic | 配置後本体logic | 本体FF | probe Fmax MHz | 更新追跡値 |
|---|---:|---:|---:|---:|---|
| 前回：回転cache＋固定mask | 2733 | 2758 | 986 | 185.735519 | 20999、263超過 |
| 不採用：read payloadのゼロ消去省略 | 2729 | 3014 | 986 | 185.048126 | 21255、519超過 |
| T spill read専用ポート | 2479 | 2503 | 987 | 175.070038 | 20744、8超過 |
| **読出し専用＋refresh幅縮小** | **2428** | **2485** | **982** | **155.981918** | **20726、10残り** |

いずれもGW2A -nowidelut、GW2AR-LV18QN88C8/I7、seed 1、同じcapture/parity/digestの観測境界。wrapperは2019 FF、配置後logic1814で一致し、本体費用はwrapperを分離したLUT＋ALU集計で比較した。BRAM/DSPの追加は0/0。Fmaxはprobe内部clockの測定であり、外部SDRAM setup/hold・PHY・全受信機STAではない。最終版は目標に対する余裕も小さい。

## T spill読出し専用ポート

背景portの割当は0=T soft spill write、1=T soft spill read、2=T deinterleave、3=S frame、4=管理。**この分担におけるport 1はreadだけを発行する。** そのwrite dataとDQMはcontrollerのread処理で使われず、readデータやRF sampleを表さない。これらの選択入力を0とし、write指定もreadへ固定した。address、valid/ready、read response、他portのデータ/マスク、FFT cacheの要求は維持する。

黙ってwriteをreadへ変換しないよう、port 1へのvalidなwrite指定は仲裁へ流さず、readyも返さず、faultをラッチする。resetで復旧する。汎用の「全portがwrite可能」という契約ではなく、受信機内の上記役割を持つservice wrapperへ明示的に特殊化したもの。今後別の分担でslotの役割を変えるなら、その費用・契約を再評価する。

[同時トレース比較](../tests/test_sdf_read_only_spill.py)は元の汎用serviceと特殊化版を並べ、合法入力でcommand/address/DQM/DQ write/ready/response/FFT cache readがcycle単位で一致することを検査する。read専用portにも任意のdummy data/maskを与え、使われないことを確かめた。その他のportにはrandom write/read/mask、response停止、同時要求を与える。

最終試験は背景500要求完了・500受理、response停止1705 cycle、合成したFFT port sample 853個で全trace一致。不正writeの非受理とfaultのresetによる解除も成功した（1 test、1.112秒）。これは共通の任意DQ入力を与える比較試験であり、独立SDRAMモデルやFFT算術oracleの代替ではない。

SoC境界やnative I10/Q10転送量は変わらない。追加softwareデシメート/再量子化やFPGA→SoCの復調データ返送も導入していない。省いたのは内部read descriptorの不使用write情報である。

## refresh期限カウンタ

refresh_ageは16 bit固定だった。今回のREFRESH_CYCLES=1203なら、0〜1203を保持する11 bitで足りる。幅をclog2(REFRESH_CYCLES+1)とし、fault期限に達した後はその値で飽和させる。

この値を使う処理はrefresh_due（>=N−32）とfault（>=N）だけ。N未満では旧counterと同じ値、N以後は両predicateが同じまま、refresh時は双方0へ戻る。従って旧counterがfault後も65535まで増えることは、外部へ新しい情報を与えない。初期化waitや他のtiming値は変更していない。

[独立した旧16 bit counterとの比較](../tests/test_sdram_refresh_width.py)でN=64/1203/65535を検査し、意図的にrefreshを止めて期限前後・fault後も同じpredicate/発火clockを確認した（1 test、3条件、0.278秒）。genericな最大設定では16 bitを維持する。

実controllerは独立pin memoryのdata/mask/command timing/refresh/backpressure検査4条件・計14848要求を通過（1 test、2.804秒）。[結果とsource hash](sdram-bounded-refresh-test.json)。特殊化serviceのcoupled trace比較も新counterで再実行した。FFT算術本体とcacheは変更しておらず、今回新たなFFT全bin照合を実施したという主張はしない。

## 不採用案

read payloadをreset/write応答時に消去せず、writing種別で0のwrite ackを返す案は、独立メモリ試験とFFT接続2条件・各24576 bin照合に成功した（101.920秒）。ただし合成4 logic減に対し、配置後は256 logic増えた。DFF/passthrough等のpacking費用を含めると悪化するため不採用とし、controllerを元へ戻してから上記counter変更を行った。機能等価でも面積が減るとは限らない実測例として保存する。

## 追跡値の読み方と次のゲート

残予約2231 logicに本体2485を置くと、20472−2231＋2485＝20726。予約超過254を旧全体の余り264で吸収した計算であり、10 logicが残る。

これは既存stage allocationを維持し、**その他の未実装部分の追加logic費用を0とした追跡値**。背景producerのdescriptor/payload保持、RF端点、管理、PHY等の実費は別途必要。BSRAMの既存予約を今回の0使用だけで無料の削減へ戻すこともしない。全体P&R/STA、実K7消費とT/S burst、S3連続取得/転送/WCET、RF→TSは未達。

次は背景保持の所有権を既存stage保持と照合して、二重計上も未計上もなく実費へ置換する。10 logicの追跡上の残りを理由に新たな費用を省略しない。①は探索停止のまま。

## 証拠と再現

- [最終CAD](sdf-sdram-read-only-bounded-refresh-evidence/summary.json)／[coupled trace](sdf-read-only-spill-coupled-trace.json)
- [read専用化だけのCAD](sdf-sdram-read-only-spill-evidence/summary.json)。元のgeneric service・controller・初期trace試験snapshotも保存。
- [不採用案CAD](sdf-sdram-no-payload-clear-evidence/summary.json)／[不採用案FFT照合](sdf-rtl-arbiter-no-payload-clear.json)。controller snapshotと試験時hashを対応させ、現行counter版へ流用しない。

CAD再現：`python ci/sdf_sdram_service_evidence.py --output <new-dir>`。同じservice実験用コピーは `--read-only-spill` でも測定できる。機能検査は上記unittestをIcarus/vvpで実行する。旧案の再現は対応snapshotを使う一時checkoutで行う。

## 背景保持の追試

[所有権照合と追加1件保持案](background-holding-budget.md)を追加した。5 producerへ独立slotを足す案は配置後3761 logicとなり、旧stage allocationを維持する追跡値22002/20736で超過したため不採用。上記20726は保持費用なしの比較元として残す。stage自身の保持から直接駆動する構成は未実装であり、この反例だけで除外しない。
