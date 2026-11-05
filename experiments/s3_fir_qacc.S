/* Four complex outputs in eight independent signed40 QACC lanes.
 * void s3_fir_qacc_{16,32}(const int16_t samples[K][8],
 *                        const int16_t coeff[K][8], uint8_t out[64]);
 * All pointers 16-byte aligned, disjoint. samples[t] is I0,Q0,...,I3,Q3;
 * coeff[t] is c0,c0,...,c3,c3. signed10 samples, signed16 coefficients.
 * Save EXACT QACC, with no shift/rounding/requantization:
 * out[0:20] = four little-endian signed40 lanes (I0,Q0,I1,Q1);
 * out[32:52] = lanes I2,Q2,I3,Q3. Other output bytes untouched.
 * Clobbers q0,q1,q2,QACC_H,QACC_L. Own PIE context before calling.
 * Caller must prepare tap-major vectors; that work is not in this kernel.
 */
.text
.macro FIR_QACC name, pairs
.align 4
.global \name
.type \name,@function
\name:
    entry a1, 32
    ee.zero.qacc
    ee.vld.128.ip q0, a2, 16
    ee.vld.128.ip q1, a3, 16
.rept \pairs
    ee.vmulas.s16.qacc.ld.ip q2, a2, 16, q0, q1
    ee.vld.128.ip q1, a3, 16
    ee.vmulas.s16.qacc.ld.ip q0, a2, 16, q2, q1
    ee.vld.128.ip q1, a3, 16
.endr
    ee.vmulas.s16.qacc.ld.ip q2, a2, 16, q0, q1
    ee.vld.128.ip q1, a3, 16
    ee.vmulas.s16.qacc q2, q1
    ee.st.qacc_l.l.128.ip a4, 16
    ee.st.qacc_l.h.32.ip a4, 16
    ee.st.qacc_h.l.128.ip a4, 16
    ee.st.qacc_h.h.32.ip a4, 16
    retw.n
.size \name, .-\name
.endm
FIR_QACC s3_fir_qacc_16, 7
FIR_QACC s3_fir_qacc_32, 15
