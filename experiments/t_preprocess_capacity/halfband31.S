/* Four consecutive decimated complex outputs, without tap-major copies.
 * Input even[19] complex signed10, odd[4] complex signed10. All a2..a5
 * pointers 16-byte aligned. even has one additional readable complex padding.
 * Coefficient vector order: h[30],h[28],...,h[0],h[15]. h odd (except 15)=0.
 * output[8] is sat16(acc >> a6), no rounding. Caller validates a6 in 0..31.
 * Own q0..q3,QACC,SAR_BYTE for the call. This is a candidate, not RF validation.
 * TRM v1.8 Table 1.7-2: vector loads define QR at stage 2, MAC/SRC read at
 * stage 1. Keep one independent instruction between each load and its consumer.
 * MAC defines QACC at stage 2; SRCMB reads it at stage 1 (one intervening NOP).
 * SRCMB defines QR at stage 1, so the following stage-1 vector store may follow.
 */
.text
.align 4
.global hb31_qacc4
.type hb31_qacc4,@function
hb31_qacc4:
    entry a1, 32
    ee.zero.qacc
.rept 4
    ee.vld.128.ip q2, a2, 0
    ee.vld.128.ip q3, a4, 16
    addi a2, a2, 4
    ee.vmulas.s16.qacc q2, q3
.rept 3
    ee.ld.128.usar.ip q0, a2, 16
    ee.vld.128.ip q1, a2, -16
    ee.vld.128.ip q3, a4, 16
    ee.src.q q2, q0, q1
    addi a2, a2, 4
    ee.vmulas.s16.qacc q2, q3
.endr
.endr
    ee.vld.128.ip q2, a3, 0
    ee.vld.128.ip q3, a4, 0
    nop
    ee.vmulas.s16.qacc q2, q3
    nop
    ee.srcmb.s16.qacc q2, a6, 0
    ee.vst.128.ip q2, a5, 0
    retw.n
.size hb31_qacc4, .-hb31_qacc4

/* Avoid an unpriced libc dependency in the candidate's history update. */
.align 4
.global hb31_copy_words
.type hb31_copy_words,@function
hb31_copy_words:
    entry a1, 32
    loop a4, .Lcopy_end
.Lcopy_start:
    l32i.n a5, a3, 0
    s32i.n a5, a2, 0
    addi.n a3, a3, 4
    addi.n a2, a2, 4
.Lcopy_end:
    retw.n
.size hb31_copy_words, .-hb31_copy_words
