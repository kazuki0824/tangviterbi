# 工程2：20K物理端子の不整合（要是正）
基準: Tang Nano 20K Rev1.30 J5=16信号、J6=18信号、合計34信号（`reports/20k-dual-s3.md`）。
`dual_s3_spi_ingress_only_area_top` はT/S双方の `spi2_clk/cs_n`各2、`spi2_d` 8bit各2、`spi3_clk/cs_n`各2、`spi3_d` 4bit各2を出している。

| 経路 | SPI2 Octal | SPI3 Quad | TS pin | event | 合計 |
|---|---:|---:|---:|---:|---:|
| **現実験top** | T10+S10=20 | T6+S6=12 | T3+S3=6 | 2 | **40>34 (6超過)** |
| **既存の計画** | T10+S10=20 | S6のみ | T3+S3=6 | 2 | **34/34 (余裕0)** |

`T_OCTAL_ONLY` はTのQuad RF書込みを無効化するが、`s3_spi_runtime_endpoint` のT側 `spi3_clk/cs_n/d` はcontrol/IQ等の既存用途のため現実験topの物理端子から除去されていない。未接続IQ返送をYosysが除去しただけで通信プロトコルおよびpin契約が34本用に再設計されたとは言えない。

**結果**: 今回の部分合成はFPGA上のlogic資源の検討として有効だが、`40>34`のため、この形での物理pin-fitには不合格。計画T Octal10/S Octal+Quad16/TS6/event2はpin本数の必要条件のみ通過し、FPGAのclock可能ピン、bank電圧、S3側IO、TS sink等の条件は未確認。

次の是正はT側Quad6を不要にするプロトコル・制御再設計、又はT側制御を既存計画の2本のイベント線へ収める具体実装（独立UART等）であり、単にT側Quadのpin数を台帳から引いてはならない。実通信契約を守った実RTLで再合成し、CST/IO制約で合法配置を検証する。

工程2は未完了。工程3へ移行しない。
