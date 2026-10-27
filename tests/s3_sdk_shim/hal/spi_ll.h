#ifndef TEST_SPI_LL_H
#define TEST_SPI_LL_H
#include <stdbool.h>
#include "driver/spi_master.h"
#define SPI_LL_GET_HW(host) (host)
bool s3_test_spi_done(spi_host_device_t);
#define spi_ll_usr_is_done(host) s3_test_spi_done(host)
#endif

unsigned s3_test_spi_running(spi_host_device_t host);
#define spi_ll_get_running_cmd(host) s3_test_spi_running(host)
