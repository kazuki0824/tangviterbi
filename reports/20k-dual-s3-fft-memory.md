# FFT―SDRAM結合：DMA・所有権・仲裁・期限

2026-10-14。今回の対象は残作業の先頭「FFTとSDRAMのDMA・バッファ所有権管理・仲裁の接続、競合込みの期限検証」だけ。共有RS改修、受信top全体の配置配線、S3 firmwareには着手していない。

## 実装した接続

- `dual_fft_dma.sv`が全frameの両passを自律実行する。Mode1/2/3の入力・中間・出力frameは互いに重ならない32-byte整列領域とし、物理容量を超える指定も拒否する。途中のtile/pass指示をPythonから供給しない。
- bankをFREE→LOADING→READY→COMPUTE→STORING→FREEとして管理する。最後のwrite応答を受けるまでFREEに戻さず、全tileの書き戻し後に次passへ移る。別bankの演算とDMAを並行させる。
- load中に次burstを先読みし、write応答待ち中に次burstの出力を組み立てる。入力1burstを保持するregisterとCDC mailboxの保持領域を使い、FFTのsample数やbit幅を削らない。
- 交差twiddleは4 clocks/wordで連続処理し、第2passの書き戻し用読み出しは1 word/clockで進める。演算と別bankの交差twiddleを並行させるため係数ROMを2組にする。tile RAM4＋係数ROM4＝8 BSRAM相当の構成で、旧8 BSRAM枠の余白を使用する。**新しい結合回路の合成占有率は未測定**。
- `dual_burst_cdc.sv`が162 MHz側と135 MHz側を、payloadを保持する1 outstandingのtoggle mailboxで接続する。制御toggleを2段同期し、応答消費まで要求payloadを変更しない。
- `dual_burst_arbiter.sv`がFFTと背景clientをburst単位round-robinで仲裁する。各client専用の応答保持slotを持ち、止まったconsumerの応答を上書きしない。controllerが受理できれば即座に要求を渡し、受理できなければpayloadを保持する。応答完了と別clientの次要求を同じedgeで扱える。
- `dual_fft_memory.sv`が上記と既存SDRAM controllerを接続する。SDRAM read/write/refreshは実controllerのpin commandとして試験する。

## 試験契約

`tests/test_dual_fft_memory.py`は入力と独立整数FFTの期待値だけを用意する。SDRAMのpin側にはcontrollerから独立したメモリ・timing checkerを接続した。基本検証器は既存`test_dual_sdram.py`を再利用する。

各modeで4条件を試す：競合なし、周期的な背景read/write、bank内row衝突、32 bursts単位の背景到着＋consumerの300 memory clocks停止。競合条件の長期要求量は、従来期限模型のcapture/output・T/S memory・管理reserveと同じ145.174484 MB/s。32-byte requestの到着間隔220.424409 ns（batch条件は32倍）で生成する。RFやLLR実処理の代わりに同量の合成トラフィックを使うため、実受信機の全client到着形状を網羅した証明ではない。

core/memory clocksは162/135 MHz、clock開始phaseは条件に応じ0/2/5 ns。SDRAM初期待ちのみ32 clocksへ短縮し、refresh・row操作・turnaroundは実controllerを使用する。入力frameを開始前にcommitする責任、出力を再利用前に消費する責任は外部producer/consumer側に残る。

同一modeで異なる入力の2 frameをGI1/32周期で投入し、その間も背景トラフィックを停止しない。次frameの解放時刻を基準に完了時間を測定するため、前frameの遅れがあれば期限判定へ引き継ぐ。3 modes×4条件×2 frames＝24 frame全てで全binが独立整数FFTと一致し、全24 frameの`deadline_pass`がtrueとなった。

| N | 周期 µs | 最悪完了 µs | 最小余裕 µs | 背景最大滞留 bytes | 最大grant待ち memory clocks |
|---:|---:|---:|---:|---:|---:|
| 2048 | 259.875 | 243.352 | 16.523 | 1632 | 326 |
| 4096 | 519.750 | 490.401 | 29.349 | 2880 | 324 |
| 8192 | 1039.500 | 973.191 | 66.309 | 5376 | 324 |

最大refresh gapは1047 memory clocksで上限1053以下。背景の最大滞留5376 bytesは未応答分を含む試験器上のqueue量であり、4 KiB FIFOでは不足する条件がある。実clientへ分けたFIFO容量の保証ではなく、実client結合時に満たす必要のある測定結果として扱う。grant待ちにはconsumer停止中にそのclient自身が待つ時間も含む。

[全24結果・source SHA256](20k-dual-s3/fft-memory-rtl.json)を保存した。最大完了値は試験した条件内の値であり、全phase・全arrival形状のWCET上限ではない。

検査内容：全mode・全binのbit exact比較、frame境界のsentinel、read/write burst数、bank所有権衝突、別bank演算との並行、重複frame指定の拒否、背景clientのreadデータ／write応答、停止中の応答保持、refresh間隔とSDRAM timing。

crossと別bankのFFTを同時実行するため、前段の「tileのFFT＋crossを一つのcompute slotに直列配置する」模型ともscheduleが異なる。追加した2 BSRAMの係数読み出しポートでこの重畳を可能にした。

初期の直列転送では、無競合でも期限を超えた。先読み／write待ちとの重畳、連続tile読み出し、仲裁の空きclock削減を行った最終RTLの結果だけを採否判定に用いる。単体controllerの354 MB/sや一定効率65%を結合回路へ与えてはいない。

## この結果で完了した範囲と限界

今回、**全frameのDMA・bank所有権・2-client仲裁・clock間転送をRTLで接続し、有限の競合条件について期限を測定するところまで**進めた。前回「Pythonによるpass制御」「DMA FSM未実装」としていた部分は置き換わった。

これで全受信機の採用条件を満たしたとはしない。

- 次項目の共有RS接続・162 MHz修正は未着手。
- 全体配置配線・物理CDC制約・reset解除・SDRAM PHY/IO timing・全domain STAは別途必要。simulatorの162/135 MHzは達成Fmaxではない。bundled-data pathにはtoggleが届く前にpayloadが安定する実装制約が必要で、独立した片側resetは許さない。
- background clientは合成トラフィック。待ち行列の最大量を記録するが、実T/S FIFO・interleave address・全到着phaseへの保証ではない。背景queueは試験器上にあり、そのFIFOをRTL化したとは主張しない。
- 新規DMA・CDC・arbiter・ROM追加を含む全体資源をまだ合成していない。旧98.63%は旧allocationの数値で、今回の接続回路が収まった測定値ではない。

性能を通った分担への正式通信割当・採用は引き続き0。残作業の先頭が「接続未実装」から「接続済み、記載条件のデジタル検証済み」へ進んだことと、実機を含む全体成立を区別する。

## 再現

```sh
# Icarus Verilog 12.0、Python 3、numpyを用意
mkdir -p build
DUAL_FFT_MEMORY_REPORT=build/dual-fft-memory-rtl.json \
  python -m unittest discover -s tests -p test_dual_fft_memory.py -v
```

CIの既存`test_dual_*.py`に含め、結果JSONもartifactへ保存する。testの成功は機能比較・protocol検査の成功で、期限判定はJSONの`deadline_pass`を別に確認する。
