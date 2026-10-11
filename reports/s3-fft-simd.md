# 8192点S3 SIMD FFTへの置換と残る期限

2026-10-11。期限に不合格の現在のスカラーFFTに代わる実装として、
Espressif ESP-DSP v1.7.1、commit `fd110921fb57b4de79f092337b9e047130762eca`
のsc16 S3アセンブリを固定した。原本・Apache-2.0ライセンス・hashを保存。
build時にsymbol名とIRAM sectionを変え、8192点の固定係数表、出力bit reversal、
cycle-count計測入口を追加した。S3 target objectとしてSIMD命令を含み、未解決symbolなしで結合できる。
まだ実機でSIMDを実行した証拠ではない。

入力32768 B×2面、係数16384 B。quarter scalar表4098 Bとの差は12286 B。
全8192 complex bins Q15を転送する。ソフト間引き・帯域削減用再量子化は行わない。
係数のscale/丸めは公式sc16契約であり、旧scalarのties-away契約とbit同値とは主張しない。
定数表のflash原本を内部SRAMへコピーして使う設計をSDK link profileに追加した。
実行入口はcore1・internal data/tableを要求し、FFT/reorder中だけそのcoreのinterruptをmaskする。
core0のRF pollingを継続し、高優先度/NMIではPIEを使わないことを全systemで確認する必要がある。

host試験は**公式ANSI実装**へ同じ係数・8192点・後処理を渡した。
zero/DC/impulse/tone/noiseの全binをNumPy FFT/8192と比較し、最大誤差1.654 complex LSB未満。
これは係数順序と後処理の試験で、S3 SIMD実行、ANSIとのbit同値、受信品質の保証ではない。
pointerのnull/misalignment/overlapもkernel実行前に拒否した。

公式1024点の15623 cyclesからのNlogN外挿162479.2 cyclesは**実測・WCETではない**。
1 core @240 MHzなら677.0 µs相当、reorder/RF/DMA/stall/IRQ費用は追加。
旧T通信モデルの500 µs・2coreを置き換えて合格とすることはできない。
2coreを500 µs連続停止する政策はRF bank期限にも不合格だった。
短いSIMD tileとcapture pollを結ぶスケジュール、全frame入力・返送・buffer再使用を
含む同時deadline評価を次の検証にする。

再現：`python ci/s3_fft_simd_evidence.py --cc xtensa-esp32s3-elf-gcc`。
[コンパイラ・source/object hash・disassembly・host結果](s3-fft-simd-evidence/results.json)。
SDK workflowの`native-direct-phy-simd`はfull係数SRAMを含むlink/startup診断を行う。
現時点の`SDK_ELF_link_verified=false`、`CPU_WCET_verified=false`、`receiver_adopted=false`を維持する。

## 短いSIMD stage tile（2026-10-11追記）

公式アセンブリの3種類のvector butterfly loopを短い呼出しへ分割した。
13 stage × 1024 block、1 block＝4 butterfly、1回最大16 block＝64 butterfly。
各coreの独立したlockで短いkernel中だけlocal interruptをmaskし、
tileの間とstage barrierの待機中にRFをpollする契約にした。
実RF/RTOS workerとbarrierへの接続、poll jitter/WCETは未完了。

8192点の全binはbit-reversed順のまま保持する。
位置iはFFT bin reverse13(i)。FPGA側でこのindex mappingを実装する必要があり、
既存通信endpointへ接続済みとはしない。入力量・通信量は削減しない。

接続断の前にtarget compileと未解決symbolなしのbundle結合、
3 unittest（range拒否、vector loop抽出、2 threadのstage同期とblock所有権）を実行し合格。
hostのrandom/extremes/zero全8192点は公式ANSI全体FFTと一致した。
これはhost ANSI arithmeticの検証で、SIMD実行や数値bit同値の証拠ではない。

実行環境のexec-server接続が切れ、復旧呼出しも回復しなかったため、
検証済みのtile sourceをGitHub接続からcommitした。raw object/log回収はできておらず、
このcommitのSDK profile追加・artifact回収変更の再実行は未確認。
target bundleの観測section値はtext2832 B、IRAM470 B＋literal20 B、rodata16384 B。
CPU cycle/WCET、受信品質、全候補判定の完了は依然として未確認。
