# S3 / Tang Nano 9K communication implementation

Status: partial components, not an adopted receiver. Native I10/Q10 is retained;
there is no SoC decimation or requantization to fit these links.

## 2026-10-10 implementation and tests

| Added block | Verification | Not included |
|---|---|---|
| Two-port acknowledged page store | 64 pages / 262144 payload bytes, stalled requests, different acknowledgement delays, exact payload/order comparison | Physical PSRAM/read PHY |
| Registered page reservation | 4096 page descriptors, byte-offset wrap, window backpressure, seven fatal errors | Payload RAM in this metadata-only test |
| Quad/Octal IQ read endpoint | Eight 4096-byte pages per width, independent byte oracle, stopped-last-SCK completion, six fatal errors | S3 ready/status driver, external IO timing |
| Complete wire-to-store chain | 24 pages / 98304 bytes over concurrent Octal/Quad 80 MHz wires and a 99 MHz core; exact ordered payload in acknowledged memory model | Physical memory, full RF chain |
| RX overrun/overflow | Both widths, overlong write and FIFO exhaustion remain fatal after CS rises/SCK stops | Long-term electrical bit-error measurement |

The current pin-constrained result is in [s3-comm-endpoint.json](s3-comm-endpoint.json).
Final revision, seed 3: **1511 / 8640 LUT4 (17.49%), 879 / 6480 FF (13.56%),
4 / 26 BSRAM (15.38%)**, with core **100.2506 MHz**, SPI2 **123.6094 MHz**,
SPI3 **84.2886 MHz**. This meets internal targets 99 / 80 / 80 MHz; the core
frequency margin is only 1.26%. Seeds 1 and 2 fail and remain in the report.
All unsuccessful optimization trials are retained in
[results.json](s3-communication-evidence/results.json), not silently replaced by
successful clock values from a different design. The original integrated trial
was 1364 LUT4 / 795 FF / 4 BSRAM and failed the core target at 61.06 MHz.
Global SPI buffers remove the dedicated-clock-routing warnings in later trials.
Only the final routed Fmax, not the pre-route estimate, is used for judgement.
This benchmark has a synthetic IQ producer and a checksum/one-cycle-ack sink:
it is not a PSRAM bandwidth or complete-receiver benchmark.

## Page reception and order

`s3_spi_rx` receives mode-0 Octal/Quad headers and 4096-byte payloads through
an asynchronous FIFO. `s3_page_guard` rejects stale epochs and malformed pages.
Its absolute frame watchdog also detects a truncated frame when SCK stops;
write overrun/FIFO overflow poisons the receive epoch.

`s3_page_reorder` owns metadata for a 16-page external-memory ring for ONE
stream. Use distinct rings for RF and FFT-result streams. Two ports can reserve
different slots concurrently. Reservation offers are registered and serialized;
the data paths remain concurrent. A later page cannot be consumed before the
oldest page. New future pages wait for window credit rather than overwriting
live slots. Duplicates, old/unaligned offsets, stale epochs, unowned completions
and early retire requests poison the epoch.

Important integration contract:

- `finish[port]` means **all memory writes acknowledged and framing validated**,
  not merely receipt of the last SPI word.
- `retire` means the consumer finished its last read/consumption, not that it
  issued a read request.
- The epoch may change only with both ports, memory and consumer stopped/reset.
- Requests/addresses remain valid and unchanged until granted. Arithmetic is
  pipelined; the cached base is invalidated on ordered retirement. A pending
  offer is applied before another offer is made, preventing stale ownership.
- `s3_rx_page_store` connects two guards, token registers, a stable round-robin
  write offer, per-port outstanding acknowledgement counters and this reorder
  block. Only framing-valid AND completely acknowledged pages become visible.
- `s3_page_guard` validates the length before entering a separate reservation
  state, keeping wide header checks out of the credit path.
- Fatal errors mask public writes/pages immediately. Internal freeze has one
  registered cycle; tentative internal changes after poison cannot escape.
- Physical payload memory/read PHY and the pre-transfer credit/status channel
  remain outside these components.

The independent `unittest` test exercises 4096 pages (16 MiB address span),
32-bit byte-offset wrap, delayed/reversed acknowledgments, full-ring credit,
consumer stalls and seven fault types. This tests metadata, not 16 MiB of
physical memory data.

## FPGA-to-S3 IQ page lifetime

`s3_spi_iq_tx` contains one complete 4 KiB page. The core fills all 1024 words
before publishing a toggle to the SPI clock domain. RAM and bundled metadata
are immutable until the last payload sampling edge returns an acknowledgement
toggle through two synchronizer stages. No dummy wire clocks are added. The
wire format remains D71B / epoch16 / byte offset32 / length16, followed by
little-endian words. `s3_spi_rx.IGNORE_IQ_READ=1` suppresses these read headers
on the shared Quad bus.

Stale epoch, wrong offset, unpublished page, truncated transfer, explicit abort
and extra clocks poison the epoch. A core-clock watchdog catches a stopped SCK
mid-page. This is not CRC protection. Publication/acknowledgement synchronizers
are not substitutes for a physical bundled-data/Gray-bus constraint audit.

There is only one TX page buffer. Its 1024-word reload takes at least 10.344 us
at 99 MHz after the previous transfer releases ownership, plus CDC latency and
memory stalls. The scheduler must overlap this with the assumed 20 us API gap
or account for extra time. No ready/status transaction has yet been budgeted;
the earlier 33.395842 MB/s Quad figure remains conditional, not measured.

## Remaining budget is not integrated fit

The measured S metric/TC8PSK/RS partial design is 5602 LUT4, 3498 FF, 6 BSRAM,
2 MULT18X18 at 100.1603 MHz. Merely adding this communication benchmark gives
7113 LUT4 (82.33%), 4377 FF (67.55%) and 10 BSRAM (38.46%). The residual 1527
LUT4 is **not** a proved allowance for the missing synchronizers, filters,
TMCC/frame/deinterleavers, physical PSRAM, clocking and status system. Separate
benchmarks include artificial loads and may share/eliminate logic after
integration; their Fmax values cannot be combined into a full-design claim.

Each RX token register can accept one 32-bit word per two 99 MHz cycles:
49.5 Mword/s per port versus the wire maxima 20 / 10 Mword/s. The common write
port can offer one word per cycle, but a physical memory controller must
actually accept and acknowledge enough requests. FIFO_AW=5 is only 32 words
of main FIFO storage; at an Octal payload rate of 20 Mword/s that is about
1.6 us of elasticity, not a substitute for page-level credit. A physical-memory
timeout after wire commit is another integration requirement; the current
page guard watchdog alone does not bound a missing backend acknowledgement.

## Environment recovery

After workspace maintenance removed local files, 239 text files were restored
from PR head `749014b74f4d878f38ed8f43621351c26023be42` and checked against the
Git blob hashes. Remote-only evidence archives are preserved in the base tree.
Uncommitted later synthesis logs and the attempted local evidence archive did
not survive; results must be regenerated rather than presented as a new CI run.
The fixed OSS CAD suite 2026-10-04 was restored and its downloaded SHA256 checked:
`8a4708629b0f0afd5a1835aca8b44d224fec5f6e544c5fd22a060ea5514f83c9`.

## Still incomplete

Separate RF/FFT stream stores and their routing, physical PSRAM/DDR PHY and read
arbitration, the actual IQ page producer, status/credit firmware, final internal
timing closure, complete receiver clock/IO/CDC constraints, full T/S demodulation
and integrated S3 real-time software remain implementation gates. The partial
communication internal target is now met, but integration may invalidate it. Hardware tests
are also outstanding; these software/RTL gaps are not classified as hardware-only.
