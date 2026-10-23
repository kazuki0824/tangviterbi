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
