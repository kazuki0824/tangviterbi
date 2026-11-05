# ② worker応答時間とbank解放の条件付き検算

2026-10-26。局所poll間隔・settling予算を、公開されたbankの処理順序とDONE/collectへ接続する。runtime sourceは変更しない。①は変更せず、性能合格・正式割当・採用は0。

## 古いjobの数をnative経路と単独APIで分ける

packingはREADY jobのうち最も小さいsequenceを選ぶ。bank index順ではない。単独packing APIでは最大3 bankがownedになれるため、対象bankより古いものを2個とする保守的な条件を計算できる。

一方、現在のnative adapterだけがbankを公開する正常経路では、受理時点の古いowned bankは最大1個である。

1. 起動時は全bankがunowned。
2. 次のRF書込み先はavailable/reclaim成功後にのみ準備・SELECTされる。
3. そのbankをnative以外は公開せず、settling完了で公開するのは書込みを終えた別のbank。
4. よってRF書込み中の1 bankはunownedのまま。3 bank中、受理後にownedになれるのは最大2 bank。

実native＋packingのT/S・4時計条件・worker停止条件の既存試験へ、書込み先unownedとcount≤2の検査を追加した。単独packing APIではindex順と異なる2→0→1のsequenceで最大bank3個を投入し、各worker24 sliceの処理順序と全107640 byteの一致を確認した。この3 bank試験を、nativeの通常到着列として扱わない。

## worker単体の応答時間

512 pair/sliceの参照条件では最大bankが8 slice。qは古いbank数で、native正常経路は0または1、q=2は単独APIのstress条件である。

- C：通常1反復全体のelapsed上限。core0は通常poll、packing、collect、両SPI API、通常feed判定を含む。core1はpackingとfeed判定。IRQやメモリ競合は、Cに含めるか下記の追加費用へ分離する。
- A：設定するslice_bound。実処理時間だけでなく、slice開始前のadmission条件を満たす必要があるため、1 sliceの課金にはmax(C,A)を使う。
- J：switch_earliestから当該workerへの公開までの上限。acceptから時計を始めない。
- E：当該workerの校正誤差。sampled_slice＋E≤A、E<Aも別途検査する。

基礎応答時間は `C + (q+1)×8×max(C,A)`。先頭Cは公開が反復途中に来た場合の残りを覆う。古いjobは残量を丸ごと最大bankとして課金するため保守的である。

追加の準備・settlement・watchdog reset・IRQ等を、任意の長さRの区間に `burst + floor(R/period)` 回まで、1回cost以下という検証済み包絡で与える。Rを「基礎応答時間＋追加費用」で単調反復し、固定点または期限予算超過まで計算する。恣意的な反復回数・秒数で打ち切らない。整数cycle列が増加し続ければ、期限から導いた有限horizonを越える。

開始済みの追加処理の残りと、その直後の新しい到来を数える必要がある。carry-inを除外した平均頻度や、根拠なしのburst=1は使えない。Cと追加費用の重複計上も避ける。数値の入力自体は証拠ではない。

workerのhorizonは `native deadline offset − J − E − 1 cycle`。最後の1 cycleはdeadline到達時の拒否条件を表す。上限が収まらない場合は「この上限では閉じない」であって、実際の期限違反や候補全体の不可能性とはしない。

## 両workerのDONEとcollectを分ける

両DONEの時刻上限は `max(J0+R0, J1+R1)`。peerのDONEがcollectの確認直後なら次のcollectまで待つ。解放遅延には通常反復2個分＋追加処理包絡を保守的に課金する。反復全体の最大時間だけから、異なる反復の末尾＋先頭も必ず1個分に収まるとは仮定しない。

bank_responseへはswitch_earliest基準のreclaim予算を別途渡す。worker deadlineを無根拠にreclaim予算へ流用しない。reclaim予算が未証明なら、両workerの局所応答が計算できてもbank全体の判定はunproved。

## 保存した結果と検証範囲

response-envelope.jsonはT/S、worker0/1、q=0/1/2の12条件を保存。未取得のC/A/J/E・追加処理包絡をnullのまま扱い、全条件unproved。q=2には単独API stressというラベルを付けた。新たな性能合格は出していない。

18 unittest成功（tests.log）。独立した整数時刻の優先実行simulationを使い、2種の周期干渉の全35位相×4 carry条件を包絡が覆うことを確認。数値は試験用で実SoCの時間見積もりではない。admission予算、deadline厳密境界、DONE後のcollect待ち、未知項、実native/packing/SPIの既存試験も含む。

残る証拠は、通常反復・追加処理の実elapsed上限と到来包絡、J/E、reclaim予算の具体値。さらに通常INDEX/settling条件、4出力arena・SPI完了順序/持続帯域、全起動メモリ、RF設定/指令、全FPGA fit/STAが必要。この応答式だけを受信機全体の成立判定にはしない。

再現:
```sh
python -m experiments.s3_worker_response --output build/response-envelope.json
PYTHONPATH=tests python -m unittest test_s3_worker_response test_s3_settling_limits test_s3_task_gap_limits test_s3_raw_schedule_limits test_s3_parallel_pack -v
```

追補: [reclaim期限の導出](../s3-reclaim-deadline/README.md)で、明示的な条件付きnativeモデルを追加した。未指定時のunprovedは維持する。実RFモデルを検証済みとする変更ではない。
