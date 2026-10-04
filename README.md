# tangviterbi

Resource/timing benchmark for an ISDB-T-oriented FEC partition on Sipeed Tang Nano 4K and Tang Nano 9K.

The benchmark answers a specific sizing question:

> Can a 16-ACS, K=7 Viterbi decoder with 8-bit soft metrics, a compact RS(204,188) decoder, and a small HyperRAM/PSRAM protocol controller fit and meet the clock budget on Tang Nano 4K or 9K?

## Throughput target

The working worst-case budget for 13-seg ISDB-T is:

- trellis rate: about **25.2 Mstep/s**
- 16 ACS lanes: **4 cycles per trellis step**
- minimum FEC clock: about **100.8 MHz**
- CI timing target: **110 MHz**

Targets:

| Board | FPGA |
|---|---|
| Tang Nano 4K | GW1NSR-LV4CQN48PC7/I6 |
| Tang Nano 9K | GW1NR-LV9QN88PC6/I5 |

## RTL

### Viterbi

`rtl/viterbi_k7_16acs.sv`

- K=7
- mother code generators 171/133 octal
- 8-bit unsigned soft inputs
- 16 ACS lanes
- four clocks per trellis step
- banked 64-state path metrics
- 64-step survivor store

### RS(204,188)

`rtl/rs204_188_compact.sv`

The RS block is deliberately serialized to minimize logic:

- one shared GF(256) multiplier
- 16 syndromes
- sequential Berlekamp-Massey
- sequential Chien search
- sequential Forney path
- 204-byte block buffer

This architecture is intended to represent a small hardware decoder, not the large fully-parallel generic RS cores that distort the 4K/9K comparison.

**Important:** the shortened-code symbol-position convention and final Forney correction mapping still need bit-exact validation against ARIB-compatible test vectors. Until then, this block is suitable for **resource/timing sizing**, not as a production-qualified RS decoder.

### Memory controller

The `mem` variant selects the controller for the board:

- 4K: `rtl/hyperram_ctrl.sv`, one x8 HyperRAM channel, 22-bit word
  address, linear-burst command/address layout.
- 9K: `rtl/psram_ctrl.sv`, two independent x8 PSRAM channels, each with
  a 21-bit word address and wrapped-burst command/address layout. The upper
  word-address bit selects the die; this is not a single x16 channel.

Both controllers use the same serialized x8 command/address/data engine.
The 9K wrapper adds a second engine, request decoding and read-data selection.
The harness uses aligned 32-bit reads/writes and stimulates both dies. All
controller data/control output bits feed the activity sink to keep both channels
observable to synthesis. A busy signal prevents requests while a transfer runs.

These are **protocol-only sizing models**. Each clock transfers one byte to/from
an abstract PHY; RWDS latency selection is supplied by the harness at request
acceptance. Physical DDR serialization, RWDS capture timing, register/power-up
initialization, PLLs, I/O placement and calibration are excluded. The `mem`
result measures this open RTL overhead, not a complete working RAM interface.
The measured 110 MHz is the logic clock and is not a RAM bus speed guarantee.

Interface references:

- [Sipeed 4K HyperRAM example](https://github.com/sipeed/TangNano-4K-example/tree/main/camera_hdmi/src/hyperram_memory_interface)
- [9K PSRAM controller interface and die layout](https://github.com/zf3/psram-tang-nano-9k)
- [Winbond W955D8MBYA command/address definition](https://www.winbond.com/hq/search/?__locale=en&q=W955D8MBYA)

The reference sources are not vendored; this benchmark remains self-contained.

## CI variants

Exactly four jobs run:

| Job | Viterbi | RS | Memory controller |
|---|---:|---:|---|
| `4k / core` | yes | yes | none |
| `4k / mem` | yes | yes | HyperRAM, one x8 channel |
| `9k / core` | yes | yes | none |
| `9k / mem` | yes | yes | PSRAM, two x8 channels |

`core` uses identical RTL and parameters on both devices. The Viterbi and RS
implementations are unchanged between `core` and `mem`. Use `mem - core` on
the **same device and revision** for controller/harness resource overhead.
That delta includes the stimulus and activity sink as well as the controller;
Fmax is measured separately for each full design and is not an additive delta.
The former Viterbi-only jobs are removed from this comparison.

## Toolchain

GitHub Actions uses OSS CAD Suite 2026-10-04:

- Yosys `synth_gowin`
- nextpnr-himbaechel
- Project Apicula device database

The CI does place-and-route, not synthesis-only, so timing is based on a routed design.

## Result

The table below is updated from the CI results after the implementation converges.

| Target | Variant | P&R | LUT/logic | FF | BSRAM | DSP | Routed Fmax | 110 MHz |
|---|---|---|---:|---:|---:|---:|---:|---|
| Tang Nano 4K | core | pending | | | | | | |
| Tang Nano 4K | mem | pending | | | | | | |
| Tang Nano 9K | core | pending | | | | | | |
| Tang Nano 9K | mem | pending | | | | | | |

CI uploads raw synthesis/P&R logs, the synthesis script, any nextpnr JSON report,
and a separate summary for each job. If placement fails, the summary still shows
packed utilization from the log, labelled as such. Fmax remains unknown unless
an achieved routed clock value is available; the requested 110 MHz is never used
as a measured Fmax. A failed fit/timing result intentionally makes the job fail.

## Scope

A PASS at 110 MHz means the selected FPGA implementation has enough routed clock margin for the 16-ACS throughput assumption. It does not prove a complete ISDB-T receiver. RF acquisition, depuncturing/interleaving integration, S31↔FPGA transport, clock-domain crossings, and bit-exact end-to-end verification remain separate tasks.
