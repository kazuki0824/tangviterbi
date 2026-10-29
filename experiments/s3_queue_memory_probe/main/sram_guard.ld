/* Same RF reservation boundaries as ESPARGOS/esp-sdr e74f2a4709.
 * Reject alias overlap as well as direct DRAM overlap. */
ASSERT(_iram_end <= 0x403a0000, "S3 RF ring overlaps IRAM")
ASSERT(_data_end <= 0x3fcb0000, "S3 RF ring overlaps data")
ASSERT(_bss_end <= 0x3fcb0000, "S3 RF ring overlaps BSS")
