#ifndef S3_TRANSPORT_H
#define S3_TRANSPORT_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdatomic.h>

/* Experimental wire contract v1. Each payload is 4096 bytes, unmodified.
 * Command: D7 1s, s=1 RF write, 2 FFT write, B IQ read request.
 * Address, MSB first: epoch[15:0], byte_offset[31:0], length[15:0].
 * Offset wraps modulo 2^32. All command/address/data phases use 4 or 8 lanes.
 * The request header cannot certify FPGA freshness; endpoint status/ready
 * and electrical integrity still need an implementation and validation.
 */
enum { S3_PAGE_BYTES = 4096, S3_RING_PAGES = 8, S3_RING_BYTES = 32768 };
enum s3_stream { S3_RF = 1, S3_FFT = 2, S3_IQ = 11 };
enum s3_result { S3_OK, S3_BUSY, S3_EMPTY, S3_STALE, S3_RANGE, S3_EXHAUSTED };
typedef struct { uint16_t command; uint64_t address; } s3_wire_header;
int s3_wire_make(s3_wire_header *out, unsigned stream, unsigned epoch,
                 uint32_t offset, size_t bytes);
int s3_wire_read(s3_wire_header header, unsigned *stream, unsigned *epoch,
                 uint32_t *offset, size_t *bytes);
void s3_wire_bytes(s3_wire_header header, uint8_t out[10]);

typedef struct { uint32_t sequence; uint16_t epoch; } s3_lease;
typedef struct { atomic_uint state; uint32_t sequence; } s3_ring_page;
typedef struct {
    uint8_t *payload;
    s3_ring_page pages[S3_RING_PAGES];
    uint32_t write_sequence;  /* one producer only */
    uint32_t submit_sequence, retire_sequence; /* one scheduler only */
    uint16_t epoch;           /* reset only while both roles are stopped */
} s3_tx_ring;

/* One producer and one scheduler may run concurrently. The scheduler owns
 * take/undo/complete, even for two SPI ports. Complete is called only after
 * the SDK returns the transaction. No callback/ISR concurrently edits this
 * object. Payload is never copied here and remains leased until retirement.
 */
int s3_ring_init(s3_tx_ring *ring, void *payload, size_t size, unsigned epoch);
int s3_ring_begin(s3_tx_ring *ring, s3_lease *lease, uint8_t **payload);
int s3_ring_publish(s3_tx_ring *ring, s3_lease lease);
int s3_ring_cancel_write(s3_tx_ring *ring, s3_lease lease);
int s3_ring_take(s3_tx_ring *ring, s3_lease *lease, const uint8_t **payload);
int s3_ring_undo_take(s3_tx_ring *ring, s3_lease lease);
int s3_ring_complete(s3_tx_ring *ring, s3_lease lease);
/* Explicit mode-stop operation: producer stopped; no FILLING or INFLIGHT
 * pages. Discards unsent old-mode data, advances epoch, never wraps epoch.
 */
int s3_ring_reset(s3_tx_ring *ring);

/* Low 20 bits are the source's native I10/Q10 fields. No decimation or
 * quantization. Input may end between samples/pairs and output between pages.
 * BUSY preserves pending bytes; consumed counts words already owned here.
 */
typedef struct {
    s3_tx_ring *ring;
    s3_lease writing;
    uint8_t *page;
    unsigned used, pending_index, pending_size;
    uint8_t pending[5];
    uint32_t first;
    bool have_first;
} s3_iq10_packer;
void s3_iq10_init(s3_iq10_packer *packer, s3_tx_ring *ring);
int s3_iq10_push(s3_iq10_packer *packer, const uint32_t *words, size_t count, size_t *consumed);
int s3_iq10_discard(s3_iq10_packer *packer); /* mode stop only */

/* Scheduler clock is the coordinator core's extended 240-MHz cycle count.
 * These bounds MUST be supplied/validated by the caller; zero-copy and SCT
 * do not prove them. Zero means wait for more RF pages or service the FFT.
 */
typedef struct { uint32_t API_cycles, segment_cycles; } s3_batch_timing;
unsigned s3_t_rf_batch(unsigned available_pages, uint64_t now, uint64_t fft_release,
                       uint64_t fft_deadline, uint64_t three_pages_ready,
                       s3_batch_timing timing);

#endif
