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
- 64-state path metrics: eight banks of even/odd metric pairs
- synchronous metric prefetch; four-clock reset initialization
- two read ports per bank mapped to 16 replicated Gowin BSRAMs
- metric arrays have clock-only processes, without asynchronous reset
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

The controllers have separate state machines and data paths. The 4K engine
drives its single channel. The independent 9K implementation selects one of two
physical x8 channels, captures that selection for the transfer, and shares its
own control/serialization logic across the dies for one outstanding request.
It does not instantiate the HyperRAM controller or duplicate a state machine
per die when transfers cannot overlap.
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

The four full-design jobs remain, with four synthesis/packing diagnostics added:

| Job | Viterbi | RS | Memory controller |
|---|---:|---:|---|
| `4k / core-only` | yes | yes | none |
| `4k / mem` | yes | yes | HyperRAM, one x8 channel |
| `9k / core-only` | yes | yes | none |
| `9k / mem` | yes | yes | PSRAM, two x8 channels |
| `4k / viterbi-only` | yes | no | none; synthesis/packing only |
| `4k / rs-only` | no | yes | none; synthesis/packing only |
| `9k / viterbi-only` | yes | no | none; synthesis/packing only |
| `9k / rs-only` | no | yes | none; synthesis/packing only |

`core-only` uses identical RTL and explicit parameters (`WITH_MEM=0`, `PSRAM=0`,
`WITH_VITERBI=1`, `WITH_RS=1`) on both devices. Its generated synthesis script is
checked for equality in CI. The decoder RTL is the same in `core-only` and `mem`.
Diagnostics disable exactly one decoder and use nextpnr `--pack-only` to obtain
comparable packed resources without running placement/routing. A successful
packing diagnostic does not establish that the design fits or meets timing.

Resource differences between `mem` and `core-only` include stimulus, observation
and synthesis/packing changes across the whole design. They are **not an isolated
controller cost**; the earlier 9K mem result was smaller than core-only despite
adding a controller. Fmax is measured separately for each routed design.

## Toolchain

GitHub Actions uses OSS CAD Suite 2026-10-04:

- Yosys `synth_gowin`
- nextpnr-himbaechel
- Project Apicula device database

The CI does place-and-route, not synthesis-only, so timing is based on a routed design.

## Result

Measurements use the pinned toolchain below; resources are consistently the
**packed utilization before placement**, including overflow. Final JSON utilization
can account for shared LUT/ALU/RAM occupancy differently and is retained as raw
evidence, but is not mixed into this comparison. All DSP primitives used: **0**.

Baseline CI at [`2af4a69`](https://github.com/kazuki0824/tangviterbi/commit/2af4a699790a8077011d0c81e75ed42081aa94bd):

| Board / variant | LUT4 used / available | FF | BSRAM | P&R at 110 MHz | Routed Fmax |
|---|---:|---:|---:|---|---|
| 4K / core-only | 7266 / 4608 | 3164 | 3 / 10 | FAIL: placement | not measured |
| 4K / mem | 7271 / 4608 | 3290 | 3 / 10 | FAIL: placement | not measured |
| 9K / core-only | 7266 / 8640 | 3164 | 3 / 26 | FAIL: placement | not measured |
| 9K / mem | 6844 / 8640 | 3302 | 3 / 26 | FAIL: placement | not measured |

The baseline single-decoder measurements found **Viterbi 3073 LUT / 2311 FF / 2
BSRAM**, versus **RS 4420 LUT / 885 FF / 1 BSRAM**, on both boards. RS has more
packed LUTs and most wide MUXs: MUX2_LUT5/6/7/8 = 1588/719/328/137 for RS,
317/26/12/0 for Viterbi. The combined 7266 LUT result cannot be partitioned by
adding isolated measurements because the harness and optimization differ.
See [measurement details](reports/metric-storage.md) for provenance/reproduction.

After the banked BSRAM metric change (local runs of this RTL with the same pin/tool
settings; CI repeats all eight jobs):

| Board / variant | LUT4 used / available | FF | BSRAM | Placement / routing | Routed Fmax | 100.8 / 110 MHz |
|---|---:|---:|---:|---|---:|---|
| 4K / core-only | 6298 / 4608 | 1637 | 19 / 10 | FAIL: capacity | not measured | unknown |
| 4K / mem | 6290 / 4608 | 1763 | 19 / 10 | FAIL: capacity | not measured | unknown |
| 9K / core-only | 6298 / 8640 | 1637 | 19 / 26 | completed | 37.04 MHz | FAIL / FAIL |
| 9K / mem | 6512 / 8640 | 1775 | 19 / 26 | completed | 37.40 MHz | FAIL / FAIL |
| 4K / viterbi-only | 2330 / 4608 | 784 | 18 / 10 | not run (diagnostic) | not measured | unknown |
| 4K / rs-only | 4196 / 4608 | 885 | 1 / 10 | not run (diagnostic) | not measured | unknown |
| 9K / viterbi-only | 2330 / 8640 | 784 | 18 / 26 | not run (diagnostic) | not measured | unknown |
| 9K / rs-only | 4196 / 8640 | 885 | 1 / 26 | not run (diagnostic) | not measured | unknown |

The new core uses 968 fewer packed LUTs and 1527 fewer FFs, at the cost of 16
additional BSRAMs. The synthesized metric banks are 16 `SDPX9B` primitives.
9K now reaches legal placement and routing, but **does not meet the throughput
clock requirement**, so its full-design CI jobs remain red on timing. The
37.04 MHz core critical path is in RS. The unchanged RS source also shows a
packing difference in the diagnostics after the Viterbi source changes; these
numbers describe whole synthesis runs, not exact isolated architectural deltas.

The 4K core remains above LUT capacity (136.7%) and BSRAM capacity (190%). Stop
placement tuning for this architecture. A 4K solution would require another
storage/resource architecture, not placement settings alone.

Next work: reduce/serialize RS polynomial-array selection and pipeline its
arithmetic/selection path, with functional and cycle-budget validation; rerun
9K core first against 100.8 and 110 MHz, then reassess 9K mem. RAM-controller
results remain protocol-only models with the exclusions stated above.

CI uploads raw synthesis/P&R logs, the synthesis script, any nextpnr JSON report,
and a separate summary for each job. Every summary uses packed utilization from the log, labelled as such; JSON
utilization is a fallback only if packed counts are absent. Fmax remains unknown unless
an achieved routed clock value is available; the requested 110 MHz is never used
as a measured Fmax. Partial JSON clock estimates are ignored until routing
completes; log fallback uses only the clocks printed after routing completion.
A failed fit/timing result intentionally makes the job fail.

## Scope

A PASS at 110 MHz means the selected FPGA implementation has enough routed clock margin for the 16-ACS throughput assumption. It does not prove a complete ISDB-T receiver. RF acquisition, depuncturing/interleaving integration, S31↔FPGA transport, clock-domain crossings, and bit-exact end-to-end verification remain separate tasks.
