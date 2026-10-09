# RS syndrome parallelism and service-budget comparison

Responds to [review 5408933122](https://github.com/kazuki0824/tangviterbi/pull/1#pullrequestreview-5408933122).
The review is correct that syndrome recurrence is independent across the sixteen
syndromes and can be parallelized. We tested the suggested 12-DSP two-way and
20-DSP four-way architectures, plus an 8-DSP reuse candidate and constant-factor
XOR transforms. **The published decoder RTL remains unchanged:** every candidate
reduces memory-inclusive capacity at its measured routed clock. A large RS cycle
saving alone does not offset the remaining four-clock Viterbi dependency.

## Same-condition measurements

Tang Nano 9K; OSS CAD Suite 2026-10-04; Yosys 0.69+190 (0e8336b4e);
nextpnr-himbaechel 0.11.1-47-ge2fe86b3; identical CST and synthesis driver;
common seed 4; unchanged 110-MHz constraint. LUT/FF/BSRAM/DSP are packed counts,
not final placed occupancy. All full-design routes completed and failed 110 MHz.
Each row measures a complete core and a complete PSRAM-inclusive protocol model;
mem minus core is not the isolated controller cost.

| Candidate | Core LUT/FF/BSRAM/DSP | Mem LUT/FF/BSRAM/DSP | Routed MHz core / mem | RS bound clocks | RS minimum MHz | Shared minimum MHz |
|---|---|---|---:|---:|---:|---:|
| current | 4052 / 1775 / 19 / 8 | 4217 / 1913 / 19 / 8 | 87.61 / 91.18 | 6766 | 104.56 | 104.56 |
| 2-way shared | 4087 / 1775 / 19 / 8 | 4251 / 1913 / 19 / 8 | 81.38 / 81.02 | 5134 | 79.34 | 100.88 |
| 2-way dedicated | 4103 / 1786 / 19 / 12 | 4239 / 1924 / 19 / 12 | 80.61 / 84.39 | 5134 | 79.34 | 100.88 |
| 4-way dedicated | 4058 / 1804 / 19 / 20 | 4361 / 1942 / 19 / 20 | 94.80 / 75.86 | 4318 | 66.73 | 100.88 |
| constant 16-way | 4186 / 1745 / 19 / 8 | 4363 / 1883 / 19 / 8 | 89.05 / 84.40 | 3502 | 54.12 | 100.88 |
| constant + GF pipeline | 4221 / 1762 / 19 / 8 | 4378 / 1900 / 19 / 8 | 81.77 / 88.21 | 7004 | 108.24 | 108.24 |

The current architecture receives each byte in one input cycle plus sixteen
syndrome cycles. Two-way and four-way use one plus eight or four respectively.
The shared two-way candidate reuses the idle feedback multiplier during receipt
and costs 8 DSP. Dedicated two-way leaves the feedback input path alone and adds
one multiplier (12 DSP). Four-way adds three syndrome multiplier paths to the
coefficient path (20 DSP, all twenty device MULT18X18 cells). Their later BM,
Omega, Chien and Forney scheduling is unchanged.

The sixteen constant multipliers have known alpha powers; synthesis implements
linear XOR networks, without DSPs. All sixteen syndromes update on the accepted
input edge, eliminating ST_SYND. The existing eight DSPs remain for later phases.
This preserves the original sticky nonzero flag behavior: the first nonzero byte
makes all running syndromes nonzero; the flag stays set until block reset. It
preserves the reference's behavior, not an independent claim of RS correctness.
The extra GF-output-register experiment uses alternating issue/consume cycles,
gates coefficient prefetch and RAM reads, and doubles the constant candidate's
3502-cycle conservative bound to 7004. It passed stream and service tests but
regressed both clock and service-budget capacity.

## Deriving the clock floors

Workload is unchanged: 25.22 Mstep/s, RS input 3.1525 MB/s, 204-byte arrival interval
`204 * 8 / 25.22e6 = 64.710547 us`. Remaining serialized phase bounds are BM 593,
Omega 177, Chien 2041, Forney 297 and output/reset 190: total 3298 clocks.

`rs_min_clock_mhz = rs_bound_cycles * 25.22 / (204 * 8)`

`shared_min_clock_mhz = max(100.88, rs_min_clock_mhz)`

Two-way saves 1632 clocks, so `6766 - 1632 = 5134`; four-way saves 2448, so the bound
is 4318. Both remove the original RS floor of about 104.56 MHz. **The Viterbi floor
of 100.88 MHz remains.** 110 MHz stays the margin target, independent of either
hard floor. At 100.88 MHz the integer block deadline is 6528 clocks; at 110 MHz it
is 7118. The review's 6527-cycle / 239-cycle-saving illustration is conservative
by one cycle when computed from the repository's exact 25.22-Mstep/s profile;
it does not change the design conclusion.

An upper bound from the two separate service budgets is
`min(Fmax / 4, Fmax * 1632 / rs_bound_cycles)` million bits/steps per second.
It helps compare the proposed designs, but does not prove a connected pipeline's
sustained rate. Input buffering, startup, burst backlog and CDC are not modeled.

| Candidate | Core budget capacity Mbit/s | Mem budget capacity Mbit/s |
|---|---:|---:|
| current | 21.132 | 21.993 |
| 2-way shared | 20.345 | 20.255 |
| 2-way dedicated | 20.152 | 21.098 |
| 4-way dedicated | 23.700 | 18.965 |
| constant 16-way | 22.262 | 21.100 |
| constant + GF pipeline | 19.053 | 20.554 |

Required capacity stays 25.22. The four-way core improves its budget capacity,
but its memory-inclusive implementation drops sharply. Constant transforms also
improve core capacity but regress mem capacity. Both full variants must be
considered; these candidates remain experiments. Constant transforms were also
routed with two other common seeds; neither fixes the regression:

| Common seed, constant candidate | Core MHz | Mem MHz |
|---|---:|---:|
| 2 | 88.28 | 84.84 |
| 3 | 80.83 | 79.05 |
| 4 | 89.05 | 84.40 |

## Equal-input verification

The old budget bench advanced the noisy PRNG every clock, including while not
ready. A changed service schedule therefore changed the actual accepted noisy
bytes. The revised bench builds each packet before either decoder runs, then
feeds both the identical bytes with independent ready handshakes. It checks 204
accepted bytes, 188 outputs in order, matching fail and the exact expected cycle
saving, including output and reset. The reference RTL remains frozen at 10d54fa.

| Same input case | Current/reference | Two-way | Four-way | Constants |
|---|---:|---:|---:|---:|
| all zero | 3658 | 2026 | 1210 | 394 |
| eight injected nonzero symbols | 6458 | 4826 | 4010 | 3194 |
| maximum of eight fixed noisy codewords | 6481 | 4849 | 4033 | 3217 |

All ten codewords save exactly 1632 / 2448 / 3264 clocks. The historical noisy
maximum 6518 belongs to a different, clock-dependent stimulus set; it is not the
baseline of this new comparison. Observed maxima are not the conservative bounds.

Each valid architectural candidate passed all seven RTL unittest methods,
including 48 stream-equivalence blocks, 1..8-symbol injections at three values,
independent stalls, consecutive blocks and twelve reset interruptions followed
by full blocks. Since ready/valid timing changes intentionally, comparison is
latency-independent; it does not assert cycle-exact timing. GF uses an independent
long-division oracle for all 65,536 products; constants additionally check all
4096 byte/factor combinations and sixteen alpha powers. The adopted branch's full
suite adds a reporting regression that distinguishes the hard throughput floor
from the 110-MHz target, including the case where Viterbi passes but RS fails.

## Other unsuccessful control experiments

Seven transition/write-predicate candidates passed the earlier cycle-exact
48-block RS equivalence and unchanged service budget. None improves both routed
full designs over 87.61 / 91.18 MHz at seed 4:

| Candidate | Core MHz | Mem MHz |
|---|---:|---:|
| bm2 | 77.39 | 83.73 |
| loop1 | 87.48 | 80.39 |
| forney1 | 78.96 | 83.26 |
| write1 | 87.83 | 86.87 |
| grow1 | 76.07 | 81.93 |
| writeomega1 | 90.37 | 86.45 |
| last1 | 81.31 | 79.98 |

bm2 registers BM growth, degree, final-round and zero-discrepancy predicates;
loop1 adds BM/Omega loop predicates; forney1 registers Chien/Forney decisions;
write1 qualifies syndrome/lambda write masks; grow1 registers only BM growth;
writeomega1 extends registered write masks to Omega; last1 registers the last
correction predicate. Source hashes and resource counts are in
[syndrome-search.json](syndrome-search.json). An initial dedicated-candidate
Icarus declaration-order error was corrected before the valid two-/four-way tests
and measurements; no malformed candidate is used as a result.

## Reproduction and remaining work

Candidate RTL is isolated under `experiments/` and is not included in normal CI
synthesis. From the repository root with the pinned tools on PATH:

```sh
python3 -m unittest discover -s tests -v
python3 experiments/compare_rs.py --rtl rtl/rs204_188_compact.sv --syndrome-cycles 16
python3 experiments/compare_rs.py --rtl experiments/rs_syndrome_2way_shared.sv --syndrome-cycles 8
python3 experiments/compare_rs.py --rtl experiments/rs_syndrome_2way.sv --syndrome-cycles 8
python3 experiments/compare_rs.py --rtl experiments/rs_syndrome_4way.sv --syndrome-cycles 4
python3 experiments/compare_rs.py --rtl experiments/rs_syndrome_constants.sv --syndrome-cycles 0
```

To reproduce P&R, use an isolated copy of this checkout, replace
`rtl/rs204_188_compact.sv` with exactly one candidate, set
`rs_syndrome_cycles_per_byte` to 8 / 4 / 0 as appropriate, and run
`bash ci/run_pnr.sh 9k core-only`, then `bash ci/run_pnr.sh 9k mem`. Run rs-only and
viterbi-only for packing diagnostics. Keep seed 4 and 110 MHz; do not combine
multiple candidate modules. Candidate hashes match the measured snapshots.

There is no tool/access blocker. **110 MHz and sustained full-rate performance
remain unresolved.** Useful next work is controlling RS placement/fanout with a
parallel syndrome architecture while shortening the remaining FSM paths, or
studying a 32-ACS / two-cycle Viterbi architecture together with memory-port and
resource limits. The existing Viterbi RTL remains unchanged. All correctness
qualification limits remain: frozen-reference agreement is not ARIB decoder
certification; the harness does not measure connected receiver throughput; PSRAM
is a protocol sizing model without DDR PHY, startup/calibration or actual RAM pads.
