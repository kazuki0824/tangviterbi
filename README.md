# tangviterbi

> **S3-N16R8 receiver audit (2026-10-09): not a qualified receiver.**
> The legacy Viterbi benchmark below fails an independent no-noise decoding
> test. Its old Fmax numbers do not qualify a working receiver decoder.
> A reverse-traceback experiment now passes independent bit/metric/reset
> tests, but the measured combined FEC still fails the 99 MHz shared clock.
> See the [current blockers and actual evidence](reports/s3-receiver-blockers.md)
> before using any earlier resource, transport, or SRAM estimate.


Resource/timing benchmark for an ISDB-T-oriented FEC partition on Sipeed Tang Nano 9K.

The benchmark answers a specific sizing question:

> Can a K=7 Viterbi decoder with 8-bit soft metrics, an RS(204,188) decoder, and a small two-channel PSRAM protocol controller fit and meet the clock budget on Tang Nano 9K?

## Throughput target

The workload stays at full ISDB-T 6-MHz, 13-segment capacity. From the published
maximum TS rate and RS overhead, use an upward-rounded **25.22 Mstep/s** profile.
The 16-ACS baseline requires four clocks/step, hence **100.88 MHz** for
Viterbi alone. The 9K optimization uses **32 ACS / two clocks per step** plus
constant 16-way RS syndrome updates. Its conservative shared clock floors are
**54.12 MHz for ISDB-T** and **61.93 MHz for the legacy ISDB-S sizing profile**.
Separate **65 MHz feasibility jobs** measure this configuration; **110 MHz
remains the margin target** in the original comparison jobs.

The baseline serialized RS engine must also finish a complete 204-byte block, including
188-byte output, in **7118 clocks at 110 MHz**. Its conservative degree-8 bound
is 6766 clocks; adding pipeline cycles without checking the service rate can
break throughput even after timing improves. See the
[performance contract and concrete next steps](reports/performance.md).
The job driver/report/test share [performance.json](ci/performance.json).

Optimization target FPGA: **GW1NR-LV9QN88PC6/I5**. The legacy ISDB-S rate is a
sizing profile, not a qualified satellite receiver implementation.

## Historical 9K benchmark result

At 65 MHz constraint and adopted common seed 1, both complete 32-ACS +
constant-RS designs finish routing and clear the ISDB-T / legacy ISDB-S sizing
clock floors. The same seed is used for the independent 110 MHz margin jobs.

| Variant | LUT4 | FF | BSRAM | MULT18X18 | Routed Fmax (65 MHz job) | 110 MHz job |
|---|---:|---:|---:|---:|---:|---|
| `core-32acs-rsconst` | 4902 | 2487 | 3 | 8 | **104.32 MHz** | FAIL |
| `mem-32acs-rsconst` | 5045 | 2625 | 3 | 8 | **105.41 MHz** | FAIL |

The metric store has 64 in-place words plus 16 shadow predecessors. The latest
change adds an eight-bit survivor-byte register and prefetches the next row
on the output edge, splitting selection across the existing two phases.
It retains 16-bit metrics and two clocks/step. Both Viterbi versions saturate
the warm-up counter, so output no longer stops again every 256 steps.

The original baseline report recorded **21 passing unittest methods**. The 32-ACS test independently
models metrics, survivor rows, pointer/state and selected output bits; it
checks 936 outputs per 1000-step reset epoch, all 64 selector indices,
uninterrupted two-clock input, randomized stalls and a reset between phases.
See [latest measurements and common-seed selection](reports/survivor-prefetch.md)
and [machine-readable evidence](reports/survivor-prefetch.json).
The [previous metric-storage stage](reports/9k-feasibility.md) records the
same-seed 74.65/81.86 MHz results before these corrections.

The [RS clock investigation](reports/rs-clock-investigation.md) compares
seven further RTL candidates and placement/routing settings. None is adopted:
mandatory clock floors already pass, and the completed trials do not improve
the adopted common core/mem clock objective. Smaller logic or fewer DSPs alone
do not demonstrate better routed timing.

End-to-end sustained throughput, complete convolutional decoder output and
ARIB-compatible RS correction qualification, and a physical PSRAM interface
remain outside the measured scope.

The separate [S3-N16R8 receiver proposal](reports/s3-internal-sram-proposal.md)
records six zero-DSP area experiments, corrected internal-SRAM accounting,
and conditional T/S transport budgets. It does not replace the adopted RTL
or qualify a full receiver. The [offline follow-up](reports/s3-offline-closure.md)
implements a bounded RS experiment with independent ISDB outer-code vectors,
checks a real ESP-IDF memory map, and tests concurrent Q15 FFT tiles and stream
ownership. It also records failed intermediate layouts and timing results.
The [SPI transport follow-up](reports/s3-transport-followup.md) adds a pinned
ESP-IDF SPI/SCT adapter, lossless IQ10 packing, page leases, and an FFT-aware
RF admission guard. Actual hot-IRAM SDK links leave 24768 bytes before the RF
banks after relocating the RF queue to reserved post-startup SRAM. The former
2-us transport-gap assumption is superseded by explicit API/SCT timing contracts;
these remain conditional and do not qualify the complete receiver.
Production RTL and the original benchmark gates are unchanged.

## RTL

### Viterbi

`rtl/viterbi_k7_32acs.sv` is the current 9K optimization:

- 32 ACS lanes, two clocks per trellis step
- 64 in-place path metrics plus 16 shadow predecessors
- static destination writes and phase-only predecessor selection
- 16-bit benchmark metrics, two-clock reset initialization
- two survivor BSRAMs; no metric BSRAMs

The 16-ACS baseline remains available:

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

The `*-32acs-rsconst` variants select `experiments/rs_syndrome_constants.sv`:
16 constant-factor XOR syndrome updates on the byte acceptance clock, followed
by the same serialized BM/Chien/Forney work. Its conservative service bound is
**3502 clocks/block**, versus 6766 for the baseline. Both use eight DSPs.

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

The original matrix retains 9K and inherited 20K comparison/regression jobs
at the 110 MHz margin target. Optimization measurements target 9K only.

| Job | Viterbi | RS | Memory | Measurement |
|---|---:|---:|---|---|
| `9k / core-only` | yes | yes | none | synthesis + P&R |
| `9k / mem` | yes | yes | PSRAM, two x8 channels | synthesis + P&R |
| `9k / viterbi-only` | yes | no | none | synthesis + packing |
| `9k / rs-only` | no | yes | none | synthesis + packing |
| `9k / core-32acs` | 32 ACS | serialized | none | synthesis + P&R |
| `9k / mem-32acs` | 32 ACS | serialized | PSRAM | synthesis + P&R |
| `9k / viterbi-32acs` | 32 ACS | no | none | synthesis + packing |
| `9k / core-32acs-rsconst` | 32 ACS | constant 16-way | none | synthesis + P&R |
| `9k / mem-32acs-rsconst` | 32 ACS | constant 16-way | PSRAM | synthesis + P&R |

Two additional jobs run `core-32acs-rsconst` and `mem-32acs-rsconst` at
**65 MHz / seed 1**. Their names and artifacts include `65 MHz`/`65mhz`.
The driver accepts `--freq` and `--seed`; without them it retains 110 MHz /
seed 4 from `ci/performance.json`. Overrides change placement constraints,
not workload rates or service bounds. The optimized 9K constant-RS jobs
explicitly use common seed 1 at both constraints; other jobs retain seed 4.

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

## Historical 16-ACS results

Measurements use the pinned toolchain below; resources are consistently the
**packed utilization before placement**, including overflow. Final JSON utilization
can account for shared LUT/ALU/RAM occupancy differently and is retained as raw
evidence, but is not mixed into this comparison. DSP usage is listed explicitly per measured variant.

The historical 16-ACS decoder RTL and common seed 4 were published at
[`8754c5f`](https://github.com/kazuki0824/tangviterbi/commit/8754c5f92991d107bf62ee7f978f69cfe847e61f).
That comparison tested syndrome parallelism with 8, 12 and 20 DSPs, and
constant-factor XOR transforms. They reduce RS service clocks but regress the
memory-inclusive capacity at their measured routed clocks, so those 16-ACS
measurements remained isolated experiments. The current 32-ACS combination is
measured separately above. No workload rate is reduced.

| Variant | LUT4 | FF | BSRAM | MULT18X18 | Routed Fmax | 110 MHz |
|---|---:|---:|---:|---:|---:|---|
| core-only | 4052 | 1775 | 19 | 8 | 87.61 MHz | FAIL |
| mem | 4217 | 1913 | 19 | 8 | 91.18 MHz | FAIL |
| viterbi-only | 2440 | 792 | 18 | 0 | not routed | unknown |
| rs-only | 1992 | 1015 | 1 | 8 | not routed | unknown |

Both full designs complete routing but fail the 110-MHz margin target and the
104.56-MHz shared hard throughput floor. CI summaries now separately report the
conservative RS service bound, RS minimum clock, shared minimum clock and target.
The full suite has seventeen unittest methods. The RS budget comparison feeds
identical precomputed codewords to both decoders: zero 3658 clocks, eight-root
6458, noisy observed maximum 6481, with unchanged conservative bound 6766.
Historical 6518-clock noisy results used a different clock-dependent stimulus.
Stream comparison permits changed latency while checking output order and fail,
48 blocks, 1..8-symbol injections, stalls and twelve reset interruptions.
Viterbi remains four clocks/step and its independent 4000-step test is unchanged.

[Latest syndrome comparison, rejection reasons and reproduction](reports/syndrome-search.md)
includes [measurement JSON, exact RTL hashes and derived clock floors](reports/syndrome-search.json).
Candidate RTL and a unittest runner live in `experiments/` and are excluded from
normal synthesis. The [previous timing search](reports/routing-search.md),
[coefficient/control improvement](reports/control-storage.md),
[first optimization stage](reports/performance-optimization.md),
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
