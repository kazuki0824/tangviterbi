# ② ownerのsentinel準備を1反復1024wordへ分割

2026-10-27。8word unrollだけでは、ownerが約70µsを連続してfillへ使うという模型上の問題が残ったため、準備を途中再開可能にした。`s3_native_poll_budget` に同じword予算を渡し、owner内の7回のRF poll全体で最大1024wordとする。pollごとに予算を補充しない。

reclaimは準備開始時の1回だけ。3072＋4096wordが全て書き終わるまでpreparedを立てない。予算0でもRF INDEX・時計・期限を確認する。未完了でRF切替期限に達した場合は停止し、未準備bankへ切り替えない。既存の `s3_native_poll` は同期準備を行う互換入口として維持するが、raw ownerは予算付き入口を使う。割込み禁止、追加間引き、再量子化は導入しない。

## 命令数と必要CPUの見積もり

fill helper自体の61命令とbarrier/store順序はSDK確認済みの8word版と同じ。source全体を再compileし、全16384開始位置の7分割・折返しを再計数した。

| 項目 | 同期8word fill | 1024wordずつのfill |
|---|---:|---:|
| 1bankのfill命令数包絡 | 15362 | 15567 |
| ownerが1反復で実行するfill仕事 | 最大7168word | **最大1024word** |
| 1反復分のfill命令数包絡 | 15362 | **2265** |
| 同じα=1.1の時間模型 | 70.41µs | **10.38µs** |

命令数包絡はcallback内部、追加された準備管理、clock、IRQ、SPIを含まない。1反復の実時間上限や30µs scan達成ではない。1024は1回のfill模型を約10µsへ抑えるための選択で、最適quantumを証明した値ではない。

分割のfill呼出し増加を加えると、S6/16のcore0上端は94.40→94.70%（追加scan1500cycleという従来感度点を保持）。さらに準備cursor/budget管理と追加callbackの差分をΔE cycle/owner反復と置き、毎秒33333.33反復の感度条件で全反復へ追加すると：

| 未測定の追加ΔE | S core0上端 |
|---:|---:|
| 0 | 94.70% |
| 100cycle | 96.09% |
| 200cycle | 97.48% |
| 300cycle | 98.87% |

core1上端79.94%は不変。追加管理費用予算は約381cycle/反復。ΔE=0を実装の無償性とはしない。稀な回だけに課金せず全反復へ置いた感度模型であり、実測費用・発生頻度ではない。

7回の1024word準備が必要で、仮に1反復30µsなら約210µsの準備区間を見込む。これは実際のRF切替期限・旧bankの解放時刻と両立することを確認した値ではない。たとえばSの公称12288 sample/bankでは、A→BからC→Aまで614.4µs。A解放320µs、C開始307.2µs、準備へ進める機会の完了間隔が30µs以下なら、max(320,307.2)+7×30=530µsとなり84.4µsを残す。解放455.45µsなら同じ十分条件は49.05µs不足する。これは公称時系列の設計予算であり、RF位相・settling・実反復上限を証明した値ではない。従来のreclaim条件だけを新しい分割準備の期限保証に流用しない。SPI API/packing等による非一様なservice間隔と公開時間を含めた有限buffer評価が残る。平均CPU・fill単独時間から受信機成立を認定しない。

## 検証

実productionの予算付きpollについて全16384開始位置、0予算・7分割、異なるquantum、途中の書込み集合、reclaim1回、未完了の期限停止・reclaim失敗をUBSan付きhost試験で確認。実raw taskのmock境界でも、7回のpollに同じ予算が渡り、途中で復活しないことを確認。native lifecycle・共通時計・parallel deadline等5テスト成功。定数の共通化後の予算poll・raw task再確認2テストも成功（tests.log、budget-final-tests.log）。実RF・実時間の試験ではない。

target計数は `python -m ci.s3_native_fill_target --toolchain build/rs-toolchain/xtensa-esp-elf --unroll 8 --prepare-quantum 1024 --output reports/s3-budgeted-fill/u8`。

[SDK run 40518679493](https://github.com/kazuki0824/tangviterbi/actions/runs/40518679493) が成功。S6/16・16KiB・8word・1024word予算と新入口のIRAM配置を含む59静的check、SDK fill命令列・literal・8 source identity等12再確認が成功。共通54＋既定59＋S59=172静的check。SDK成果物・hash・出所はsdk-S/T、packing CFG再計数はcfg-S/Tに保存。Sのcaptureは168bytes（+8）、IRAM末尾0x40388200、既知driver控除後の内部空き上限16324bytes（分割前から264bytes減）。実起動・実時間の確認ではない。
