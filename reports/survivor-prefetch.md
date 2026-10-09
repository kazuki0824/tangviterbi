# 9K survivor prefetch and continuous output

The 32-ACS survivor selector is split into a registered byte and final bit
selection, using the existing two ACS phases. Both Viterbi versions now
saturate their warm-up counter at 64 steps, eliminating the output gap that
recurred every 256 accepted steps. The 32-ACS architecture retains **16-bit
metrics, 80 metric words and two clocks/step**. RS scheduling/work rates are
unchanged; no extra DSP or BSRAM is used.

## Fixed-seed RTL comparison

Pinned OSS CAD Suite 2026-10-04, GW1NR-LV9QN88PC6/I5, 65 MHz constraint,
common seed 4. Counts are packed utilization before placement; only clocks
printed after completed routing are treated as achieved Fmax.

| Stage | Core Fmax | Mem Fmax | Core LUT4 / FF | Mem LUT4 / FF |
|---|---:|---:|---:|---:|
| Previous `04dd6f0`, counter still wrapping | 74.65 MHz | 81.86 MHz | 4879 / 2479 | 5040 / 2617 |
| Warm-up counter saturation only | 83.61 MHz | 81.10 MHz | 4878 / 2479 | 5035 / 2617 |
| Saturation + byte prefetch | 89.43 MHz | 105.81 MHz | 4902 / 2487 | 5045 / 2625 |

The byte stage costs eight FFs in each complete design. The same-seed table
separates the functional counter correction from the prefetch change. The
counter-only source is retained in
[`experiments/fixtures/viterbi32_counter_fixed.sv`](../experiments/fixtures/viterbi32_counter_fixed.sv)
for reproduction; it is excluded from normal synthesis. Historical in-place
metric measurements remain in [the previous report](9k-feasibility.md).

## Two-clock prefetch schedule

| Edge | RAM row requested | Byte register | Output |
|---|---|---|---|
| Phase 1, valid output for row r | r+1 | previous row/old state value is unused next phase | consume the byte selected for row r; advance pointer/state |
| Phase 0 of next step | r+1 | select byte from prefetched row r+1 using updated state | none |
| Phase 1 of next step | r+2 | previous byte value | consume row r+1; advance pointer/state |

The read address advances on exactly the same condition as valid traceback
output. If it stayed at `tb_ptr` on the output edge, the next phase-0 byte
selection would consume the preceding row with the new state. Initial warm-up
and idle stalls keep the current read address; reset restarts warm-up and the
store is populated before any output is enabled. After warm-up, the look-ahead
row is also different from the current write row, so valid output needs no
read/write collision behavior from the BSRAM. No third trellis clock is added.

## Common-seed 110 MHz search

The optimized netlists were each synthesized once and rerouted at 110 MHz
with seeds 1..10 and a 900-second limit per run. Exact source/netlist/log
SHA256 values and exit/status fields are in [measurement JSON](survivor-prefetch.json).
The adopted **common seed 1** maximizes the smaller core/mem routed Fmax;
the two designs never use independently selected seeds. Work rates, RS service
bound and 110 MHz margin criterion are unchanged. Seed 4 above remains the
isolated RTL comparison; changes from seed 4 to the adopted seed are placement
search gains, not additional RTL gains.

| Seed | Core Fmax (MHz) | Mem Fmax (MHz) | Both meet 110 MHz |
|---|---:|---:|---|
| 1 | 104.32 | 105.41 | FAIL |
| 2 | 100.26 | 104.60 | FAIL |
| 3 | 100.14 | 101.41 | FAIL |
| 4 | 89.43 | 105.81 | FAIL |
| 5 | 97.45 | 103.41 | FAIL |
| 6 | 102.93 | 100.96 | FAIL |
| 7 | 95.06 | 106.04 | FAIL |
| 8 | 94.29 | 102.50 | FAIL |
| 9 | 103.01 | 107.92 | FAIL |
| 10 | 92.77 | 107.82 | FAIL |

## Adopted 9K result

The independent 65 MHz run at common seed 1 measures:

| Variant | LUT4 | FF | BSRAM | DSP | Routed Fmax at 65 MHz | 110 MHz sweep at same seed |
|---|---:|---:|---:|---:|---:|---|
| core-32acs-rsconst | 4902 | 2487 | 3 | 8 | 104.32 MHz | 104.32 MHz / FAIL |
| mem-32acs-rsconst | 5045 | 2625 | 3 | 8 | 105.41 MHz | 105.41 MHz / FAIL |

The ISDB-T / legacy ISDB-S sizing clock floors remain 54.12 / 61.93 MHz for
32 ACS plus the conservative 3502-clock constant-RS block service bound.
Controller-inclusive differences include stimulus/observation and whole-design
optimization; they are not the isolated resource cost of PSRAM control.
The seed-4 critical paths now lie in RS: core 5.78 ns logic + 5.40 ns routing,
mem 3.73 + 5.72 ns. Future timing changes should follow actual routed paths
at the adopted seed, not add more Viterbi selector stages automatically.
At adopted seed 1, the paths are RS block-RAM address/control (core,
5.39 ns logic + 4.20 ns routing) and coefficient-selection/feedback (mem,
5.68 + 3.80 ns). The remaining 110 MHz gaps are 5.68 and 4.59 MHz.

## Verification

`python3 -m unittest discover -s tests -v`: **21 methods PASS**.
The strengthened 32-ACS bench derives all metrics, survivor rows, pointers,
state updates and expected selected output bits from its own software model.
It does not derive expected output from the DUT's row/pointer/state. Each of
two reset epochs runs 1000 full steps at each of widths 16/10, including the
first 320 steps without idle clocks, then randomized stalls. It checks exactly
936 outputs per epoch after the initial 64-step warm-up, all 64 survivor
indices, and reset after phase 0. The 16-ACS bench now also requires output
after warm-up without periodic gaps.

Before the saturation fix, the new test rejected the old counter at step 256.
A byte-prefetch mutation with no read-ahead was rejected by the independent
output model at step 65. Existing PSRAM transaction, RS stream, GF arithmetic
and conservative service-bound tests remain passing. This validates selector
and continuous-output behavior of the sizing model; it does not certify
decoded convolutional input bits or a complete broadcast receiver.

## Reproduction and limitations

With the pinned toolchain on PATH, run from this checkout:

```sh
python3 -m unittest discover -s tests -v
bash ci/run_pnr.sh 9k core-32acs-rsconst --freq 65 --seed 1
```

Archive `build/` before each next run, then use `mem-32acs-rsconst`. Use
`--freq 110` for the margin comparison. To reproduce the ten-seed sweep,
change `--seed` to 1..10 for both variants. To reproduce the counter-only
stage, replace the 32-ACS file in a separate checkout with the retained
fixture, keep the current saturated 16-ACS source and use 65 MHz / seed 4.

Selected raw P&R logs, nextpnr JSON, synthesis scripts and summaries are under
[`reports/survivor-prefetch/`](survivor-prefetch/). The original 110 MHz
comparison jobs and 20K regressions remain; the adopted placement seed applies
only to the two optimized 9K constant-RS variants. The 65 MHz jobs use that
same common seed. This optimization does not reduce the workload or metric
width and does not change RS cycles.

The sizing harness still does not measure a sustained integrated Viterbi/RS
receiver stream. ARIB-compatible RS correction and complete convolutional
decoder output qualification, buffering/CDC, and physical PSRAM
PHY/startup/calibration remain separate work.
