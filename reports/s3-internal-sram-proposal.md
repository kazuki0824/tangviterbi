# ESP32-S3-WROOM-1U-N16R8 + Tang Nano 9K: two-change proposal

This is a receiver implementation proposal, not a qualified receiver. T and
legacy S use separate bitstreams in the board's external SPI NOR flash and
reuse resources after stopping reception. No extra software decimation or
requantization is allowed. Packing native I10/Q10 into 20 bits is lossless.

## Proposed ownership

| Mode | ESP32-S3 | FPGA | TS endpoint |
|---|---|---|---|
| T | RF acquisition/control, lossless packing, 8192-point Q15 complex FFT | FIR/rate conversion, synchronization, equalization/demapping, time deinterleave, Viterbi, RS, TS | FPGA serial TS |
| S | RF acquisition/control, lossless packing | FIR/rate conversion, synchronization, TC8PSK, frame deinterleave, RS, TS | Same FPGA serial TS pins |

The prior finite-model IDs are `S3-T-004/v0` and `S3-S-000/v0`.
All rates are decimal MB/s; memory sizes are bytes.

## Change 1: measure an additional RS area reduction

The prior receiver estimate already replaced both DSP-based GF multipliers
with Boolean GF(256) logic. Repeating that replacement is not a new saving.
`experiments/s3_rs_area.py` builds that exact dual-multiplier baseline and
an additional single-multiplier candidate from the same constant-syndrome RTL.
The original adopted RTL and its CI timing targets are retained.

The shared-multiplier candidate keeps the two operand-register banks and selects the bank
whose product is consumed in the current state. Coefficient-consuming states
are BM_DISC, BM_COEF, BM_UPDATE and OMEGA_ACC. Other product-consuming states
use feedback. No service cycles or soft-input precision are changed.
The controlled alternatives also include LUT4-only mapping without any RTL
change and removal of polynomial-array asynchronous resets whose values are
initialized in BM_INIT before consumption. The reset alternative retains
the FSM, output and syndrome resets and gates writes during reset.

The prior zero-DSP module anchor is 1978 LUT + 107 ALU = 2085 conservative
logic equivalents, 960 FF, one BSRAM. T's whole-receiver budget is 8681/8640
logic equivalents: the additional reduction must exceed 41 **and** preserve
resource/timing constraints. LUT+ALU is an estimate convention, not a claim
that isolated cell sums prove physical packing of the whole receiver.

The PR workflow compares module counts using the same pinned OSS CAD Suite
2026-10-04 and routes core/mem and isolated-RS partial benchmarks at 125 MHz,
seed 1. An isolated RS clock result diagnoses a possible separate fast RS
domain; it does not prove the CDC or full receiver.
Actual results and revised receiver budgets will be recorded after CI.
Routing completion is distinct from meeting the 125 MHz target. S's actual
receiver RS floor is 121.475625 MHz for this 3502-cycle engine; the existing
repository's lower-rate S sizing profile cannot substitute for that floor.

## Change 2: put FFT transfer staging in internal SRAM

| Allocation | T bytes | S bytes |
|---|---:|---:|
| Existing OS/control reservation | 65536 | 65536 |
| Two active links, two 4092-byte banks each | 16368 | 16368 |
| RF capture reservation | 32768 | 32768 |
| FFT work/twiddle/swap reservation | 98304 | 0 |
| Two input epochs (33792 bytes each) | 67584 | 0 |
| Two output epochs (32768 bytes each) | 65536 | 0 |
| Total | **346096** | **114672** |
| Remainder against 524288 physical bytes | **178192** | **409616** |

Use fixed, aligned `MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA | MALLOC_CAP_8BIT`
allocations for the transfer buffers. Never silently fall back to PSRAM.
Allocate before RF start; failure prevents receiver start. DMA descriptors,
ISR code, task stacks and actual RF driver state must be included in the
linker map/heap audit; 512 KiB physical SRAM is not the available DMA heap.
The 64 KiB reservation is a budget, not measured firmware usage.

This moves 133120 bytes and 128.061568 MB/s of intermediate write+read traffic
off PSRAM. The selected T mode has no remaining modeled SoC PSRAM DSP traffic.
That traffic now loads internal SRAM; it has not disappeared. Simultaneous
RF capture, FFT and both link DMA channels require a measured service bound.
Do not infer a CPU-cycle saving without measurements.

## Transfer contract and outstanding gates

T boundaries: SoC -> FPGA RF 40.000000 MB/s and FFT bins 31.522848 MB/s;
FPGA -> SoC synchronized Q15 IQ 32.507937 MB/s. S: SoC -> FPGA RF
100.000000 MB/s. The candidate common wiring is LCD16 at 40 MHz plus
80 MHz quad SPI (SoC master, FPGA slave). SPI is half duplex: both
directions share one capacity. Payload 4092 bytes, 16-byte framing, 0.3 us
SPI command and a budgeted 2 us gap give 38.971429 MB/s effective SPI;
LCD's effective payload rate is 79.688413 MB/s. These are design contracts,
not measured DMA bandwidth. Alternative feasible port sets must be retained
in the revised route enumeration.

Remaining gates include: continuous gap-free RF sample acquisition at the
specified rates; DSP kernel WCET and core scheduling; physical SRAM/DMA
availability and arbitration; full-receiver synthesis/P&R including CDC,
real PSRAM PHY and actual pins; S TC8PSK and ARIB decoder qualification;
external RF conversion/filtering/tuning appropriate to both bands; valid TS
capture at the external endpoint; two-image NOR boot/reconfiguration and
reset/Hi-Z behavior. Background programming is permitted only for the
onboard external NOR multiple-bitstream arrangement. No SPI-flash update
is part of uninterrupted reception.

Sources: [ESP32-S3 memory allocation](https://docs.espressif.com/projects/esp-idf/en/v5.2/esp32s3/api-reference/system/mem_alloc.html),
[SPI master](https://docs.espressif.com/projects/esp-idf/en/v5.2/esp32s3/api-reference/peripherals/spi_master.html),
the attached prior finite receiver estimate, and the raw PR synthesis logs.
