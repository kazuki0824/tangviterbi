.text
.align 4
.global s3_fir_reg_32_0135
.type s3_fir_reg_32_0135,@function
s3_fir_reg_32_0135:
entry a1, 32
ee.zero.qacc
ee.vld.128.ip q7, a3, 16
ee.vld.128.ip q0, a2, 16
ee.vld.128.ip q1, a2, 16
ee.vld.128.ip q2, a2, 16
ee.vld.128.ip q3, a2, 16
ee.vld.128.ip q4, a2, 16
ee.vld.128.ip q5, a2, 16
ee.movi.32.a q0, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q5, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
addi a2, a2, -32
ee.vld.128.ip q0, a2, 16
ee.vld.128.ip q1, a2, 16
ee.vld.128.ip q2, a2, 16
ee.vld.128.ip q3, a2, 16
ee.vld.128.ip q4, a2, 16
ee.vld.128.ip q5, a2, 16
ee.movi.32.a q0, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q5, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc q6, q7
ee.st.qacc_l.l.128.ip a4, 16
ee.st.qacc_l.h.32.ip a4, 16
ee.st.qacc_h.l.128.ip a4, 16
ee.st.qacc_h.h.32.ip a4, 16
retw.n
.size s3_fir_reg_32_0135, .-s3_fir_reg_32_0135
.text
.align 4
.global s3_fir_reg_32_0246
.type s3_fir_reg_32_0246,@function
s3_fir_reg_32_0246:
entry a1, 32
ee.zero.qacc
ee.vld.128.ip q7, a3, 16
ee.vld.128.ip q0, a2, 16
ee.vld.128.ip q1, a2, 16
ee.vld.128.ip q2, a2, 16
ee.vld.128.ip q3, a2, 16
ee.vld.128.ip q4, a2, 16
ee.vld.128.ip q5, a2, 16
ee.movi.32.a q0, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q5, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q5, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
addi a2, a2, -32
ee.vld.128.ip q0, a2, 16
ee.vld.128.ip q1, a2, 16
ee.vld.128.ip q2, a2, 16
ee.vld.128.ip q3, a2, 16
ee.vld.128.ip q4, a2, 16
ee.vld.128.ip q5, a2, 16
ee.movi.32.a q0, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q5, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q5, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc q6, q7
ee.st.qacc_l.l.128.ip a4, 16
ee.st.qacc_l.h.32.ip a4, 16
ee.st.qacc_h.l.128.ip a4, 16
ee.st.qacc_h.h.32.ip a4, 16
retw.n
.size s3_fir_reg_32_0246, .-s3_fir_reg_32_0246
.text
.align 4
.global s3_fir_reg_16_0124
.type s3_fir_reg_16_0124,@function
s3_fir_reg_16_0124:
entry a1, 32
ee.zero.qacc
ee.vld.128.ip q7, a3, 16
ee.vld.128.ip q0, a2, 16
ee.vld.128.ip q1, a2, 16
ee.vld.128.ip q2, a2, 16
ee.vld.128.ip q3, a2, 16
ee.vld.128.ip q4, a2, 16
ee.movi.32.a q0, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q0, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc q6, q7
ee.st.qacc_l.l.128.ip a4, 16
ee.st.qacc_l.h.32.ip a4, 16
ee.st.qacc_h.l.128.ip a4, 16
ee.st.qacc_h.h.32.ip a4, 16
retw.n
.size s3_fir_reg_16_0124, .-s3_fir_reg_16_0124
.text
.align 4
.global s3_fir_reg_16_0134
.type s3_fir_reg_16_0134,@function
s3_fir_reg_16_0134:
entry a1, 32
ee.zero.qacc
ee.vld.128.ip q7, a3, 16
ee.vld.128.ip q0, a2, 16
ee.vld.128.ip q1, a2, 16
ee.vld.128.ip q2, a2, 16
ee.vld.128.ip q3, a2, 16
ee.vld.128.ip q4, a2, 16
ee.movi.32.a q0, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc q6, q7
ee.st.qacc_l.l.128.ip a4, 16
ee.st.qacc_l.h.32.ip a4, 16
ee.st.qacc_h.l.128.ip a4, 16
ee.st.qacc_h.h.32.ip a4, 16
retw.n
.size s3_fir_reg_16_0134, .-s3_fir_reg_16_0134
.text
.align 4
.global s3_fir_reg_16_0234
.type s3_fir_reg_16_0234,@function
s3_fir_reg_16_0234:
entry a1, 32
ee.zero.qacc
ee.vld.128.ip q7, a3, 16
ee.vld.128.ip q0, a2, 16
ee.vld.128.ip q1, a2, 16
ee.vld.128.ip q2, a2, 16
ee.vld.128.ip q3, a2, 16
ee.vld.128.ip q4, a2, 16
ee.movi.32.a q0, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc q6, q7
ee.st.qacc_l.l.128.ip a4, 16
ee.st.qacc_l.h.32.ip a4, 16
ee.st.qacc_h.l.128.ip a4, 16
ee.st.qacc_h.h.32.ip a4, 16
retw.n
.size s3_fir_reg_16_0234, .-s3_fir_reg_16_0234
.text
.align 4
.global s3_fir_reg_16_0235
.type s3_fir_reg_16_0235,@function
s3_fir_reg_16_0235:
entry a1, 32
ee.zero.qacc
ee.vld.128.ip q7, a3, 16
ee.vld.128.ip q0, a2, 16
ee.vld.128.ip q1, a2, 16
ee.vld.128.ip q2, a2, 16
ee.vld.128.ip q3, a2, 16
ee.vld.128.ip q4, a2, 16
ee.vld.128.ip q5, a2, 16
ee.movi.32.a q0, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q0, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q1, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q2, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 0
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 1
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 1
ee.movi.32.q q6, a5, 0
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 2
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 2
ee.movi.32.q q6, a5, 0
ee.movi.32.a q4, a5, 0
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 2
ee.movi.32.a q4, a5, 3
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7
ee.movi.32.a q3, a5, 3
ee.movi.32.q q6, a5, 0
ee.movi.32.a q4, a5, 1
ee.movi.32.q q6, a5, 1
ee.movi.32.a q4, a5, 2
ee.movi.32.q q6, a5, 2
ee.movi.32.a q5, a5, 0
ee.movi.32.q q6, a5, 3
ee.vmulas.s16.qacc q6, q7
ee.st.qacc_l.l.128.ip a4, 16
ee.st.qacc_l.h.32.ip a4, 16
ee.st.qacc_h.l.128.ip a4, 16
ee.st.qacc_h.h.32.ip a4, 16
retw.n
.size s3_fir_reg_16_0235, .-s3_fir_reg_16_0235
