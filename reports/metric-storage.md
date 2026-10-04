# Metric storage review measurements

The baseline decoder RTL is from `2af4a699790a8077011d0c81e75ed42081aa94bd`.
The diagnostic harness and job driver are those in this change. The baseline
measurements preceded the metric storage redesign; the same driver was used to
repeat the four baseline packing diagnostics. The RS source is unchanged.

Tools: OSS CAD Suite **2026-10-04**, Yosys **0.69+190 / 0e8336b4e**,
nextpnr-himbaechel **0.11.1-47-ge2fe86b3**. Device, family, CST and target clock
are specified by `ci/run_pnr.sh`. The default nextpnr seed is used.

All counts in this file and README are **packed utilization before placement**.
The raw JSON report's post-placement accounting is not substituted into this
comparison. DSP primitives are all zero. Machine-readable counts, resource
capacities, route status, errors and RTL SHA256 hashes are in
[metric-storage.json](metric-storage.json).

## Baseline isolated synthesis/packing

| Device | Decoder | LUT4 | FF | BSRAM | MUX2_LUT5 | MUX2_LUT6 | MUX2_LUT7 | MUX2_LUT8 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 4K | Viterbi | 3073 | 2311 | 2 | 317 | 26 | 12 | 0 |
| 4K | RS | 4420 | 885 | 1 | 1588 | 719 | 328 | 137 |
| 9K | Viterbi | 3073 | 2311 | 2 | 317 | 26 | 12 | 0 |
| 9K | RS | 4420 | 885 | 1 | 1588 | 719 | 328 | 137 |

RS is the larger packed LUT block, and contributes most of the wide MUXs. This
contradicts attributing all combined-core MUX counts to Viterbi metric storage.
The isolated sums include duplicated harness logic and separate optimization,
so they are not an exact partition of the combined 7266-LUT core.

The baseline full-design CI results are preserved in README and
[run 37230676713](https://github.com/kazuki0824/tangviterbi/actions/runs/37230676713).
All four failed before routing; no routed Fmax is assigned to them.

## Banked BSRAM design

Eight banks are indexed by state bits `[3:1]`; each word packs the even/odd
metrics. The row address is `{generation, state[5:4]}`. Each bank has one write
port and two synchronous read ports, replicated by Yosys into **16 SDPX9B**
primitives. Next-group prefetch preserves 16 ACS lanes and four clocks per
accepted trellis step. At generation turnover, group-0 predecessor rows were
written in groups 0 and 2, avoiding a dependence on same-address read/write
collision behavior. Only the source generation needs a four-clock reset sweep;
the destination generation is fully written before becoming the source.

| Design | LUT4 | FF | BSRAM | Routing | Routed Fmax | 100.8 / 110 MHz |
|---|---:|---:|---:|---|---:|---|
| 4K core | 6298 | 1637 | 19 / 10 | capacity failure | unmeasured | unknown |
| 4K mem | 6290 | 1763 | 19 / 10 | capacity failure | unmeasured | unknown |
| 9K core | 6298 | 1637 | 19 / 26 | completed | 37.04 MHz | FAIL / FAIL |
| 9K mem | 6512 | 1775 | 19 / 26 | completed | 37.40 MHz | FAIL / FAIL |

The 9K core route completed before evaluating 9K mem. Both still exit nonzero
for timing; neither is a 110-MHz P&R PASS. The core critical path starts at an
RS register, passes through wide selections and ends at the RS block RAM
control path. Core MUX2_LUT5/6/7/8 fell from **1772/675/311/117** to
**1659/605/285/109**. LUT and FF reductions are measured for the full synthesis
run; not all changes can be attributed to an isolated metric-storage cost.
For example, unchanged RS source packs to 4196 LUTs in the new diagnostics
rather than 4420 after the parsed Viterbi source changes.

4K core is still 136.7% of LUT and 190% of BSRAM capacity. No further placement
settings were tried to rescue this over-capacity design. A different resource
architecture is needed for 4K. For 9K, the next work is RS array-selection and
arithmetic pipelining, including functional and cycle-budget checks, followed
by core timing measurement first and then controller-inclusive measurement.

## Reproduction and validation

Run the four full jobs with `bash ci/run_pnr.sh <4k|9k> <core-only|mem>`.
Run the four diagnostics with `bash ci/run_pnr.sh <4k|9k> <viterbi-only|rs-only>`.
Diagnostics run synthesis and `--pack-only`; they intentionally do not claim
P&R success or Fmax. To reproduce the baseline diagnostics in a disposable
checkout of this change, replace only `rtl/viterbi_k7_16acs.sv` with
`git show 2af4a699790a8077011d0c81e75ed42081aa94bd:rtl/viterbi_k7_16acs.sv`
before running the diagnostics. Restore the revised RTL afterward.

`python3 -m unittest discover -s tests -v` checks identical board synthesis
inputs, main/diagnostic elaboration, memory-controller transactions, reporting
failure/diagnostic accounting, and independent metric recurrence. The metric
test covers 4000 accepted steps across 16-/10-bit widths, overflow truncation,
ties, stalls, changing external inputs, two reset epochs, survivor writes and
four-clock scheduling. It validates the storage/ACS change, not end-to-end
Viterbi traceback or ARIB-compatible RS correction. Those remain unqualified.

RAM controller measurements remain protocol-level sizing models. DDR PHY,
power-up/register initialization, PLLs, physical RWDS capture, calibration and
actual memory pin placement are excluded.
