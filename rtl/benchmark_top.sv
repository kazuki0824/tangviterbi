module benchmark_top #(
    parameter integer WITH_MEM = 0,
    parameter integer MEM_DQ = 8
) (
    input  wire clk,
    input  wire resetn,
    output wire activity
);
    reg [31:0] lfsr;
    reg [2:0]  rs_div;
    reg [1:0]  vit_div;

    wire vit_ready;
    wire vit_valid;
    wire vit_bit;

    wire [7:0] rs_out;
    wire rs_ceo;
    wire rs_valid;

    reg mem_req;
    wire mem_ready;
    wire mem_cs_n;
    wire mem_ck_en;
    wire mem_oe;
    wire [MEM_DQ-1:0] mem_wdata;
    wire [31:0] mem_rdata;

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            lfsr <= 32'h1ace_b00c;
            rs_div <= 3'd0;
            vit_div <= 2'd0;
            mem_req <= 1'b0;
        end else begin
            lfsr <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
            rs_div <= rs_div + 3'd1;
            vit_div <= vit_div + 2'd1;
            if (WITH_MEM) begin
                if (!mem_req && !mem_ready && (&lfsr[5:2]))
                    mem_req <= 1'b1;
                else if (mem_req)
                    mem_req <= 1'b0;
            end else begin
                mem_req <= 1'b0;
            end
        end
    end

    viterbi_k7_16acs u_viterbi (
        .clk(clk),
        .resetn(resetn),
        .in_valid(vit_ready && (vit_div == 2'd0)),
        .in_ready(vit_ready),
        .soft0(lfsr[7:0]),
        .soft1(lfsr[15:8]),
        .out_valid(vit_valid),
        .out_bit(vit_bit)
    );

    // GPLv3 third-party benchmark dependency, fetched only in CI.
    RS_dec u_rs (
        .clk(clk),
        .reset(~resetn),
        .CE(rs_div == 3'd0),
        .input_byte(lfsr[23:16]),
        .Out_byte(rs_out),
        .CEO(rs_ceo),
        .Valid_out(rs_valid)
    );

    generate
        if (WITH_MEM) begin : g_mem
            hyperram_ctrl #(.DQ_W(MEM_DQ)) u_mem (
                .clk(clk),
                .resetn(resetn),
                .req(mem_req),
                .write(lfsr[6]),
                .addr(lfsr[27:6]),
                .wdata(lfsr),
                .phy_rdata(lfsr[MEM_DQ-1:0]),
                .ready(mem_ready),
                .cs_n(mem_cs_n),
                .ck_en(mem_ck_en),
                .phy_oe(mem_oe),
                .phy_wdata(mem_wdata),
                .rdata(mem_rdata)
            );
        end else begin : g_no_mem
            assign mem_ready = 1'b0;
            assign mem_cs_n = 1'b1;
            assign mem_ck_en = 1'b0;
            assign mem_oe = 1'b0;
            assign mem_wdata = {MEM_DQ{1'b0}};
            assign mem_rdata = 32'd0;
        end
    endgenerate

    // Fold every benchmark block into a real output so synthesis cannot prune it.
    assign activity = lfsr[0] ^ vit_bit ^ vit_valid ^ rs_out[0] ^ rs_ceo ^
                      rs_valid ^ mem_ready ^ mem_cs_n ^ mem_ck_en ^ mem_oe ^
                      mem_wdata[0] ^ mem_rdata[0];
endmodule
