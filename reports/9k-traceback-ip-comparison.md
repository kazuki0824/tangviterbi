# PR #8 follow-up: traceback architecture comparison (preliminary, not a receiver qualification)

## Correction of earlier status statement

The historical 9K README reports that a **legacy** Viterbi benchmark failed an independent noiseless decode. That statement must NOT be transferred to the **current PR #8 three-context decoder**: its `tests/test_three_context_k7.py` runs two RTL memory variants, verifies 36,864 total input trellis steps against an independent metric/survivor oracle, and checks clean-stream decoded bits after the first 64 bits. Those are reported local checks, **not** evidence of complete receiver qualification. PR #8's current three-context split-bank candidate is still rejected by post-route 51.926476 MHz < required 100.848485 MHz and 3317 LUT4+ALU lower-bound > its 2096-I area allowance.

## Reviewed RTL and sources

* Current #8: `rtl/three_context_k7.sv`, `experiments/three_context_k7.py`, `tests/test_three_context_k7.py`, `reports/three-context-k7-results.md`. The 32-ACS baseline in main is **not** an equivalent three-context comparison.
* External reference: [coole198669/viterbi_decoder, traceback.v at 5412b61](https://github.com/coole198669/viterbi_decoder/blob/5412b61196a425179def39e030828dac978161da/traceback.v), [viterbi_core.v](https://github.com/coole198669/viterbi_decoder/blob/5412b61196a425179def39e030828dac978161da/viterbi_core.v). LGPL license notice in README; preserve headers and review redistribution obligations before vendoring.
* `traceback.v` counts from `tb_len_i << 1`, issues a survivor-memory read on alternate cycles, updates a 6-bit state on returned valid data, and emits 32-bit half or 64-bit full block results. Its `tb_rd_o/tb_addr_o/tb_rdata_i` are **external memory interfaces**, not a free internal RAM. `viterbi_core.v` runs 64 BMU/ACS lanes and has frame/segment control; it is not a drop-in replacement for #8's 16-ACS four-clock context scheduler.
* `traceback.v` also has two procedural drivers for `tb_bits_valid_r`, one of which looks intended for `last_bit_load_r`. That is a concrete RTL defect/synthesis ambiguity to resolve in an adapted implementation. Do **not** silently assume the upstream block is production-ready.

## Head-to-head architecture and scheduling

| Dimension | #8 existing three-context implementation | coole198669 approach |
|---|---|---|
| Trellis datapath | 16 ACS, 4 clocks/step, shared across 3 contexts | 64 BMU + 64 ACS, one full-state step in parallel |
| Survivor access | #8 generated in-place context-selected store + traceback | 64-bit survivor row per trellis step; external 64-bit read interface |
| Traceback schedule | advances under context slots; stalls and context isolation tested | segment-triggered, sequential reverse memory reads on alternate clocks |
| Block result | per-context stream bits | 32/64-bit block output after traceback interval |
| One traceback of length 64 | current effective service schedule must be derived from #8 RTL | at least 128 counter clocks for one length-64 segment, excluding startup/output handshakes |
| Context-switch state | per-context state in #8 RTL | not built into upstream; 3 contexts need state, address, scratch, arbitration |
| Proven same-device utilization | 3317 LUT4+ALU lower bound, 4 BSRAM, 51.926476 MHz (split variant) | NOT measured |
| Integration verdict | functionality tested; P&R performance fails | not a drop-in and no proof of improvement |

**Memory calculation (logical payload only):** storing 64 survivor bits for 64 steps per context takes 4096 bits; three contexts take 12,288 bits. This is not an estimate of physical BSRAM count, which depends on ports and packing. The upstream 64-bit survivor read per alternate clock cannot be assumed to fit a single physical BSRAM port/shape in Gowin. Buffer overwrite safety and simultaneous ACS writes remain to be checked.

**Timing bound:** for #8, accepted trellis steps must sustain 25.212121 Mstep/s, or at least 100.848484 MHz at four clocks/step *before* any extra stalls. A traceback memory scheme alone cannot eliminate the current measured soft/erasure -> BM -> ACS critical path (logic 8.72 ns and routing 10.54 ns). Replacing only traceback is therefore **not a demonstrated route to timing closure**. Retaining a four-clock interface is an explicit acceptance gate.

## Controlled comparison implementation and remaining evidence

1. Establish a structurally equivalent #8 fork with the same 16-ACS input and metric math, soft precision (8-bit), puncturing erasures, 3-context interleaving, reset/idle behavior and required 25.212121 Mstep/s. Change ONLY survivor storage/traceback.
2. Implement upstream-inspired sliding-window double-buffering with bounded memory ports; do not vendor the upstream RTL verbatim, because of the 64-ACS/frame interface mismatch and the multiple-driver finding.
3. Run the existing independent oracle suite for both versions, plus uninterrupted operation and wraparound across many windows; compare full decoded-bit sequence, not only survivor decisions.
4. Synthesize, place and route both with pinned OSS CAD, identical GW1NR-LV9QN88PC6/I5, constraints, seed and 108 MHz target. Record routed MHz, LUT4, ALU, FF, RAM16SDP4, BSRAM, DSP, and negative outcomes explicitly.
5. Check unchanged four-clock interval, simultaneous survivor read/write collisions, three-context schedule and flush latency. Reject an apparent area win that misses either Fmax or the 2096-I logic budget; do not claim whole-receiver feasibility from a partial block.

**Current implementation (2026-10-23):** `rtl/three_context_k7_window.sv` changes only the existing decoder's 60-convergence/64-emission window to 64-convergence/64-emission, adjusts the traceback start position, and retains the same 16-ACS, 8-bit soft metrics and context scheduler. `tests/test_three_context_k7_window.py` runs the independent oracle on that candidate; `ci/compare_traceback_pnr.py` and `.github/workflows/traceback-comparison.yml` execute both candidates on identical GW1NR-9 settings (108 MHz, seed 1). This is an **upstream-inspired scheduling experiment**, not a verbatim port of coole198669's 64-ACS RTL or its exact external SRAM microarchitecture. Baseline+experimental oracle CI at commit `c07f21a` succeeded (run 39911060518). The newly added paired-P&R run at commit `0186a70` must be inspected for results before a quantitative conclusion. The same-clock schedule does not independently guarantee enough receiver area or throughput.

## Same-target comparison measured by CI (run 39911179061)

Matched `GW1NR-LV9QN88PC6/I5`, same 108 MHz target and seed 1; both completed routing. CI workflow jobs are green because the measurement driver does **not** enforce the timing/area acceptance gates; `partial_target_pass` is false for **both** candidates.

| P&R measurement | Existing #8 split-bank 60+64 | Trial 64+64 window | Delta |
|---|---:|---:|---:|
| Routed Fmax (MHz) | 51.9264755 | 57.0873985 | +5.160923 (+9.94%) |
| LUT4+ALU position lower-bound | 3317 | 3311 | -6 |
| DFF | 757 | 757 | 0 |
| BSRAM | 4 | 4 | 0 |
| RAM16SDP4 | 160 | 160 | 0 |
| Required minimum MHz (4 clocks/step) | 100.848485 | 100.848485 | both fail |

This is **not** a viable receiver architecture. The trial is also well above the K7-only `2096-I` logic allowance. The CI baseline and experimental oracle checks in run 39911060518 succeeded; this does not cover complete receiver operation, all continuous streaming and full physical I/O timing. Measured values were taken from individual P&R job logs rather than inferred from the workflows' green check marks.

Compare artifacts:
- [Existing 60+64](https://github.com/kazuki0824/tangviterbi/actions/runs/39911179061/artifacts/12482509388)
- [Experimental 64+64](https://github.com/kazuki0824/tangviterbi/actions/runs/39911179061/artifacts/12483175622)

Next: the remaining BM->ACS critical path needs pipelining/overlap without increasing four clocks/step, and metric/survivor physical banks need to fit the overall `2096-I` allocation. A real implementation of the upstream two-cycle SRAM schedule and 64-ACS alternative, including actual Gowin port mapping, is **not** covered by this narrowly controlled timing experiment.

## Direct external-IP RTL measurement (run 39960597565, 2026-10-23)

The actual pinned `coole198669/viterbi_decoder` 64-ACS decoder was synthesized twice with Yosys Gowin flow, not merely the 64+64 local derivative. Source SHA256 values and full mapped netlist are recorded by CI. Results:

| Variant | Mapped top LUT4+ALU | Mapped FF | P&R | Admissible Fmax |
|---|---:|---:|---|---|
| Upstream unmodified | 38 (P&R 77) | 27 | completes with core optimized out | **None: invalid** |
| Upstream traceback multiple-driver corrected | **8567** | **1863** | failed legal placement (ALU) after 57,668,431 attempts | **None: unrouted** |

The source file `traceback.v` writes `tb_bits_valid_r` from two procedural blocks; diagnostic second run changes the first to `last_bit_load_r` and preserves original code in unmodified case. This dramatically changes what the synthesizer retains. **Do not interpret 172/194 MHz unmodified result as external-IP performance.** The corrected mapped top has 8567 LUT4+ALU, near the device's 8640 nominal LUT4 positions, and is already a **single-context** original 64-ACS decoder, not the three-context 16-ACS RTL. Nominal 8567/8640 alone does not prove or disprove physical fit because ALU packing, RAM and placement constraints apply. Actual legal placement failed and no timing/Fmax exists. The `mapped_top_is_flat=false` flag reflects Yosys $scopeinfo/internal module declarations in its emitted JSON, so infer fit from *mapped top cell types and placement failure*, not that flag alone. Observe that baseline PR #8 has **3317 post-route** positions and **757 post-route** FF; these are not matched mapping-stage counts.

[Direct CI Run](https://github.com/kazuki0824/tangviterbi/actions/runs/39960597565).

**Defensible conclusion:** coole198669's original 64-ACS one-context IP as tested cannot be adopted as an already-fitting, routed three-context 9K decoder. Local 16-ACS design has considerably smaller measured logic footprint but itself fails its 100.848485 MHz deadline, and its area exceeds the allocated K7-alone 2096-I budget. Therefore **neither measured implementation qualifies for the whole receiver**. Whether a redesigned 3-context implementation employing coole's traceback/memory scheduling could meet area+timing remains an open engineering question requiring an equivalent-function implemented candidate, not conjecture from IP counts.

**Still unverified:** side-by-side independent functional decoding of corrected upstream with matching 8bit soft and erasure semantics; rate-normalized throughput and three-context save/restore; cross-seed placement and entire decoder/receiver. CI job green is only successful measurement execution and does not change rejection.

## Alternating-cycle Survivor read experiment (run 40106415482)

The PR now contains `rtl/three_context_k7_coole_scheduled.sv`, a **three-context adaptation of the external implementation's every-other-clock survivor read + subsequent state transition schedule**, retaining the baseline 16-ACS, four clocks per accepted step, 8-bit soft inputs and erasure interface. Unlike the earlier window-only experiment, this changes the memory access/traceback scheduling. It is **not** a full `coole198669` 64-ACS port; upstream's exact microarchitecture remains distinct.

| GW1NR-9 mapped, routed measurement (108MHz target, seed 1) | Existing #8 | 64+64 window-only | Alternating-cycle external-inspired scheduling |
|---|---:|---:|---:|
| Routed Fmax (MHz) | 51.926476 | 57.087399 | **43.230156** |
| Post-route LUT4+ALU | 3317 | 3311 | **2909** |
| DFF | 757 | 757 | **610** |
| BSRAM | 4 | 4 | **4** |
| RAM16SDP4 | 160 | 160 | **128** |
| Necessary 100.848485MHz | FAIL | FAIL | **FAIL** |

The coole-scheduled trial saves 408 logic positions, 147 DFF and 32 RAM16SDP4 against the existing #8, **but loses 8.696 MHz Fmax**. It cannot be adopted under the stated ISDB-T rate contract. The P&R job's green status means experiment executed; `partial_target_pass=false`. [CI measurement](https://github.com/kazuki0824/tangviterbi/actions/runs/40106415482).

**Functional qualification:** `tests/test_three_context_k7_coole_scheduled.py` was added to compare the new variant against the same independent metric/survivor/decoded-bit oracle. This result must be explicitly checked before functional claims. Do not infer functional correctness from P&R. Physical receiver integration and downstream output service contracts are still unverified.
