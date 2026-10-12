#ifndef TEST_SPI_MASTER_H
#define TEST_SPI_MASTER_H
#include <stdint.h>
#include <stdbool.h>
typedef int esp_err_t;typedef int spi_host_device_t;typedef struct fake_device *spi_device_handle_t;
enum { ESP_OK=0,ESP_ERR_INVALID_ARG=1,ESP_ERR_INVALID_STATE=2,ESP_ERR_TIMEOUT=3,ESP_ERR_NOT_SUPPORTED=4,ESP_ERR_NOT_FINISHED=5,SPI2_HOST=2,SPI3_HOST=3,SPI_DMA_CH_AUTO=1 };
enum { SPI_TRANS_MODE_OCT=1,SPI_TRANS_MODE_QIO=2,SPI_TRANS_MULTILINE_CMD=4,SPI_TRANS_MULTILINE_ADDR=8,SPI_TRANS_DMA_BUFFER_ALIGN_MANUAL=16,SPI_DEVICE_HALFDUPLEX=1,SPI_DEVICE_NO_DUMMY=2,SPICOMMON_BUSFLAG_MASTER=1,SPICOMMON_BUSFLAG_OCTAL=2,SPICOMMON_BUSFLAG_QUAD=4 };
typedef struct {unsigned flags;uint16_t cmd;uint64_t addr;void *user;unsigned length,rxlength;void *rx_buffer;const void *tx_buffer;} spi_transaction_t;
typedef struct {spi_transaction_t base;unsigned sct_gap_len;} spi_multi_transaction_t;
typedef struct {unsigned max_transfer_sz,flags;} spi_bus_config_t;
typedef struct {int command_bits,address_bits,dummy_bits,mode,clock_speed_hz,spics_io_num,queue_size;unsigned flags;} spi_device_interface_config_t;
esp_err_t spi_bus_initialize(spi_host_device_t,const spi_bus_config_t*,int);
esp_err_t spi_bus_free(spi_host_device_t);
esp_err_t spi_bus_add_device(spi_host_device_t,const spi_device_interface_config_t*,spi_device_handle_t*);
esp_err_t spi_bus_remove_device(spi_device_handle_t);
esp_err_t spi_bus_multi_trans_mode_enable(spi_device_handle_t,bool);
esp_err_t spi_device_get_actual_freq(spi_device_handle_t,int*);
esp_err_t spi_device_queue_multi_trans(spi_device_handle_t,spi_multi_transaction_t*,unsigned,int);
esp_err_t spi_device_queue_trans(spi_device_handle_t,spi_transaction_t*,int);
esp_err_t spi_device_get_multi_trans_result(spi_device_handle_t,spi_multi_transaction_t**,int);
esp_err_t spi_device_get_trans_result(spi_device_handle_t,spi_transaction_t**,int);
#define SOC_SPI_SCT_SUPPORTED 1
#include "freertos/FreeRTOS.h"
esp_err_t spi_device_acquire_bus(spi_device_handle_t,unsigned);
void spi_device_release_bus(spi_device_handle_t);
esp_err_t spi_device_polling_start(spi_device_handle_t,spi_transaction_t*,unsigned);
esp_err_t spi_device_polling_end(spi_device_handle_t,unsigned);
#endif
