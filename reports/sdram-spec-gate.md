# ② SDRAM仕様による154.286 MHz案の判定

2026-10-19 JST。**共通154.285714 MHz案を周波数上限で除外する理由はない。PHY合格は未確定。** 従来のcontroller単体Fmaxを実メモリ仕様へ読み替えず、Gowinの現行データシートを確認した。

## 根拠と検算

- [Sipeedの製品説明](https://wiki.sipeed.com/hardware/en/tang/tang-nano-20k/nano-20k.html)：対象はGW2AR-LV18QN88C8/I7、32-bit/64-Mbit SDR SDRAM。
- [DS226-2.7E（2026-07-31）](https://cdn.gowinsemi.com.cn/DS226E.pdf) §2.2.1（本文pp5–6）：SDR SDRAM 166 MHz、access time 5.4 ns、CL=2/3、4096 refresh/64 ms。対象をDDRやPSRAMと取り違えない。
- 同資料表3-20（本文pp38–39）のC8/I7：PLL PFD 3–500 MHz、VCO 500–1250 MHz、出力3.90625–625 MHz。
- [IPUG279-1.4E（2025-05-09）](https://cdn.gowinsemi.com.cn/IPUG279E.pdf) §6.2：controller user側はcontroller clockへ同期し、メモリclockの位相を調整してread/writeのsetup/holdを合わせる。旧1.3Eではなく位相説明の改訂版を参照する。

[再現可能な検算](../experiments/sdram_spec_gate.py)／[JSON](sdram-spec-gate.json)。27×40/7＝154.285714 MHz、周期6.481481 ns。IDIV_SEL=6、FBDIV_SEL=39、ODIV_SEL=4ならPFD=3.857143 MHz、VCO=617.142857 MHzで上の範囲内。ただしPLL配置、lock、位相・ジッタを含むSTAが済んだという意味ではない。

公称166 MHzとの差は11.714286 MHz。これを配線timingの余裕と呼ばない。周期からaccess timeを引いた1.081481 nsも、入出力配線、capture位相、setup/hold、uncertaintyを控除しておらず、slackではない。

4096 refresh/64 msは15.625 µs間隔に相当する。現候補の1203 cycles＝約7.797222 µsはそれより短いので、頻度不足ではない。今回はrefreshを間引かず従来の保守的設定を維持する。温度等の条件と個別command timingの認定は別途必要。

## 具体化したclock/PHY契約

| 項目 | 設計条件 | 状態 |
|---|---|---|
| 入力clock | 基板27 MHz源、周期37.037037 ns | 周波数既知、source jitterをSTAへ反映する必要 |
| 演算・controller user側 | 同じPLL出力154.285714 MHz、周期6.481481 ns | 内部async FIFOを前提としない |
| メモリ端子clock | 同じPLL由来、同周波数、位相φはSTAで選定 | φ未決定。0°/90°/180°を根拠なく固定しない |
| command/address/write DQ | メモリ側setup/holdとIO/配線遅延を満たすよう登録 | actual delay・端子制約未接続 |
| read DQ | CLとcapture edgeに一致するデータを取込み、validも整列 | access maxだけではhold側を証明できない |
| reset | PLL lock後にcommon domainで解除同期 | 未統合。lockの瞬時観測だけで全FSMを解除しない |
| S3入力 | 独立送信clockを各入力経路で取込み | 内部統一だけではこの境界のCDCは消えない |

例えばread側のsetup条件は、対応するメモリclock edgeからの最大access＋DQ配線遅延＋capture setup＋uncertaintyがcapture edgeまでの時間内に入ること。hold側は次データが変わり始める最小時刻を使用する。CLに対応するedge番号とφを定義して両方を満たす必要があり、max access=5.4 nsだけでinput-delayのminを作らない。write側もcommand/address/DQのmax・min双方を検査する。全経路false-path指定で通過扱いにしない。

## ここで未確定のもの

DS226の上記仕様とIPUG279の**外部メモリ向けGUI既定値**からは、今回の内蔵メモリについてtRCD/tRP/tRFC/tWR/tMRD/tRAS/tRC/tRRD、CL3時の詳細条件、DQ hold、入力setup/hold、package/IO遅延を一式確定できていない。外部GUI既定値や別メーカーの似たメモリの値を、搭載品の保証値として転用しない。

次に必要なのは対象device用Gowin内蔵SDRAM IPの生成設定・simulation timing model・実装制約、または同等のメーカー資料である。取得後に現自作controllerの待ち時間/最短command間隔と照合し、PLL/PHYを含む実装へ進む。資料で埋められない項目は実機で位相/温度/連続read-writeを検証する必要がある。今回確認した公開資料だけでPHY合格までは閉じられない。

**停止対象はPHYの合格認定であり、②全体を不可能とはしていない。** デジタル側の仲裁・buffer寿命・期限検証は仮定を明示して継続可能。ただし不明なmemory timingに依存する全受信機の合格は出さない。共通clock案がPHYで落ちた場合だけ二domain案のCDC費用を測る順序を維持する。

今回は新しいRTL/CAD測定ではなく仕様照合と算術検算。前回のデジタル試験を物理合格へ昇格しない。混合予算20472 logic・46 BSRAMと残予約は変更せず、確認済みCDC削減0、正式性能合格/通信割当/採用0。native I10/Q10、FPGA→SoCは指令のみ、追加softwareの品質低下禁止を維持する。
