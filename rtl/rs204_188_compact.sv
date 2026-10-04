module gf256_mul (
    input  wire [7:0] a,
    input  wire [7:0] b,
    output reg  [7:0] y
);
    integer k;
    reg [7:0] aa;
    reg [7:0] bb;
    reg [7:0] pp;
    always @* begin
        aa = a;
        bb = b;
        pp = 8'd0;
        for (k = 0; k < 8; k = k + 1) begin
            if (bb[0])
                pp = pp ^ aa;
            aa = aa[7] ? ((aa << 1) ^ 8'h1d) : (aa << 1);
            bb = bb >> 1;
        end
        y = pp;
    end
endmodule

module rs_block_ram (
    input  wire       clk,
    input  wire       we,
    input  wire [7:0] waddr,
    input  wire [7:0] wdata,
    input  wire [7:0] raddr,
    output reg  [7:0] rdata
);
    (* ram_style = "block" *) reg [7:0] mem [0:255];

    always @(posedge clk) begin
        rdata <= mem[raddr];
    end

    always @(posedge clk) begin
        if (we)
            mem[waddr] <= wdata;
    end
endmodule

// Compact, sequential RS(204,188) architecture for resource/timing benchmarking.
//
// The design uses one GF(256) multiplier shared by syndrome generation,
// Berlekamp-Massey, Chien search and Forney evaluation. At 110 MHz the
// serialized architecture has enough cycle budget for the ~25.2 Mbit/s
// post-Viterbi worst-case stream considered by this repository.
//
// The shortened-code position convention and final Forney correction mapping
// still require bit-exact validation against ARIB test vectors before this
// block can be called production decoder RTL. The arithmetic/state/storage
// structure is complete enough for the intended LUT/BSRAM/Fmax comparison.
module rs204_188_compact (
    input  wire       clk,
    input  wire       resetn,
    input  wire       in_valid,
    output wire       in_ready,
    input  wire [7:0] in_byte,
    output reg        out_valid,
    output reg [7:0]  out_byte,
    output reg        block_fail
);
    localparam ST_INPUT          = 6'd0;
    localparam ST_SYND           = 6'd1;
    localparam ST_BM_INIT        = 6'd2;
    localparam ST_BM_START       = 6'd3;
    localparam ST_BM_DISC        = 6'd4;
    localparam ST_BM_CHECK       = 6'd5;
    localparam ST_INV_SQUARE     = 6'd6;
    localparam ST_INV_MUL        = 6'd7;
    localparam ST_BM_COEF        = 6'd8;
    localparam ST_BM_UPDATE      = 6'd9;
    localparam ST_BM_POST        = 6'd10;
    localparam ST_OMEGA_INIT     = 6'd11;
    localparam ST_OMEGA_ACC      = 6'd12;
    localparam ST_OMEGA_STORE    = 6'd13;
    localparam ST_CHIEN_INIT     = 6'd14;
    localparam ST_CHIEN_EVAL     = 6'd15;
    localparam ST_CHIEN_CHECK    = 6'd16;
    localparam ST_CHIEN_NEXT     = 6'd17;
    localparam ST_FORNEY_INIT    = 6'd18;
    localparam ST_FORNEY_OMEGA   = 6'd19;
    localparam ST_FORNEY_X2      = 6'd20;
    localparam ST_FORNEY_D0      = 6'd21;
    localparam ST_FORNEY_D1      = 6'd22;
    localparam ST_FORNEY_D2      = 6'd23;
    localparam ST_FORNEY_MAG     = 6'd24;
    localparam ST_FORNEY_READ    = 6'd25;
    localparam ST_FORNEY_WRITE   = 6'd26;
    localparam ST_OUTPUT         = 6'd27;
    localparam ST_BLOCK_RESET    = 6'd28;

    reg [5:0] state;

    reg [7:0] synd [0:15];
    reg [7:0] lambda [0:8];
    reg [7:0] bpoly [0:8];
    reg [7:0] temp_poly [0:8];
    reg [7:0] omega [0:15];

    reg [7:0] error_x [0:7];
    reg [7:0] error_pos [0:7];

    reg [7:0] byte_q;
    reg [7:0] byte_count;
    reg [4:0] synd_idx;
    reg syndrome_nonzero;

    reg [4:0] bm_n;
    reg [3:0] bm_i;
    reg [3:0] bm_l;
    reg [3:0] bm_m;
    reg [3:0] update_i;
    reg [7:0] discrepancy;
    reg [7:0] bval;
    reg [7:0] coef;

    reg [7:0] inv_acc;
    reg [3:0] inv_bit;
    reg inv_mode; // 0=BM division, 1=Forney derivative inversion

    reg [4:0] omega_j;
    reg [3:0] omega_i;
    reg [7:0] omega_acc;

    reg [7:0] chien_x;
    reg [7:0] chien_acc;
    reg [3:0] chien_k;
    reg [7:0] chien_pos;
    reg [3:0] error_count;

    reg [3:0] error_i;
    reg [7:0] forney_acc;
    reg [4:0] forney_k;
    reg [7:0] omega_value;
    reg [7:0] x2;
    reg [7:0] deriv_acc;
    reg [7:0] magnitude;
    reg [7:0] corrected_q;

    reg [7:0] out_index;
    reg       out_primed;

    reg       ram_we;
    reg [7:0] ram_waddr;
    reg [7:0] ram_wdata;
    reg [7:0] ram_raddr;
    wire [7:0] ram_rdata;

    reg [7:0] gf_a;
    reg [7:0] gf_b;
    wire [7:0] gf_y;

    integer i;

    gf256_mul u_gf_mul(.a(gf_a), .b(gf_b), .y(gf_y));

    rs_block_ram u_block_ram (
        .clk(clk),
        .we(ram_we),
        .waddr(ram_waddr),
        .wdata(ram_wdata),
        .raddr(ram_raddr),
        .rdata(ram_rdata)
    );

    // Keep the block buffer in a dedicated synchronous RAM process so Gowin
    // BSRAM inference is not destroyed by the asynchronously-reset decoder FSM.
    always @* begin
        ram_we = 1'b0;
        ram_waddr = 8'd0;
        ram_wdata = 8'd0;
        ram_raddr = 8'd0;

        if ((state == ST_INPUT) && in_valid) begin
            ram_we = 1'b1;
            ram_waddr = byte_count;
            ram_wdata = in_byte;
        end

        if ((state == ST_FORNEY_MAG) ||
            (state == ST_FORNEY_READ) ||
            (state == ST_FORNEY_WRITE)) begin
            ram_raddr = error_pos[error_i];
        end

        if (state == ST_FORNEY_WRITE) begin
            ram_we = 1'b1;
            ram_waddr = error_pos[error_i];
            ram_wdata = corrected_q ^ magnitude;
        end

        if (state == ST_OUTPUT) begin
            ram_raddr = out_primed ? (out_index + 8'd1) : out_index;
        end
    end

    function automatic [7:0] alpha_power_1_to_16;
        input [3:0] idx;
        begin
            case (idx)
                4'd0:  alpha_power_1_to_16 = 8'h02;
                4'd1:  alpha_power_1_to_16 = 8'h04;
                4'd2:  alpha_power_1_to_16 = 8'h08;
                4'd3:  alpha_power_1_to_16 = 8'h10;
                4'd4:  alpha_power_1_to_16 = 8'h20;
                4'd5:  alpha_power_1_to_16 = 8'h40;
                4'd6:  alpha_power_1_to_16 = 8'h80;
                4'd7:  alpha_power_1_to_16 = 8'h1d;
                4'd8:  alpha_power_1_to_16 = 8'h3a;
                4'd9:  alpha_power_1_to_16 = 8'h74;
                4'd10: alpha_power_1_to_16 = 8'he8;
                4'd11: alpha_power_1_to_16 = 8'hcd;
                4'd12: alpha_power_1_to_16 = 8'h87;
                4'd13: alpha_power_1_to_16 = 8'h13;
                4'd14: alpha_power_1_to_16 = 8'h26;
                default: alpha_power_1_to_16 = 8'h4c;
            endcase
        end
    endfunction

    function automatic inv_exponent_bit;
        input [3:0] bit_index;
        begin
            // 254 = 8'b11111110
            inv_exponent_bit = (bit_index != 0);
        end
    endfunction

    assign in_ready = (state == ST_INPUT);

    always @* begin
        gf_a = 8'd0;
        gf_b = 8'd0;
        case (state)
            ST_SYND: begin
                gf_a = synd[synd_idx];
                gf_b = alpha_power_1_to_16(synd_idx[3:0]);
            end
            ST_BM_DISC: begin
                gf_a = lambda[bm_i];
                gf_b = synd[bm_n - bm_i];
            end
            ST_INV_SQUARE: begin
                gf_a = inv_acc;
                gf_b = inv_acc;
            end
            ST_INV_MUL: begin
                gf_a = inv_acc;
                gf_b = bval;
            end
            ST_BM_COEF: begin
                gf_a = discrepancy;
                gf_b = inv_acc;
            end
            ST_BM_UPDATE: begin
                gf_a = coef;
                gf_b = bpoly[update_i];
            end
            ST_OMEGA_ACC: begin
                gf_a = lambda[omega_i];
                gf_b = synd[omega_j - omega_i];
            end
            ST_CHIEN_EVAL: begin
                gf_a = chien_acc;
                gf_b = chien_x;
            end
            ST_CHIEN_NEXT: begin
                gf_a = chien_x;
                gf_b = 8'h02;
            end
            ST_FORNEY_OMEGA: begin
                gf_a = forney_acc;
                gf_b = error_x[error_i];
            end
            ST_FORNEY_X2: begin
                gf_a = error_x[error_i];
                gf_b = error_x[error_i];
            end
            ST_FORNEY_D0, ST_FORNEY_D1, ST_FORNEY_D2: begin
                gf_a = deriv_acc;
                gf_b = x2;
            end
            ST_FORNEY_MAG: begin
                gf_a = omega_value;
                gf_b = inv_acc;
            end
            default: begin
                gf_a = 8'd0;
                gf_b = 8'd0;
            end
        endcase
    end

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            state <= ST_INPUT;
            byte_q <= 8'd0;
            byte_count <= 8'd0;
            synd_idx <= 5'd0;
            syndrome_nonzero <= 1'b0;
            out_valid <= 1'b0;
            out_byte <= 8'd0;
            block_fail <= 1'b0;
            bm_n <= 5'd0;
            bm_i <= 4'd0;
            bm_l <= 4'd0;
            bm_m <= 4'd1;
            update_i <= 4'd0;
            discrepancy <= 8'd0;
            bval <= 8'd1;
            coef <= 8'd0;
            inv_acc <= 8'd1;
            inv_bit <= 4'd7;
            inv_mode <= 1'b0;
            omega_j <= 5'd0;
            omega_i <= 4'd0;
            omega_acc <= 8'd0;
            chien_x <= 8'd1;
            chien_acc <= 8'd0;
            chien_k <= 4'd0;
            chien_pos <= 8'd0;
            error_count <= 4'd0;
            error_i <= 4'd0;
            forney_acc <= 8'd0;
            forney_k <= 5'd0;
            omega_value <= 8'd0;
            x2 <= 8'd0;
            deriv_acc <= 8'd0;
            magnitude <= 8'd0;
            corrected_q <= 8'd0;
            out_index <= 8'd0;
            out_primed <= 1'b0;
            for (i=0; i<16; i=i+1)
                synd[i] <= 8'd0;
            for (i=0; i<9; i=i+1) begin
                lambda[i] <= 8'd0;
                bpoly[i] <= 8'd0;
                temp_poly[i] <= 8'd0;
            end
            for (i=0; i<16; i=i+1)
                omega[i] <= 8'd0;
        end else begin
            out_valid <= 1'b0;

            case (state)
                ST_INPUT: begin
                    if (in_valid) begin
                        byte_q <= in_byte;
                        synd_idx <= 5'd0;
                        state <= ST_SYND;
                    end
                end

                ST_SYND: begin
                    synd[synd_idx] <= gf_y ^ byte_q;
                    if ((gf_y ^ byte_q) != 8'd0)
                        syndrome_nonzero <= 1'b1;

                    if (synd_idx == 5'd15) begin
                        if (byte_count == 8'd203) begin
                            if (!(syndrome_nonzero || ((gf_y ^ byte_q) != 8'd0))) begin
                                out_index <= 8'd0;
                                out_primed <= 1'b0;
                                block_fail <= 1'b0;
                                state <= ST_OUTPUT;
                            end else begin
                                state <= ST_BM_INIT;
                            end
                        end else begin
                            byte_count <= byte_count + 8'd1;
                            state <= ST_INPUT;
                        end
                    end else begin
                        synd_idx <= synd_idx + 5'd1;
                    end
                end

                ST_BM_INIT: begin
                    for (i=0; i<9; i=i+1) begin
                        lambda[i] <= (i == 0) ? 8'd1 : 8'd0;
                        bpoly[i] <= (i == 0) ? 8'd1 : 8'd0;
                        temp_poly[i] <= 8'd0;
                    end
                    bm_l <= 4'd0;
                    bm_m <= 4'd1;
                    bval <= 8'd1;
                    bm_n <= 5'd0;
                    state <= ST_BM_START;
                end

                ST_BM_START: begin
                    discrepancy <= synd[bm_n];
                    bm_i <= 4'd1;
                    state <= ST_BM_DISC;
                end

                ST_BM_DISC: begin
                    if ((bm_i <= bm_l) && (bm_i <= bm_n)) begin
                        discrepancy <= discrepancy ^ gf_y;
                        bm_i <= bm_i + 4'd1;
                    end else begin
                        state <= ST_BM_CHECK;
                    end
                end

                ST_BM_CHECK: begin
                    if (discrepancy == 8'd0) begin
                        bm_m <= bm_m + 4'd1;
                        if (bm_n == 5'd15)
                            state <= ST_OMEGA_INIT;
                        else begin
                            bm_n <= bm_n + 5'd1;
                            state <= ST_BM_START;
                        end
                    end else begin
                        for (i=0; i<9; i=i+1)
                            temp_poly[i] <= lambda[i];
                        inv_acc <= 8'd1;
                        inv_bit <= 4'd7;
                        inv_mode <= 1'b0;
                        state <= ST_INV_SQUARE;
                    end
                end

                ST_INV_SQUARE: begin
                    inv_acc <= gf_y;
                    if (inv_exponent_bit(inv_bit))
                        state <= ST_INV_MUL;
                    else if (inv_bit == 0)
                        state <= inv_mode ? ST_FORNEY_MAG : ST_BM_COEF;
                    else begin
                        inv_bit <= inv_bit - 4'd1;
                        state <= ST_INV_SQUARE;
                    end
                end

                ST_INV_MUL: begin
                    inv_acc <= gf_y;
                    if (inv_bit == 0)
                        state <= inv_mode ? ST_FORNEY_MAG : ST_BM_COEF;
                    else begin
                        inv_bit <= inv_bit - 4'd1;
                        state <= ST_INV_SQUARE;
                    end
                end

                ST_BM_COEF: begin
                    coef <= gf_y;
                    update_i <= 4'd0;
                    state <= ST_BM_UPDATE;
                end

                ST_BM_UPDATE: begin
                    if ((update_i + bm_m) <= 8)
                        lambda[update_i + bm_m] <= lambda[update_i + bm_m] ^ gf_y;

                    if (update_i == 4'd8)
                        state <= ST_BM_POST;
                    else
                        update_i <= update_i + 4'd1;
                end

                ST_BM_POST: begin
                    if ((bm_l << 1) <= bm_n) begin
                        for (i=0; i<9; i=i+1)
                            bpoly[i] <= temp_poly[i];
                        bm_l <= bm_n + 1 - bm_l;
                        bval <= discrepancy;
                        bm_m <= 4'd1;
                    end else begin
                        bm_m <= bm_m + 4'd1;
                    end

                    if (bm_n == 5'd15)
                        state <= ST_OMEGA_INIT;
                    else begin
                        bm_n <= bm_n + 5'd1;
                        state <= ST_BM_START;
                    end
                end

                ST_OMEGA_INIT: begin
                    omega_j <= 5'd0;
                    omega_i <= 4'd0;
                    omega_acc <= 8'd0;
                    state <= ST_OMEGA_ACC;
                end

                ST_OMEGA_ACC: begin
                    if ((omega_i <= bm_l) && (omega_i <= omega_j)) begin
                        omega_acc <= omega_acc ^ gf_y;
                        omega_i <= omega_i + 4'd1;
                    end else begin
                        state <= ST_OMEGA_STORE;
                    end
                end

                ST_OMEGA_STORE: begin
                    omega[omega_j] <= omega_acc;
                    if (omega_j == 5'd15)
                        state <= ST_CHIEN_INIT;
                    else begin
                        omega_j <= omega_j + 5'd1;
                        omega_i <= 4'd0;
                        omega_acc <= 8'd0;
                        state <= ST_OMEGA_ACC;
                    end
                end

                ST_CHIEN_INIT: begin
                    chien_x <= 8'd1;
                    chien_pos <= 8'd0;
                    error_count <= 4'd0;
                    chien_acc <= lambda[bm_l];
                    chien_k <= (bm_l == 0) ? 0 : (bm_l - 1'b1);
                    state <= (bm_l == 0) ? ST_CHIEN_CHECK : ST_CHIEN_EVAL;
                end

                ST_CHIEN_EVAL: begin
                    chien_acc <= gf_y ^ lambda[chien_k];
                    if (chien_k == 0)
                        state <= ST_CHIEN_CHECK;
                    else
                        chien_k <= chien_k - 4'd1;
                end

                ST_CHIEN_CHECK: begin
                    if ((chien_acc == 8'd0) && (error_count < 8)) begin
                        error_pos[error_count] <= chien_pos;
                        error_x[error_count] <= chien_x;
                        error_count <= error_count + 4'd1;
                    end
                    state <= ST_CHIEN_NEXT;
                end

                ST_CHIEN_NEXT: begin
                    chien_x <= gf_y;
                    if (chien_pos == 8'd203) begin
                        state <= ST_FORNEY_INIT;
                    end else begin
                        chien_pos <= chien_pos + 8'd1;
                        chien_acc <= lambda[bm_l];
                        chien_k <= (bm_l == 0) ? 0 : (bm_l - 1'b1);
                        state <= (bm_l == 0) ? ST_CHIEN_CHECK : ST_CHIEN_EVAL;
                    end
                end

                ST_FORNEY_INIT: begin
                    block_fail <= (error_count != bm_l);
                    if (error_count == 0) begin
                        out_index <= 8'd0;
                        out_primed <= 1'b0;
                        state <= ST_OUTPUT;
                    end else begin
                        error_i <= 4'd0;
                        forney_acc <= omega[15];
                        forney_k <= 5'd14;
                        state <= ST_FORNEY_OMEGA;
                    end
                end

                ST_FORNEY_OMEGA: begin
                    forney_acc <= gf_y ^ omega[forney_k];
                    if (forney_k == 0) begin
                        omega_value <= gf_y ^ omega[0];
                        state <= ST_FORNEY_X2;
                    end else begin
                        forney_k <= forney_k - 5'd1;
                    end
                end

                ST_FORNEY_X2: begin
                    x2 <= gf_y;
                    deriv_acc <= lambda[7];
                    state <= ST_FORNEY_D0;
                end

                ST_FORNEY_D0: begin
                    deriv_acc <= gf_y ^ lambda[5];
                    state <= ST_FORNEY_D1;
                end
                ST_FORNEY_D1: begin
                    deriv_acc <= gf_y ^ lambda[3];
                    state <= ST_FORNEY_D2;
                end
                ST_FORNEY_D2: begin
                    deriv_acc <= gf_y ^ lambda[1];
                    bval <= gf_y ^ lambda[1];
                    inv_acc <= 8'd1;
                    inv_bit <= 4'd7;
                    inv_mode <= 1'b1;
                    state <= ST_INV_SQUARE;
                end

                ST_FORNEY_MAG: begin
                    magnitude <= gf_y;
                    state <= ST_FORNEY_READ;
                end

                ST_FORNEY_READ: begin
                    corrected_q <= ram_rdata;
                    state <= ST_FORNEY_WRITE;
                end

                ST_FORNEY_WRITE: begin
                    if (error_i + 1 >= error_count) begin
                        out_index <= 8'd0;
                        state <= ST_OUTPUT;
                    end else begin
                        error_i <= error_i + 4'd1;
                        forney_acc <= omega[15];
                        forney_k <= 5'd14;
                        state <= ST_FORNEY_OMEGA;
                    end
                end

                ST_OUTPUT: begin
                    if (!out_primed) begin
                        // One cycle to prime the synchronous BSRAM read port.
                        out_primed <= 1'b1;
                    end else begin
                        out_byte <= ram_rdata;
                        out_valid <= 1'b1;
                        if (out_index == 8'd187)
                            state <= ST_BLOCK_RESET;
                        else
                            out_index <= out_index + 8'd1;
                    end
                end

                default: begin
                    byte_count <= 8'd0;
                    out_primed <= 1'b0;
                    synd_idx <= 5'd0;
                    syndrome_nonzero <= 1'b0;
                    for (i=0; i<16; i=i+1)
                        synd[i] <= 8'd0;
                    state <= ST_INPUT;
                end
            endcase
        end
    end
endmodule
