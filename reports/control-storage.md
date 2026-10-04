# 9K coefficient/control timing improvement

This report preserves the RTL improvement at 7670242. The
[latest timing search](routing-search.md) keeps this RTL and adopts a common
placement seed, reaching 87.61 / 91.18 MHz.

## Result

Registered one-hot coefficient selectors, constant per-entry write destinations,
two separate GF operand paths and byte-prefetched Viterbi traceback improve
both complete 9K designs. No FSM service cycles were added.

The comparison starts at [74cebe5](https://github.com/kazuki0824/tangviterbi/commit/74cebe50ba8e58300620e5f4b780060ba49d827b),
verified by [CI run 37238039476](https://github.com/kazuki0824/tangviterbi/actions/runs/37238039476).
After measurements use OSS CAD Suite 2026-10-04, Yosys 0.69+190 (0e8336b4e),
nextpnr-himbaechel 0.11.1-47-ge2fe86b3, unchanged CST/job driver, default seed
and 110-MHz constraint. Counts are packed utilization before placement.
[Measurement JSON and exact RTL hashes](control-storage.json) identify the
measured implementation. CI retains raw synthesis and routing evidence.

| Variant | LUT4 before → after | FF before → after | BSRAM | MULT18X18 before → after | Routed Fmax before → after | 110 MHz |
|---|---:|---:|---:|---:|---:|---|
| core-only | 4422 → 4052 | 1661 → 1775 | 19 | 4 → 8 | 72.54 → 83.80 MHz | FAIL |
| mem | 4545 → 4217 | 1799 → 1913 | 19 | 4 → 8 | 79.02 → 88.57 MHz | FAIL |
| viterbi-only | 2440 → 2440 | 784 → 792 | 18 | 0 → 0 | not routed | unknown |
| rs-only | 2066 → 1992 | 909 → 1015 | 1 | 4 → 8 | not routed | unknown |

Fmax increases by 15.52% / 12.09% and LUT4 decreases by 8.37% / 7.22% for
core / mem. Both complete routing, but still fail 110 MHz, the 100.88-MHz
Viterbi floor and the approximately 104.56-MHz conservative RS service floor.
Packing-only diagnostics establish resource usage, not routed timing.
No workload or acceptance threshold was lowered.

## Implementation

- Each syndrome, polynomial and error-position entry has a constant write
  destination. Registered one-hot write masks replace variable-address writes;
  writes outside the nine-entry lambda polynomial disappear rather than wrap.
  Reset and block initialization preserve the original array behavior.
- Registered one-hot read masks advance during existing FSM cycles. Reads OR
  masked entries instead of combining counter subtraction, address decoding
  and array selection. Empty speculative masks are not consumed. Stage changes
  initialize masks before use, including the last zero-discrepancy BM round
  entering Omega evaluation and restart after asynchronous reset.
- Syndrome/BM/Omega products and inversion/Chien/Forney feedback use separate
  registered operand paths and two GF multipliers. Each maps four carryless
  subproducts to MULT18X18; total DSP usage rises from four to eight. This
  reduces the operand MUX, without changing the number of operations or cycles.
- Viterbi selects an eight-bit survivor byte during groups 0..2, then selects
  its output bit at group 3. Eight registers split the previous 64:1 selection
  across existing cycles. Metric banks, traceback behavior and output timing
  remain equivalent to the previous RTL.

The full designs retain 19/26 BSRAM and use 8/20 MULT18X18, leaving seven BSRAMs
and twelve DSPs. Memory-controller differences also include harness and
whole-design optimization; subtracting mem/core counts is not an isolated
controller cost.

## Verification and service budget

`PATH=/tmp/oss-cad-suite/bin:$PATH python3 -m unittest discover -s tests -v`
passes all sixteen tests:

- Every GF operand pair (65,536) matches independent polynomial arithmetic.
- RS matches the frozen pre-optimization decoder cycle by cycle for ready,
  valid, byte and fail: 48 blocks, including 1..8 injected symbols with three
  values, stalled/consecutive inputs, and twelve processing reset interruptions.
- RS service times remain 3658 clocks for zero error, 6458 for the eight-root
  test and an observed maximum of 6518 for noisy inputs. The conservative
  6766-clock bound and 7118-clock deadline at 110 MHz are unchanged.
- Viterbi checks 4000 steps across two metric widths, including recurrence,
  ties, overflow, survivor/traceback selection, stalls, reset and four clocks/step.
- PSRAM transaction, elaboration and report regressions pass.

Old/new equivalence preserves existing behavior; it is not independent ARIB
decoder qualification. Shortened RS symbol mapping, Viterbi traceback
qualification and end-to-end receiver throughput remain unverified. PSRAM
still excludes DDR PHY, startup, calibration and real memory pin placement.

## Alternatives and remaining path

All entries below use the same pinned toolchain and unchanged clock constraint.
Only functionally checked candidates are listed as implementation comparisons.

| Candidate | core MHz | mem MHz | Decision |
|---|---:|---:|---|
| Constant writers only | 70.49 | 69.18 | No improvement |
| One-hot read/write masks, one GF multiplier | 76.68 | 75.91 | Lower minimum full-design Fmax |
| Selected masks + two GF paths + traceback byte | 83.80 | 88.57 | Adopted; final rerun reproduced both values |
| Extra partial coefficient-read registers | 83.74 | 78.03 | Extra storage did not improve both designs |
| Dedicated GF square/xtime with two GF paths | 91.10 | 82.86 | Lower minimum full-design Fmax |
| Selected RTL, timing weight 20 / criticality exponent 4 | 83.91 | 88.20 | Default placement settings retained |

The extra-read-register experiment initially stopped before placement because
Yosys emitted a `$buf` cell that nextpnr could not implement. Narrowing an
unused selector register eliminated it and allowed measurement. This was a
tool compatibility issue, not device exhaustion. The candidate was excluded
after functional fixes and timing comparison; the selected RTL has no such
blocker. Earlier candidates with output mismatches were rejected before adoption.

The selected critical paths run from RS selector/control registers through
coefficient selection to registered GF operands: core has 4.93 ns logic plus
7.01 ns routing; mem has 4.86 ns logic plus 6.43 ns routing. Neither path crosses
the DSP multiplication itself. Further work must shorten these selection and
control paths while preserving service cycles, or account for any added cycles
against the limited RS budget. 110-MHz operation is still not established.
