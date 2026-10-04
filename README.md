# tangviterbi

Resource/timing benchmark for an ISDB-T-oriented FEC partition on Sipeed Tang Nano 4K and Tang Nano 9K.

The benchmark is intentionally narrow: it answers whether a **16-ACS, K=7 Viterbi decoder with 8-bit soft inputs, an RS(204,188) decoder, and a small HyperRAM/PSRAM controller core** can fit and meet the clock budget on the two Gowin devices.

## Target

For the worst-case 13-seg throughput budget used in the design discussion:

- trellis rate: about **25.2 Mstep/s**
- 16 ACS lanes: 4 cycles per trellis step
- required FEC clock: about **100.8 MHz**
- CI target: **110 MHz** (roughly 9% margin)

Targets:

| Board | FPGA |
|---|---|
| Tang Nano 4K | GW1NSR-LV4CQN48PC7/I6 |
| Tang Nano 9K | GW1NR-LV9QN88PC6/I5 |

## What is synthesized

Four builds are produced:

1. 4K, Viterbi + RS only
2. 4K, Viterbi + RS + x8 HyperRAM protocol-controller core
3. 9K, Viterbi + RS only
4. 9K, Viterbi + RS + x32 PSRAM/HyperRAM protocol-controller core

The Viterbi RTL is local to this repository. The RS(204,188) RTL is fetched in CI from
`freecores/reed_solomon_decoder` at commit
`2d581673ad7d3a97bca63c674b867ec80db0e2c6`.

The memory-controller block synthesized here is the command/data-path controller. It does
**not** claim to reproduce Gowin's proprietary generated memory PHY. That distinction is
important when interpreting LUT/Fmax headroom.

## Toolchain

GitHub Actions uses the pinned OSS CAD Suite 2026-10-04 release:

- Yosys `synth_gowin`
- nextpnr-himbaechel
- Project Apicula device database

CI runs place-and-route, not synthesis-only, so the timing result is a routed Fmax estimate.

## Result

The result table will be filled after the first CI run.

| Target | Variant | P&R | LUT/logic | FF | BSRAM | DSP | Routed Fmax | 110 MHz |
|---|---|---|---:|---:|---:|---:|---:|---|
| Tang Nano 4K | core | pending | | | | | | |
| Tang Nano 4K | core+mem | pending | | | | | | |
| Tang Nano 9K | core | pending | | | | | | |
| Tang Nano 9K | core+mem | pending | | | | | | |

## Interpretation

Passing 110 MHz means the 16-ACS time-multiplexing assumption has enough routed timing
margin for the 25.2 Mstep/s budget. It does **not** by itself prove a complete ISDB-T
demodulator: depuncturing, interleaving, buffering, clock-domain crossings, the ESP32-S31
interface, and RF acquisition are outside this benchmark.

The purpose of this repository is to replace the earlier 4K-vs-9K resource estimate with
a repeatable synthesis/P&R measurement.
