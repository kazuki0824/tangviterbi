idf_component_register(SRCS "queue_probe.c" "../../s3_raw_queue.c" "../../s3_inline_pack.c"
 INCLUDE_DIRS "../.." PRIV_REQUIRES esp_driver_spi esp_system heap esp_psram)
target_compile_definitions(${COMPONENT_LIB} PRIVATE S3_PP_CORE0_SIXTEENTHS=5 S3_RAW_TRANSFER_BYTES=16384)
