/* Exact signed10 x signed16 dot products; ESP32-S3 PIE, windowed ABI.
 * void s3_fir_accx_{16,32}(const int16_t *i, const int16_t *q,
 *                         const int16_t *coeff, int32_t out[2]);
 * a2/a3: contiguous newest-to-oldest planar history, 2-byte aligned.
 * a4: 16-byte aligned coefficients, same order; a5: 4-byte aligned output.
 * History loads cover floor(ptr/16)*16 through that address + (K/8+1)*16.
 * Caller must make that whole region readable (mirrored ring is one option).
 * Samples must remain signed10 values. No output rescaling/quantization.
 * Clobbers PIE q0..q7, ACCX, SAR_BYTE; caller/runtime must own their context.
 * Comparison kernel only: no DMA, phase update, unpack or RTOS integration.
 */
.text
.align 4
.global s3_fir_accx_16
.type s3_fir_accx_16,@function
s3_fir_accx_16:
    entry a1, 32
    movi a6, 0
    ee.vld.128.ip q4, a4, 16
    ee.vld.128.ip q5, a4, 16
    ee.zero.accx
    ee.ld.128.usar.ip q0, a2, 16
    ee.vld.128.ip q1, a2, 16
    ee.src.q.ld.ip q2, a2, 16, q0, q1
    ee.vmulas.s16.accx q0, q4
    ee.src.q q0, q1, q2
    ee.vmulas.s16.accx q0, q5
    ee.srs.accx a7, a6, 0
    s32i a7, a5, 0
    ee.zero.accx
    ee.ld.128.usar.ip q0, a3, 16
    ee.vld.128.ip q1, a3, 16
    ee.src.q.ld.ip q2, a3, 16, q0, q1
    ee.vmulas.s16.accx q0, q4
    ee.src.q q0, q1, q2
    ee.vmulas.s16.accx q0, q5
    ee.srs.accx a7, a6, 0
    s32i a7, a5, 4
    retw.n
.size s3_fir_accx_16, .-s3_fir_accx_16
.align 4
.global s3_fir_accx_32
.type s3_fir_accx_32,@function
s3_fir_accx_32:
    entry a1, 32
    movi a6, 0
    ee.vld.128.ip q4, a4, 16
    ee.vld.128.ip q5, a4, 16
    ee.vld.128.ip q6, a4, 16
    ee.vld.128.ip q7, a4, 16
    ee.zero.accx
    ee.ld.128.usar.ip q0, a2, 16
    ee.vld.128.ip q1, a2, 16
    ee.src.q.ld.ip q2, a2, 16, q0, q1
    ee.vmulas.s16.accx.ld.ip.qup q3, a2, 16, q0, q4, q1, q2
    ee.vmulas.s16.accx.ld.ip.qup q0, a2, 16, q1, q5, q2, q3
    ee.vmulas.s16.accx q2, q6
    ee.src.q q3, q3, q0
    ee.vmulas.s16.accx q3, q7
    ee.srs.accx a7, a6, 0
    s32i a7, a5, 0
    ee.zero.accx
    ee.ld.128.usar.ip q0, a3, 16
    ee.vld.128.ip q1, a3, 16
    ee.src.q.ld.ip q2, a3, 16, q0, q1
    ee.vmulas.s16.accx.ld.ip.qup q3, a3, 16, q0, q4, q1, q2
    ee.vmulas.s16.accx.ld.ip.qup q0, a3, 16, q1, q5, q2, q3
    ee.vmulas.s16.accx q2, q6
    ee.src.q q3, q3, q0
    ee.vmulas.s16.accx q3, q7
    ee.srs.accx a7, a6, 0
    s32i a7, a5, 4
    retw.n
.size s3_fir_accx_32, .-s3_fir_accx_32
