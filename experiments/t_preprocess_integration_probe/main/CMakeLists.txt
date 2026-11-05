idf_component_register(SRCS "integration_probe.c" "../tpre_runtime.c" "../tpre_sdk.c" "../tpre_pie.S"
 "../../t_preprocess_capacity/native_adapter.c" "../../t_preprocess_capacity/halfband_pipeline.c"
 "../../t_preprocess_capacity/halfband31.c" "../../t_preprocess_capacity/halfband31.S"
 "../../s3_native_capture.c" "../../s3_capture_bridge.c" "../../s3_cycle_clock.c"
 INCLUDE_DIRS ".." "../.." "../../t_preprocess_capacity"
 PRIV_REQUIRES esp_driver_spi esp_system heap esp_psram esp_timer esp_phy
 LDFRAGMENTS "hot.lf")
target_compile_definitions(${COMPONENT_LIB} PRIVATE S3_NATIVE_FILL_UNROLL=8)
# These atomics only access validated internal objects; the rest of IDF keeps
# its SPIRAM workaround. Disable SLP's expensive scalar unpack expansion.
target_compile_options(${COMPONENT_LIB} PRIVATE -mno-disable-hardware-atomics -fno-tree-slp-vectorize -fstack-usage)
target_link_options(${COMPONENT_LIB} INTERFACE "-T${CMAKE_CURRENT_LIST_DIR}/sram_guard.ld")
