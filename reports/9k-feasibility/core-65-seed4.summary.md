# 9k / core-32acs-rsconst

- Blocks: Viterbi + RS; controller: **none**
- Viterbi architecture: **32 ACS / 2 clocks per trellis step**
- RS syndrome schedule: **0 cycles/input byte (constant-16way)**
- Scope: protocol RTL only; DDR PHY, initialization and calibration excluded
- P&R at 65 MHz: **PASS**
- Placement/routing completed: **yes**
- Placement/routing seed: **4**
- 50.44 MHz Viterbi clock criterion: **PASS**
- ISDB-S Viterbi clock criterion: **57.72 MHz (PASS)**
- Conservative RS service bound: **3502 clocks/block**
- Minimum RS clock from cycle budget: **54.12 MHz**
- ISDB-S minimum RS clock from cycle budget: **61.93 MHz**
- Minimum shared clock from cycle budgets: **54.12 MHz**
- Hard throughput clock criterion: **PASS**
- ISDB-S minimum shared clock from cycle budgets: **61.93 MHz**
- ISDB-S hard throughput clock criterion: **PASS**
- End-to-end sustained throughput: **not measured by the sizing harness**
- 65 MHz timing criterion: **PASS**
- 110 MHz margin target criterion: **FAIL**
- extracted routed Fmax: **74.65 MHz**

Resource counts below are packed utilization before placement.

| Resource | Used | Available |
|---|---:|---:|
| VCC | 1 | 1 |
| IOB | 3 | 276 |
| LUT4 | 4879 | 8640 |
| OSER16 | 0 | 80 |
| IDES16 | 0 | 80 |
| IOLOGICI | 0 | 276 |
| IOLOGICO | 0 | 276 |
| MUX2_LUT5 | 164 | 4320 |
| MUX2_LUT6 | 0 | 2160 |
| MUX2_LUT7 | 0 | 1080 |
| MUX2_LUT8 | 0 | 1080 |
| ALU | 2014 | 6480 |
| GND | 1 | 1 |
| DFF | 2479 | 6480 |
| RAM16SDP4 | 0 | 270 |
| BSRAM | 3 | 26 |
| ALU54D | 0 | 10 |
| MULTADDALU18X18 | 0 | 10 |
| MULTALU18X18 | 0 | 10 |
| MULTALU36X18 | 0 | 10 |
| MULT36X36 | 0 | 5 |
| MULT18X18 | 8 | 20 |
| MULT9X9 | 0 | 40 |
| PADD18 | 0 | 20 |
| PADD9 | 0 | 40 |
| GSR | 1 | 1 |
| OSC | 0 | 1 |
| rPLL | 0 | 2 |
| FLASH608K | 0 | 1 |
| BUFG | 0 | 22 |
| DQCE | 0 | 24 |
| DCS | 0 | 8 |
| DHCEN | 0 | 24 |
| CLKDIV | 0 | 8 |
| CLKDIV2 | 0 | 16 |
| MIPI_IBUF | 0 | 22 |
| MIPI_OBUF | 0 | 20 |
