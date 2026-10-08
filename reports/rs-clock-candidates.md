# 9K RS clock-path candidate screening

Hardware baseline: `754c111695dc64651466e729155846fcc08d2bbb`; no
candidate RTL is adopted in this report. OSS CAD Suite 2026-10-04,
`GW1NR-LV9QN88PC6/I5`, `GW1N-9C`, same CST, 110 MHz constraint,
default P&R and paired seeds. Core means Viterbi + RS; mem adds the same
PSRAM controller. The 20K profile is not part of this 9K optimization.

## Endpoint provenance

The baseline core worst launching register maps to RS `out_index` and
captures the RAM output-associated DFF. The baseline mem worst launching
register maps to RS `bm_n` and captures `discrepancy` at `ST_BM_START`
(`discrepancy <= synd[bm_n]`). The repeated high raw-arrival mem reset
loads map to `feedback_a`/`feedback_b`, while the CE loads map to
`out_index`. Baseline core lambda select is `lambda_select`, and a RAM
associated CE load is `out_primed`. Inferred RAM output DFF has no
pre-ABC original-register tag. The Yosys FSM is already one-hot (28 bits).

Provenance was injected as a cell attribute on DFFs before ABC. Stripping
only those tags yields byte-for-byte identical JSON objects for both
baseline variants; the method does not change their netlist. Archive
includes trace scripts/logs and original-register mappings. Raw arrival
rankings alone do not give setup slack; full endpoint path diagnostics
are being measured separately with the pinned nextpnr source.

## Isolated candidates, common seed 1

Baseline: core **104.32**, mem **105.41**, common minimum **104.32 MHz**;
packed LUT4 **4902/5045**, DFF **2487/2625**, BSRAM 3/3, DSP 8/8.

| Candidate | Core MHz | Mem MHz | Paired min MHz | LUT4 core/mem | DFF core/mem |
|---|---:|---:|---:|---:|---:|
| maskdecode | 94.22 | 99.20 | 94.22 | 4870/5041 | 2487/2625 |
| discmask | 99.90 | 99.44 | 99.44 | 4873/5044 | 2503/2641 |
| discbanks | 101.02 | 90.02 | 90.02 | 4898/5058 | 2519/2657 |
| addrfuse | 98.48 | 88.06 | 88.06 | 4897/5046 | 2487/2625 |
| banks-addrfuse | 102.59 | 102.49 | 102.49 | 4885/5052 | 2519/2657 |
| bm4 | 99.67 | 104.84 | 99.67 | 4872/5023 | 2486/2624 |
| prefix-dualbyte | 72.51 | 107.28 | 72.51 | 4876/5036 | 2495/2633 |
| banks-prefix-dualbyte | 77.89 | 93.55 | 77.89 | 4910/5054 | 2527/2665 |
| addrprefix | 95.68 | 101.95 | 95.68 | 4891/5041 | 2487/2625 |
| dualbyte | 97.64 | 95.18 | 95.18 | 4886/5052 | 2495/2633 |

All 20 candidate seed-1 runs completed routing. None improves the paired
seed-1 objective. `banks-addrfuse` banks 16 syndrome entries in four
4-entry prefetch paths and folds `out_primed` into the output-address
adder. It was the best combined seed-1 trial and was also swept for all
ten paired seeds. Other trials isolate the syndrome mask/index selection,
BM index width, RS address carry logic, and Viterbi survivor byte selection.
Their source differences are archived; these are experimental snapshots.

| Paired seed | Baseline min MHz | Candidate core MHz | Candidate mem MHz | Candidate min MHz |
|---:|---:|---:|---:|---:|
| 1 | 104.32 | 102.59 | 102.49 | 102.49 |
| 2 | 100.26 | 111.50 | 100.01 | 100.01 |
| 3 | 100.14 | 104.56 | 100.48 | 100.48 |
| 4 | 89.43 | 102.39 | 101.79 | 101.79 |
| 5 | 97.45 | 93.25 | 88.92 | 88.92 |
| 6 | 100.96 | 103.20 | 85.21 | 85.21 |
| 7 | 95.06 | 107.34 | 92.85 | 92.85 |
| 8 | 94.29 | 89.39 | 106.33 | 89.39 |
| 9 | 103.01 | 104.43 | 91.53 | 91.53 |
| 10 | 92.77 | 101.38 | 103.75 | 101.38 |

The candidate's best common minimum is **102.49 MHz** (seed
1), below the baseline's **104.32 MHz** (seed 1). Candidate seed 2
does pass core at **111.50 MHz**, but mem reaches only **100.01 MHz**.
No shared seed reaches 110 MHz in both variants, so this candidate is
not suitable for adoption. These trials show that local logical changes
can shift the critical path into the Viterbi survivor RAM/byte path; a
change to the original RS critical cone does not guarantee paired Fmax.

## Checks and limits

All isolated variants' P&R logs and reports are in the archive; synthesis
and current source files are included. Selected candidate benches pass
the independent 16/10-bit Viterbi metric/survivor model or constant RS
schedule test, as appropriate. Yosys SAT proofs in the archive check
address arithmetic across all index/phase combinations, 4-bit BM index
range transitions, syndrome mask/bank selection algebra under their
stated cycle predicates, and the captured survivor byte selection under
stable read phase. Those local proofs do not establish equivalence of
the complete Viterbi + RS receiver. The adopted baseline's 21 unittest
methods are covered separately by the normal CI workflow.

The 110 MHz target remains unmet; mandatory 54.12/61.93 MHz sizing floors
and 65 MHz feasibility have passed on the adopted hardware. This result
does not qualify sustained receiver operation or real PSRAM PHY startup.

Evidence: [machine-readable results](rs-clock-candidates.json) and
[raw logs, source snapshots, proofs and provenance](rs-clock-candidate-evidence.tar.gz).
