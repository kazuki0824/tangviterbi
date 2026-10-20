# ②：16 symbol単位のT時間DI集約案

正式採用0、全受信機成立未確認、①停止を維持。
今回の変更は実験用の配置モデル・BL8読書き部品であり、時間DI全体RTLの完成ではない。
6個の既存8-bit soft値をそのまま保存し、SoCの再量子化・追加デシメートを導入しない。

## 配置と値の検証

各carrierについて16 symbol分（96 bytes）をまとめ、32-byte境界のBL8へ分割する。
遅延Dのringをceil((D+16)/16)*16 sampleへ拡張する。
先に最新16sampleを書いても、必要な過去sampleが上書きされない空間を確保する。
読出しは時刻t-Dから16sample。Dの端数を捨てたり遅延を丸めたりしない。
D=0はbypass。全有効Iと96遅延クラスを独立queue oracleへ照合し、複数周回も成功。
BL8の整列、ring境界、領域非重複も検査した。

入出力の転置はまだRTL化していない。一時領域への入力write/read・出力write/readの
計4passを要求数へ計上する。実際のtile保持、各buffer所有権、pipeline遅延は未検証。

| 最大I条件 | ring bytes | 一時領域2個を含む残容量 | 一時領域4個を含む残容量 | BL8/symbol |
|---|---:|---:|---:|---:|
| Mode1 | 5809440 | 2339552 | 2099936 | 1399.125 |
| Mode2 | 5987904 | 1921472 | 1442240 | 2876.25 |
| Mode3 | 6344832 | 1085312 | 126848 | 5830.5 |

上記残容量から他stage領域をさらに引く。Mode3でinput/outputを各ping-pong、計4個にすると、
既存T spill 59904＋S frame77952 bytesだけでも**11008 bytes超過**。FFT等はまだ含まない。
この独立4buffer配置は採用しない。3個以下の配置には所有権・順序の検証が必要であり、
容量に入るという算術だけで成立扱いしない。
[モデル・集計](t-time-block-layout.json)、[検査ログ](t-time-block-layout-test.log)。

## BL8読書きRTL

- `experiments/t_time_block_reader.sv`：96 bytesをringから読出す。先頭offset、wrap、
  request/response停止、下流停止を扱う。1 outstanding、32-byte response保持。
- `experiments/t_time_block_writer.sv`：96 bytesを3個のBL8へ可逆packして書く。
  requestとresponseを待ち、完了前にbufferを再使用しない。
- base/endは32-byte整列、startは有効領域内という呼出し契約。writer startも32-byte整列。
  end=8 MiBを表せる24-bit境界を使用。
- 単独テストは制御されたresponseモデル。実controller・arbiterとの接続、途中resetによる
  in-flight応答処理、実時間DIデータ経路、P&Rは未検証。

| 単独合成 | logic | FF | 判断 |
|---|---:|---:|---|
| 初版reader、可変barrel shift | 1539 | 349 | 面積改善の対象。元source/mapを保存 |
| reader、先頭byteを順にdiscard | 415 | 349 | 次の接続検証用。先頭offset分0〜31 clocksを追加 |
| writer | 130 | 338 | 次の接続検証用 |

内部discardは読出しBL8の不要なprefixだけであり、要求された96 bytesを間引かない。
reader55296 bytes、writer6912 bytesを照合。リングの全開始offset、8 MiB上端、停止を検査して成功。
[試験](t-time-block-io-test.log)、[合成とsource hash](t-time-block-evidence.json)。
これらの値を既存allocationへ単純加算・減算して全受信機面積を決めない。

## 競合下の要求数スクリーニング：不合格

Mode3の5830.5 BL8/symbolをMode1周期へ換算して切り上げた1458 BL8/periodを、
既存のservice/reader/K7/S/FFT模擬アクセス試験へ与えた。
元のcarrier単位方式2470より少ないが、次の期限違反が残った。

| S | 背景第1完了（期限40095） | 第2完了（期限80190） | 期限違反 |
|---|---:|---:|---:|
| binary | 62996 | 88389 | 2 |
| TC8 | 67189 | 89792 | 2 |

[結果](shared-receiver-block-tti-load-test.json)、[ログ](shared-receiver-block-tti-load-test.log)。
T/K7データ照合は成功、背景期限は失敗。
**これは平均要求数を平滑化し旧合成アドレスへ与えた試験**であり、16-symbol batchの実到着や
配置・row locality・transpose順序を再現していない。従って案全体の不可能性の証明ではないが、
要求数を減らしただけで旧仲裁・配置のまま採用する根拠は得られなかった。
今回のreader/writer RTLをこの競合試験へ接続したという意味でもない。

## 次の判断に必要なもの

実配置からのアドレス列・16-symbol到着時刻・3個以下のbuffer所有権・transpose保持量を
一つのscheduleとして作り、実controllerと全clientの競合で検証すること。
今回残った問題は背景期限とbuffer運用であり、単なるpackingデータ破壊ではない。
実FFT146.22 MHz未達、全受信機の未実装段、S3/WCET/PHY等は前回一覧から解消していない。
