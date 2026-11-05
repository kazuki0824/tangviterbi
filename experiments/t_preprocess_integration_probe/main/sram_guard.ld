ASSERT(_bss_end <= 0x3fcb0000, "T probe static DRAM overlaps RF banks")
ASSERT(_data_end <= 0x3fcb0000, "T probe initialized DRAM overlaps RF banks")
ASSERT(_iram_end <= 0x403a0000, "T probe IRAM exceeds internal window")
