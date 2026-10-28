# ② 通常RF監視経路の費用内訳

2026-10-28 JST。変更後S候補の固定SDK ELF（commit 9da570f、hashはresults.json）を再解析した。runtimeは変更していない。

対象は準備済み、settling=false、written<12288、age期限内、clock正常・上位32bit=0で折返しなしという通常経路。全7回のRF監視がこの経路を通り、両SPIが動作中である1反復の**部分費用**を計数する。全反復の平均でも最悪経路でもない。

| 内訳 | 命令数 |
|---|---:|
| poll_rf自身 | 14 |
| s3_native_poll_budget自身 | 73 |
| clock_now自身＋cycle_clock_read | 26＋20＝46（2回） |
| healthy callback | 6 |
| INDEXのMMIO read callback | 4 |
| RF監視1回の合計 | **189** |
| RF監視7回 | **1323** |
| 2本のSPI動作中確認（wrapper込み） | **78** |
| 部分合計 | **1401** |

α=1.1の従来模型なら1541.1cycle、240MHzで6.42125µsに相当する。実時間ではない。collect、別のcollect時計、feedと時計、owner制御、packing、fill、IRQ、MMIO待ち、window exception等はこの合計に入らない。間接callはraw runtimeのcallback接続を前提に実関数の命令数を加えた。全到達経路の形式証明ではなく、指定経路の全分岐接続とcall数・実SDK source/hashの照合である。

## 見積もりへの意味

- 追加scan1500cycleは未測定の感度点として維持するが、この通常経路の部分費用だけで1541.1cycle相当になる。1500をscan全体の保証上限や保守的な実測値と読んではいけない。
- 256pair案の805.544cycle/追加scanという平均予算を、現runtimeの全反復に使える時間上限として達成したとは言えない。特定経路の費用と経路頻度を含む平均費用は違うため、これだけで平均不成立とも断定しない。
- 512pair案の管理200cycle込みscan予算2225.546cycleと比べると、この部分費用を引いた残額は684.446cycle。collect等の全未計上処理がここに収まるとの保証はない。
- 既存U0=20 Mcycles/sには旧25000反復/s側の未分類費用を残している。今回の命令数をそのまま全33333.33反復/sへ追加すると二重計上になり得る。Uの内訳と各状態頻度を再構成するまでCPU占有率は置換しない。

次の対象はcollect・feed・owner制御を含む同経路の残費用と、切替/settling/準備経路の頻度。RF監視回数を減らす実装変更は監視gapとreclaim期限を再検証してから判断する。

再現：`python -m ci.s3_owner_quiet_path_audit --toolchain build/rs-toolchain/xtensa-esp-elf`。全命令経路・分岐選択・ELF/source hashはresults.json。
