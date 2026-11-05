// Scenario 2: preserve 10-bit I and Q for both simultaneous RF streams.
// The SPI page endpoint -> IQ unpacker connection is real ready/valid wiring.
// FFT/K7 remains a separately driven partial module: no synchronization,
// FIR, equalizer, RS or TS connection is asserted by this resource probe.
module dual_s3_iq_ingress_joint_fft_area_top(
    input wire clk, resetn, scan_enable, scan_in,
    output wire signature,
    input wire [1:0] frontend_idle, frontend_locked, frontend_fault,
    input wire [1:0] spi2_clk, spi2_cs_n, spi3_clk, spi3_cs_n,
    input wire [15:0] spi2_d,
    inout wire [7:0] spi3_d,
    input wire [1:0] iq_ready,
    output wire [1:0] iq_valid,
    output wire [19:0] iq_i, iq_q,
    output wire [1:0] stream_enable, fault, RF_last,
    output wire [63:0] RF_offset,
    output wire [31:0] epoch,
    output wire [5:0] RF_credit_gray
);
    wire [1:0] rf_valid, rf_ready;
    wire [63:0] rf_data;

    dual_s3_spi_ingress_only_area_top ingress (
        .clk(clk), .resetn(resetn),
        .frontend_idle(frontend_idle), .frontend_locked(frontend_locked),
        .frontend_fault(frontend_fault),
        .spi2_clk(spi2_clk), .spi2_cs_n(spi2_cs_n),
        .spi3_clk(spi3_clk), .spi3_cs_n(spi3_cs_n),
        .spi2_d(spi2_d), .spi3_d(spi3_d),
        .RF_valid(rf_valid), .RF_ready(rf_ready),
        .RF_data(rf_data), .RF_offset(RF_offset),
        .RF_last(RF_last), .stream_enable(stream_enable),
        .fault(fault), .epoch(epoch), .RF_credit_gray(RF_credit_gray)
    );
    genvar lane;
    generate for(lane=0;lane<2;lane=lane+1) begin: g_iq
        wire active_epoch = resetn && stream_enable[lane] && !fault[lane];
        s3_iq10_unpack unpacker(
            .clk(clk), .resetn(active_epoch),
            .in_valid(rf_valid[lane]), .in_ready(rf_ready[lane]),
            .in_data(rf_data[lane*32+:32]),
            .out_valid(iq_valid[lane]), .out_ready(iq_ready[lane]),
            .out_i(iq_i[lane*10+:10]), .out_q(iq_q[lane*10+:10])
        );
    end endgenerate

    shared_receiver_fft_metadata_probe fft_k7_memory (
        .clk(clk), .resetn(resetn),
        .scan_enable(scan_enable), .scan_in(scan_in),
        .signature(signature)
    );
endmodule
