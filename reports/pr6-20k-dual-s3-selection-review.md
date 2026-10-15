# PR #6: 20K + dual ESP32-S3 simultaneous T/S — architecture-selection review

**Status: archived research evidence, not an adopted or qualified receiver.**
Frozen source snapshot: [PR #6 at `9aab5c3a9fec`](https://github.com/kazuki0824/tangviterbi/tree/9aab5c3a9fec4bba40ad0640780861e973e5dbb6).
Baseline `main`: `4f92e8ee52256375e1ce10890e77986509444332` (before this archival commit).
The entire evaluation is scoped to one Tang Nano 20K board, two ESP32-S3-WROOM-1U modules (independent T and S RF tune), simultaneous full ISDB-T and conventional ISDB-S TS outputs. ISDB-S3, video decoding and CAS are out of scope.
The per-SoC RF input and any necessary frequency converters, filters and satellite LNB supply are **not** supplied by the three boards alone.

## Decision record — why candidate B must not be treated as selected

The first PR #6 revision ([initial estimate](https://github.com/kazuki0824/tangviterbi/blob/e388f88ca11e17cba2d8d8f04a79206d81c3ce6d/reports/20k-dual-s3.md)) prioritized candidate B:
the two S3s capture and transfer native I10/Q10; the FPGA performs both demodulators, a tiled T FFT using shared SDRAM, and shared T/S/TMCC RS.
It was explicitly only a **validation hypothesis** (performance-admitted and adopted receivers: zero).
The initial design *allocation*, not whole-receiver synthesis, was 18,737/20,736 logic sites (90.36%), 43/46 BSRAM, 38/48 DSP.
After standalone RTL/placement evidence, the revised allocation was 20,452/20,736 logic sites (98.63%), 44/46 BSRAM and 38/48 DSP.
Thus 1,715 of the originally available 1,999 logic sites were consumed by revisions without proving that all omitted receiver blocks fit.

Known before candidate B was prioritized:
- S3-S RF + API CPU low/high models were approximately 90.14% / **106.81%**, neither a measured joint worst case;
- S3-S I/Q transfer required 100 MB/s; the modeled Octal+Quad route left only 3.7035 MB/s (3.57%) spare, with no independently verified physical timing;
- T/S links + two serial TS ports + event pins exhausted the modeled **34/34** available connector signals, even before resolving physical pin conflicts.

This should have triggered cheap, decisive feasibility gates **before** specializing the memory-controller and buffer architecture.
Enumerating 16,384 FPGA/S3 stage-ownership pairs did not enumerate alternate FFT *algorithms*, streaming dataflows or resource-sharing schedules.
Selecting B as an experiment was defensible; continuing to treat it as the leading implementation without reranking after the budget collapsed was not.
No available result proves B impossible for every implementation or proves another partition feasible.

## Preserved positive and negative evidence (do not conflate)

| Evidence | Finite result or boundary | What it **does not** prove |
|---|---|---|
| [Two-slot vs three-slot frame experiment](20k-dual-s3-frame-stream.md) | The two-slot trial violated the T Mode-1 deadline in 20/48 frames; the three-slot trial passed its stated finite conditions, but Mode-1 T-client headroom was only **0.502955 µs / 259.875 µs (0.19%)** | All phases, sustained real RF arrival, downstream stalls, full receiver |
| [SDRAM traces and failures](20k-dual-s3-memory-contract.md), [turnover](20k-dual-s3-memory-turnover.md) | Shared SDRAM average demand estimated at **271.266 MB/s**, of which T tile FFT consumes **189.137 MB/s**; row-conflict traffic was measured below the assumed blanket 65% efficiency; older scheduling and staging choices yielded unbounded queue/backlog counterexamples | Guaranteed bandwidth or WCET at a synthesized 135 MHz interface |
| [Partial FPGA placement](20k-dual-s3-fft-sdram.md) | The standalone shared RS placement/timing run missed 162 MHz (**157.431 MHz** shown with nonzero exit), and the available nextpnr timing model omitted some DSP/dual-port RAM arcs | Correct full-chip timing at 162 MHz |
| [Frame-stream partial synthesis](20k-dual-s3-frame-stream.md) | Mode-3 subset: 10,955 LUT+ALU, 29 BSRAM, 10 DSP, plus distributed RAM; assigning extra buffers separately can require **47/46 BSRAM** | Complete FPGA receiver fit or that buffers can be added for free |
| [S3 + link audit](20k-dual-s3.md) | 40/100 MB/s T/S native I/Q, assuming 16/40 MSa/s and lossless packing, with 80 MSa/s S sensitivity explored separately | RF-quality, uninterrupted radio capture, pin-map setup/hold, actual interconnect WCET |

The numerical results are trace- and implementation-specific. Some reports deliberately retain failed experiments, then later repairs; read their dated scope instead of promoting any earlier failure or pass into a global result.

## Reusable output and reproduction boundary

- [Whole-stage/transport inventory and limits](20k-dual-s3.md), [shared-RS schedules](20k-dual-s3-progress.md), [T deinterleaver](20k-dual-s3-t-time-dma.md), [S permutation](20k-dual-s3-s-frame-dma.md), [memory clients](20k-dual-s3-memory-clients.md), and [FFT/bus](20k-dual-s3-fft-memory.md) are archived as historical reports.
- The complete [`reports/20k-dual-s3/`](20k-dual-s3/) recorded evidence tree (128 files, including all candidate route tables, JSON/CSV counterexamples, source-hash manifests, compressed synthesis/RTL snapshots) was carried across **unaltered**, so counterexamples and trial provenance are retained even if the PR branch is deleted.
- Seven independent, non-receiver `experiments/dual_*.py` analytical models and four associated standalone `tests/test_dual_*.py` unittest modules are retained for future reassessment. They model finite workloads, not RF or static-timing acceptance. On the PR branch, the respective **21 unit tests** passed in the observed CI job; this archival transfer itself is not a new execution or whole-CI pass.
- All active `rtl/dual_*.sv`, CI modifications, and RTL-integrated testbenches stay exclusively in PR #6. Any relative link to excluded source is pinned to the frozen PR revision. No PR closure, rebase or history rewrite is implied.

## Required gates before choosing the next leading architecture

1. Verify the **actual RF premise**: usable T and conventional-S I/Q sample rates, converter/LNB requirements, RF filters, C/N/MER/BER and continuous capture. The ESP32-S3's internal Wi-Fi RF is not a broadcast-band tuner; external converters are mandatory.
2. Verify both **lossless** source-to-FPGA links concurrently at 40/100 MB/s (or re-evaluate the S=80 MSa/s case requiring 200 MB/s). Include frame markers, jitter, driver/CPU worst cases, bank ownership, all simultaneous connector uses and real pin electrical constraints.
3. Compare the existing SDRAM-heavy tiled FFT against **on-chip streaming/hybrid FFT** architectures at unchanged input fidelity. Count actual BRAM/DSP/LUT, worst arbitration delay and exact output order. PlutoSDR's FPGA FFT/early equalization is relevant as a *design principle*, not a directly transplantable Xilinx FFT core or a proof that S3 can replace AVX2 PC FEC.
4. If moving T deinterleaving/Viterbi/RS onto S3 is considered, require real S3 WCET and PSRAM capacity/traffic first; do not assume the N16 (without R8) has PSRAM, or that host-PC FEC benchmarks transfer to ESP32-S3.
5. For any finalist, integrate full RF synchronization, equalization/demapping, TMCC-controlled profiles, T/S error correction, transport and two TS outputs; pass whole-chip routing and **complete** STA for every clock, all T modes and GI values, S coding modes, adverse relative phases and sustained finite queue/credit limits. Real two-frequency TS and signal-quality testing remains separate.

The next architecture is **unselected**. The lessons and measured negative evidence remain valid regardless of whether PR #6 itself is closed.
