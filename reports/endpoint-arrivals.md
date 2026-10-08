# 9K endpoint timing: normal P&R can produce detailed output

Hardware baseline: `754c111695dc64651466e729155846fcc08d2bbb`.
Parent: `3d3512b201aa6e52b502414b936544394d9a0c3b`.
OSS CAD Suite 2026-10-04, nextpnr `e2fe86b3`, GW1NR-LV9QN88PC6/I5,
GW1N-9C, unchanged CST, default placer/router, common seed 1, 110 MHz.
This is a diagnostic run; it introduces no performance RTL or P&R setting.

## The earlier failure is avoidable

Reloading already routed JSON with packing, placement and routing disabled
asserted inside nextpnr. That blocks that particular reload method.
Running normal, complete P&R from the synthesis JSON with
`--detailed-timing-report` **succeeds in both variants**. It returns exit 1
because 110 MHz timing fails, after routing and report generation complete;
there is no internal assertion or timeout in these two runs.
The previous router2 assertion is a separate, unresolved tool failure.

| Variant | Routed Fmax | Full critical-path period | Reduction needed for 110 MHz | Detailed nets / endpoint entries |
|---|---:|---:|---:|---:|
| Core | 104.32 MHz | 9.586 ns | 0.495 ns | 759 / 912 |
| PSRAM-inclusive | 105.41 MHz | 9.487 ns | 0.396 ns | 784 / 940 |

The complete `fmax`, `critical_paths` and `utilization` fields exactly match
the previously committed 110 MHz reports. Packing, placement and routing
checksums also match the prior baseline. Detailed reporting therefore has
no observed physical effect here. The mandatory 54.12 / 61.93 MHz sizing
floors and the separate 65 MHz feasibility condition still pass;
110 MHz remains unmet.

## What the additional data establishes

The additional JSON contains an arrival range for each timed endpoint.
It does **not** contain that endpoint's setup slack, complete path or
capture setup correction. In the pinned
[timing implementation](https://github.com/YosysHQ/nextpnr/blob/e2fe86b3/common/kernel/timing.cc),
`build_detailed_net_timing_report` copies the endpoint's arrival value.
Rankings and threshold counts below are screening data, **not counts of
110 MHz violations or substitutes for full-path Fmax**.

All entries in each variant use the same rising-edge launch/capture domain.
Clock net names differ because the flattened shared clock has different
aliases. Synthetic cell names identify hierarchy and endpoint families;
they do not establish an exact source register or RTL cone by themselves.

| Variant | Raw arrival at least 9.0 ns | Raw arrival at least 8.5 ns |
|---|---|---|
| Core | 3 RS endpoints: 2 D, 1 CE | 9 RS endpoints plus 1 Viterbi endpoint |
| PSRAM-inclusive | 15 RS endpoints: 3 D, 8 RESET, 4 CE | 32 RS endpoints |

Selected high-arrival endpoints, using shortened family names only in this
table. JSON and the archive retain the full names and all mapped endpoints.

| Variant | Endpoint family / port | Raw maximum arrival | Physical BEL |
|---|---|---:|---|
| Core | RS block-RAM output-associated register / D | 9.447 ns | X30Y19/DFF2 |
| Core | RS lambda selection / D | 9.317 ns | X25Y5/DFF4 |
| Core | RS block-RAM-associated control / CE | 9.169 ns | X31Y20/DFF4 |
| Core | Viterbi survivor byte / D | 8.966 ns | X3Y20/DFF3 |
| Mem | RS feedback-associated register / D | 9.348 ns | X4Y6/DFF2 |
| Mem | RS error-position register / D | 9.207 ns | X16Y19/DFF0 |

In mem, one net feeds eight RESET endpoints with arrival at least 9.0 ns;
another feeds four CE endpoints in that band. Those are repeated control
loads worth tracing, alongside the data selections. The core's Viterbi
byte endpoint also needs monitoring when RS paths improve. Mem's largest
Viterbi raw arrival is only 6.272 ns at this particular adopted seed;
this is not a claim about every placement seed.

Locations come from `NEXTPNR_BEL` in the prior seed-1 routed JSON, checked
against all three new P&R checksums and the identical full critical-path
report. Every reported endpoint and its immediate driver maps to a cell.
Only the immediate driver is included; it is not necessarily the launching
register of the complete path.

## Decision

Keep the adopted hardware and placement settings. Detailed measurement
is now available, so the failed JSON reload is not a general analysis
blocker. There is still no measured new candidate that meets 110 MHz.

The next focused investigation is to trace the repeated RS control loads
and data selections in both variants back to their actual RTL predicates,
then obtain complete setup-path information for the selected endpoints.
This screening result supports that investigation; it does not yet prove
which rewrite improves Fmax. Defer further width reduction or additional
arithmetic parallelism while the adopted-seed high-arrival endpoints are
predominantly in RS. Any candidate must preserve cycle budgets and output
semantics and improve the common core/mem objective in routed trials.

## Evidence and reproduction

[Summary, top endpoints, locations and hashes](endpoint-arrivals.json).
[Raw detailed reports, P&R logs, all mapped arrivals and collector](endpoint-arrivals-evidence.tar.gz).
The collector validates report equality, checksums, cell mappings and the
archive's report hashes. It records original temporary paths; adjust them
for another checkout. The diagnostic archive contains no new RTL.

Produce each variant's synthesis JSON in its own directory using the
existing driver, then run normal P&R from that JSON. For example, with the
pinned suite on PATH and from one variant's isolated checkout:

```sh
bash ci/run_pnr.sh 9k core-32acs-rsconst --freq 65 --seed 1
nextpnr-himbaechel --json build/design.json \
  --device GW1NR-LV9QN88PC6/I5 --vopt family=GW1N-9C \
  --vopt cst=constraints/tangnano9k.cst --freq 110 --seed 1 \
  --detailed-timing-report --report build/detailed-report.json
```

Use `mem-32acs-rsconst` in a separate checkout for the second variant.
Keep the complete normal P&R sequence; do not reload a routed JSON with
`--no-pack --no-place --no-route`. An exit 1 after routing is the retained
110 MHz timing failure, not failure to obtain the detailed report.
No hardware/test source changed in this follow-up; the parent's completed
CI passed all 21 unittest methods. This does not qualify receiver-stream
behavior or physical PSRAM operation.
