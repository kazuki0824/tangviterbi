# 9K performance optimization

## Result

The RS coefficient/multiplier operand selection is scheduled one cycle ahead,
using existing FSM cycles. The shared GF(256) operation now uses four Gowin
MULT18X18 primitives, and Viterbi selects complementary branch costs directly
instead of subtracting after selection. No extra RS service cycles or Viterbi
step cycles are introduced.

Baseline is [10d54fa](https://github.com/kazuki0824/tangviterbi/commit/10d54fab300f06d994ebf822c42bbcbeafba338c),
verified by [CI run 37235747258](https://github.com/kazuki0824/tangviterbi/actions/runs/37235747258).
After values are local P&R with OSS CAD Suite 2026-10-04, Yosys 0.69+190
(0e8336b4e), nextpnr-himbaechel 0.11.1-47-ge2fe86b3, the unchanged 9K CST,
unchanged job driver, default seed, and 110-MHz constraint. Resource counts
are consistently packed utilization before placement. Diagnostic jobs are
packing only. [Machine-readable measurements and source hashes](performance-optimization.json)
identify the exact measured RTL; CI uploads full logs and reports.

| Variant | LUT4 before → after | FF after | BSRAM after | MULT18X18 after | Routed Fmax before → after | 110 MHz |
|---|---:|---:|---:|---:|---:|---|
| core-only | 6298 → 4422 | 1661 | 19 | 4 | 36.98 → 72.54 MHz | FAIL |
| mem | 6378 → 4545 | 1799 | 19 | 4 | 36.99 → 79.02 MHz | FAIL |
| viterbi-only | 2330 → 2440 | 784 | 18 | 0 | not routed | unknown |
| rs-only | 4221 → 2066 | 909 | 1 | 4 | not routed | unknown |

Core timing improves by 1.96x and PSRAM-inclusive timing by 2.14x; LUT4 usage
falls by 29.8% and 28.7%, respectively. Both complete routing, but **both still
fail 110 MHz and the 100.88-MHz Viterbi floor**. The RS 6766-clock conservative
bound also needs approximately 104.56 MHz. These measurements do not establish
full-rate operation. No timing criterion or workload rate was relaxed.

## Implementation

- Polynomial and syndrome address selection feeds registered multiplier
  operands, rather than a large MUX followed by GF arithmetic in one cycle.
  Dependent inversion/Chien/Forney operations forward the current GF result
  into the next operands; coefficient reads run alongside the current multiply.
- Lambda and omega coefficients needed after a multiply have shared prefetched
  registers. Error position/value selection is latched before Forney work.
  The lambda update index is an explicitly bounded five-bit sum. Speculative
  out-of-range reads are never consumed by the FSM.
- Each 4x4 carryless product encodes input bits at positions 0, 3, 6 and 9 of
  a ten-bit integer. An ordinary integer multiplier accumulates at most four
  terms per coefficient. Three-bit spacing prevents inter-coefficient carry;
  each coefficient's low bit is its GF(2) parity. Four such products form the
  8x8 polynomial product, followed by reduction modulo 0x11d. Yosys maps these
  to four MULT18X18 cells. This is one shared GF operation per cycle, with no
  operation-latency increase; it trades previously unused DSPs for logic timing.
- Viterbi computes the four soft costs using eight-bit complements and selects
  both predecessor branch costs in parallel. Metric width, truncation, tie
  preference, metric banking, survivor storage and four-clock scheduling remain.

The added operand/coefficient registers have no reset. Every consumer has a
preceding state that initializes them, including after block or asynchronous
reset. The existing block RAM remains one BSRAM and metric/survivor RAM stays
at eighteen BSRAMs. The combined design leaves seven of twenty-six BSRAMs and
sixteen of twenty MULT18X18 cells unused.

## Verification and cycle budget

`PATH=/tmp/oss-cad-suite/bin:$PATH python3 -m unittest discover -s tests -v`
passes sixteen tests:

- All 65,536 GF operand pairs match an independent carryless polynomial
  product followed by long division by 0x11d.
- RS input-ready, output-valid, output-byte and failure flag match a frozen
  pre-optimization RTL snapshot cycle for cycle over 24 blocks (zero,
  eight-root and noisy cases, input stalls, consecutive blocks) and twelve
  asynchronous reset interruptions. The fixture records its source commit.
- RS block service remains 3658 clocks for zero input, 6458 for the eight-error
  case and at most 6518 observed in the deadline test. All fit the 7118-clock
  deadline **at 110 MHz**; the conservative 6766-clock bound is unchanged.
- Viterbi checks 4000 steps across 16-bit and 10-bit metrics, independently
  encoded branches, truncation/overflow, ties, survivor writes, traceback
  output selection, stalls/reset and four-clock scheduling.
- PSRAM transactions, four variant elaboration and report regressions pass.

Matching the old decoder is a regression check, not independent ARIB RS or
Viterbi traceback qualification. Nor does meeting a cycle budget at 110 MHz
prove the measured, slower design can sustain the input stream.

## Alternatives measured

All trials below used the same device, toolchain, CST and default seed; changes
are implementations rather than a seed search. Candidates are compared across
both core and PSRAM-inclusive variants; a better isolated-core result alone
is not the selection criterion.

| Candidate | Core MHz | PSRAM-inclusive MHz | Outcome |
|---|---:|---:|---|
| Coefficient prefetch, original GF and Viterbi | 54.29 | not run | not selected |
| Registered GF operands, balanced XOR GF, parallel Viterbi branch costs | 59.63 | 77.45 | not selected |
| Explicit decoded coefficient read ports | 67.56 | 70.01 | not selected |
| LUT Karatsuba GF plus sliced Viterbi comparator | 54.52 | 54.18 | not selected |
| Three DSP products, original traceback selection | 82.88 | 70.21 | not selected |
| Three DSP products plus byte-prefetched traceback | 84.92 | 63.16 | not selected |
| Four DSP products plus byte-prefetched traceback | 65.24 | 59.03 | not selected |
| Four DSP products, original traceback selection (selected) | 72.54 | 79.02 | selected |

The selected four-product DSP implementation improves the slower of the two
main variants more than the three-product alternative, uses slightly fewer
LUT4s in both, and consumes one additional DSP. A byte-prefetched traceback
and a sliced comparator were tested but did not improve both complete designs;
they are not included in the final RTL.

## Remaining timing work

The selected core's critical path is within RS coefficient/control storage:
5.08 ns logic plus 8.71 ns routing (13.79 ns total). The PSRAM-inclusive
critical path is also RS storage/control: 5.41 ns logic plus 7.25 ns routing
(12.66 ns). Neither selected critical path crosses a MULT18X18 multiplier.
The next change should localize and simplify coefficient/control fanout and
array write enables, preserving the service-cycle budget. Isolated Viterbi
P&R of the parallel-branch-cost candidate was about 76 MHz, with traceback
selection on the critical path; those exploratory standalone runs are separate
from the packing-only CI diagnostics.

Further timing work therefore needs both RS storage/control and Viterbi
selection/ACS validation. Simply inserting wait cycles into every GF operation
would break the service budget. Buffering/clock-domain integration and bit-exact
ARIB decoder validation remain separate requirements in the
[performance contract](performance.md). PSRAM remains a protocol model without
physical DDR PHY, initialization, calibration or actual memory pin placement.
