// Receiver-only variant of the legacy dual endpoint measurement.
// The IQ return path is disabled and not made available on the top level.
// Although this removes unused logic during synthesis, it does NOT prove
// source-synchronous ingress timing, TS output, or end-to-end receive.
module dual_s3_spi_ingress_only_area_top(
    input wire clk, resetn,
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
    genvar i;
    generate for(i=0;i<2;i=i+1)begin : physical_ports
        wire ignored_fft_valid,ignored_fft_last;
        wire [31:0] ignored_fft_data,ignored_fft_offset;
        wire ignored_iq_begin_ready,ignored_iq_word_ready;
        wire [1:0] ignored_publish;
        s3_spi_runtime_endpoint #(
            .IMAGE_ID(i == 0 ? 8'd0 : 8'd1),
            .BUILD_TAG(32'h20c2026),
            .T_OCTAL_ONLY(i == 0)
        ) endpoint(
            .clk(clk),.resetn(resetn),
            .frontend_idle(frontend_idle[i]),
            .frontend_locked(frontend_locked[i]),
            .frontend_fault(frontend_fault[i]),
            .spi2_clk(spi2_clk[i]),.spi2_cs_n(spi2_cs_n[i]),
            .spi2_d(spi2_d[i*8+:8]),
            .spi3_clk(spi3_clk[i]),.spi3_cs_n(spi3_cs_n[i]),
            .spi3_d(spi3_d[i*4+:4]),
            .RF_valid(RF_valid[i]),.RF_ready(RF_ready[i]),
            .RF_data(RF_data[i*32+:32]),.RF_offset(RF_offset[i*32+:32]),
            .RF_last(RF_last[i]),
            .FFT_valid(ignored_fft_valid),.FFT_ready(1'b0),
            .FFT_data(ignored_fft_data),.FFT_offset(ignored_fft_offset),
            .FFT_last(ignored_fft_last),
            .IQ_begin(1'b0),.IQ_begin_ready(ignored_iq_begin_ready),
            .IQ_begin_offset(32'b0),.IQ_word_valid(1'b0),
            .IQ_word_ready(ignored_iq_word_ready),.IQ_word_data(32'b0),
            .stream_enable(stream_enable[i]),.fault(fault[i]),
            .epoch(epoch[i*16+:16]),
            .RF_credit_gray(RF_credit_gray[i*3+:3]),
            .IQ_publish_gray(ignored_publish)
        );
    end endgenerate
endmodule
