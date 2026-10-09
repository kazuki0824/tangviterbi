set(probe_sources "memory_probe.c")
if("$ENV{PROBE_TRANSPORT}" STREQUAL "1")
    list(APPEND probe_sources "../../s3_transport.c" "../../s3_spi_transport.c" "../../s3_fft_tiles.c" "../../s3_capture_bridge.c")
endif()
idf_component_register(SRCS ${probe_sources} INCLUDE_DIRS "." "../.." PRIV_REQUIRES heap esp_driver_spi)
target_compile_definitions(${COMPONENT_LIB} PRIVATE
    PROBE_TERRESTRIAL=$ENV{PROBE_TERRESTRIAL} PROBE_LINKS=$ENV{PROBE_LINKS}
    PROBE_ZEROCOPY=$ENV{PROBE_ZEROCOPY}
    PROBE_TRANSPORT=$ENV{PROBE_TRANSPORT} PROBE_LATE_RF=$ENV{PROBE_LATE_RF})
if("$ENV{PROBE_RING64}" STREQUAL "1")
    target_compile_definitions(${COMPONENT_LIB} PRIVATE PROBE_RING64=1 S3_RING_PAGE_COUNT=16)
endif()
target_link_options(${COMPONENT_LIB} INTERFACE "-T${CMAKE_CURRENT_LIST_DIR}/sram_guard.ld")
