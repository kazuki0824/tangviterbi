// Dual hardware SPI ingress endpoint area probe for scenario 2.
// Two fully independent physical ports; 1U-N16R8 SoC T and SoC S.
// This is not an ISDB receiver. No RF analog, FIR/sync, demapper, RS/TS.
// Expose all meaningful endpoint data/control to prohibit trivial pruning.
module dual_s3_spi_endpoints_area_top(
    input wire clk, resetn,
    input wire [1:0] frontend_idle, frontend_locked, frontend_fault,
    input wire [1:0] spi2_clk, spi2_cs_n, spi3_clk, spi3_cs_n,
    input wire [15:0] spi2_d,
    inout wire [7:0] spi3_d,
    output wire [1:0] RF_valid, FFT_valid, RF_last, FFT_last,
    input wire [1:0] RF_ready, FFT_ready,
    output wire [63:0] RF_data, RF_offset, FFT_data, FFT_offset,
    input wire [1:0] IQ_begin, IQ_word_valid,
    output wire [1:0] IQ_begin_ready, IQ_word_ready,
    input wire [63:0] IQ_begin_offset, IQ_word_data,
    output wire [1:0] stream_enable, fault,
    output wire [31:0] epoch,
    output wire [5:0] RF_credit_gray,
    output wire [3:0] IQ_publish_gray
);
    genvar i;
    generate for (i=0; i<2; i=i+1) begin: two_receiver_ports
        s3_spi_runtime_endpoint #(
            .IMAGE_ID(i == 0 ? 8'd0 : 8'd1),
            .BUILD_TAG(32'h20c2026),
            .T_OCTAL_ONLY(i == 0)
        ) endpoint (
            .clk(clk), .resetn(resetn),
            .frontend_idle(frontend_idle[i]),
            .frontend_locked(frontend_locked[i]),
            .frontend_fault(frontend_fault[i]),
            .spi2_clk(spi2_clk[i]),
            .spi2_cs_n(spi2_cs_n[i]),
            .spi2_d(spi2_d[8*i+:8]),
            .spi3_clk(spi3_clk[i]),
            .spi3_cs_n(spi3_cs_n[i]),
            .spi3_d(spi3_d[4*i+:4]),
            .RF_valid(RF_valid[i]), .RF_ready(RF_ready[i]),
            .RF_data(RF_data[32*i+:32]),
            .RF_offset(RF_offset[32*i+:32]),
            .RF_last(RF_last[i]),
            .FFT_valid(FFT_valid[i]), .FFT_ready(FFT_ready[i]),
            .FFT_data(FFT_data[32*i+:32]),
            .FFT_offset(FFT_offset[32*i+:32]),
            .FFT_last(FFT_last[i]),
            .IQ_begin(IQ_begin[i]),
            .IQ_begin_ready(IQ_begin_ready[i]),
            .IQ_begin_offset(IQ_begin_offset[32*i+:32]),
            .IQ_word_valid(IQ_word_valid[i]),
            .IQ_word_ready(IQ_word_ready[i]),
            .IQ_word_data(IQ_word_data[32*i+:32]),
            .stream_enable(stream_enable[i]),
            .fault(fault[i]),
            .epoch(epoch[16*i+:16]),
            .RF_credit_gray(RF_credit_gray[3*i+:3]),
            .IQ_publish_gray(IQ_publish_gray[2*i+:2])
        );
    end endgenerate
endmodule
