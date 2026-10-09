# Tang Nano 9K: 65 MHz feasibility and metric storage

The optimized 32-ACS + constant-16way RS configuration completes full P&R at
65 MHz / seed 4 on 9K: **74.65 MHz core, 81.86 MHz with PSRAM controller**.
Both clear the repository's ISDB-T 54.12 MHz and legacy ISDB-S sizing 61.93 MHz
clock floors. **110 MHz margin is still unmet.** This is a FEC sizing result;
end-to-end sustained receiver throughput is not measured.

## Conditions and comparison

Measurements use OSS CAD Suite 2026-10-04, Yosys 0.69+190 (0e8336b4e),
nextpnr-himbaechel 0.11.1-47-ge2fe86b3, GW1NR-LV9QN88PC6/I5 and the unchanged
9K CST. LUT/FF/BSRAM/DSP counts are consistently **packed utilization before
placement**. Fmax is extracted only after `Routing complete`; partial or
timed-out runs have unknown Fmax. Exact input/log hashes and nextpnr reports
are linked in [measurement JSON](9k-feasibility.json).

| Design / target / seed | LUT4 | FF | BSRAM | DSP | Routed Fmax | 65 MHz | T / legacy S floors |
|---|---:|---:|---:|---:|---:|---|---|
| Original core / 65 / 4 | 6434 | 3248 | 3 | 8 | 60.17 MHz | FAIL | PASS / FAIL |
| Original mem / 65 / 4 | 6585 | 3386 | 3 | 8 | unknown; 900 s timeout | unknown | unknown |
| Selected core / 65 / 4 | 4879 | 2479 | 3 | 8 | **74.65 MHz** | **PASS** | **PASS / PASS** |
| Selected mem / 65 / 4 | 5040 | 2617 | 3 | 8 | **81.86 MHz** | **PASS** | **PASS / PASS** |

The original PR head was `901de569b798fd06cb9435cbd72c8fd04afa1c77`.
Its [110 MHz CI run](https://github.com/kazuki0824/tangviterbi/actions/runs/37255156300)
also measured core at 60.17 MHz; mem failed legal placement and had no routed
Fmax. The 65 MHz original-mem seed-4 result above is a fresh 900-second retry,
not the earlier manually interrupted run. Core LUT4 falls by 1555 (24.2%) and
mem LUT4 by 1545 (23.5%); each removes 769 FFs. The core/mem difference includes
stimulus/observation and whole-design optimization, not an isolated RAM cost.

## Review comment: 65 MHz and common seed 1..10

In response to [the proposed experiment order](https://github.com/kazuki0824/tangviterbi/pull/3#issuecomment-5987199003),
the driver accepts `--freq` and `--seed` without editing workload settings.
Two independent 9K 65 MHz feasibility CI jobs were added, while all existing
110 MHz comparison jobs remain. Existing 20K jobs are inherited regressions;
the optimization measurements and adoption decision here target 9K only.

The following sweep uses the **original RTL**, one cached synthesized netlist
per variant, 65 MHz constraint, and a 900-second limit per nextpnr run.
It does not select a seed from a different architecture.

| Seed | Original core Fmax (MHz) | Original mem Fmax (MHz) |
|---|---:|---:|
| 1 | 57.82 | timeout (900 s) |
| 2 | 60.54 | 52.67 |
| 3 | 60.24 | timeout (900 s) |
| 4 | 60.17 | timeout (900 s) |
| 5 | 58.70 | timeout (900 s) |
| 6 | 58.90 | timeout (900 s) |
| 7 | timeout (900 s) | timeout (900 s) |
| 8 | 57.84 | 58.59 |
| 9 | 56.43 | timeout (900 s) |
| 10 | 57.48 | timeout (900 s) |

No completed run clears the 61.93 MHz legacy-S floor. The best original core
is 60.54 MHz (seed 2); the best original mem is 58.59 MHz (seed 8).
Timeout is an unmeasured result, not proof of impossible placement and not
zero MHz. Constraint relaxation and this seed search alone did not establish
both hard clock requirements, motivating the metric-locality change.

## Selected metric storage

Two complete ping-pong generations had 128 metric words and a generation
selector. The selected design has 64 words updated in place, static per-state
write processes, and 16 shadow words. Only the predecessor quarter overwritten
by phase 0 needs a snapshot:

| Phase | Old predecessors read | New destinations written | Extra action |
|---|---|---|---|
| 0 | states 0..15 and 32..47 | states 0..31 | snapshot old 16..31 into shadow |
| 1 | shadow 16..31 and states 48..63 | states 32..63 | finish step |

The snapshot and phase-0 writes are nonblocking assignments on the same edge,
so the snapshot uses the old generation. Old states 48..63 remain intact until
phase 1 consumes them. Idle cycles cannot update metrics/shadow, and reset
reinitializes the main store in two clocks; shadow is overwritten before use.
This removes `(128 - 80) * 16 = 768` metric FFs plus the bank-selector FF.
Predecessor reads now use phase-only two-way selection. Metric width remains
16 bits in the benchmark; ACS arithmetic, truncation, tie rules, accepted-input
cadence and traceback schedule are preserved. No renormalization or RS
parallelism increase is used.

Local diagnostic trials preceding adoption used the same 65 MHz / seed 4:

| Trial | Core Fmax | Mem Fmax | Decision |
|---|---:|---:|---|
| Static writes, still two complete generations | 54.83 MHz | 61.70 MHz | legacy-S floor unmet; not adopted |
| Static writes plus four-way one-hot reads | 54.05 MHz | unknown; cancelled before routing | core fails T floor; not adopted |
| 64 in-place + 16 shadow words | 74.65 MHz | 81.86 MHz | adopted |

The first trial's additional completed core seeds 1/2/3 gave
60.13/60.78/59.61 MHz. Further diagnostic runs were stopped once the smaller
store succeeded; these are not full ten-seed sweeps of those candidates.

The selected runs' whole-design critical paths moved to Viterbi survivor
traceback selection: **8.95 ns logic + 4.45 ns routing** (core),
**8.20 + 4.02 ns** (mem). These contrast with the original core metric path
6.48 + 10.14 ns. The next 110 MHz timing work should therefore investigate
survivor selection/prefetch, then measure both complete designs again.

## Validation and clock requirements

`python3 -m unittest discover -s tests -v`: **21 methods PASS**.
The independent 32-ACS recurrence covers 2000 full steps at each of widths
16/10, all lane metrics/decisions, survivor writes, idle stalls, two-clock
throughput and a reset after phase 0. The baseline 16-ACS tests also pass.
Constant-RS checks cover 65536 GF operand products, 4096 constant products,
16 alpha powers, 48 latency-independent output/fail comparisons against the
frozen implementation and twelve reset interruptions.

The RS budget test uses identical precomputed codewords for both engines.
Constant-RS takes 394 clocks for zero-error, 3194 for the eight-root case and
an observed noisy maximum of 3217, versus reference 3658/6458/6481. The saving
is exactly 3264 syndrome clocks. The unchanged conservative bound is 3502,
separate from the observed maximum. The legacy-S deadline at 65 MHz is 3675.

| Profile | Work rate | Viterbi floor (2 clocks/step) | RS/shared floor (3502 clocks/block) |
|---|---:|---:|---:|
| ISDB-T | 25.22 Mstep/s | 50.44 MHz | 54.12 MHz |
| Legacy ISDB-S sizing | 28.86 Mstep/s | 57.72 MHz | 61.93 MHz |

The report tests verify that a 65 MHz constraint does not replace the 110 MHz
margin criterion or alter these rates/bounds, and that failed/partial routing
does not promote estimated or requested clocks to achieved Fmax.

## Reproduction and remaining work

From this PR checkout, with the pinned toolchain on PATH:

```sh
python3 -m unittest discover -s tests -v
bash ci/run_pnr.sh 9k core-32acs-rsconst --freq 65 --seed 4
```

Archive `build/` before the next variant (the driver overwrites it):

```sh
bash ci/run_pnr.sh 9k mem-32acs-rsconst --freq 65 --seed 4
```

Omit `--freq` to reproduce the independent 110 MHz margin jobs. To reproduce
the original seed sweep, use a separate checkout at the baseline commit,
copy the current `ci/run_pnr.sh` and `ci/report.py` into that checkout, and run
both variants with `--freq 65 --seed N` for N=1..10, archiving each build.
Apply a 900-second limit to nextpnr and record unknown Fmax for any timeout.
The recorded sweep reused `build/design.json` for seeds other than 4;
netlist SHA256 values are in the JSON.

Selected seed-4 raw P&R logs, nextpnr JSON, synthesis scripts and summaries
are stored in [core evidence](9k-feasibility/core-65-seed4.pnr.log) and
[mem evidence](9k-feasibility/mem-65-seed4.pnr.log); CI also uploads these files
for both the 65 and 110 MHz jobs.

Remaining constraints: 110 MHz clock margin is not established; the harness
does not connect the two engines into a bounded, sustained receiver stream;
ARIB-compatible RS correction accuracy is unqualified; the PSRAM model does
not include DDR PHY, startup, calibration or physical RAM I/O placement.
Passing these sizing clock floors does not remove those integration tasks.
