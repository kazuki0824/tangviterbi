# tangviterbi

Resource/timing benchmark for an ISDB-T-oriented FEC partition on Sipeed Tang Nano 9K.

The benchmark answers a specific sizing question:

> Can a 16-ACS, K=7 Viterbi decoder with 8-bit soft metrics, a compact RS(204,188) decoder, and a small two-channel PSRAM protocol controller fit and meet the clock budget on Tang Nano 9K?

## Throughput target

The workload stays at full ISDB-T 6-MHz, 13-segment capacity. From the published
maximum TS rate and RS overhead, use an upward-rounded **25.22 Mstep/s** profile.
The current 16 ACS lanes require four clocks/step, hence **100.88 MHz** for
Viterbi alone. **110 MHz remains the routed implementation target.**

The serialized RS engine must also finish a complete 204-byte block, including
188-byte output, in **7118 clocks at 110 MHz**. Its conservative degree-8 bound
is 6766 clocks; adding pipeline cycles without checking the service rate can
break throughput even after timing improves. See the
[performance contract and concrete next steps](reports/performance.md).
The job driver/report/test share [performance.json](ci/performance.json).

Target FPGA: **GW1NR-LV9QN88PC6/I5**. This ISDB-T profile does not yet size ISDB-S.

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
- 64-step survivor store with byte-prefetched traceback selection

### RS(204,188)

`rtl/rs204_188_compact.sv`

The RS block is deliberately serialized to minimize logic:

- two GF(256) operand paths, each built from four DSP carryless subproducts
- registered one-hot coefficient selectors and constant per-entry writes
- coefficient and GF operand prefetch without added service cycles
- 16 syndromes
- sequential Berlekamp-Massey
- sequential Chien search
- sequential Forney path
- 204-byte block buffer

This architecture is intended to represent a small hardware decoder, not the large fully-parallel generic RS cores that inflate the sizing estimate.

**Important:** the shortened-code symbol-position convention and final Forney correction mapping still need bit-exact validation against ARIB-compatible test vectors. Until then, this block is suitable for **resource/timing sizing**, not as a production-qualified RS decoder.

### Memory controller

The `mem` variant uses `rtl/psram_ctrl.sv`: two x8 PSRAM channels, each with
21-bit word addressing and wrapped-burst command/address layout. The upper
word-address bit selects the die; the engine handles one outstanding request
and shares control/serialization across the two physical x8 channels.
The harness uses aligned 32-bit transfers, stimulates both dies and observes
all controller output bits.

This is a **protocol-only sizing model**. Each clock transfers one byte through
an abstract PHY; RWDS latency selection is supplied at request acceptance.
DDR serialization, physical RWDS timing, power-up/register initialization,
PLLs, actual memory I/O placement and calibration are excluded. The 110-MHz
logic target does not establish a RAM bus speed or a working memory interface.

Interface references:

- [9K PSRAM controller interface and die layout](https://github.com/zf3/psram-tang-nano-9k)
- [Winbond W955D8MBYA command/address definition](https://www.winbond.com/hq/search/?__locale=en&q=W955D8MBYA)

The reference sources are not vendored.

## CI variants

Four 9K-only jobs run:

| Job | Viterbi | RS | Memory | Measurement |
|---|---:|---:|---|---|
| `9k / core-only` | yes | yes | none | synthesis + P&R |
| `9k / mem` | yes | yes | PSRAM, two x8 channels | synthesis + P&R |
| `9k / viterbi-only` | yes | no | none | synthesis + packing |
| `9k / rs-only` | no | yes | none | synthesis + packing |

The same decoder RTL is used in core and mem. Diagnostics disable exactly one
decoder; packing success does not establish a fit or achieved timing.
Resource differences between mem and core include stimulus, observation and
whole-design optimization, and are not an isolated controller cost.

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
evidence, but is not mixed into this comparison. DSP usage is listed explicitly per measured variant.

The latest 9K implementation uses registered one-hot coefficient selection,
constant per-entry writes, separate coefficient/feedback GF paths and a
byte-prefetched Viterbi traceback. Measurements use OSS CAD Suite 2026-10-04,
the unchanged 110-MHz constraint and default seed. The previous revision is
[`74cebe5`](https://github.com/kazuki0824/tangviterbi/commit/74cebe50ba8e58300620e5f4b780060ba49d827b),
verified by [CI run 37238039476](https://github.com/kazuki0824/tangviterbi/actions/runs/37238039476).

| Variant | LUT4 before → after | FF after | BSRAM after | MULT18X18 after | Routed Fmax before → after | 110 MHz |
|---|---:|---:|---:|---:|---:|---|
| core-only | 4422 → 4052 | 1775 | 19 | 8 | 72.54 → 83.80 MHz | FAIL |
| mem | 4545 → 4217 | 1913 | 19 | 8 | 79.02 → 88.57 MHz | FAIL |
| viterbi-only | 2440 → 2440 | 792 | 18 | 0 | not routed | unknown |
| rs-only | 2066 → 1992 | 1015 | 1 | 8 | not routed | unknown |

Core / mem Fmax improves by 15.52% / 12.09%, with LUT4 reduced by 8.37% / 7.22%.
Both complete routing but still fail the 110-MHz target and full-rate clock
floors. DSP usage rises from four to eight MULT18X18, with 19 BSRAMs unchanged.
The sixteen tests include exhaustive GF products, cycle-exact RS comparison
for 48 blocks plus twelve processing reset interruptions, service deadlines
and 4000 Viterbi recurrence/output steps. RS service clocks and four Viterbi
clocks/step are unchanged.

[Latest implementation, alternatives and remaining timing paths](reports/control-storage.md)
include [measurement JSON and exact RTL hashes](reports/control-storage.json).
The [first optimization stage](reports/performance-optimization.md),
[historical metric BSRAM results](reports/metric-storage.md) and
[performance contract](reports/performance.md) remain available.

CI uploads raw synthesis/P&R logs, the synthesis script, any nextpnr JSON report,
and a separate summary for each job. Every summary uses packed utilization from the log, labelled as such; JSON
utilization is a fallback only if packed counts are absent. Fmax remains unknown unless
an achieved routed clock value is available; the requested 110 MHz is never used
as a measured Fmax. Partial JSON clock estimates are ignored until routing
completes; log fallback uses only the clocks printed after routing completion.
A failed fit/timing result intentionally makes the job fail.

## Scope

A timing PASS at 110 MHz establishes clock margin. Sustained throughput also requires the per-step/per-block service budgets and bounded buffering. It does not prove a complete ISDB-T receiver. RF acquisition, depuncturing/interleaving integration, S31↔FPGA transport, clock-domain crossings, and bit-exact end-to-end verification remain separate tasks.
