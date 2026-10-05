# 9K timing search and common placement seed

## Adopted result

Use **seed 4 for both full designs**, configured once in
[`ci/performance.json`](../ci/performance.json), passed explicitly to nextpnr
and recorded in the job summary. All decoder/controller RTL is unchanged from
[7670242](https://github.com/kazuki0824/tangviterbi/commit/7670242ee36b6d122c34f816560f57ad0c984187),
verified by [CI run 37242331746](https://github.com/kazuki0824/tangviterbi/actions/runs/37242331746).
This is a placement/routing improvement, not a logic or service-rate change.

Measurements use OSS CAD Suite 2026-10-04, Yosys 0.69+190 (0e8336b4e),
nextpnr-himbaechel 0.11.1-47-ge2fe86b3, the same 9K CST and **110-MHz target**.
Only the seed changes for the adopted before/after comparison. Counts are
packed utilization before placement. A fresh synthesis-and-routing run with
the updated driver reproduces both results from the seed sweep.

| Variant | LUT4 | FF | BSRAM | MULT18X18 | Routed Fmax default → seed 4 | 110 MHz |
|---|---:|---:|---:|---:|---:|---|
| core-only | 4052 | 1775 | 19 | 8 | 83.80 → 87.61 MHz | FAIL |
| mem | 4217 | 1913 | 19 | 8 | 88.57 → 91.18 MHz | FAIL |
| viterbi-only | 2440 | 792 | 18 | 0 | not routed | unknown |
| rs-only | 1992 | 1015 | 1 | 8 | not routed | unknown |

Core and mem improve by 4.55% and 2.95%, with no extra logic, DSPs or cycles.
The seed is shared across variants, rather than selecting a different seed for
each harness. Diagnostics still measure packing only; their configured seed
does not establish routed timing. Packed counts remain identical.

This result still fails the 110-MHz target, the 100.88-MHz Viterbi floor and
the approximately 104.56-MHz conservative RS floor. Seed optimization is
specific to the pinned netlist, toolchain and constraints; a later RTL change
needs fresh measurements. It does not prove achievable timing at other seeds
or on the physical board.

## Tested RTL alternatives

All eleven candidates were measured with the previous default seed and
unchanged toolchain, target and CST. Each passed the existing RS service test
and cycle-exact comparison against the frozen decoder: 48 blocks, 1..8-symbol
injection, stalled/consecutive input and twelve processing reset interruptions.
These checks establish old/new equivalence, not independent ARIB qualification.
[JSON measurements and RTL hashes](routing-search.json) retain resources and
the exact measured source identity for every candidate.

| Candidate | core MHz | mem MHz | MULT18X18 | Finding |
|---|---:|---:|---:|---|
| Bitwise reduction of one-hot reads | 80.35 | 90.01 | 8 | Core regresses |
| Separate GF path for BM update | 72.71 | 93.76 | 12 | Core regresses; bottleneck moves |
| Hold unused GF operands | 83.19 | 82.95 | 8 | Both regress |
| Default GF operands to polynomial reads | 82.43 | 84.86 | 8 | Both regress |
| Above plus simpler RAM read selection | 90.10 | 79.87 | 8 | Mem regresses |
| Prefetch the next correction position/value | 81.69 | 86.02 | 8 | Both regress |
| Three registered lambda-read groups | 81.11 | 81.07 | 8 | Both regress |
| Separate BM-update GF plus simpler RAM selection | 87.47 | 90.87 | 12 | Both improve; common seed 4 surpasses both without four extra DSPs |
| Generate syndrome alpha powers with xtime | 91.82 | 86.24 | 8 | Mem regresses |
| Alpha recurrence plus correction prefetch | 89.01 | 88.17 | 8 | Mem regresses |
| Registered binary lambda read index | 86.14 | 79.27 | 8 | Mem regresses |

The split-GF/RAM candidate is a valid improvement over the previous default,
but the selected unchanged RTL with seed 4 achieves more in both full designs
and keeps twelve of twenty DSPs available. No experimental RTL is included in
the adopted implementation.

## Seed comparison on unchanged RTL

| Common seed | core MHz | mem MHz |
|---|---:|---:|
| Previous default | 83.80 | 88.57 |
| 2 | 85.54 | 87.53 |
| 3 | 85.40 | 84.72 |
| **4, adopted** | **87.61** | **91.18** |

The sweep routed the original netlists. The adopted driver then synthesized
both designs afresh and reproduced seed 4. No target, synthesis optimization,
placement weight or per-variant constraint was relaxed.

## Verification and remaining work

All sixteen unittest tests pass with the adopted configuration. The job-driver
regression now checks that every variant receives the shared seed and clock
target. Report output accepts an explicit execution seed and distinguishes
packing diagnostics from routed measurements. GF arithmetic still checks all
65,536 operand pairs; Viterbi still checks 4000 steps at two metric widths.
RS times remain 3658 clocks for zero error, 6458 for the eight-root case and
an observed maximum of 6518 for noisy inputs; the conservative bound remains
6766 against the 7118-clock deadline at 110 MHz.

The selected critical paths are inside the RS FSM control/data logic. Both
source and sink registers map to the RS FSM process, and neither reported
path crosses a MULT18X18 cell. Core has 5.68 ns logic plus 5.73 ns routing;
mem has 5.49 ns logic plus 5.48 ns routing. The synthesis-generated names are
not sufficient to identify a particular source register by their prefixes.

Further work can register RS transition/write predicates in earlier available
FSM cycles or revise the scheduling/parallelism. Any added cycles must fit the
352-clock conservative slack at 110 MHz; blindly adding a cycle to every GF
operation or syndrome update exceeds it. These are remaining design options,
not a demonstrated 110-MHz implementation. No placement, tool compatibility
or access issue blocked the measurements in this search.

The sizing harness still stimulates the decoders independently. End-to-end
throughput, independent decoder qualification, bounded stream buffering and
CDC are unverified. PSRAM remains a protocol model without DDR PHY, startup,
calibration or actual memory pin placement.
