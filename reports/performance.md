# 9K performance contract and next steps

Target device: Tang Nano 9K, GW1NR-LV9QN88PC6/I5. The original contract below
covers the 16-ACS ISDB-T 6-MHz, 13-segment sizing question. The current 32-ACS
configuration also reports the repository's legacy ISDB-S sizing profile;
passing either clock floor does not qualify a complete receiver.

## Current 32-ACS / constant-RS configuration

The [9K feasibility report](9k-feasibility.md) supersedes the historical next
steps below for the optimized configuration. Work rates remain 25.22 Mstep/s
for ISDB-T and 28.86 Mstep/s for legacy ISDB-S. The 32-ACS engine consumes
two clocks/step; constant 16-way syndrome updates reduce the conservative RS
service bound to `204 + 3298 = 3502` clocks/block.

| Clock requirement | ISDB-T | Legacy ISDB-S sizing |
|---|---:|---:|
| Viterbi | 50.44 MHz | 57.72 MHz |
| RS bound / block arrival interval | 54.12 MHz | 61.93 MHz |
| Shared hard floor | **54.12 MHz** | **61.93 MHz** |

At 65 MHz / seed 4 the in-place metric implementation routes at **74.65 MHz
core / 81.86 MHz PSRAM-inclusive**, clearing both floors. The 65 MHz feasibility
constraint is a separate CI job, while the original 110 MHz margin jobs remain.
The selected design retains 16-bit metrics, 32 ACS and the existing RS schedule.
The next timing target is the survivor traceback selection path: the measured
65 MHz runs report 8.95 ns logic + 4.45 ns routing (core) and 8.20 + 4.02 ns
(mem). These are whole-design critical paths after metric storage was improved.

Twenty-one unittest methods pass, including 4000 independent 32-ACS steps at
widths 16/10, a reset between phases, and constant-RS budget/stream/arithmetic
checks. Observed constant-RS maximum is 3217 clocks versus the conservative
3502 bound; the legacy ISDB-S block deadline at 65 MHz is 3675 clocks.
110 MHz margin, bounded pipeline integration, physical PSRAM timing and
ARIB-compatible correction vectors remain unestablished.

## Original 16-ACS required work rate

[ARIB/DiBEG's transmission parameters](https://www.dibeg.org/techp/structure/)
list RS(204,188) and a maximum useful TS rate of approximately 23.234 Mbit/s.
From those published, rounded values, the RS input / Viterbi output rate is
approximately `23.234 * 204 / 188 = 25.21136 Mbit/s`. The engineering profile
rounds this upward to **25.22 Mstep/s**, rather than lowering the required rate
to match current timing. These are the repo's workload/acceptance settings,
not a claim that a particular FPGA clock is prescribed by ARIB.

The values used by the job driver, report and RS service-time test are in
[`ci/performance.json`](../ci/performance.json).

| Requirement | Value / acceptance |
|---|---|
| Viterbi work rate | at least 25.22 million accepted trellis steps/s |
| Current 16-ACS architecture | 4 clocks/step; clock floor 100.88 MHz |
| Implementation target | 110 MHz routed timing, for core and PSRAM-inclusive model |
| RS input rate | 3.1525 MB/s, before removing RS parity bytes |
| RS block arrival interval | 204 bytes / 3.1525 MB/s = 64.711 us |
| Single serialized RS service deadline at 110 MHz | at most 7118 clocks/block, including input, correction, output and reset |
| Stream integration | no unbounded input stall or packet loss; bounded buffering between Viterbi and RS |
| Decoder correctness | bit-exact independent reference vectors, including 0..8 symbol errors; still unqualified |

Routed timing alone does not validate sustained throughput: the current sizing
harness stimulates the two decoders independently, not as a complete receiver
pipeline. The report explicitly says end-to-end throughput is unmeasured.
Any added pipeline latency must be included in the RS block service deadline.
A faster clock with more cycles per block can still fail this rate contract.

## Baseline serialized RS cycle budget

The current serialized FSM (two separate multiplier paths, unchanged scheduling) has a conservative bound for degree <=8 and
at most eight correction positions:

| Phase | Conservative clocks |
|---|---:|
| Receive 204 bytes and 16 syndrome updates/byte | 3468 |
| BM initialization and 16 rounds (up to 37 clocks/round) | 593 |
| Omega initialization and 16 coefficients (up to 11 clocks/coefficient) | 177 |
| Chien initialization and 204 positions (up to 10 clocks/position) | 2041 |
| Forney initialization and up to 8 positions (37 clocks/position) | 297 |
| Output 188 bytes, read priming and block reset | 190 |
| Total bound | **6766** |

That bound requires approximately **104.56 MHz** at the chosen work rate.
Thus the earlier approximately 100.8-MHz number describes Viterbi alone, not a
proof that the complete serialized RS architecture meets its block deadline.
110 MHz remains the target, leaving only 352 clocks/block against this bound.
Blindly doubling GF-operation latency would consume more than this slack.

The current `rs_budget_tb` measures service time for zero-error, eight injected
errors into an all-zero codeword, and eight deterministic noisy blocks. At the
measured decoder revision these take 3658, 6458 and up to 6481 clocks/block.
The bench precomputes identical codewords for the current decoder and frozen
reference, independently of readiness. It enforces the profile deadline, 188
matching output bytes and fail; it does not prove
RS correction accuracy or exhaust all error patterns. The analytical bound and
observed test maximum are deliberately kept separate.

## Historical 16-ACS improvements and proposed work

The [first optimization report](performance-optimization.md) records
coefficient/GF-operand prefetch, DSP-based carryless GF products and parallel
Viterbi branch-cost selection. The [latest control/storage improvement](control-storage.md)
adds registered one-hot read/write masks, constant coefficient writers, two
separate GF operand paths and byte-prefetched traceback. These preserve the
6766-clock conservative RS bound and four Viterbi clocks/step. The [latest timing search](routing-search.md) keeps this RTL and uses common
placement seed 4: core and PSRAM-inclusive timing reach 87.61 and 91.18 MHz,
still below all required clock floors. Seventeen tests include all GF operand pairs, 48 latency-independent old/new
RS blocks plus twelve reset interruptions, 4000 Viterbi steps and separate
RS/shared-clock reporting. The [latest syndrome comparison](syndrome-search.md)
measures two-way (8 or 12 DSP), four-way (20 DSP) and constant-factor transforms.
The analytical bounds fall to 5134, 4318 and 3502 respectively. RS clock floors
become 79.34, 66.73 and 54.12 MHz; **shared clock floor remains 100.88 MHz because
Viterbi remains four clocks/step**. Their memory-inclusive capacity regresses at
actual routed Fmax, so the 16-ACS baseline retained the 6766-clock bound.
Historical noisy maximum 6518 used a different stimulus; it is not the baseline
of the new equal-input comparison.

| Order | Historical proposed change | Required check |
|---|---|---|
| 1 | Make syndrome parallelism fit the timing/fanout of both complete designs; shorten remaining RS FSM paths | routed clock plus RS service bound; compare shared-clock capacity in both core and mem |
| 2 | Study 32 ACS / two clocks per step if a lower Viterbi floor is needed | memory ports, BSRAM/LUT/DSP budget, actual architecture and recurrence correctness |
| 3 | Add bounded FIFO / ping-pong buffering; consider separate decoder clocks | average service rate, burst backlog and CDC correctness; FIFO alone cannot fix a rate deficit |

The reviewed throughput floor and margin target are distinct. CI derives
`rs_min_clock_mhz` from the profile's syndrome schedule and other phase bounds,
then uses `max(viterbi_min_clock_mhz, rs_min_clock_mhz)` for complete designs.
The 110-MHz target remains unchanged. Transition/write predicate prefetch was
also tested in seven variants; none improved both routed designs. See the new
comparison for exact measurements and candidate sources.

The 16-ACS metric store uses 16 BSRAMs; with survivor and RS storage
it uses 19 of 26 before additional stream buffering; RS now uses eight of twenty
MULT18X18 cells. All changes must fit the
remaining physical resources. There are credible design options, but a
successful 110-MHz 9K implementation is not yet established.

Keep core-only and PSRAM-inclusive P&R plus Viterbi-only and RS-only packing
diagnostics. Diagnose timing first, then verify the revised core, then measure
the controller-inclusive design. Keep the workload rate and correctness
requirements fixed while changing the microarchitecture. Memory remains a
protocol-level sizing model: DDR PHY, startup, calibration and actual memory
pin placement are excluded.
