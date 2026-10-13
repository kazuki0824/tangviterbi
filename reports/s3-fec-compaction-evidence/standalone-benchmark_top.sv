module benchmark_top #(
    parameter integer WITH_MEM = 0,
    parameter integer WITH_VITERBI = 1,
    parameter integer WITH_RS = 1,
    parameter integer VITERBI_ACS = 16
) (
    input  wire clk,
    input  wire resetn,
    output wire activity
);
    reg [63:0] lfsr;

    wire vit_ready,mv; wire [35:0] mc; wire [3:0] mb;
    s3_tc8psk_metric_folded metric(clk,resetn,1'b1,,lfsr[15:0],lfsr[31:16],mv,vit_ready,mc,mb);
    wire vit_valid;
    wire [1:0] tc_bits;
    wire vit_bit=^tc_bits;

    wire rs_ready;
    wire rs_valid;
    wire [7:0] rs_out;
    wire rs_fail;

    reg mem_req;
    wire mem_ready;
    wire mem_busy;
    wire [1:0] mem_cs_n;
    wire [1:0] mem_ck_en;
    wire [1:0] mem_oe;
    wire [15:0] mem_wdata;
    wire [31:0] mem_rdata;

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            lfsr <= 64'hc14fb4391aceb00c;
            mem_req <= 1'b0;
        end else begin
            lfsr <= {lfsr[62:0], lfsr[63] ^ lfsr[62] ^ lfsr[60] ^ lfsr[59]};
            if (WITH_MEM) begin
                if (!mem_req && !mem_busy && (&lfsr[5:2]))
                    mem_req <= 1'b1;
                else if (mem_req)
                    mem_req <= 1'b0;
            end else begin
                mem_req <= 1'b0;
            end
        end
    end

    generate
        if (WITH_VITERBI) begin : g_viterbi
            if (VITERBI_ACS == 32) begin : g_32acs
                s3_tc8psk u_viterbi (
                    .clk(clk),
                    .resetn(resetn),
                    .in_valid(mv),
                    .in_ready(vit_ready),
                    .costs(mc),
                    .b1_choice(mb),
                    .out_valid(vit_valid),
                    .out_bits(tc_bits)
                );
            end else begin : g_16acs
                viterbi_k7_16acs u_viterbi (
                    .clk(clk),
                    .resetn(resetn),
                    .in_valid(vit_ready),
                    .in_ready(vit_ready),
                    .soft0(lfsr[7:0]),
                    .soft1(lfsr[15:8]),
                    .out_valid(vit_valid),
                    .out_bit(vit_bit)
                );
            end
        end else begin : g_no_viterbi
            assign vit_ready = 1'b0;
            assign vit_valid = 1'b0;
            assign vit_bit = 1'b0;
        end
    endgenerate

    generate if (WITH_RS) begin : g_rs
    rs204_188_compact u_rs (
        .clk(clk),
        .resetn(resetn),
        .in_valid(rs_ready),
        .in_ready(rs_ready),
        .in_byte(lfsr[23:16]),
        .out_valid(rs_valid),
        .out_byte(rs_out),
        .block_fail(rs_fail)
    );
    end else begin : g_no_rs
        assign rs_ready = 1'b0;
        assign rs_valid = 1'b0;
        assign rs_out = 8'd0;
        assign rs_fail = 1'b0;
    end endgenerate

    generate
        if (WITH_MEM) begin : g_mem
                psram_ctrl u_mem (
                    .clk(clk),
                    .resetn(resetn),
                    .req(mem_req),
                    .write(lfsr[6]),
                    .addr({lfsr[27:7], 1'b0}),
                    .wdata(lfsr),
                    .phy_rdata(lfsr[15:0]),
                    .phy_rwds(lfsr[31:30]),
                    .ready(mem_ready),
                    .busy(mem_busy),
                    .cs_n(mem_cs_n),
                    .ck_en(mem_ck_en),
                    .phy_oe(mem_oe),
                    .phy_wdata(mem_wdata),
                    .rdata(mem_rdata)
                );
        end else begin : g_no_mem
            assign mem_ready = 1'b0;
            assign mem_busy = 1'b0;
            assign mem_cs_n = 2'b11;
            assign mem_ck_en = 2'b00;
            assign mem_oe = 2'b00;
            assign mem_wdata = 16'd0;
            assign mem_rdata = 32'd0;
        end
    endgenerate

    assign activity = lfsr[0] ^ vit_bit ^ vit_valid ^
                      rs_out[0] ^ rs_valid ^ rs_fail ^
                      mem_ready ^ (^mem_cs_n) ^ (^mem_ck_en) ^ (^mem_oe) ^
                      (^mem_wdata) ^ (^mem_rdata);
endmodule
