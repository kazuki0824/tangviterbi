# tangviterbi

Resource/timing benchmark for an ISDB-T-oriented FEC partition on Sipeed Tang Nano 4K and Tang Nano 9K.

The benchmark answers a specific sizing question:

> Can a 16-ACS, K=7 Viterbi decoder with 8-bit soft metrics, a compact RS(204,188) decoder, and a small HyperRAM/PSRAM protocol controller fit and meet the clock budget on Tang Nano 4K or 9K?

## Throughput target

The working worst-case budget for 13-seg ISDB-T is:

- trellis rate: about **25.2 Mstep/s**
- 16 ACS lanes: **4 cycles per trellis step**
- minimum FEC clock: about **100.8 MHz**
- CI timing target: **110 MHz**

Targets:

| Board | FPGA |
|---|---|
| Tang Nano 4K | GW1NSR-LV4CQN48PC7/I6 |
| Tang Nano 9K | GW1NR-LV9QN88PC6/I5 |

## RTL

### Viterbi

`rtl/viterbi_k7_16acs.sv`

- K=7
- mother code generators 171/133 octal
- 8-bit unsigned soft inputs
- 16 ACS lanes
- four clocks per trellis step
- banked 64-state path metrics
- 64-step survivor store

### RS(204,188)

`rtl/rs204_188_compact.sv`

The RS block is deliberately serialized to minimize logic:

- one shared GF(256) multiplier
- 16 syndromes
- sequential Berlekamp-Massey
- sequential Chien search
- sequential Forney path
- 204-byte block buffer

This architecture is intended to represent a small hardware decoder, not the large fully-parallel generic RS cores that distort the 4K/9K comparison.

**Important:** the shortened-code symbol-position convention and final Forney correction mapping still need bit-exact validation against ARIB-compatible test vectors. Until then, this block is suitable for **resource/timing sizing**, not as a production-qualified RS decoder.

### Memory controller

`rtl/hyperram_ctrl.sv`

This is the command/address/data-path controller used to measure controller overhead.

- 4K build: x8 datapath
- 9K build: x16 datapath

It deliberately excludes Gowin's proprietary/generated DDR PHY and calibration macro. Therefore the `mem` result measures **open RTL protocol-controller overhead**, not the complete physical PSRAM interface.

## CI variants

Six jobs are run so the resource delta is visible instead of collapsing everything into one number:

| Variant | Viterbi | RS | memory controller |
|---|---:|---:|---:|
| `viterbi` | yes | no | no |
| `core` | yes | yes | no |
| `mem` | yes | yes | yes |

Each variant is placed and routed for both 4K and 9K.

## Toolchain

GitHub Actions uses OSS CAD Suite 2026-10-04:

- Yosys `synth_gowin`
- nextpnr-himbaechel
- Project Apicula device database

The CI does place-and-route, not synthesis-only, so timing is based on a routed design.

## Result

The table below is updated from the CI results after the implementation converges.

| Target | Variant | P&R | LUT/logic | FF | BSRAM | DSP | Routed Fmax | 110 MHz |
|---|---|---|---:|---:|---:|---:|---:|---|
| Tang Nano 4K | viterbi | pending | | | | | | |
| Tang Nano 4K | core | pending | | | | | | |
| Tang Nano 4K | mem | pending | | | | | | |
| Tang Nano 9K | viterbi | pending | | | | | | |
| Tang Nano 9K | core | pending | | | | | | |
| Tang Nano 9K | mem | pending | | | | | | |

## Scope

A PASS at 110 MHz means the selected FPGA implementation has enough routed clock margin for the 16-ACS throughput assumption. It does not prove a complete ISDB-T receiver. RF acquisition, depuncturing/interleaving integration, S31↔FPGA transport, clock-domain crossings, and bit-exact end-to-end verification remain separate tasks.
