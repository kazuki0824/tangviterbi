# PR #6 FFT architecture re-selection — necessary-condition screen

**Not an implementation or an adopted first candidate.** Applies to Tang Nano 20K + 2 ESP32-S3 (simultaneous T and conventional ISDB-S); the separate Tang Nano 9K + 1 S3 T/S switching scenario must use separate NOR images and a separate 9K resource/PHY model. No extra software decimation, loss of I/Q bits, or LLR reduction is authorized.

## Recorded PR #6 decision error

The first B hypothesis used 18,737/20,736 logic positions and 43/46 BSRAM. Revised whole-receiver **allocation** is 20,452/20,736 and 44/46; the recent *incomplete* Mode-3 partial synthesis alone uses 42 BSRAM. These are not interchangeable measured whole-chip fits. Tiled T FFT caused modeled 189.137 of total 271.266 MB/s SDRAM traffic. S3-S native IQ needs 100 MB/s and a modeled Octal+Quad link retains 3.7035 MB/s (3.57%) only; S3-S low/high CPU utilization model is ~90.14/106.81%. A port model occupies 34/34 connector signals. These hard gates should precede deeper B-specific optimization.

## Alternative radix-2 single-path delay-feedback screens

Internal FFT is complex Q15 (4 bytes per sample); SRAM budgeting unit 2048 useful bytes per BSRAM. A radix-2 SDF requires N-1 samples of delay. Mode 3 N=8192 => 32,764 bytes, **16 BSRAM minimum** before input/output, multipliers, control and actual port inference. A hybrid variant places only the 4096-word maximum delay externally and retains up to 4095 words (16,380 bytes, **8 BSRAM minimum**) internally. Modes 1/2 need 4/8 minimum BSRAM for N=2048/4096 without that external delay. These are data-storage minima, **not synthesized SDF RTL resource measurements**.

At Mode 3 GI1/32, period 1,039.500 us: one external read + write per input complex sample = **63.045695 MB/s** theoretical mean, ignoring burst, refresh, arbiter, peak arrival shape and additional staging. Existing upstream T symbol RAM stores 29,952 bytes. Spilling it with one external read+write per symbol adds **57.627706 MB/s** ideal mean. Removing old 189.137 MB/s tiled FFT demand from 271.266 MB/s and adding these terms gives theoretical values:

| Hypothesis | BSRAM substitution arithmetic from partial 42 + separate RS 2 | Estimated average SDRAM MB/s | Status |
|---|---:|---:|---|
| Existing B tiled baseline | 44/46 | 271.266 | Whole-chip unqualified |
| All on-chip SDF | 52/46 | 82.129 | Fails optimistic BSRAM substitution |
| Hybrid SDF | 44/46 | 145.175 | Ordering and fit unknown |
| Hybrid plus external T-input hold | 29/46 **only if 15 mapped blocks truly vanish** | 202.802 | All resources and timing unknown |

These *substitution values are not actual RTL synthesis*: the original FFT 8 BSRAM was an allocation, old partial netlist includes other blocks/stimulus, and inferred RAM ports can add real blocks. A separate output reordering read+write can add at least **63.045695 MB/s**, pushing the last estimate to ~265.848 MB/s. Whether this pass can be fused into the downstream layout remains unproven. Streaming architecture can also consume additional DSP/multipliers compared with a folded tile FFT. Neither full RTL resources nor clock closure follow from these averages.

## Mandatory next tests

1. RF premise: verify genuinely gapless native S3 IQ at T16/S40 MSa/s and required analog-bandwidth/CN/BER on external frequency conversion, with no resolution-reducing workaround. Recorded ESP-SDR source and API models are not end-to-end silicon verification.
2. Implement actual variable-N FFT hybrid: precise stage schedule, twiddle rounding, port topology, FIFO/backpressure, output reorder, independent fixed-point/NumPy oracle. Keep all N bins and sample/LLR precision. Compare it with existing tile FFT **at the same clock and board constraints**, including LUT/BSRAM/DSP/P&R and valid STA.
3. Measure SDRAM pin-model refresh/row misses and worst-phase continuous S-FEC + T delay-stage + LLR spill + two TS traffic, not just averages; ensure bounded queues and true symbol ownership.
4. Run whole FPGA RF-sync/equalizer/demapper/TMCC/deinterleaver/FEC/dual TS closure and S3 joint RF/packing/DMA/API WCET. No candidate passes merely through a 16,384-row stage ownership enumeration.
5. For 9K, separately verify image-specific fit, physical PSRAM availability, NOR MSPI strap and 1.8 V RECONFIG_N hardware, stop/drain/reload/epoch/tune/lock; Background Programming does not mean uninterrupted demodulation across reconfiguration.

**Static conditions checked**: (a) stage delay sizes equal (N−1)*4 bytes, (b) internal+external hybrid delays equal full delay, (c) 2 KiB-block minima are arithmetic, (d) bus traffic formula uses explicit GI1/32 period, (e) all candidates remain unqualified. Unit tests exercise these invariants. **Not checked**: actual SDF RTL, UART/GPIO physical closure, synthesis, physical STA, production PHY, real end-to-end TS, native S3 RF continuous capture. Do not promote this report as receiver evidence.

Prior evidence: [PR6 selection audit](pr6-20k-dual-s3-selection-review.md), [T buffer](20k-dual-s3-t-buffer.md), [dual architecture estimate](20k-dual-s3.md), [FFT+SDRAM trials](20k-dual-s3-fft-sdram.md).
