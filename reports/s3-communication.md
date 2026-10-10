# S3 / Tang Nano 9K communication implementation

Status: partial components, not an adopted receiver. Native I10/Q10 is retained;
there is no SoC decimation or requantization to fit these links.

## Page reception and order

`s3_spi_rx` receives mode-0 Octal/Quad headers and 4096-byte payloads through
an asynchronous FIFO. `s3_page_guard` rejects stale epochs and malformed pages.
Its absolute frame watchdog also detects a truncated frame when SCK stops;
write overrun/FIFO overflow poisons the receive epoch.

`s3_page_reorder` owns metadata for a 16-page external-memory ring for ONE
stream. Use distinct rings for RF and FFT-result streams. Two ports can reserve
different slots simultaneously. A later page cannot be consumed before the
oldest page. New future pages wait for window credit rather than overwriting
live slots. Duplicates, old/unaligned offsets, stale epochs, unowned completions
and early retire requests poison the epoch.

Important integration contract:

- `finish[port]` means **all memory writes acknowledged and framing validated**,
  not merely receipt of the last SPI word.
- `retire` means the consumer finished its last read/consumption, not that it
  issued a read request.
- The epoch may change only with both ports, memory and consumer stopped/reset.
- The payload memory, memory arbitration, physical PSRAM and pre-transfer
  credit/status channel are not implemented by this metadata component.

The independent `unittest` test exercises 4096 pages (16 MiB address span),
32-bit byte-offset wrap, delayed/reversed acknowledgments, full-ring credit,
consumer stalls and seven fault types. This tests metadata, not 16 MiB of
physical memory data.

## Environment recovery

After workspace maintenance removed local files, 239 text files were restored
from PR head `749014b74f4d878f38ed8f43621351c26023be42` and checked against the
Git blob hashes. Remote-only evidence archives are preserved in the base tree.
Uncommitted later synthesis logs and the attempted local evidence archive did
not survive; results must be regenerated rather than presented as a new CI run.
The fixed OSS CAD suite 2026-10-04 was restored and its downloaded SHA256 checked:
`8a4708629b0f0afd5a1835aca8b44d224fec5f6e544c5fd22a060ea5514f83c9`.

## Still incomplete

FPGA-to-S3 IQ read endpoint, two-port payload-memory integration, physical PSRAM,
status/credit firmware, complete receiver clock/IO/CDC constraints and integrated
real-time reception remain separate implementation gates. Hardware tests are
also outstanding; these software/RTL gaps are not classified as hardware-only.
