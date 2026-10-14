# 固定小数点FFT・SDRAMの実装と部分配置配線

**本報告はd752002時点の部品実装の履歴。後続の[FFT―SDRAM結合](20k-dual-s3-fft-memory.md)で、ここで未実装としたFFTのDMA・所有権FSM・仲裁・CDCを接続した。以下の部分面積・未結合の説明を現在の全体実装状態と読み替えない。**

2026-10-14。継続対象は20K×1＋S3×2の同時T/S受信。**部品RTLの機能試験を進めたが、全受信機の性能合格・通信正式割当・採用は引き続き0件。** 以下は現在の実装の測定範囲を示す。通信都合のSoC追加decimation/requantizationは導入していない。

## 1. 実装した範囲

| 部品 | 実装内容 | 検証と残る接続 |
|---|---|---|
| `dual_fft_tile.sv` | 2×4 KiB、32/64/128点、最大16 lanesのin-place radix-2 DIT。計算bankと別bankへのDMAを並行可能 | 2 clocks/butterfly、bit reversal、bank交替を確認。load/readは同一DMA portを共有し同時実行不可 |
| `dual_fft_cross.sv` | 交差twiddle、4 clocks/complex、出力backpressure | 整数参照値と一致。full-frameのDMA/所有権FSMは未接続 |
| `dual_fft_twiddle.sv` | W8192の全phase、18-bit signed Q1.16。2048×17-bit quarter ROM、端点は定数 | 全8192 phaseを独立sin/cos計算と比較。ROMは2 BSRAM |
| `dual_fft_burst_map.sv` | Mode1/2/3、両pass、load/writebackの32-byte burstアドレスとtile index | 全mode・全方向・全tile・全beatを列挙。全sampleを1回ずつ覆いaliasなし。アドレス生成器であってDMA schedulerではない |
| `dual_sdram_burst.sv` | 32-bit SDR、BL8、4-bank open-page、初期化、refresh、byte mask、burst応答保持 | 独立メモリmodelでread/write/mask/refresh/backpressureを確認。PLL、PHY、CDC、複数client仲裁は未接続 |

FFTの入出力はsigned 16-bit I/Q、各stageで1/2正規化しFFT/Nを出力する。係数は+1を正確に表せるQ1.16、丸めはnearest/ties-away、範囲外は飽和しoverflowを通知する。全binを保持する。RF native I10/Q10をソフトウェアで狭める変更ではない。受信チェーン全体のdynamic rangeとBERは別途確認する。

丸めは`(x + (x < 0 ? 2^(s-1)-1 : 2^(s-1))) >>> s`とした。負の算術右shiftのfloorを利用し、絶対値・再符号化のcarry chainを除いた。独立参照モデルは絶対値方式を保持し、単にRTL式を書き写した比較ではない。

frame baseは32-byte整列、各frameが物理容量内に収まり重ならないことを呼出側の契約とする。mapperは21-bitアドレスの末端overflowやframeの生存期間を保証しない。

## 2. FFTの機能と期限

`tests/test_dual_fft_rtl.py`は3 tests。tile単体のzero/DC/impulse/random/飽和、別bankの並行load、全phase ROMに加え、N=2048/4096/8192それぞれrandom/toneの全binを検証した。**frame間のpass制御はPython試験器**であり、独立したSDRAM controllerと結合したfull-frame RTLではない。

[fft-rtl.json](20k-dual-s3/fft-rtl.json)にsource hashと誤差を保存した。全6 frameのRTL出力は再帰型整数FFT参照とbit exact。NumPy FFT/Nに対する最大complex誤差は約2.294 LSB以下。random vectorのSNRはN=2048/4096/8192で約49.57/47.14/44.12 dB。これは有限vectorの数値誤差で、受信所要C/N、BER、全入力の精度証明ではない。8 LSBのtest閾値も放送規格の許容値ではない。

| N | butterfly＋crossの計算cycles | 162 MHz仮定 | GI1/32の周期 |
|---:|---:|---:|---:|
| 2048 | 30,720 | 189.630 µs | 259.875 µs |
| 4096 | 65,536 | 404.543 µs | 519.750 µs |
| 8192 | 139,264 | 859.654 µs | 1039.500 µs |

kernelのcyclesはRTLで確認した。full-frameの起動・DMA・ROM切替・bank所有権移行を含む最終期限ではない。162 MHz自体も全経路のSTA合格値ではない。

## 3. SDRAMの実アクセス試験

geometryは4 banks×2048 rows×256 columns×32 bits。controllerの設計入力は135 MHz、CL=3、tRCD/tRP/tWR/tMRD=3 cycles、tRFC=10 cycles、refresh間隔上限1053 cycles。初期waitは27000 cycles（135 MHzなら200 µs）、8回refresh後にCL3/BL8を設定する。**これらは実デバイスで135 MHzを保証するtiming値として認定していない。** シミュレーションでは初期waitだけ32 cyclesに短縮。

独立command monitorはACT/PRE/READ/WRITE/REFRESH、tRCD/tRP/tRAS/tWR/tRFC、DQ衝突、byte maskと応答保持を照合する。応答停止中もrefreshを継続することを試験。全traceで最大refresh gapは1042 cyclesで1053以下。

| アクセス列 | open-page | 実測cycles | 135 MHz仮定の有効帯域 |
|---|---|---:|---:|
| 同一row、read 256 bursts | off | 4,661 | 237.271 MB/s |
| 同一row、write 256 bursts | off | 4,675 | 236.560 MB/s |
| 同一row、read 256 bursts | on | 3,123 | 354.121 MB/s |
| 同一row、write 256 bursts | on | 3,123 | 354.121 MB/s |
| Mode3の6×全frameアクセス、6144 bursts | on | 79,555 | **333.632 MB/s** |
| read/write＋bankごとのrow衝突、512 bursts | on | 9,228 | **239.688 MB/s** |

Mode3列は入力write→各tileのpass1 read/write→各tileのpass2 read/write→出力read。両passはmapperと同じburst順を独立Python式で生成する。計算待ちを挟まないbacklogged requestのcontroller測定であり、FFTの実行時間や他clientの同時到着を合格にした値ではない。詳細は[sdram-rtl.json](20k-dual-s3/sdram-rtl.json)。

**同一rowだけの354 MB/sをもって、共有busに65%＝351 MB/sを一律付与してはいけない。** FFT順では61.784%、row衝突列では44.387%まで落ちる。既存の平均需要271.266 MB/sを上回るtraceがあることも期限証明にはならない。各FIFOの最長grant間隔を含む実arbiter、frame配置、双方向turnaroundを結合して再検証する。現controllerを65%一定モデルへ代入して合格とすることを禁止する。

## 4. 部分配置配線とタイミング解析の限界

固定版OSS CAD Suite 2026-10-04、nextpnr `e2fe86b3`、GW2AR-LV18QN88C8/I7・GW2A-18C、seed=1で再現。各部品に256-bit刺激registerと観測回路を付けた合成topを配置配線した。**刺激回路の費用も含み、全受信機や部品単体の厳密な最小面積ではない。** logic位置は配置後LUT4+ALU（FF用pass-throughを含む）として数える。

| 部分top | logic位置 | FF | BSRAM | DSP18 | 指定MHz | 表示MHz（不完全STA） | exit |
|---|---:|---:|---:|---:|---:|---:|---:|
| fft | 2,344 | 529 | 6 | 8 | 162 | 216.685 | 0 |
| rs | 2,786 | 1,311 | 2 | 0 | 162 | 157.431 | 1 |
| sdram | 1,515 | 866 | 0 | 0 | 135 | 272.109 | 0 |


[機械結果とsource hash](20k-dual-s3/components/summary.json)、各合成・P&R log、report、topを同directoryにgzipで保存した。clock入力は内部domain目標を表した試験条件であり、実基板の27 MHz oscillatorを162/135 MHzへ変換するPLL回路・SDRAM IO制約を実装したものではない。

さらに、使用した[固定版nextpnr timing生成source](https://github.com/YosysHQ/nextpnr/blob/e2fe86b3/himbaechel/uarch/gowin/gowin_arch_gen.py)と付属GW2A-18C databaseを確認すると、次の欠落がある。

- DSP/MULTのtiming groupがなく、BRAM→複素乗算→BRAMを表示Fmaxで網羅できない。
- DP RAM port Bのoutput arcが`DOB`でなく`DO`になっている。また`ADB`のinput timingが`dp`ではなく`sp`に追加されている。

したがって部分P&Rの正常終了や表示Fmaxが高くても、全domain STA合格ではない。RSは欠落のある解析でも162 MHz目標を下回り、nextpnrが非ゼロ終了した。失敗を削除して合格扱いにせず、logとexit codeを保存した。`gw_sh`はこの環境に無く、vendor STAまたは検証済みの完全なtiming modelによる確認が必要。存在しないDSP遅延値を仮定してデータベースを修正することはしていない。

## 5. 資源予算と次の順序

FFT allocationを旧1400から2500 logic、共有RSを2700から3000 logicへ見直した。全mode可変のFFT＋mapper＋刺激回路は2344 logicを使用する。以下は未実装の接続回路も既存枠に入るという未検証の設計予算であり、増額して成立を認定したものではない。

| 案 | logic allocation | 占有率 /20736 | BSRAM | 状態 |
|---|---:|---:|---:|---|
| A | 22,252 | 107.31% | 47/46 | 容量超過 |
| B | 20,452 | 98.63% | 44/46 | 全体性能未確認 |
| C | 18,952 | 91.40% | 56/46 | 容量超過 |
| D | 18,452 | 88.99% | 40/46 | 全体性能未確認 |

案Bのlogic残は284位置（1.37%）しかなく、配置配線や未接続制御の余裕を確認済みとは呼べない。

以上はallocationの更新であり、全体合成で得た占有率ではない。FFTはDMA/所有権FSMが未実装、I/O/controlの3000 logic枠のうちSDRAM controller試験topだけで1515を使う。残りのCDC・仲裁・RF input・TS・TMCC等が収まることは未証明。BSRAM予算は44/46のまま維持し、部分FFTの6 BSRAMを根拠なく全体の空きに戻さない。

進める順序は次のとおり。pin/clock制約は全体接続より前に固める。S3 firmwareの実装・静的容量確認はFPGA作業と独立して進められる。

1. FFTのDMA/所有権FSM、SDRAM arbiter、実際のframe配置を結合。全modeのcycle simulationで計算・refresh・他client競合込みの期限とqueue容量を確認。
2. 共有RSの入力queue・DMA・出力FIFOを接続し、162 MHz未達を解消するか、clock変更に対してFFT/RS/queue期限を再計算。
3. 完成基板のpin/clock/搭載負荷を反映した全受信topを接続し、全体の合成・配置配線・全経路STAを行う。
4. S3-T/S専用firmware、実driver、packing、bank管理を結合し、内部RAM/Flash配置を確認。実機で最悪実行時間を測定する。
5. RF品質、連続TS、2系統同時転送、温度・電源条件を実機確認し、性能を通った案に通信路を正式割当、非ゼロ経路の案を採用する。

まだこの環境で実装可能な接続・firmware作業も残る。「残りは配置配線と実機測定だけ」ではない。現段階で採用0を維持するのは、未実装・不合格の条件を残したためであり、20K構成の不可能性を証明した意味ではない。

## 6. 再現

```sh
# Python + numpy、Icarus Verilogを用意
DUAL_FFT_REPORT=build/fft-rtl.json python -m unittest discover -s tests -p test_dual_fft_rtl.py -v
python -m unittest discover -s tests -p test_dual_fft_burst_map.py -v
DUAL_SDRAM_REPORT=build/sdram-rtl.json python -m unittest discover -s tests -p test_dual_sdram.py -v
python -m unittest discover -s tests -p test_dual_s3_20k_estimate.py -v
python experiments/dual_s3_20k_estimate.py --output build/20k-dual-s3
# 固定版OSS CAD Suiteの実行ファイルを指定
python ci/dual_fft_memory_evidence.py --yosys /path/to/oss-cad-suite/bin/yosys --nextpnr /path/to/oss-cad-suite/bin/nextpnr-himbaechel --output build/components
```

CIにも追加した。component-placement jobは測定記録用であり、タイミング失敗をJSONに保存する。jobの成功は受信機性能合格を意味しない。今回、変更のない3144-codeword共有RS機能試験は再実行せず、前回証拠を維持した。変更部品の新規5 testsと見積もり7 testsを実行した。

一次資料：

- [Gowin GW2AR DS226E](https://cdn.gowinsemi.com.cn/DS226E.pdf)：SDRAM geometry。
- [Gowin SDRAM Controller IP User Guide](https://www.gowinsemi.com/upload/database_doc/281/document/5d280116bebab.pdf)：CL/BL、初期化、timing parameterの構成。manualのdefault clockは10 nsであり、135 MHz動作保証への読み替えはしない。
- [Sipeed TangNano-20K examples](https://github.com/sipeed/TangNano-20K-example)：完成基板向け実装の参照入口。
- [OSS CAD Suite固定release](https://github.com/YosysHQ/oss-cad-suite-build/releases/tag/2026-10-04)：archive SHA256 `8a4708629b0f0afd5a1835aca8b44d224fec5f6e544c5fd22a060ea5514f83c9`。CIはhash検査後に利用する。
