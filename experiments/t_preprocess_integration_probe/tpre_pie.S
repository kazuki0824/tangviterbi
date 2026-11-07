/* RF-off task-local warmup: FreeRTOS's lazy CP3 exception owns the context.
 * No manual CPENABLE manipulation; ordinary ISR entry does not disable CP3. */
    .section .iram1,"ax",@progbits
    .align 4
    .global tpre_pie_warmup
    .type tpre_pie_warmup,@function
tpre_pie_warmup:
    entry a1, 16
    ee.zero.qacc
    retw.n
    .size tpre_pie_warmup, .-tpre_pie_warmup
