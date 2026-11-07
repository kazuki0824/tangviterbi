| ID | SoC prefix＋RF | CPU低/高 % | logic/FF/BSRAM/DSP（混合予算） | ↑ MB/s |
|---|---|---:|---|---:|
| S3-T-000:hybrid | RF only | 31.953/38.620 | 9478/6332/16/18 | 40.000000 |
| S3-T-000:resident | RF only | 31.953/38.620 | 9466/6301/24/18 | 40.000000 |
| S3-T-001:hybrid | FIR | 89.678/123.435 | 8726/4796/14/10 | 32.507937 |
| S3-T-001:resident | FIR | 89.678/123.435 | 8714/4765/22/10 | 32.507937 |
| S3-T-003:hybrid | FIR, sync | 103.018/150.114 | 8470/4540/13/9 | 31.522848 |
| S3-T-003:resident | FIR, sync | 103.018/150.114 | 8458/4509/21/9 | 31.522848 |
| S3-T-007:unchanged | FIR, sync, FFT | 135.581/182.678 | 5741/3038/3/5 | 31.522848 |
| S3-T-00f:unchanged | FIR, sync, FFT, equalize_demap | 143.021/197.557 | 5357/2654/3/0 | 28.813853 |
| S3-T-01f:unchanged | FIR, sync, FFT, equalize_demap, time_deinterleave | 159.028/229.572 | 5101/2526/3/0 | 28.813853 |
| S3-T-03f:unchanged | FIR, sync, FFT, equalize_demap, time_deinterleave, Viterbi | 1162.167/2235.849 | 2149/1024/1/0 | 3.151515 |
| S3-T-07f:unchanged | FIR, sync, FFT, equalize_demap, time_deinterleave, Viterbi, RS | 1233.115/2306.745 | 64/64/0/0 | 2.904337 |
| S3-T-0ff:unchanged | FIR, sync, FFT, equalize_demap, time_deinterleave, Viterbi, RS, TS | 1232.510/2305.535 | 0/0/0/0 | 0.000000 |
| S3-S-000:unchanged | RF only | 76.758/93.424 | 6421/4190/14/15 | 100.000000 |
| S3-S-001:unchanged | FIR | 232.133/332.974 | 5869/3166/8/3 | 115.440000 |
| S3-S-003:unchanged | FIR, sync | 280.233/429.174 | 5613/2910/7/1 | 115.440000 |
| S3-S-007:unchanged | FIR, sync, TC8PSK | 1384.336/2637.381 | 2405/1152/3/0 | 7.215000 |
| S3-S-00f:unchanged | FIR, sync, TC8PSK, frame_deinterleave | 1405.491/2667.606 | 2149/1024/1/0 | 7.250542 |
| S3-S-01f:unchanged | FIR, sync, TC8PSK, frame_deinterleave, RS | 1568.683/2830.647 | 64/64/0/0 | 6.521250 |
| S3-S-03f:unchanged | FIR, sync, TC8PSK, frame_deinterleave, RS, TS | 1567.325/2827.930 | 0/0/0/0 | 0.000000 |
