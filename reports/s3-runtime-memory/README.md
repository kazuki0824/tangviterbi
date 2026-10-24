# ② N16R8：SPI/PHYの動的確保とFlash配置条件

N16R8だけで成立する案も許容し、①は変更しない。前段の[起動確保列](../s3-startup-order/README.md)に続き、SPI/GDMA/PHYの未計上領域を検証する。

実SDK比較へ、heap関数Flash配置＋PHY較正データのNVS保存なし、を追加。`ESP_PHY_CALIBRATION_AND_DATA_STORAGE=n`ではSDKの`esp_phy_load_cal_and_init()`が起動時に`register_chipv7_phy(..., PHY_RF_CAL_FULL)`を呼ぶ。較正自体を省略する変更ではない。起動時間とNVS依存が変わる候補で、受信性能を保証するものでもない。PLL追従は維持する。

まだ診断ELFでありapp_mainはRF/PHY/SPIを起動しない。CIリンク結果・詳細台帳は検証後に追記する。全受信機の性能合格・正式経路・採用は0/0/0を維持する。
