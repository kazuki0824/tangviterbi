// Area-only co-residency probe. The two SPI ingress engines and the
// existing joint FFT + SDRAM + TC8/K7 subsystem are synthesized in ONE netlist.
// They are deliberately NOT connected through a fake/dummy demodulator.
// Lack of T/S FIR, synchronization, equalizer, interleavers, RS, TMCC, TS,
// board IO/PHY, and bounded ingress CDC must never be claimed as complete.
module dual_s3_ingress_joint_fft_area_top(
    input wire clk, resetn, scan_enable, scan_in,
    output wire signature,
    input wire [1:0] frontend_idle, frontend_locked, frontend_fault,
    input wire [1:0] spi2_clk, spi2_cs_n, spi3_clk, spi3_cs_n,
    input wire [15:0] spi2_d,
    inout wire [7:0] spi3_d,
    output wire [1:0] RF_valid, RF_last,
    input wire [1:0] RF_ready,
    output wire [63:0] RF_data, RF_offset,
    output wire [1:0] stream_enable, fault,
    output wire [31:0] epoch,
    output wire [5:0] RF_credit_gray
);
    dual_s3_spi_ingress_only_area_top rx(
        .clk(clk), .resetn(resetn),
        .frontend_idle(frontend_idle),
        .frontend_locked(frontend_locked),
        .frontend_fault(frontend_fault),
        .spi2_clk(spi2_clk), .spi2_cs_n(spi2_cs_n),
        .spi3_clk(spi3_clk), .spi3_cs_n(spi3_cs_n),
        .spi2_d(spi2_d), .spi3_d(spi3_d),
        .RF_valid(RF_valid), .RF_last(RF_last), .RF_ready(RF_ready),
        .RF_data(RF_data), .RF_offset(RF_offset),
        .stream_enable(stream_enable), .fault(fault),
        .epoch(epoch), .RF_credit_gray(RF_credit_gray)
    );
    shared_receiver_fft_metadata_probe fft_k7_memory(
        .clk(clk), .resetn(resetn),
        .scan_enable(scan_enable), .scan_in(scan_in),
        .signature(signature)
    );
endmodule
