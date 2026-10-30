idf_component_register(SRCS "queue_owner_probe.c" "generated/s3_queue_tasks.c"
 "../../s3_raw_queue.c" "../../s3_queue_receiver_open.c" "../../s3_inline_pack.c" "../../s3_parallel_capture.c"
 "../../s3_cycle_clock.c" "../../s3_native_capture.c" "../../s3_capture_bridge.c"
 INCLUDE_DIRS "generated" "../.." PRIV_REQUIRES esp_driver_spi esp_system heap esp_psram esp_timer)
target_compile_definitions(${COMPONENT_LIB} PRIVATE S3_PP_CORE0_SIXTEENTHS=5 S3_RAW_TRANSFER_BYTES=16384 S3_NATIVE_FILL_UNROLL=8)
