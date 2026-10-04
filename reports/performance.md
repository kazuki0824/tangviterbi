# 9K performance contract and next steps

Target device: Tang Nano 9K, GW1NR-LV9QN88PC6/I5. This profile covers the existing
ISDB-T 6-MHz, 13-segment sizing question. ISDB-S needs a separate rate/coding
profile; passing this profile does not establish ISDB-S capacity.

## Required work rate

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

## Existing RS cycle budget

The current single-multiplier FSM has a conservative bound for degree <=8 and
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

The new `rs_budget_tb` measures service time for zero-error, eight injected
errors into an all-zero codeword, and eight deterministic noisy blocks. At the
measured decoder revision these take 3658, 6458 and up to 6518 clocks/block.
The test enforces the profile deadline and 188 output bytes; it does not prove
RS correction accuracy or exhaust all error patterns. The analytical bound and
observed test maximum are deliberately kept separate.

## Implemented improvements and remaining work

The [performance optimization report](performance-optimization.md) records
coefficient/GF-operand prefetch, DSP-based carryless GF products and parallel
Viterbi branch-cost selection. These preserve the 6766-clock conservative RS
bound and four Viterbi clocks/step. Core and PSRAM-inclusive routed timing
improve to 72.54 and 79.02 MHz, but both remain below the required clock floors.
The tests now include all GF operand pairs and cycle-exact old/new RS outputs.

| Order | Remaining change | Required check |
|---|---|---|
| 1 | Localize RS coefficient/control fanout and array write enables; the selected paths are dominated by storage/control routing | both complete routed designs; old/new output equivalence and service clocks |
| 2 | Improve Viterbi traceback selection and ACS paths; a byte-prefetched traceback alone did not improve both full designs | preserve output timing, metrics, survivor behavior, four clocks/step and BSRAM ports |
| 3 | Add bounded FIFO / ping-pong input buffering; consider separate decoder clocks if useful | average service rate, burst backlog and CDC correctness; FIFO alone cannot fix a rate deficit |
| 4 | Reconsider ACS parallelism and metric banking if required | full memory-port/BSRAM/LUT budget; extra lanes need actual architecture changes |

The existing metric store already uses 16 BSRAMs; with survivor and RS storage
it uses 19 of 26 before additional stream buffering. All changes must fit the
remaining physical resources. There are credible design options, but a
successful 110-MHz 9K implementation is not yet established.

Keep core-only and PSRAM-inclusive P&R plus Viterbi-only and RS-only packing
diagnostics. Diagnose timing first, then verify the revised core, then measure
the controller-inclusive design. Keep the workload rate and correctness
requirements fixed while changing the microarchitecture. Memory remains a
protocol-level sizing model: DDR PHY, startup, calibration and actual memory
pin placement are excluded.
