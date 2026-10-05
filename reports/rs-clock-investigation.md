# 9K clock investigation: choose the effective change before adopting RTL

Baseline hardware: `754c111695dc64651466e729155846fcc08d2bbb`.
Device: GW1NR-LV9QN88PC6/I5. OSS CAD Suite 2026-10-04.
This investigation keeps that hardware and its adopted common seed 1.
The RS candidates below are rejected experiments, not implementation changes.

## Which clock condition matters?

| Condition | Meaning | Baseline result |
|---|---|---|
| 54.12 MHz | ISDB-T conservative shared cycle-budget floor | Both variants exceed it |
| 61.93 MHz | Legacy ISDB-S conservative sizing floor | Both variants exceed it |
| 65 MHz | Separate feasibility P&R constraint | Both jobs pass |
| 110 MHz | Retained margin/comparison target | Both jobs fail timing |

The 65 and 110 MHz constraints produce **identical packing, placement and
routing checksums** at common seed 1, not merely equal rounded Fmax:

| Variant | Packing / placement / routing checksums | Routed Fmax at either constraint |
|---|---|---:|
| core | `e4a7212c / 7ab58fca / 9bb41296` | 104.32 MHz |
| PSRAM-inclusive | `62674a15 / 0c9b0bd7 / f4c362e4` | 105.41 MHz |

Changing the constraint alone has no observed physical speed benefit in
these runs. It changes the pass/fail threshold. This is an observation for
this netlist/tool/seed, not a guarantee for all designs or constraints.
The workload, cycle bounds and 110 MHz margin criterion remain unchanged.

At the baseline, 110 MHz requires a 9.0909 ns clock period. The routed
critical paths are approximately 9.59 / 9.49 ns, requiring about **0.50 /
0.40 ns** improvement. Baseline path components are 5.39 ns logic + 4.20 ns
routing (core) and 5.68 + 3.80 ns (mem); logic includes clock-to-Q/setup.
Shortening one named path is insufficient if another path becomes critical.

## Changes whose benefit was already established

Cycle-count reduction changes the required clock, rather than the achieved
Fmax. The existing 32-ACS engine halves Viterbi from four to two clocks per
step. The constant 16-way syndrome engine saves 3264 clocks per 204-byte
block, reducing the conservative RS bound from 6766 to 3502 clocks.
These explain the current 54.12 / 61.93 MHz shared sizing floors; they are
not end-to-end receiver measurements.

The previous metric-store localization removed a generation mux and
substantial storage. The subsequent survivor-byte stage improved both
routed clocks in the fixed-seed-4 comparison, without extra service cycles:
counter-fixed core/mem 83.61 / 81.10 MHz -> byte-prefetched 89.43 /
105.81 MHz. See [that controlled comparison](survivor-prefetch.md).
Seed selection is a separate placement effect, not an RTL speedup.

## New RTL experiments: same seed and constraint

All rows use seed 1, 110 MHz, the same device/CST and unchanged workload.
Resources are packed utilization before placement. Fmax is after routing.

| Experiment | Core MHz | Mem MHz | Core / mem LUT4 | FF change | DSP |
|---|---:|---:|---|---:|---:|
| Baseline | **104.32** | **105.41** | 4902 / 5045 | 0 | 8 |
| Separate output read-address counter | 107.94 | 100.14 | 4882 / 5050 | +8 each | 8 |
| Counter + hold unused GF inputs | 89.53 | 97.76 | 4879 / 5039 | +8 each | 8 |
| Counter + balanced coefficient reductions | 89.75 | 102.75 | 4894 / 5052 | +8 each | 8 |
| Direct registered RAM read address | 90.23 | 90.70 | 4886 / 5044 | +8 each | 8 |
| Locally gated GF inputs, XOR merge | 99.90 | 93.52 | 4840 / 5008 | 0 | 8 |
| Locally gated GF inputs, OR for disjoint terms | 103.14 | 95.08 | 4842 / 5027 | 0 | 8 |
| Three-product Karatsuba GF | 101.21 | 98.76 | 4911 / 5055 | 0 | 6 |

All variants use three BSRAMs. No candidate meets 110 MHz. Reducing LUTs,
DSPs or a local logic cone does not establish an improvement in the whole
routed design. For example, the address-counter candidate moves the mem
critical path to Viterbi survivor RAM -> byte selection (6.68 ns logic +
3.31 ns routing). The Karatsuba mem path has only 2.73 ns logic but
7.40 ns routing. These are different critical paths, not an isolated
measurement of the same cone before and after.

## Common-seed sensitivity

Four candidates also received a prespecified common seed 1..5 sweep.
For each seed the score is `min(core Fmax, mem Fmax)`. Core and mem cannot
choose different seeds. The baseline uses the same five seeds from the
previous [ten-seed measurement](survivor-prefetch.json).

| Candidate | Pair minima for seeds 1 / 2 / 3 / 4 / 5 (MHz) | Median | Best common-seed score |
|---|---|---:|---:|
| Baseline | 104.32 / 100.26 / 100.14 / 89.43 / 97.45 | 100.14 | **104.32** |
| Address counter | 100.14 / 94.96 / 90.67 / 84.01 / 95.27 | 94.96 | 100.14 |
| Registered RAM address | 90.23 / 95.53 / 95.53 / 94.26 / 101.98 | 95.53 | 101.98 |
| Locally gated inputs / OR merge | 95.08 / 103.67 / 91.47 / 101.11 / 100.70 | 100.70 | 103.67 |
| Karatsuba GF | 98.76 / 96.10 / 100.41 / 91.22 / 100.47 | 98.76 | 100.47 |

The OR-merge candidate's median rises 0.56 MHz and mean rises 0.086 MHz,
but its best common-seed score falls 0.65 MHz relative to the adopted pair.
This small sample does not prove universal ineffectiveness or statistical
significance. It supplies no improvement worth replacing the measured
baseline, and no completed run clears the 110 MHz target.
A fixed random seed controls a tool setting; RTL changes still change the
placement problem. Attribute a benefit using routed results across seeds,
not a presumed identical physical placement or one favorable component.

## Placement/routing settings without RTL changes

At the baseline netlist, seed 1 and 110 MHz:

| P&R setting | Core MHz | Mem MHz | Outcome |
|---|---:|---:|---|
| Default heap timing weight 10 | 104.32 | 105.41 | Baseline |
| Heap timing weight 20 | 95.67 | 108.13 | Pair minimum worsens |
| Heap timing weight 40 | 101.33 | 108.78 | Pair minimum worsens |
| Router2 + timing-driven ripup | unknown | unknown | Both abort inside nextpnr |

Router2 aborts with `assertion_failure: w2n_entry == nullptr`
(`base_arch.h:259`). Routing completion and a final Fmax are absent;
these are tool-blocked measurements, not timing failures or successes.
A separate attempt to reload routed JSON for detailed timing without
repacking/replacing aborts at `array2d.h:78` (`x >= 0 && x < m_width`).
Thus this investigation has the normal critical-path reports, not a new
near-critical-path census. No conclusion is based on incomplete routing.

**Follow-up:** [normal P&R with detailed reporting](endpoint-arrivals.md)
works in both variants and reproduces the baseline physical result. The
JSON-reload failure above is therefore specific to that attempted method.
The follow-up records endpoint arrivals and physical locations; those
arrivals are screening data, not complete setup paths or per-endpoint slack.

## Decision and the next useful evidence

**Retain baseline RTL, seed 1 and default P&R settings.** No new performance
candidate is adopted. The mandatory sizing clock conditions already pass;
110 MHz remains an explicit unmet margin target. Do not lower the workload
or hide its failed jobs to make CI green.

Before another clock-oriented implementation change, obtain a trustworthy
list of near-critical endpoints and physical locations for both complete
variants, and identify a repeated cone or interconnect problem. A single
critical-path name or reduced resource count is not enough. Any subsequent
candidate must improve the common core/mem clock objective in comparable
routed trials and preserve GF results, output ordering and cycle budgets.
The two nextpnr assertions above block the attempted supplementary methods;
normal P&R remains usable. This is an evidence requirement, not a claim
that further optimization is impossible.
The linked follow-up supplies a usable diagnostic method and identifies
repeated RS data/control endpoint families for the next cone investigation.

There is a separate remaining functional question: sustained Viterbi -> RS
stream service, convolutional output against transmitted bits, ARIB RS
correction and a physical PSRAM interface are still unqualified. Higher
Fmax alone cannot close those gaps.

## Validation and reproducibility

- Every RTL candidate passed the existing constant-RS test: all 65,536
  GF products, 4096 constant products, 48 block comparisons / 12 reset
  interruptions and the unchanged service test (max observed 3217 clocks,
  bound 3502, legacy-S deadline 3675 at 65 MHz).
- Both locally gated operand forms were SAT-equivalent to the original
  four operand selections for unconstrained input bits and state values.
  An intentional XOR -> OR Horner mutation fails the same proof.
  This proves those combinational selections, not the whole receiver.
- The shared RS equivalence bench now asserts coverage of zero-syndrome
  output, no-locator output and final-correction output entries, plus actual
  Forney reads: 157 reads for constant-RS, 148 for the baseline serialized
  RS across the existing 48 blocks. The serialized zero-syndrome branch
  enters from ST_SYND; constant-RS enters from ST_INPUT.
- Full unittest suite: 21 methods pass. Hardware sources and performance.json
  remain byte-for-byte identical to baseline.

[Machine-readable measurements / hashes](rs-clock-investigation.json) and
[full evidence archive](rs-clock-investigation-evidence.tar.gz) contain all
52 trials: **50 completed routing measurements, two tool aborts**. They
include raw P&R logs/reports, seven source patches against 754c111,
measurement helpers, SAT miters/logs and validation transcripts. Source
patches are rejected experiments and excluded from normal synthesis.

To reproduce a candidate, check out baseline 754c111 in a separate directory,
extract the archive, apply its `patches/<candidate>.patch` with `patch -p1`,
and run, with the pinned suite on PATH:

```sh
bash ci/run_pnr.sh 9k core-32acs-rsconst --freq 110 --seed 1
bash ci/run_pnr.sh 9k mem-32acs-rsconst --freq 110 --seed 1
```

Use separate output directories for the two commands because `build/` is
shared. Repeat both at each common seed for the sweep. For setting trials,
use the baseline netlists and append the exact options recorded in JSON to
the nextpnr invocation. The archived tuning helper records original `/tmp`
locations; adjust those paths for a new checkout. To reproduce the pure
operand proof, run Yosys `read_verilog -sv <proof.sv>; prep -top proof;
flatten; opt; sat -verify -prove ok 1` on its archived miter. Mutation failure
is intentional and is not a production test failure.
