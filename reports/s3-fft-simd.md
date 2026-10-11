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
