# S3-N16R8 / Tang Nano 9K：実機なしで実施した検証

> 後続の[成立条件の再検証](s3-receiver-blockers.md)で、旧Viterbiの復号不良、
> RF bank公開を含む32 KiB queue案の期限違反、およびRF本体を含めた
> SRAM配置の問題を確認した。本稿の旧見積もりだけで成立と判定しない。

**後続の実装結果：** [実SPI/SCT・無損失梱包・SRAM再配置](s3-transport-followup.md)を参照。本書の7080 B余白は実ドライバーを含まない最小probeであり、実SPI/hot IRAM込みの旧配置は8000 B超過した。起動後RF queueへ変更したT配置の静的余白は24768 B。2 usをAPI全体のgapとした通信モデルも旧条件として残す。現実装ではAPI費用とSCT内gapを分けて再計算しており、受信機成立は未判定。以下のRS検証結果は引き続き有効。

2026-10-09。PR #4。T/S実行時切替、基板外付けSPI NORの複数image、ソフトウェアでの追加間引き・帯域都合の再量子化禁止を維持する。**RSのS向け処理速度は部分回路で必要下限を超えた。一方、完全な受信機の成立判定は未達。** 今回の成果は実験用RTL・ホスト実装・実リンク・配置配線の検証である。`rtl/`の既存採用版は変更していない。

## 今回確定したこと

| 項目 | 実施内容 | 結果と適用範囲 |
|---|---|---|
| RSの処理期限 | 同期逆元ROM、Chienの評価/位置更新統合、次数9以上の早期fail、全65536 BM制御経路の列挙 | 規格対応版は最大 **2666 clocks/block**。最長制御経路をRTLでも通し、通常の8バイト訂正vectorでも同じ2666周期を観測 |
| RSの規格上の不具合 | 独立encoderで入力を作り、生成根・短縮位置・Forney式を修正 | 262 vector合格。全204位置の単一誤り、2〜8バイト誤り、17回の処理途中reset、245か所のresetなし連続blockを含む |
| 旧T SRAM案 | ESP-IDF v5.5.1で実際にリンク、RFのD/IRAM aliasをASSERT | 2通信路は **43016 B超過**、3通信路は **51200 B超過**。旧案は不採用 |
| 改訂T SRAM案 | payloadのzero-copy、header/descriptor分離、上位SRAMに起動後の係数領域を予約 | 最小probeはリンク成功。RF領域までの静的余白は2通信路 **7080 B**、3通信路 **6536 B**。完全なRF firmwareの余白ではない |
| 2並列FFT | CのQ15 in-place tile、bit-reversalの所有権、段間barrierを実装 | 32/256/8192点×5入力の15条件で逐次版とbit一致。独立浮動小数FFTとの差は最大1.467 LSB未満。S3 SIMD/WCETは未測定 |
| FFT/RF通信の競合 | Octal busの離散eventモデル、6開始位相×256 symbol | 500 us FFT/2 us gapの契約で期限違反0。RF queueはDMA中の1 descriptor込み最大25445 B /32768 B |

## RS：等価性だけでは見つからなかった問題

旧回路との出力等価試験には合格しても、放送用のRS符号が訂正できる保証にはならない。旧規約を保持した短縮版に独立ISDB vectorを17個投入すると、合格は全zeroの1個だけだった。無誤りの非zero符号語でもfailを誤って立てる。この失敗結果も `s3-legacy-rs-vector-diagnostic.json` に保存した。

[ARIB STD-B31 v2.2 §3.3](https://www.arib.or.jp/english/html/overview/doc/6-STD-B31v2_2-E1.pdf#page=32)と[ITU-R BO.1408 §2](https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-0-199910-S!!PDF-E.pdf#page=3)の外符号に合わせ、`experiments/s3_rs_isdb.py`で次を修正した。

1. syndromeの生成根をα¹…α¹⁶から **α⁰…α¹⁵** へ変更する。GFは0x11d、α=0x02。
2. 204-byte入力の先頭を多項式のx²⁰³係数とする。位置jのlocator rootはα^(j−203)=α^(j+52)。Chienの開始点と位置保存を対応させる。
3. first root b=0に対し、訂正値を `Omega(x)/(Lambda'(x)*x)` とする。分母積の受渡しを1周期追加するため、最大8訂正で8周期増える。
4. 次数0の係数先読み、位置0/203、次数9〜16の早期failを境界試験する。次数16の4-bit wrapも更新前に検出する。

この変更は旧回路との完全等価性を意図しない。独立encoderはcarry-less積と多項式除算で符号語を生成し、16個の根すべてでsyndromeゼロを検算する。0〜8バイト誤りでは元の188 bytesへの復元とfail=0を要求する。9個以上の誤りを必ず検出する保証、erasure対応、受信機全体のARIB適合性はこの試験の範囲外。

| フェーズ | 従来の保守上限 | 旧規約を保つ短縮版の精密上限 | ISDB規約修正版 |
|---|---:|---:|---:|
| 入力 | 204 | 204 | 204 |
| BM | 593 | 305 | 305 |
| Omega | 177 | 141 | 141 |
| Chien | 2041 | 1633 | 1633 |
| Forney | 297 | 185 | 193 |
| 出力/reset | 190 | 190 | 190 |
| 合計 | 3502 | 2658 | **2666** |

BMの全zero/nonzero軌跡65536通りを列挙し、次数超過で終了する21845通りも含める。正常次数のすべての経路に最大8回のForneyを保守的に課しても、最大は2666。これは制御モデル＋RTL最長経路試験であり、形式検証による全RTL状態の証明ではない。入力stallと出力側の蓄積待ちは含めない。decoder出力にはbackpressureがないので、後段FIFOは別途必要。

Sの6.521250 MB/sでは34687.5 block/s、到着周期28.828829 usとなる。必要RS clockは **92.476875 MHz**。99 MHzなら26.929293 us/block、余裕 **1.899536 us（6.589%）**。旧2758周期は中間の粗い上限、2658周期は旧規約版の上限であり、現行ISDB版には2666を使用する。

## 配置配線

初回の同期ROM指定だけでは、256×8 ROMがLUTへ展開された。`schedule4`の99/125 MHz条件はどちらもcore70.95/mem64.21/RS66.99 MHzで、Sの期限を満たさなかった。面積もRS2016論理相当へ増加した。結果は[run 37885216791](https://github.com/kazuki0824/tangviterbi/actions/runs/37885216791)と `s3-area/schedule4-auto-ROM-*.json` に残す。

修正版は `ram_style="block"` を明示する。ローカルYoWASPではblock bufferとinverse ROMをそれぞれDPX9B/SPX9へ割り当てることを確認した。CIの最終測定値は同じOSS CAD Suite 2026-10-04内で比較し、異なるYosys版の面積差を混ぜない。

規格修正のみの `isdb4` は、[run 37886060001](https://github.com/kazuki0824/tangviterbi/actions/runs/37886060001)でRS単体81.46 MHz、mem88.04 MHzとなり、必要な92.476875 MHzに届かなかった。そこでBMの次数更新条件と多項式選択maskを前段で登録し、制御counter→shift→selectorの組合せ経路を短くした。サービス周期は2666のまま。

最終の `isdb-predecode4` は [run 37888374112](https://github.com/kazuki0824/tangviterbi/actions/runs/37888374112)で測定した。source commitは `d00a102a36bddaee792af0980516f9174fa44e04`、生成RS RTL SHA-256は `08594ea679ff1a779e0a72b241d0de1fa87c520e292414b2bb07cf1144e3d610`。独立262 vectorもこの同一RTLで全件合格した。

| 部分ハーネス | 規格修正のみ Fmax | 制御改善後 Fmax | LUT4 | FF | BSRAM | 99 MHz目標 |
|---|---:|---:|---:|---:|---:|---|
| FEC core | 81.86 MHz | **105.41 MHz** | 4840 | 2543 | 4 | PASS |
| FEC＋メモリcontroller | 88.04 MHz | **107.91 MHz** | 5016 | 2681 | 4 | PASS |
| RS単体＋計測wrapper | 81.46 MHz | **97.92 MHz** | 1779 | 1041 | 2 | FAIL |

独立module合成はRS **1747 LUT+ALU相当 / 1016 FF / 2 BSRAM / 0 DSP**、Viterbi **2953 LUT+ALU相当 / 1502 FF / 2 BSRAM / 0 DSP**。この論理相当数と上表の配置後LUT4は異なる指標である。生の結果は [isdb-predecode4-99.json](s3-area/isdb-predecode4-99.json)。

Sの92.476875 MHzというサービス下限は全3ハーネスで上回る。99 MHzはcore/memで通ったが、RS単体の配置では1.08 MHz不足する。したがって「どの統合条件でも99 MHzで成立」とはしない。96 MHzなら算術上は27.770833 us/block、余裕1.057995 us（3.670%）だが、96 MHzの別domain採用にはPLL/CDCを含めた再検証が必要。現段階では99 MHz統合案のまま、全受信機STAを残ゲートとする。

これらのcore/memはFECとプロトコルcontrollerの部分ハーネス。実PSRAM PHY、全復調器、CDC、実ピンのI/O timingまで含む受信機の配置配線ではない。workflowのsuccessとtiming PASSは別に扱う。

## SRAM：総量と配置を分けて検証

初回probeは16 MB Flash/Octal PSRAM、2 coreのESP-IDF v5.5.1でビルドした。SDK commitは `fcae32885b0296b32044cb99ecbdc50d98dddb83`。RFは `[0x3fcb0000,0x3fce0000)` を予約し、IRAM alias、data、BSSの3か所をlinker ASSERTで検査する。

| 最小probe | リンク | BSS末尾 | RF領域までの余白 |
|---|---|---|---:|
| 旧T・2通信路 | FAIL | 0x3fcba808 | −43016 B |
| 旧T・3通信路 | FAIL | 0x3fcbc800 | −51200 B |
| 旧S・2通信路 | PASS | 0x3fca2008 | 57336 B |
| 改訂T・2通信路 | PASS | 0x3fcae458 | 7080 B |
| 改訂T・3通信路 | PASS | 0x3fcae678 | 6536 B |

失敗：[run 37884467973](https://github.com/kazuki0824/tangviterbi/actions/runs/37884467973)。改訂：[run 37885216772](https://github.com/kazuki0824/tangviterbi/actions/runs/37885216772)。各mapの主要symbol、SDK、source SHA、終了状態は `s3-memory/*.json` に保存した。完全なmap/ELF/build logは各runのartifactにある。

改訂内容は次のとおり。

- RF packed queue 32768 Bを維持する。旧通信staging（8184 B/port）を除去し、payloadをRF queue/FFT slotから直接DMAへ渡す設計とする。1 portあたりheader32 B＋descriptor予約512 Bを確保する。**scatter/gather driver自体は未実装**。
- FPGAによるGI除去後の8192複素sampleだけを受け取るため、FFT slotは2×32768 Bとする。全8192 binをQ15複素値のまま返す。framingは別descriptorに置く。
- tile FFTに必要なtwiddleはN/2複素値＝16384 B。`[0x3fce0000,0x3fce4000)` を `SOC_RESERVE_MEMORY_REGION` でheapから除外し、`app_main`以後に初期化する。ELFの初期data/BSSには置かない。

上位領域は[IDF memory_layout.c](https://github.com/espressif/esp-idf/blob/v5.5.1/components/heap/port/esp32s3/memory_layout.c)のboot時利用可能領域 `[0x3fce0000,0x3fce9710)` 内に収める。起動前から使用したり、PSRAMへ退避したりしない。SDK変更時にはこの固定境界を再監査する。

改訂案の旧費目ベース総量は、2通信路でT476224 B、S394304 B。これは予約を足した設計台帳の値であり、実リンクでの空きheapではない。7 KB程度の下位静的余白はRF driverや追加IRAMで容易に消費される。現probeにはRF/PHY、実GDMA、RF処理の両core stack、最適化FFTのhot IRAMが入っていないため、**完全なfirmwareが収まったとは判定しない**。T/S共存firmwareではモード間の確保/解放と所有権も実装する必要がある。

## FFTと通信の検証範囲

`s3_fft_tiles.c` は機能基準となるscalar C実装。bit-reversalは小さいindexだけが交換対を所有し、各段のbutterfly tileは重ならない。2 host threadが異なる順序でtileを実行し、段ごとにbarrierを置いた。逐次版とのbit一致、NumPy FFT/Nとの比較、C未定義動作sanitizerを実行した。[host CI](https://github.com/kazuki0824/tangviterbi/actions/runs/37885216817)と `s3-fft-tiles.json` を参照。

FFTの各段の1/2 scalingはQ15 FFTの数値仕様であり、転送量を減らすための追加処理ではない。64蝶形演算/tileのコードがS3で2 us以内に終わるという保証はない。既存SIMDベンチマークをこのscalar実装へ流用せず、SIMD化、barrier/RF監視を含むWCETを別途求める。

`s3_stream_schedule.py` はRF 40 MB/sを連続発生させ、FFT完了後は先行RF transaction終了を待ってFFTを優先する。FFT返送は32768 Bを9 transaction、432.1 us。解析上のslot解放上限は500+53.65+432.1=985.75 usで、1039.5 us周期に対して53.75 us余る。6開始位相の試験最大は985.70 us、queue最大25445 B。以前の21376 Bの概算は送信開始前の蓄積を十分に含めていなかった。

FFT 600 usでは256 symbol中115回、gap 10 usでは108回のslot期限違反を検出した。後者はqueueも超過した。正常条件だけを通すテストにしない。これらはCPU/RF bank解放/Quad入力/内部SRAM arbitrationを統合した最悪時証明ではなく、固定サービス契約下のシミュレーションである。

## 分担と通信経路

分担は初期案の2種類を維持する。TはSoCがRF制御・無損失20-bit梱包・FFT、FPGAがFIR/同期/GI除去/等化/デマップ/デインタリーブ/FEC/TS。SはSoCがRF制御・無損失梱包、FPGAが残りの復調/FEC/TS。RSは両モードとも規格修正版を前提とする。

主配線もSPI2 Octal80＋SPI3 Quad80を維持する。4092 B payload、16 B header、24 command clocks、2 us gapで実効76.272134/38.971429 MB/s。T主割当は下りRF40＋FFT31.522848をOctal、上りIQ31.522848をQuadとし、余裕は4.749287/7.448581 MB/s。Sは下り100 MB/sを66.183423/33.816577へ分散し、余裕10.088712/5.154851 MB/s。制御は別の低速線、TSはFPGAから共通4線へ出す。

容量内の全port subsetは、同じ13 port profile/同じ2分担に対して再列挙する。帯域・半二重方向・GPIO本数・FPGA予算・SRAM予算を同時に満たすものだけを容量候補とし、物理pin/CDC/firmware実証のないものを受信機採用とはしない。

改訂版ではTの上りも8192点/1039.5 us＝31.522848 MB/sに統一した。旧32.507937 MB/sはガード区間込み8448点の値であり、新しい32768 B slotとは一致しない。FFT入力/出力の数値精度や全bin転送は維持する。

| 主配線の予算 | T | S | 容量・意味 |
|---|---:|---:|---|
| 論理相当 | 8344（96.574%） | 8144（94.259%） | 8640、FEC以外は段別推定 |
| FF | 6306（97.315%） | 5730（88.426%） | 6480 |
| BSRAM | 16（61.538%） | 25（96.154%） | 26 |
| DSP18 | 14（70%） | 15（75%） | 20 |
| SoC設計台帳 | 476224 B | 394304 B | 512 KiB総量との比較。実heap余白ではない |
| CPU設計値 | 424.554 Mcycles/s（88.449%） | 373.325 Mcycles/s（77.776%） | 2×240 MHz、実測WCETではない |
| モジュール信号 / FPGA header信号 | 19 / 22 | 19 / 22 | 制御・再構成 / TSを含む本数、実pin配置は未検証 |

| 方式・主経路 | 使用帯域 MB/s | 実効容量 MB/s | 余裕 MB/s（容量比） | 4092 Bごとの追加gap許容 |
|---|---:|---:|---:|---:|
| T・Octal下り：RF＋FFT | 71.522848 | 76.272134 | 4.749287（6.227%） | 3.562487 us |
| T・Quad上り：GI除去後IQ | 31.522848 | 38.971429 | 7.448581（19.113%） | 24.810608 us |
| S・Octal下り：RF分割 | 66.183423 | 76.272134 | 10.088712（13.227%） | 8.178171 us |
| S・Quad下り：RF分割 | 33.816577 | 38.971429 | 5.154851（13.227%） | 16.005741 us |

帯域表のgapは容量モデル上の平均到着間隔との差。TのFFT burstについては前節のeventモデルを別に適用した。T主配線は方向を固定し、他のport subsetでは平均帯域の線形計画から1個の割当例を保存する。すべての連続的な分配比やclock周波数を列挙したという意味ではない。

再列挙の結果は **T45組（包含最小15組）、S5組（包含最小5組）**。Tの追加候補には4通信路構成も含む。2/3通信路の最小link probeのみを実行済みで、4通信路firmwareのリンク合格は主張しない。

全50組について上下方向、半二重リンクの合算負荷、flow保存、帯域差、gap差、資源上限、GPIO本数、包含最小判定を生成処理とは別の計算で検算した。全候補の分担、転送format、stage期限、port別割当・余裕、資源量は [JSON](s3-receiver-routes-offline.json)、表形式は [CSV](s3-receiver-routes-offline.csv) に保存した。

これらは条件付き容量候補である。TはFFが残り174個、SはBSRAMが残り1個の推定であり、未実装blockの増分を吸収できる保証はない。全候補の `receiver_adopted` は **false** を維持する。

再生成：

```sh
python3 experiments/s3_receiver_budget.py \
  --fec reports/s3-area/isdb-predecode4-99.json \
  --output reports/s3-receiver-routes-offline.json \
  --csv reports/s3-receiver-routes-offline.csv
python3 -m unittest discover -s tests -p 'test_s3_fft_tiles.py' -v
python3 -m unittest discover -s tests -p 'test_s3_stream_schedule.py' -v
```

FFTとstreamの計4 unittestはローカルで再実行し合格。RSの生成・独立vector・制御期限・合成・配置配線は上記CIと `ci/s3_area_benchmark.py` で再現できる。既存[FPGA workflow](https://github.com/kazuki0824/tangviterbi/actions/runs/37888374253)でも26 unittestが完走し、1件skipを伴う成功を確認した（NumPy依存FFTは専用host CIで別途成功）。同workflowは既存9k CADの6条件でゲート失敗が残り、例としてmem-32acs-rsconstは110 MHz要求に対し105.41 MHz。PR全体がgreenという意味ではない。

## 残る作業

| 実機なしで進められる作業 | 実機が必要な最終確認 |
|---|---|
| SIMD FFTへの置換、tile scheduler、zero-copy DMA/packet再結合、RF firmwareとの統合と全link map | RF取得と両core/内部SRAM/GDMAを併走させた500 us WCET、2 us gap、bank ownership |
| T/S復調・TMCC・同期・TC8PSK・interleaver・FECの独立vector拡充と全RTL統合 | RF入力のC/N・周波数偏差・マルチパス耐性、TS連続性 |
| 実PSRAM PHY、全clock/CDC、実pin CST、全受信機合成・P&R | 80 MHz信号品質、PSRAM連続帯域、電源/clock余裕 |
| 基板外付けSPI NORのimage配置・boot/復旧・切替制御、容量検査 | 書込み/再構成/復旧試験とT/S切替停止時間 |

実機がないことだけが残課題ではない。今回閉じたのはRSの局所的な機能/期限と、最小SRAM配置・FFT所有権の検証である。完全な受信機の成立条件は引き続き未達。
