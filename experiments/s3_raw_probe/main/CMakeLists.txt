idf_component_register(SRCS "raw_probe.c"
 "../../s3_parallel_pack.c" "../../s3_parallel_capture.c" "../../s3_parallel_spi.c"
 "../../s3_raw_tasks.c" "../../s3_timer_clock.c" "../../s3_cycle_clock.c" "../../s3_native_capture.c" "../../s3_capture_bridge.c"
 "../../s3_transport.c" "../../s3_spi_transport.c"
 INCLUDE_DIRS "." "../.."
 PRIV_REQUIRES esp_system heap esp_driver_spi esp_timer esp_phy esp_psram)
target_link_options(${COMPONENT_LIB} INTERFACE "-T${CMAKE_CURRENT_LIST_DIR}/sram_guard.ld")

if(RAW_LATE_TASK_STACKS)
 target_compile_definitions(${COMPONENT_LIB} PRIVATE RAW_LATE_TASK_STACKS=1)
endif()

if(RAW_ONLY_SPI)
 target_compile_definitions(${COMPONENT_LIB} PRIVATE S3_RAW_ONLY_SPI=1)
endif()
