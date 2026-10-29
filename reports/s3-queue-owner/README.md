# ② S側：先行queueを接続した受信taskの費用・期限

2026-10-30 JST。S5/16、可逆inline packing、16KiB、SPI2 Octal＋SPI3 Quad、準備2048語/反復・1024語/poll。①は対象外。

## 実コードの接続

既存task lifecycleから [変換器](../../experiments/s3_queue_tasks_source.py) で候補C/headerを生成する。SDKとhost検査は同じ生成物を使い、SDK成果物中のソースと現在の生成物の完全一致も検査する。元の単一転送taskは変更しない。

起動検査をqueueのdevice・pack・host・未使用状態へ変更し、ownerはcount>0で回収、count<2で投入する。停止時は各port最大2件を回収するが、TIMEOUT/faultでは所有権を保持する。実装には1poll最大1024語の制限を追加し、反復合計2048語という模型の配分と揃えた。未消費語数を次のpollへ持ち越す。単に旧定数1024を2048へ変更するだけの実装は採用しない。

[SDK run 40915522463](https://github.com/kazuki0824/tangviterbi/actions/runs/40915522463) は成功。入力commit・artifact hashは [provenance](sdk/provenance.json)。これは受信taskを保持したlink probeであり、app_mainはRFを開始しない。

## 単価と重複の整理

|項目|生成コードの包絡|使用単価|範囲|
|---|---:|---:|---|
|owner制御|333命令/反復|367 cycle|7pollの制御、collect前の時計、通常feed判定、port順序・条件分岐を包含|
|うちpoll制御|23命令×7|owner内に包含|1024語上限・消費語数の差引き・stop/fault判定。native本体は別|
|worker制御|56命令/反復|62 cycle|通常feed・stop判定。packingは別|
|RF基本処理|既存179命令/poll|197 cycle|従来213cycleに含めたpollラッパ14命令を除き、ownerとの重複を解消|
|期限到来時のWDT追加|通常feedとの差分＋peer reset待ち|516 cycle|通常判定はowner/workerに含むため再加算しない|

命令数×1.1を切上げる費用模型。[命令・CFG経路・加算先](instructions.json)。SDK投入/回収・割込み、inline slice、native各状態、collect、tickの既存単価は維持し、owner追加0/100/300cycleという仮置きは使用しない。実ownerの2port forループを模型へ接続し、並べ替えた擬似ownerを使わない。

## 同じ費用での期限評価

[全条件・頻度・費用台帳](runtime.json)。追加stallなしの20000bank（6.164秒）で出力byte照合と費用保存が成立した。

|観測項目|結果|
|---|---:|
|arena最大使用|123328 / 131072 byte|
|arena最小残量|7744 byte|
|RF監視最大間隔|68.208 µs|
|job期限余裕の最小値|187.808 µs|
|owner反復 / RF poll|180215 / 1261505（7倍）|
|worker反復|1889725|
|tick|各core616回|
|WDT更新|各core2回|
|SPI IRQ：初回 / 開始 / 完了 / 連続|2 / 14447 / 14447 / 23171回|

20000bankは以前の比較と同じ観測長で、2.5秒周期のWDT更新を複数回含める。観測した最大値・最小値であり、無期限の境界値を保証するものではない。

追加stall感度は `joint_charge` の課金に0/1/2/5/10/15/20/30%を追加する。非同期IRQ/tickの直接加算部分は増やさないため、「すべての未計上処理を15%以内と確認した」という意味ではない。0〜15%の評価点は4000bank通過、20%は67bankで次の受入れ148731byteが128KiBを超過、30%は5bankでpacking期限違反。実機stall率の範囲を推定した結果ではない。

## 未確定範囲

今回閉じたのはqueue接続後の正常受信ループ制御費用と同じ費用による有限期限評価。RF-off起動/peer待ち/再選局/停止の時間、指令入力とsupervisor、register-window例外、メモリ/MMIO待ち・競合、最終task/IRQ構成は残る。生成taskの存在を完成した受信アプリとは扱わない。全SoC費用確定・実機成立認定は未完了。

再現：`python -m ci.s3_queue_owner_audit --toolchain <xtensa-esp-elf>`、`python -m experiments.s3_queue_owner_runtime`、`python -m unittest tests.test_s3_queue_tasks`。

## task・queue・RF領域をまとめたメモリ検査

[SDK run 40917626944](https://github.com/kazuki0824/tangviterbi/actions/runs/40917626944) でN16R8構成をlinkし、[配置・割当検算](memory.json)を実施した。128KiB転送領域、RF領域、2taskのstack/TCBを同じELFに保持し、ROMとの非重複と配置条件を通過。費用probeとこのELFの8関数について、再配置アドレスを除いた命令・分岐の完全一致を確認した。

queue深さ2で、既知SPI割当の下限は2port合計1584byte。その差引き後の内部メモリ容量の**上限は16820byte**。GDMA channel/group/pair、lock、interrupt handle、allocator header/alignment、PHY/calibration等は未計上なので、実際の空き容量・起動保証ではない。固定task stackは各4096byteを配置したが最大stack使用量は未確定。構成定数はCMakeと生成header、stack引数は実際のcreate_tasks命令から確認した。

再現：`python -m ci.s3_queue_memory_audit --rom <esp32s3_rev0_rom.elf> --toolchain <xtensa-esp-elf>`。保存したELFと入力commitは [provenance](memory-sdk/provenance.json)。回帰検査結果は [tests.log](tests.log)。

検証結果：73 tests成功。全イベントの回数・各core課金時刻を分母とした回/sは [統合JSON](../receiver-integrated-estimate/estimate.json) の `queue_connected_owner_candidate.event_rates_per_core_accounted_horizon` に収録。最後の課金が観測停止時刻を越える場合を混同しないため、core別の課金終端を分母にする。
