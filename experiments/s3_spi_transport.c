#include "s3_spi_transport.h"
#include "esp_idf_version.h"
#include "esp_memory_utils.h"
#include "esp_attr.h"
#include <string.h>

#if ESP_IDF_VERSION != ESP_IDF_VERSION_VAL(5, 5, 1)
#error "Audit SCT private API before changing the ESP-IDF version"
#endif
_Static_assert(SOC_SPI_SCT_SUPPORTED, "SCT required");

esp_err_t s3_spi_open(s3_spi_port *p, spi_host_device_t host,
                       const spi_bus_config_t *pins, int cs, unsigned lanes,
                       bool sct, spi_multi_transaction_t *storage, unsigned capacity)
{
    if (!p || !pins || !storage || capacity == 0 || capacity > S3_SPI_MAX_SEGMENTS ||
        (!sct && capacity != 1) || cs < 0 || (host != SPI2_HOST && host != SPI3_HOST) ||
        (lanes != 4 && lanes != 8) || (lanes == 8 && host != SPI2_HOST) ||
        (sct && host != SPI2_HOST)) return ESP_ERR_INVALID_ARG;
    memset(p, 0, sizeof(*p));
    p->host = host; p->lanes = lanes; p->sct = sct;
    p->segments = storage; p->capacity = capacity;
    spi_bus_config_t config = *pins;
    /* IDF allocates ceil(max_transfer_sz/4092) descriptors in BOTH directions.
     * An SCT segment uses one 60-byte config descriptor and two for 4096 B.
     * 24 is pool capacity, not an allocated 98-KiB payload staging area.
     */
    config.max_transfer_sz = sct ? 3 * capacity * 4092 : S3_PAGE_BYTES;
    config.flags = SPICOMMON_BUSFLAG_MASTER |
                   (lanes == 8 ? SPICOMMON_BUSFLAG_OCTAL : SPICOMMON_BUSFLAG_QUAD);
    esp_err_t err = spi_bus_initialize(host, &config, SPI_DMA_CH_AUTO);
    if (err != ESP_OK) return err;
    spi_device_interface_config_t dev = {
        .command_bits = 16, .address_bits = 64, .dummy_bits = 0,
        .mode = 0, .clock_speed_hz = 80000000, .spics_io_num = cs,
        .queue_size = 1, .flags = SPI_DEVICE_HALFDUPLEX | SPI_DEVICE_NO_DUMMY,
    };
    err = spi_bus_add_device(host, &dev, &p->device);
    if (err != ESP_OK) { spi_bus_free(host); return err; }
    if (sct) err = spi_bus_multi_trans_mode_enable(p->device, true);
    int actual_khz = 0;
    if (err == ESP_OK) err = spi_device_get_actual_freq(p->device, &actual_khz);
    if (err == ESP_OK && actual_khz != 80000) err = ESP_ERR_NOT_SUPPORTED;
    if (err != ESP_OK) {
        spi_bus_remove_device(p->device); spi_bus_free(host); p->device = NULL;
    }
    return err;
}

esp_err_t IRAM_ATTR s3_spi_prepare_pages(s3_spi_port *p, unsigned stream, unsigned epoch,
                                uint32_t offset, void *const payloads[], unsigned pages)
{
    if (!p || !p->device || p->busy || p->poisoned) return ESP_ERR_INVALID_STATE;
    p->count = 0;
    if (!payloads || pages == 0 || pages > p->capacity) return ESP_ERR_INVALID_ARG;
    for (unsigned i = 0; i < pages; ++i) {
        /* A ring wrap may use different page pointers, without a copy. */
        uint8_t *b = payloads[i];
        if (!b || ((uintptr_t)b & 3) || !esp_ptr_internal(b) ||
            !esp_ptr_internal(b + S3_PAGE_BYTES-1) || !esp_ptr_dma_capable(b) ||
            !esp_ptr_dma_capable(b + S3_PAGE_BYTES-1)) return ESP_ERR_INVALID_ARG;
    }
    s3_wire_header header;
    if (s3_wire_make(&header, stream, epoch, offset, S3_PAGE_BYTES) != S3_OK)
        return ESP_ERR_INVALID_ARG;
    for (unsigned i = 0; i < pages; ++i) {
        s3_wire_make(&header, stream, epoch, offset + i*S3_PAGE_BYTES, S3_PAGE_BYTES);
        spi_multi_transaction_t *s = &p->segments[i];
        memset(s, 0, sizeof(*s));
        s->base.flags = (p->lanes == 8 ? SPI_TRANS_MODE_OCT : SPI_TRANS_MODE_QIO) |
            SPI_TRANS_MULTILINE_CMD | SPI_TRANS_MULTILINE_ADDR | SPI_TRANS_DMA_BUFFER_ALIGN_MANUAL;
        s->base.cmd = header.command; s->base.addr = header.address;
        s->base.user = p;
        if (stream == S3_IQ) {
            s->base.rxlength = S3_PAGE_BYTES * 8; s->base.rx_buffer = payloads[i];
        } else {
            s->base.length = S3_PAGE_BYTES * 8; s->base.tx_buffer = payloads[i];
        }
        /* Requested CS-inactive gap only. Actual DMA configuration fetch and
         * bus arbitration time are additional, unmeasured silicon costs. */
        s->sct_gap_len = 1;
    }
    p->count = pages;
    return ESP_OK;
}

esp_err_t IRAM_ATTR s3_spi_prepare(s3_spi_port *p, unsigned stream, unsigned epoch,
                          uint32_t offset, void *payload, unsigned pages)
{
    if (!p || !p->device || p->busy || p->poisoned) return ESP_ERR_INVALID_STATE;
    p->count = 0;
    if (!payload || pages == 0 || pages > S3_SPI_MAX_SEGMENTS) return ESP_ERR_INVALID_ARG;
    void *buffers[S3_SPI_MAX_SEGMENTS];
    for (unsigned i = 0; i < pages; ++i) buffers[i] = (uint8_t *)payload + i*S3_PAGE_BYTES;
    return s3_spi_prepare_pages(p, stream, epoch, offset, buffers, pages);
}

esp_err_t IRAM_ATTR s3_spi_prepare_credit_status(s3_spi_port *p,unsigned epoch,void *response)
{
    if(!p||!p->device||p->busy||p->poisoned)return ESP_ERR_INVALID_STATE;
    p->count=0;
    uint8_t *b=response;
    if(p->host!=SPI2_HOST||p->lanes!=8||!p->sct||!epoch||epoch>UINT16_MAX||
       !b||((uintptr_t)b&3)||!esp_ptr_internal(b)||!esp_ptr_internal(b+15)||
       !esp_ptr_dma_capable(b)||!esp_ptr_dma_capable(b+15))return ESP_ERR_INVALID_ARG;
    spi_multi_transaction_t *s=&p->segments[0];
    memset(s,0,sizeof(*s));
    s->base.flags=SPI_TRANS_MODE_OCT|SPI_TRANS_MULTILINE_CMD|
        SPI_TRANS_MULTILINE_ADDR|SPI_TRANS_DMA_BUFFER_ALIGN_MANUAL;
    s->base.cmd=0xd71c;s->base.addr=((uint64_t)epoch<<48)|16;
    s->base.rxlength=128;s->base.rx_buffer=response;s->base.user=p;
    s->seg_trans_flags=SPI_MULTI_TRANS_DUMMY_LEN_UPDATED;s->dummy_bits=16;
    s->sct_gap_len=1;p->count=1;
    return ESP_OK;
}

esp_err_t IRAM_ATTR s3_spi_queue(s3_spi_port *p)
{
    if (!p || !p->device || p->busy || p->poisoned || !p->count)
        return ESP_ERR_INVALID_STATE;
    p->busy = true;
    esp_err_t err = p->sct ? spi_device_queue_multi_trans(p->device, p->segments, p->count, 0) :
                            spi_device_queue_trans(p->device, &p->segments[0].base, 0);
    /* SCT error paths in this pinned SDK may already own DMA descriptors.
     * Do not recycle payload or silently retry after any unexpected failure. */
    if (err != ESP_OK) p->poisoned = true;
    return err;
}

esp_err_t IRAM_ATTR s3_spi_reap(s3_spi_port *p)
{
    if (!p || !p->device || !p->busy || p->poisoned) return ESP_ERR_INVALID_STATE;
    esp_err_t err;
    void *completed = NULL;
    if (p->sct) {
        spi_multi_transaction_t *done = NULL;
        err = spi_device_get_multi_trans_result(p->device, &done, 0); completed = done;
    } else {
        spi_transaction_t *done = NULL;
        err = spi_device_get_trans_result(p->device, &done, 0); completed = done;
    }
    if (err == ESP_ERR_TIMEOUT) return err;
    if (err != ESP_OK || completed != &p->segments[0]) {
        p->poisoned = true; return err == ESP_OK ? ESP_ERR_INVALID_STATE : err;
    }
    p->busy = false; p->count = 0;
    return ESP_OK;
}

esp_err_t s3_spi_close(s3_spi_port *p)
{
    if (!p || !p->device || p->busy || p->poisoned) return ESP_ERR_INVALID_STATE;
    esp_err_t err = p->sct ? spi_bus_multi_trans_mode_enable(p->device, false) : ESP_OK;
    if (err == ESP_OK) err = spi_bus_remove_device(p->device);
    if (err != ESP_OK) return err;
    p->device = NULL;
    return spi_bus_free(p->host);
}

static esp_err_t IRAM_ATTR rf_submit(s3_rf_transfer *x, s3_spi_port *p, s3_tx_ring *r,
                                    s3_page_credit *credit,unsigned pages)
{
    if (!x || !p || !r || pages == 0 || pages > 3 || pages > p->capacity)
        return ESP_ERR_INVALID_ARG;
    if (x->count || p->busy || p->poisoned) return ESP_ERR_INVALID_STATE;
    if(credit){
        if(credit->epoch!=r->epoch||credit->poisoned||!credit->synced)
            return ESP_ERR_INVALID_STATE;
        uint32_t used=(credit->next-credit->retired)&0xfffff;
        if(used>credit->window){s3_credit_poison(credit);return ESP_ERR_INVALID_STATE;}
        if(pages>credit->window-used)return ESP_ERR_NOT_FINISHED;
    }
    void *buffers[3];
    unsigned taken = 0;
    for (; taken < pages; ++taken) {
        const uint8_t *buffer;
        if (s3_ring_take(r, &x->leases[taken], &buffer) != S3_OK) break;
        buffers[taken] = (void *)buffer;
    }
    esp_err_t err = taken == pages ? s3_spi_prepare_pages(p, S3_RF, r->epoch,
        x->leases[0].sequence * S3_PAGE_BYTES, buffers, pages) : ESP_ERR_NOT_FINISHED;
    if (err != ESP_OK) {
        while (taken) {
            if (s3_ring_undo_take(r, x->leases[--taken]) != S3_OK) {
                p->poisoned = true; return ESP_ERR_INVALID_STATE;
            }
        }
        return err;
    }
    x->ring = r; x->port = p; x->count = pages;
    if(credit){
        uint32_t first;
        if(s3_credit_reserve(credit,pages,&first)!=S3_OK||
           first!=(x->leases[0].sequence&0xfffff)){
            p->poisoned=true;s3_credit_poison(credit);return ESP_ERR_INVALID_STATE;
        }
    }
    err=s3_spi_queue(p);
    if(err!=ESP_OK&&credit)s3_credit_poison(credit);
    return err;
}

esp_err_t IRAM_ATTR s3_rf_submit(s3_rf_transfer *x,s3_spi_port *p,s3_tx_ring *r,unsigned pages)
{
    return rf_submit(x,p,r,NULL,pages);
}

esp_err_t IRAM_ATTR s3_rf_submit_credited(s3_rf_transfer *x,s3_spi_port *p,
                                        s3_tx_ring *r,s3_page_credit *credit,unsigned pages)
{
    if(!credit)return ESP_ERR_INVALID_ARG;
    return rf_submit(x,p,r,credit,pages);
}

esp_err_t IRAM_ATTR s3_rf_reap(s3_rf_transfer *x)
{
    if (!x || !x->count || !x->port || !x->ring) return ESP_ERR_INVALID_STATE;
    esp_err_t err = s3_spi_reap(x->port);
    if (err != ESP_OK) return err;
    for (unsigned i = 0; i < x->count; ++i) {
        if (s3_ring_complete(x->ring, x->leases[i]) != S3_OK) {
            x->port->poisoned = true; return ESP_ERR_INVALID_STATE;
        }
    }
    x->count = 0;
    return ESP_OK;
}
