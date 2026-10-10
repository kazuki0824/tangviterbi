# S用FECの資源圧縮と採否の再検算

追記：RS部分移管による90 MHz部分配置と、RSの平均/連続上限の期限を
[s3-rs-offload.md](s3-rs-offload.md)で更新した。本書の28.8288 µsはTS平均。
新しい保守的な連続上限は28.135828 µsで、ここに記載した圧縮候補の不合格は変わらない。

2026-10-10。対象はTang Nano 9K＋ESP32-S3-WROOM-1U-N16R8。
ISDB-T/Sは実行時切替。`receiver_adopted=false`、`safe_to_flash=false`。

**今回の圧縮で機能は維持できたが、面積と実時間期限を同時に満たす受信構成はまだ得られていない。**
新しい小面積版を採用候補へ昇格させない。以下は検査した具体的なRTLの比較であり、
考え得る全実装・全アルゴリズムを排除する証明ではない。

## 占有率の訂正

配置後のnextpnr JSONの`LUT4`欄にはALUが含まれない。
今回のnarrow-LUT構成の実ロジック位置数は**配置後LUT4＋ALU**である。
配置前LUT4欄はALUの`BLOCKER_LUT`を含む。配置後はそのplaceholderを除去し、
LUT/ALUと共有できなかったFFの位置へpass-through LUTを挿入する。
配置前LUT数、配置後LUT数、物理位置数を混同した以前の余裕計算は撤回する。

| 配置済みの部分回路 | 配置後LUT4 | ALU | ロジック位置 / 8640 | FF / 6480 | BSRAM / 26 |
|---|---:|---:|---:|---:|---:|
| PSRAM BIST | 1320 | 328 | 1648、19.07% | 685、10.57% | 2、7.69% |
| SPI→実PSRAM→頁reader | 2461 | 616 | 3077、35.61% | 1391、21.47% | 4、15.38% |
| 2面IQ通信、メモリはモデル | 1627 | 520 | 2147、24.85% | 963、14.86% | 6、23.08% |
| 旧S距離/TC8PSK/RS＋抽象メモリ | 5602 | 2028 | 7630、88.31% | 3498、53.98% | 6、23.08% |
| 新圧縮FEC＋抽象メモリ、seed2 | 4343 | 1432 | 5775、66.84% | 2524、38.95% | 8、30.77% |

各行は別topであり、単純加算で全体占有率にはならない。最後の行は周波数不合格。
FPGA全受信回路・T側復調・ESP32-S3のCPU使用率の証明ではない。

## 配置前に除外できるnetlistの監査

固定したpacked netlistについて、FFがLUT/ALUと同じ位置を共有するには、FFのDが
その位置のLUTのF又はALUのSUMに直結している必要がある。各driverは最大1個のFFと共有する。
したがって必要位置数の楽観的な下限は次式となる。

`real LUT数 + ALU数 + fabric FF数 − FFのDを駆動する異なるLUT/ALU数`

CE/reset/clockの一致、隣接セル、carry配置の制約を無視しているため、下限を通っても
配置成功を意味しない。wide LUT・distributed RAMには未対応なので監査を拒否する。
RTL再合成・構成変更にもこの下限は持ち越さない。
PSRAM単体は下限1643に対して実際1648、受信経路は3069に対して3077で、監査と矛盾しない。

| S用FEC＋実PSRAM受信経路の変更段階 | 必要位置数の下限 | 容量比 | 判断 |
|---|---:|---:|---|
| 元の32 ACS | 10498 | 121.50% | このmapped netlistは入らない |
| 出力2面を128×2 bit BSRAMへ | 9946 | 115.12% | 同上 |
| B1保存を64 state分から4 branch分へ | 9703 | 112.30% | 同上 |
| RSのOmega/誤り位置表を2 BSRAMへ | 9310 | 107.75% | 同上 |
| TC8PSKを22 ACS・3 clocks/symbolへ | 9009 | 104.27% | 同上 |
| 固定Q15距離回路に限り12-bit経路メトリックへ | 8903 | 103.04% | 同上 |
| 距離回路の正確な演算を3クロックで共有 | 8616 | 99.72% | 下限のみ通過。heap/seed1は合法配置未発見、Fmaxなし |

最後の下限の残り24位置を、使用可能な余裕と呼ばない。
このtopにはまだfilter、carrier/timing、TMCC、deinterleave、descramble、TS構築がない。
FECとメモリの入力は独立した合成負荷であり、RFからTSへつないだ試験ではない。
wide LUT許可・FF enableをmux化した別試行も配置不合格で、過去trialを保存した。

## 変更の内容と実時間期限

| 変更 | 維持した情報・実装上の注意 | 機能検証 |
|---|---|---|
| 出力のBSRAM化 | (B1,B0)全情報、出力cycleを維持。未書込みRAMはvalidで隠す | 旧版との9 epoch・45396 cycle比較、途中reset/stall |
| B1保存の圧縮 | 4 branchの最良B1を保存。traceback時に前状態とB0から171/133の(X,Y)を再構成 | 独立符号化8192 symbolと旧版cycle比較 |
| RSの表をBSRAM化 | Omega16×8、誤り情報8×16。最後の受信byteだけに誤りがある場合もprefetchを間に合わせる1 cycleを追加 | 独立262 vectors全合格、17 dirty-reset、245連続block境界。失敗経路10 packetも旧版とbyte/status一致 |
| 22 ACS | 0..21、22..43、44..63を3 cycleで更新。11本のshadowを再利用し64状態を維持 | 任意9-bit costの10240 symbol、655360状態を無限精度ACSと比較 |
| 12-bit経路メトリック | Q15/SHIFT22契約に限定。入力costを丸め直さずmodulo計算。任意9-bit costには従来13 bitを維持 | 別の10240 symbol、655360状態を無限精度と比較。13-bit版との出力一致、5 reset epoch |
| 距離演算共有 | 同じQ15 dot product・同じCOST_SHIFT。2個の減算/丸め回路を時間共有。入力は1 symbol/3 clocks | 境界値/全象限を含む4145 IQ対とstallを独立oracleで照合。実RTL→12-bit TC8PSKで8192 symbolの情報復号 |

99 MHzが達成できれば、22 ACSと距離回路は33 MSymbol/s（Sの28.86に対して14.35%の容量差）。
RSは最大2667 cycles＝26.939394 µs、188 B出力期限28.828829 µsに対して1.889435 µsの余裕。
これは**99 MHzを達成するという条件付き**の計算である。

実PSRAMを外した新圧縮FEC＋抽象メモリtopの配置配線結果は次の通り。

| seed | Fmax | 99 MHz制約 |
|---:|---:|---|
| 1 | 75.5915 MHz | FAIL |
| 2 | 83.8645 MHz | FAIL |
| 3 | 83.4446 MHz | FAIL |

最良のseed2でもTC8PSKは27.9548 MSymbol/s＜28.86、RSは31.8013 µs＞28.8288 µs。
RSだけでも92.511563 MHz以上が必要。目標99 MHzから計算した期限余裕を、
この実測配置の余裕として報告してはいけない。critical pathは距離出力からACSの演算/選択経路。
合成上のFF数削減と実時間性能の両立が、引き続き環境内で必要な再設計である。

## 12-bitで比較結果を保てる根拠

枝番号は(X,Y)。絶対射影は
`[|32768 I|, |23170(Q-I)|, |23170(I+Q)|, |32768 Q|]`。
I,Qの整数範囲は[-32768,32767]、量子化の分母は2^22。
絶対値の符号が変わる4直線と入力矩形で領域を分割すると、各領域の射影差は一次式になる。
全交点を有理数で列挙し、各領域の頂点で最大/最小を取ることで全2^32組を覆う。
共通offset付きの丸めの差は`ceil(射影差/2^22)`以下、飽和処理は差を増加させない。

| 枝ラベルのXOR | 絶対射影差の上限 | 丸め後のcost差上限 |
|---:|---:|---:|
| 1 | 1073741824 | 256 |
| 2 | 1073741824 | 256 |
| 3 | 1518469120 | 363 |

ある状態へ合流する2候補は、直前状態の最上位bitだけが異なる。
一方の最良経路の6 symbol前の入力bitを反転すると、同じ終状態へ入るもう一方の有効経路になる。
171/133符号器へのこの単一bit反転の7 symbolの出力XORは`[3,1,0,3,3,2,3]`。
従って候補cost差は双方向とも最大`4×363＋2×256＝1964＜2048`。
初期の6 symbolは等しい初期メトリックを持つ初期状態bitの反転と、その応答の末尾部分で同様に覆う。

全状態の真のメトリックを4096剰余で保持したと仮定すると、次の各合流の符号付き差が
この範囲内で真の順序を保つ。初期値0からの帰納法で、12-bit modulo ACSは無限精度と同じ枝を選ぶ。
これは新たな再量子化ではない。別のCOST_SHIFT、入力形式、初期INF、符号にはそのまま使えない。
11 bitの可否まではこの上限では確定しない。

## 採用手順への反映と通信

ユーザー指定の「性能を満たす分担→通信路を割当→0本でない候補を採用」に従い、
現時点の具体的な圧縮RTLは第1段階で保留/不採用となる。
通信帯域が足りても、今回の面積・期限不合格を相殺しない。
この変更ではSoC/FPGA間の情報、native I10/Q10の可逆packing、SPI経路、TS出力を変更していない。
SoC上で帯域のために追加デシメート・再量子化する候補は導入していない。
既存の通信条件・帯域余裕は`s3-communication.md`と`s3-receiver-blockers.md`の表に保持する。

最終回帰は`unittest discover`の56件、255.975秒、全合格。これは機能検査の合格であり、
上記の面積・周波数の不合格を上書きしない。

## 再現・証拠

固定OSS CAD suite 2026-10-04、Yosys 0.69+190 / nextpnr e2fe86b3。

```sh
python -m unittest discover -s tests -p 'test_s3_*.py' -v > build/s3-compaction-all-tests.log 2>&1
python ci/s3_psram_benchmark.py --compact-output
python ci/s3_psram_benchmark.py --compact-b1
python ci/s3_psram_benchmark.py --compact-rs
python ci/s3_psram_benchmark.py --acs22
python ci/s3_psram_benchmark.py --metric-q15
python ci/s3_psram_benchmark.py --folded-metric
python ci/s3_fec_extension_benchmark.py --kind tc8psk-compact
python ci/s3_fec_compaction_evidence.py --test-log build/s3-compaction-all-tests.log
```

必要位置下限で除外した試行はexit_code=126、配置未発見は125。
benchmark script自身の正常終了を受信機の合格判定に使わず、JSONのexit_code/期限/フラグを読む。
`s3-fec-compaction-evidence/`にRTL、source hash、合成条件、配置失敗ログ、全seed、試験結果を保存する。

一次実装根拠：[nextpnr e2fe86b3 Gowin slice_valid / create_passthrough_luts](https://github.com/YosysHQ/nextpnr/blob/e2fe86b3/himbaechel/uarch/gowin/gowin.cc)。
符号・変調の一次資料：[ITU-R BO.1408-1 §9, Fig.13–15](https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-1-200204-I!!PDF-E.pdf)。
