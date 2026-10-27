# ② 実行構成の確定状況と、現在の証拠で閉じられない判定

2026-10-27。細分化した監査を成立判定へ戻すため、保存ELFの役割と実taskの設定責任を再確認した。runtimeと①は変更しない。

**追補：以下は実構成について成立を確認するための条件であり、条件付き見積もりの着手条件ではない。** 完成アプリや保証WCETを待たずに、既知の命令量・資源予算と未測定費用の感度分析から設計判断はできる。[SoC時間・実効帯域・FPGA全体・確度を統合した見積もり](../receiver-estimate-20261027/README.md)を現在の見積もり入口とする。

## 保存ELFは受信アプリではない

`experiments/s3_raw_probe/main/raw_probe.c` のapp_mainはprintfとvolatile anchorの読取りだけを実行する。PHY、SPI open、native RF start、task launcherの関数をリンクへ残すが呼ばない。ファイル冒頭と既存配置報告にもlink-onlyと明記されている。この点は今回新しく発生した制約ではない。

従って保存ELFから検証できるのは、そのビルドの静的配置・記述子layout・retained関数・一部命令列等。**受信中のIRQ登録一覧、実task priority、IRQ affinity、stack高水位、C/H/S/W/Rの実時間は、このELFが存在するだけでは得られない。** wrapper symbolがあることやSDK testが緑であることを実行構成の証拠にはしない。

## コードで確定したもの／callerに残るもの

| 対象 | 現行コードから確認できた内容 | 残る入力・証拠 |
|---|---|---|
| worker | launcherが各coreへ1 task、peer先行で作成。ownerはcore0 | priorityはcaller引数。実stack余裕・他task干渉 |
| SPI | bulk・32 KiB・queue_size=1・80 MHz実周波数検査・callback未指定 | board pins、intr_flags、isr_cpu_idはcaller設定。実配線品質 |
| IRQ lock | 固定SDKの直接利用者11関数を列挙済み | 全componentの受信中登録一覧・affinity・共有handler・発火包絡 |
| RF/PHY | native handoffとpacking、task開始/停止のhost試験がある | PHY初期化を含む実受信構成とRF ABI/連続取得/信号品質 |
| TWDT | callerが実設定を渡し、runtimeが所有する契約 | 実設定、他subscription、timer/IRQ干渉の確認 |
| clock/cache | cycle clock候補とIRAM配置検査がある | 受信中のclock/cache/flash操作条件とメモリ仲裁 |

SPI非sharedを選び、両SPI IRQをcore0へ置く候補では、そのSPI queueのcross-core競合を除外できる。これで他componentのcore1共有IRQがallocator共通lockを保持しないことまでは証明されない。固定SDKの関数をさらに分解しても、未作成の受信アプリがどう登録するかは一意に決まらない。

## 完了へ向けた順序と完了条件

1. **受信アプリの構成を具体化する。** PHY/RF初期化、pins、SPI IRQ属性/affinity、priority、clock/cache方針を含む実際に起動する構成が成果物。link-only appのanchor増加を代用にしない。
2. **その構成を対象にIRQ/taskと時間証拠を得る。** RF開始直前の登録情報だけでなく、受信中に変わらない条件・他IRQの発火と共有lock保持も対象。測定最大値は自動的にWCETではないため、試験範囲と保証範囲を区別する。SPI_UPDATE等はhardwareの数値根拠が必要。
3. **既存の期限・容量式へ接続する。** C/H/S/W/Rとworkerの費用・到来包絡に根拠が揃って初めて代入。T/S各SoC、全bank長・carry・順序付き回収、継続動作について判定する。
4. **独立して残るFPGA全体を閉じる。** 保存部分構成は19,627/20,736 site、152.091263 MHzで、現K7最低152.626638 MHzに未達。これを全受信機の配置・速度と見なさず、全復調/TS/新transportを含む資源・STA・機能の証拠が必要。

上記1〜2の欠落が現在のSoC実時間判定を止める具体的理由。これは全候補不可能という結論でも、FPGA等の独立作業まで止める理由でもない。形式モデルの追加だけを繰り返して1〜2を完了扱いにしない。

## 今回の再検証

実IRQ routing、実req_core、IRQ形式モデル、実queue、owner/ISR CAS、SDK primitive、worker response、実task lifecycle/launcherをまとめて実行し21 unittest成功（validation.json）。実機受信・WCET・全FPGAの証明ではない。

前4d1a0bbのGitHub Actionsは確認時、host FFT、linker-map、RF coexistence link、raw-only SPI placementの4 workflowがsuccess、startupがin_progress、receiver closureがqueued。今回の21試験とは別であり、この文書のcommitのCI成功とはしない。

過去の小さな監査ごとに応答を終了したのは報告上の都合で、依頼全体の品質や依存関係上必要な中断ではなかった。進捗報告は作業中にも行えるため、その理由でユーザーへ続行指示を繰り返し求める判断は不適切だった。
