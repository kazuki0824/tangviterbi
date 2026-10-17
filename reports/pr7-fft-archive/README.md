# PR #7 retrospective archive — research evidence, not an adopted receiver

Source: https://github.com/kazuki0824/tangviterbi/pull/7
Frozen research HEAD: `0fcd7a2e059809a3eacbca03a881b3cbd04f5091`
Base main before preservation: `c5ff884550cc4a33243309091ae8a09c1c1680f4`
Status: **research retired; FPGA receiver NOT established**.

## Purpose and disposition

This directory preserves the original PR #7 research source, *including rejected RTL*, test oracles, benchmark scripts, architecture notes and four CI YAML snapshots **as inert files**. It does **not** promote `research_sdf_*` as production RTL, add their tests to the active test tree, merge PR #7, or claim full receiver acceptance. All files are byte-for-byte copies from frozen PR #7 HEAD; the original relative directory layout is retained underneath this archive. Research tools require restoring the original checkout layout (or adjusting their paths) before running them. Test fixtures run relative to repo-root `rtl/` paths; running them directly from this archive is not claimed or tested.

## Recorded evidence and limitations

- Functional positive evidence: https://github.com/kazuki0824/tangviterbi/actions/runs/38996746126 — independent Q15/Q1.16 DIF FFT whole-bin comparison for 2048/4096/8192 points, framed finite zero-tail test, synthetic 1-cycle external RAM. Later: https://github.com/kazuki0824/tangviterbi/actions/runs/39000576578 — `rtl-gates` success.
- Resource negative evidence: https://github.com/kazuki0824/tangviterbi/actions/runs/39000576578 — `mapped-resource-screen` reported `logic_cells=9047`, `dsp_cells=50` **exceeding Tang Nano 20K's 48 DSP18**. The `bsram_cells=0` report is **not evidence that zero BRAM is physically required**: primitive classification and independent P&R were not completed.
- Early synthesis red CI: https://github.com/kazuki0824/tangviterbi/actions/runs/39000186358 — Yosys specialization assert; not a physical resource impossibility proof.
- Structural issue: the experimental framed FFT drains with N−1 dummy input words and resets each frame. No gapless receiver throughput was demonstrated. The external delay port is an ideal synchronous 32-bit interface, **not** actual SDRAM arbitration, pin timing or refresh.
- Signal chain not implemented/qualified: two S3 raw-IQ continuously at native 16/40 MSa/s, simultaneous RF frontend, T/S synchronization, equalization, full FEC, output TS, 9K NOR multi-image switch, physical P&R/STA, worst-case S3 scheduling and I/O.

## Preserved items

- `experiments/`: FFT memory/traffic model and independent whole-array fixed-point oracle.
- `tests/`: arithmetic, stage handshake, oracle-vs-NumPy, 3-mode full-frame and framed-adapter bit-exact tests (archived, **not automatically run by main**).
- `rtl/`: research SDF and framed FFT source, pinned twiddle ROM, including the unsuccessful 50-DSP design.
- `ci/`: measured GW2A primitive count script.
- `reports/fft-architecture-reselection.md`: early calculations and historical limitations; use this README for the eventual decision.
- `.github/workflows/research-hybrid-fft.yml`: exact experimental CI snapshot only, intentionally **not active in main**.
- `.github/workflows/{fpga,s3-area,endpoint-diagnostics}.yml`: snapshots of PR #7 fan-out changes, separately applied as active workflow changes on main.

## Design decision for the next iteration

Reject only the **measured unshared-multiplier SDF implementation** at DSP 50/48. Do **not** reject all FFT algorithms, Tang Nano 20K, or either proposed receiver hardware configuration. Future candidate evaluation must measure shared/folded multipliers, DSP/BRAM/LUT together, sustained frame and DMA service, S3 native IQ and CPU WCET, full T/S chain, and complete physical timing. The new first-candidate comparison (9K T/S-switched and 20K T/S-simultaneous) is a distinct study.

## Static completion conditions

1. Compare this directory's archived files with PR #7 frozen-head GitHub blob SHAs (the folder includes all 14 non-workflow research files and all four workflow files).
2. Confirm the three active CI workflow files equal the PR #7 selected versions, with the unrelated base main content preserved.
3. Confirm no `rtl/research_sdf_*.sv`, `tests/test_research_*.py` or research-only CI workflow is active at repository root on main.
4. Confirm main fast-forward commit and then PR #7 **closed / merged=false**. Never interpret the archive as a qualified full receiver.

No rebase, force-push, resolve action, or PR merge was required.
