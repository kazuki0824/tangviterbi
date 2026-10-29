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

## Validated final three-context comparison — 2026-10-25

**Run [40196899136](https://github.com/kazuki0824/tangviterbi/actions/runs/40196899136), source `02df5b8c8c2b39e4460fc2f0184eb42061d7a7f0`.**

The independent long-stream oracle succeeded across all three measured implementations: baseline 2 test cases, 64/64-window 1 test case, and coole-inspired alternating survivor read 1 test case. Each exercises 6 epochs, 3 contexts, 1024 symbols/context/epoch (18,432 trellis steps per variant), including soft metrics, puncturing/erasure, context interleaving, idle and reset. The coole-inspired variant's previously failing test now passes.

### The actual error and correction

Commit `caa2119d` changed `read_ptr <= wr_ptr-1;` into `read_ptr <= wr_ptr-4; // comment` on a line that also contained `state[context_id] <= 0; walk[context_id] <= 0;`. The line comment **accidentally suppressed both assignments**, so the tracing state and walk counter were not reset at the start of each block. This introduced a real regression in our experimental RTL. In the failing CI, 15 start events per epoch/context sometimes coincided with stale `walk==123`; the `if(start_trace)` priority suppressed 1–7 actual completions, explaining the loss of 64-bit blocks. The test bench also initially contained a shadowed `actual` variable and read a deleted temporary file; those diagnostic-test defects were fixed separately and must not be attributed to the decoder.

Commit `02df5b8c` places `read_ptr`, `state` and `walk` reset assignments on separate active lines. The existing independent oracle suite proves this correction in run 40196899136, without weakening the decoded-bit assertions. We did not add special handling for simultaneous start/completion; the coincidence arose from the missing trace counter reset.

### Matched target measurements

All three locally equivalent 3-context, 16-ACS, 8-bit soft/erasure RTL candidates used `GW1NR-LV9QN88PC6/I5`, 108 MHz constraint, seed 1; all completed routing but **failed** the required 100.848485 MHz.

| Metric | Current #8 split banks | 64/64 local window | coole-inspired alternating read, corrected |
|---|---:|---:|---:|
| Post-route Fmax MHz | 51.926476 | 57.087399 | **42.526047** |
| LUT4+ALU positions | 3317 | 3311 | **2905** |
| FF | 757 | 757 | **610** |
| BSRAM | 4 | 4 | **4** |
| RAM16SDP4 | 160 | 160 | **128** |
| Independent full-stream oracle | PASS | PASS | **PASS** |
| Required clock 100.848485 MHz | FAIL | FAIL | **FAIL** |
| K7-only allowance `2096-I` logic positions | FAIL | FAIL | **FAIL** |

The corrected alternating-read experiment saves 412 positions (12.42%), 147 FF and 32 RAM16SDP4 compared with #8 but *reduces* Fmax by 9.400429 MHz (18.10%). This is a negative adoption result. The 64/64 local-window trial has the best observed route Fmax (57.087399 MHz), still far below the minimum; its advantage is seed-specific and not a receiver qualification.

### Direct upstream original-IP cross-check

The real `coole198669` 64-ACS **single-context** IP RTL (pinned 5412b61), including its BMU/ACS/normalizer/traceback, was evaluated separately. Original upstream multi-driven traceback produces an invalid optimized-away netlist. Correcting that multiple-driver fault retains 8567 mapped LUT4+ALU and 1863 FF, but placement on 9K fails; no valid routed Fmax. This upstream original is neither an equivalent 3-context design nor an observed lower-area alternative. Do not compute direct equivalence ratios between mapped original and post-route adapted designs.

**Comparison conclusion:** among controlled same-semantics adaptations, the original #8 and the coole-style traceback schedule both fail 9K timing/area constraints; the coole-style schedule trades speed for area rather than solving either acceptance gate. A viable redesign has not been established. This **closes the specifically requested side-by-side comparison** of this external traceback approach, not the ISDB receiver or a search over every possible K7 design and not the entire open-source IP catalog. The PR remains Draft as evidence, not a mergeable decoder. No rebase/Resolve/merge.

## 2026-10-30 BM staging versus branch-delta experiment

[CI run 40903217765](https://github.com/kazuki0824/tangviterbi/actions/runs/40903217765): all independent functional tests, including staged-BM, BM-delta and static mutation guards, succeeded. All candidate P&R jobs completed; all timing outcomes remain below requirement.

| Candidate | Routed Fmax (MHz) | LUT4+ALU | FF | BSRAM | RAM16SDP4 | Oracle |
|---|---:|---:|---:|---:|---:|---|
| Existing #8 | 51.926476 | 3317 | 757 | 4 | 160 | PASS |
| BM-staged | 64.846642 | 3347 | 793 | 4 | 160 | PASS |
| BM-delta | 64.796219 | 3493 | 793 | 4 | 160 | PASS |

BM-delta changes the signed modulo comparison algebraically from (src1+branch1)-(src0+branch0) to (src1-src0)+(branch1-branch0), keeping 13-bit metrics and 4 clocks/step. It worsens Fmax by 0.050423 MHz and increases logic by 146 versus BM-staged; reject BM-delta. BM-staged improves Fmax but is still <100.848485 MHz and exceeds the K7 allowance 2096-I. No receiver acceptance claim.

Static mutation guard tests detect the earlier start_trace state/walk reset comment-out bug and preserve interfaces. These are technical safeguards; they are **not a substitute** for explicit continuation-versus-interruption decisions.

Next design questions are ahead-of-step branch-metric overlap without added cycles, per-lane ACS routing, metric/survivor bank reassignment and full receiver resources/deadlines. The present benchmark does not qualify any complete design.
