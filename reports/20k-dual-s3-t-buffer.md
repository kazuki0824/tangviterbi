# T入力1 symbol保持と時間deinterleave RAM削減

第1項目のT上流有限保持を実RTLへ移した変更です。第1項目全体の完了ではなく、共有RS接続（第2項目）には進んでいません。

## 実装

- plan ROMを80から34 bitに縮小。carrier番号、active layer mask、lengthを保持し、`span=delay×length`と32-byte整列spanの累積からbaseを生成します。既存META周期で計算し、空groupはbaseを進めません。各symbolでBASEへ戻します。
- Mode 3のin-place symbol RAMは29952 byte。2つの16-bit pair bankとし、各bankを7×1024 wordsのBSRAM＋320 wordsのdistributed RAMへ分割します。BSRAM14個＋末尾1280 byteです。4-byte入出力／2-byte交換、LLR精度は維持します。
- `dual_t_buffered_time_dma`に別の1 symbol RAMを実装。最後の入力wordでcommitし、childが最後のwordを受けるまで再利用しません。満杯ならstartを拒否し、処理中に次symbolを保持できます。最終drainはchildがreadyになるまで保持します。
- `dual_fft_stream_ts_memory`へ接続。仲裁は既存round-robinを維持します。T/S優先やcapture優先への変更は今回の最終RTLに含めません。

## 期限の変更と成立条件

旧構成の「解放から1周期P以内に計算終了」という条件を、位相0だけの結果で全位相へ拡張できません。旧構成の半周期反例は旧条件の不合格として保持します。

新構成では入力保持を**実RAM**として追加しています。計算期限の数値だけを緩めず、以下を同時に判定します。

1. sourceが周期Pで1 symbolを解放し、4 bytes/memory clockで入力する。
2. start待ち・word待ちがともに0、各symbolを次の解放までに受け切る。解放済み未captureは最大1 symbol。
3. Tの計算・出力はそれぞれ解放から2P以内。既存in-place交換により前symbolの出力は次symbolをchildへ渡すときに進む。
4. FFT capture待ち0、FFT出力はscheduled window終了から2P以内。
5. S sourceの待ちは最大1 byte、S出力は二面再使用期限以内。

入力RAMの容量・所有権はRTLが強制し、試験器側で待ちが生じれば判定を落とします。source自体は固定burstの独立LLR列であり、FFT→等化／demapperの実接続ではありません。実demapperの到着形状は別途保証が必要です。

## 確定ソースの結果

| Mode | T開始位相 ns | frames | T計算最大 µs | T計算期限 µs | FFT出力最大 µs | FFT出力期限 µs |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 48 | 278.681753 | 519.750 | 325.149828 | 519.750 |
| 1 | 129937 | 48 | 312.574396 | 519.750 | 346.292953 | 519.750 |
| 1 | 194906 | 48 | 306.672067 | 519.750 | 337.805301 | 519.750 |
| 1 | 64968 | 48 | 355.750802 | 519.750 | 349.374435 | 519.750 |
| 2 | 0 | 24 | 412.178060 | 1039.500 | 531.111403 | 1039.500 |
| 3 | 0 | 12 | 650.203922 | 2079.000 | 1018.778109 | 2079.000 |

6条件・計228 FFT frames／589824 bins、T 2156544 bytes、S 6 super-framesで全データ一致。全条件でFFT capture待ち、T start/word待ち、T入力capture期限違反、T計算／出力期限違反は0。T未capture最大1 symbol、S待ち最大1 byte。S最大20.100354 ms < 二面再使用期限21.608316 ms。

旧HEAD `ec68b96`のT開始位相だけを129937 nsへ変更した反例を再実行しました。計算最大301.833654 µs > 1P=259.875 µsで27/48回の計算期限違反、capture待ち0でした。結果とhash対応ソースは[baseline-half](20k-dual-s3/t-buffer/baseline-half.json)／[snapshot](20k-dual-s3/t-buffer/baseline-half-sources.tar.gz)。新旧は保持回路と期限契約が異なるため、旧1P条件への合格を主張しません。

[各条件のJSON・ログ・source manifest](20k-dual-s3/t-buffer/source-sha256.json)を保存。CIには半周期の有限契約判定を追加しました。

単体試験は独立carrier履歴との全byte比較、I=0、Mode 3 I=1の履歴一巡、入出力・応答停止を含みます。buffer付き試験はchildのin-place境界で上書き前の旧byte出力と転送byteを確認し、child処理中の次symbol captureが実際に発生したことも検査します。

## 部分合成

| Mode | LUT＋ALU | FF | BSRAM /46 | DSP18 /48 | RAM16SDP4 | LUTRAM込みlogic /20736 |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 10857 | 5276 | 20 (43.48%) | 12 (25.00%) | 80 | 11177 (53.90%) |
| 3 | 12076 | 5537 | 42 (91.30%) | 11 (22.92%) | 240 | 13036 (62.87%) |

Mode 3へ共有RSの2 BSRAMを単純加算すると44/46、残り2です。同期・等化・demapper・TMCC・queueを含む全体収容は未確認です。[合成記録](20k-dual-s3/t-buffer/synthesis/summary.json)のsource hashを作業ソースと照合しました。

刺激・観測回路を含む固定profileの部分topです。上流保持RAMは合成値に含まれ、別途16 BSRAMを再加算しません。RAM16SDP4はlibrary cost=4でlogicへ換算します。合法配置・pin fit・全体STAの合格値ではありません。

## 再現と証拠

```sh
DUAL_T_TIME_REPORT=build/t-unit.json python -m unittest discover -s tests -p test_dual_t_time_dma.py -v
python -m unittest discover -s tests -p test_dual_t_buffered_time_dma.py -v
DUAL_FRAME_TS_MODES=11 DUAL_FRAME_T_PHASE_NS=129937 DUAL_FRAME_TS_REPORT=build/t-half.json python -m unittest discover -s tests -p test_dual_frame_ts.py -v
python ci/dual_memory_clients_evidence.py --yosys /path/to/oss-cad-suite/bin/yosys --components stream_ts1,stream_ts3 --output build/t-synth
```

Icarus 11.0、OSS CAD Suite 2026-10-04を使用。合成toolchain archive SHA256は`8a4708629b0f0afd5a1835aca8b44d224fec5f6e544c5fd22a060ea5514f83c9`。計算clockはcore162／memory135 MHzを仮定します。全phase／長期安定性／STAを有限simulationから保証しません。

作業中に実行環境が切り替わり未Pushのログを失ったため、公開証拠は復元した確定ソースでの再実行分です。失われた優先度変更案のログは証拠として掲載しません。

## 残件の範囲

T上流1 symbol保持をRTLへ移した点は進展です。残る第1項目はRF同期・等化／demapper接続、動的TMCCとS slot制御、全体資源の精算、全位相と実到着／下流サービス条件の保証です。全受信topの配置配線・全経路STA、共有RS接続、S3 firmware／実WCET、RF品質・連続TSの実機検証も未完了です。これらを新規追加した残件とは扱わず、既存の未完了範囲として維持します。
