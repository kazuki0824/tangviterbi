module gf256_mul (
    input  wire [7:0] a,
    input  wire [7:0] b,
    output reg  [7:0] y
);
    // Four parallel 4x4 carryless products, then reduction
    // modulo x^8+x^4+x^3+x^2+1. No table or additional latency is needed.
    function automatic [6:0] clmul4;
        input [3:0] x, z;
        reg [9:0] spaced_x, spaced_z;
        reg [19:0] integer_product;
        begin
            // Three bits per coefficient prevent carries into the next
            // coefficient (a 4x4 product sums at most four one-bit terms).
            spaced_x = {x[3], 2'b0, x[2], 2'b0, x[1], 2'b0, x[0]};
            spaced_z = {z[3], 2'b0, z[2], 2'b0, z[1], 2'b0, z[0]};
            integer_product = spaced_x * spaced_z;
            clmul4 = {integer_product[18], integer_product[15], integer_product[12],
                      integer_product[9], integer_product[6], integer_product[3], integer_product[0]};
        end
    endfunction
    wire [6:0] low_product = clmul4(a[3:0], b[3:0]);
    wire [6:0] high_product = clmul4(a[7:4], b[7:4]);
    wire [6:0] cross_product = clmul4(a[3:0], b[7:4]) ^ clmul4(a[7:4], b[3:0]);
    wire [14:0] full_product = {8'b0, low_product} ^ {4'b0, cross_product, 4'b0} ^ {high_product, 8'b0};
    reg [14:0] reduced;
    integer degree;
    always @* begin
        reduced = full_product;
        for (degree = 14; degree >= 8; degree = degree - 1)
            reduced = reduced ^ ((15'h11d << (degree - 8)) & {15{reduced[degree]}});
        y = reduced[7:0];
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
// Two GF(256) multipliers separate coefficient and feedback operations.
// Sixteen constant-factor XOR networks update all syndromes per accepted byte.
// The serialized later phases retain the budget for the ~25.2 Mbit/s
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

    reg [7:0] byte_count;
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

    reg [7:0] coefficient_a, coefficient_b, feedback_a, feedback_b;
    wire [7:0] coefficient_y, feedback_y;

    // Prefetch independent coefficients during the preceding FSM cycle. This
    // separates the array selection network from the shared GF arithmetic,
    // without adding cycles to syndrome, BM, Chien or Forney processing.
    reg [7:0] lambda_q, omega_q;
    reg [7:0] error_x_q, error_pos_q;
    reg [15:0] synd_select, omega_select, omega_write;
    reg [8:0] lambda_select, bpoly_select, lambda_write;
    reg [7:0] synd_operand, lambda_operand, bpoly_operand, omega_operand;
    integer read_slot;
    always @* begin
        synd_operand = 0; lambda_operand = 0;
        bpoly_operand = 0; omega_operand = 0;
        for (read_slot=0; read_slot<16; read_slot=read_slot+1) begin
            synd_operand = synd_operand | (synd[read_slot] & {8{synd_select[read_slot]}});
            omega_operand = omega_operand | (omega[read_slot] & {8{omega_select[read_slot]}});
        end
        for (read_slot=0; read_slot<9; read_slot=read_slot+1) begin
            lambda_operand = lambda_operand | (lambda[read_slot] & {8{lambda_select[read_slot]}});
            bpoly_operand = bpoly_operand | (bpoly[read_slot] & {8{bpoly_select[read_slot]}});
        end
    end

    // Decode the NEXT cycle's prefetch selection ahead of the array read.
    // Recurrences shift a one-hot mask, avoiding subtract/decode/MUX chains.
    // Empty masks are speculative addresses which the FSM does not consume.
    always @(posedge clk) begin
        synd_select <= 16'd1;
        lambda_select <= 9'd1;
        bpoly_select <= 9'd1;
        omega_select <= 16'h4000;
        case (state)
            ST_BM_INIT: begin
                synd_select <= 16'd0;
                lambda_select <= 9'd2;
            end
            ST_BM_START: begin
                synd_select <= synd_select >> 1;
                lambda_select <= 9'd4;
            end
            ST_BM_DISC: begin
                synd_select <= synd_select >> 1;
                lambda_select <= lambda_select << 1;
            end
            ST_BM_CHECK: begin
                synd_select <= (bm_n == 15) ? 16'd1 : (16'd1 << bm_n);
                lambda_select <= ((bm_n == 15) && (discrepancy == 0)) ? 9'd1 : 9'd2;
            end
            ST_INV_SQUARE, ST_INV_MUL:
                lambda_select <= 9'd1 << bm_m;
            ST_BM_COEF: begin
                lambda_select <= lambda_select << 1;
                bpoly_select <= 9'd2;
            end
            ST_BM_UPDATE: begin
                lambda_select <= lambda_select << 1;
                bpoly_select <= bpoly_select << 1;
            end
            ST_BM_POST: begin
                synd_select <= (bm_n == 15) ? 16'd1 : (16'd1 << bm_n);
                lambda_select <= (bm_n == 15) ? 9'd1 : 9'd2;
            end
            ST_OMEGA_INIT: begin
                synd_select <= 16'd0;
                lambda_select <= 9'd2;
            end
            ST_OMEGA_ACC: begin
                if ((omega_i <= bm_l) && (omega_i <= omega_j)) begin
                    synd_select <= synd_select >> 1;
                    lambda_select <= lambda_select << 1;
                end else begin
                    synd_select <= 16'd1 << (omega_j + 5'd1);
                    lambda_select <= (omega_j == 15) ? (9'd1 << bm_l) : 9'd1;
                end
            end
            ST_OMEGA_STORE: begin
                synd_select <= synd_select >> 1;
                lambda_select <= (omega_j == 15) ? (lambda_select >> 1) : 9'd2;
            end
            ST_CHIEN_INIT, ST_CHIEN_EVAL: begin
                if ((state == ST_CHIEN_INIT && bm_l == 0) ||
                    (state == ST_CHIEN_EVAL && chien_k == 0))
                    lambda_select <= 9'd1 << bm_l;
                else
                    lambda_select <= lambda_select >> 1;
            end
            ST_CHIEN_CHECK: lambda_select <= lambda_select >> 1;
            ST_CHIEN_NEXT: lambda_select <= lambda_select >> 1;
            ST_FORNEY_INIT, ST_FORNEY_WRITE: omega_select <= 16'h2000;
            ST_FORNEY_OMEGA: begin
                omega_select <= omega_select >> 1;
                lambda_select <= (forney_k == 0) ? 9'd32 : 9'd128;
            end
            ST_FORNEY_X2: lambda_select <= 9'd8;
            ST_FORNEY_D0: lambda_select <= 9'd2;
            default: begin end
        endcase
        if (state == ST_BM_COEF) lambda_write <= lambda_select;
        else if (state == ST_BM_UPDATE) lambda_write <= lambda_write << 1;
        if (state == ST_OMEGA_INIT) omega_write <= 16'd1;
        else if (state == ST_OMEGA_STORE) omega_write <= omega_write << 1;
    end

    // These registers need no reset: every consumer has a preceding prefetch
    // state. Out-of-range speculative reads are discarded by the FSM.
    always @(posedge clk) begin
        lambda_q <= lambda_operand;
        omega_q <= omega_operand;
        if (state == ST_FORNEY_INIT) begin
            error_x_q <= error_x[0];
            error_pos_q <= error_pos[0];
        end else if (state == ST_FORNEY_WRITE) begin
            error_x_q <= error_x[error_i + 4'd1];
            error_pos_q <= error_pos[error_i + 4'd1];
        end
    end

    // Give each coefficient a local write enable. Constant destinations avoid
    // the variable-address write shifters generated for resettable arrays.
    genvar slot;
    generate for (slot=0; slot<16; slot=slot+1) begin : g_synd_omega
        always @(posedge clk or negedge resetn) begin
            if (!resetn) begin
                synd[slot] <= 8'd0;
                omega[slot] <= 8'd0;
            end else begin
                if (state == ST_BLOCK_RESET)
                    synd[slot] <= 8'd0;
                else if ((state == ST_INPUT) && in_valid)
                    synd[slot] <= gf_constant(synd[slot], alpha_factor(slot+1)) ^ in_byte;
                if ((state == ST_OMEGA_STORE) && omega_write[slot])
                    omega[slot] <= omega_acc;
            end
        end
    end
    for (slot=0; slot<9; slot=slot+1) begin : g_polynomial
        always @(posedge clk or negedge resetn) begin
            if (!resetn) begin
                lambda[slot] <= 8'd0;
                bpoly[slot] <= 8'd0;
                temp_poly[slot] <= 8'd0;
            end else begin
                if (state == ST_BM_INIT) begin
                    lambda[slot] <= (slot == 0) ? 8'd1 : 8'd0;
                    bpoly[slot] <= (slot == 0) ? 8'd1 : 8'd0;
                    temp_poly[slot] <= 8'd0;
                end else begin
                    if ((state == ST_BM_UPDATE) && lambda_write[slot])
                        lambda[slot] <= lambda_q ^ coefficient_y;
                    if ((state == ST_BM_CHECK) && (discrepancy != 0))
                        temp_poly[slot] <= lambda[slot];
                    if ((state == ST_BM_POST) && ((bm_l << 1) <= bm_n))
                        bpoly[slot] <= temp_poly[slot];
                end
            end
        end
    end
    for (slot=0; slot<8; slot=slot+1) begin : g_error
        always @(posedge clk) begin
            if (resetn && (state == ST_CHIEN_CHECK) && (chien_acc == 0) && (error_count == slot)) begin
                error_pos[slot] <= chien_pos;
                error_x[slot] <= chien_x;
            end
        end
    end endgenerate


    gf256_mul u_coefficient_mul(.a(coefficient_a), .b(coefficient_b), .y(coefficient_y));
    gf256_mul u_feedback_mul(.a(feedback_a), .b(feedback_b), .y(feedback_y));

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
            ram_raddr = error_pos_q;
        end

        if (state == ST_FORNEY_WRITE) begin
            ram_we = 1'b1;
            ram_waddr = error_pos_q;
            ram_wdata = corrected_q ^ magnitude;
        end

        if (state == ST_OUTPUT) begin
            ram_raddr = out_primed ? (out_index + 8'd1) : out_index;
        end
    end

    function automatic [7:0] gf_xtime;
        input [7:0] x;
        begin
            gf_xtime = {x[6:0], 1'b0} ^ (8'h1d & {8{x[7]}});
        end
    endfunction

    function automatic [7:0] alpha_factor;
        input integer power;
        reg [7:0] x;
        integer i;
        begin
            x = 8'd1;
            for (i=0; i<power; i=i+1) x = gf_xtime(x);
            alpha_factor = x;
        end
    endfunction

    function automatic [7:0] gf_constant;
        input [7:0] x, factor;
        reg [7:0] shifted, product;
        integer i;
        begin
            shifted = x; product = 0;
            for (i=0; i<8; i=i+1) begin
                product = product ^ (shifted & {8{factor[i]}});
                shifted = gf_xtime(shifted);
            end
            gf_constant = product;
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

    // Separate coefficient products from Horner/inversion feedback. This
    // removes the broad array/feedback operand MUX from each multiplier input.
    // Both inputs are scheduled in existing cycles; operation count is unchanged.
    reg [7:0] coefficient_next_a, coefficient_next_b;
    reg [7:0] feedback_next_a, feedback_next_b;
    always @* begin
        coefficient_next_a = 0; coefficient_next_b = 0;
        feedback_next_a = 0; feedback_next_b = 0;
        case (state)
            ST_BM_START, ST_BM_DISC, ST_OMEGA_INIT, ST_OMEGA_ACC, ST_OMEGA_STORE: begin
                coefficient_next_a = lambda_operand; coefficient_next_b = synd_operand;
            end
            ST_BM_COEF: begin
                coefficient_next_a = coefficient_y; coefficient_next_b = bpoly[0];
            end
            ST_BM_UPDATE: begin
                coefficient_next_a = coef; coefficient_next_b = bpoly_operand;
            end
            ST_INV_SQUARE: begin
                if (!inv_exponent_bit(inv_bit) && !inv_mode) begin
                    coefficient_next_a = discrepancy; coefficient_next_b = feedback_y;
                end
            end
            default: begin end
        endcase
        case (state)
            ST_BM_CHECK, ST_FORNEY_D2: begin
                feedback_next_a = 1; feedback_next_b = 1;
            end
            ST_INV_SQUARE: begin
                if (inv_exponent_bit(inv_bit)) begin
                    feedback_next_a = feedback_y; feedback_next_b = bval;
                end else if (inv_mode) begin
                    feedback_next_a = omega_value; feedback_next_b = feedback_y;
                end
            end
            ST_INV_MUL: begin
                feedback_next_a = feedback_y; feedback_next_b = feedback_y;
            end
            ST_CHIEN_INIT: begin
                feedback_next_a = lambda_q; feedback_next_b = 1;
            end
            ST_CHIEN_EVAL: begin
                feedback_next_a = feedback_y ^ lambda_q; feedback_next_b = chien_x;
            end
            ST_CHIEN_CHECK: begin
                feedback_next_a = chien_x; feedback_next_b = 8'h02;
            end
            ST_CHIEN_NEXT: begin
                feedback_next_a = lambda_q; feedback_next_b = feedback_y;
            end
            ST_FORNEY_INIT: begin
                feedback_next_a = omega[15]; feedback_next_b = error_x[0];
            end
            ST_FORNEY_OMEGA: begin
                if (forney_k == 0) begin
                    feedback_next_a = error_x_q; feedback_next_b = error_x_q;
                end else begin
                    feedback_next_a = feedback_y ^ omega_q; feedback_next_b = error_x_q;
                end
            end
            ST_FORNEY_X2: begin
                feedback_next_a = lambda_q; feedback_next_b = feedback_y;
            end
            ST_FORNEY_D0, ST_FORNEY_D1: begin
                feedback_next_a = feedback_y ^ lambda_q; feedback_next_b = x2;
            end
            ST_FORNEY_WRITE: begin
                feedback_next_a = omega[15]; feedback_next_b = error_x[error_i + 4'd1];
            end
            default: begin end
        endcase
    end
    always @(posedge clk) begin
        coefficient_a <= coefficient_next_a; coefficient_b <= coefficient_next_b;
        feedback_a <= feedback_next_a; feedback_b <= feedback_next_b;
    end

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            state <= ST_INPUT;
            byte_count <= 8'd0;
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
        end else begin
            out_valid <= 1'b0;

            case (state)
                ST_INPUT: begin
                    if (in_valid) begin
                        // The sticky flag matches the original decoder: the
                        // first nonzero byte makes every running syndrome
                        // nonzero, and the flag stays set until block reset.
                        if (in_byte != 0) syndrome_nonzero <= 1'b1;
                        if (byte_count == 8'd203) begin
                            if (!(syndrome_nonzero || (in_byte != 0))) begin
                                out_index <= 8'd0;
                                out_primed <= 1'b0;
                                block_fail <= 1'b0;
                                state <= ST_OUTPUT;
                            end else begin
                                state <= ST_BM_INIT;
                            end
                        end else begin
                            byte_count <= byte_count + 8'd1;
                        end
                    end
                end

                ST_BM_INIT: begin
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
                        discrepancy <= discrepancy ^ coefficient_y;
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
                        inv_acc <= 8'd1;
                        inv_bit <= 4'd7;
                        inv_mode <= 1'b0;
                        state <= ST_INV_SQUARE;
                    end
                end

                ST_INV_SQUARE: begin
                    inv_acc <= feedback_y;
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
                    inv_acc <= feedback_y;
                    if (inv_bit == 0)
                        state <= inv_mode ? ST_FORNEY_MAG : ST_BM_COEF;
                    else begin
                        inv_bit <= inv_bit - 4'd1;
                        state <= ST_INV_SQUARE;
                    end
                end

                ST_BM_COEF: begin
                    coef <= coefficient_y;
                    update_i <= 4'd0;
                    state <= ST_BM_UPDATE;
                end

                ST_BM_UPDATE: begin

                    if (update_i == 4'd8)
                        state <= ST_BM_POST;
                    else
                        update_i <= update_i + 4'd1;
                end

                ST_BM_POST: begin
                    if ((bm_l << 1) <= bm_n) begin
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
                        omega_acc <= omega_acc ^ coefficient_y;
                        omega_i <= omega_i + 4'd1;
                    end else begin
                        state <= ST_OMEGA_STORE;
                    end
                end

                ST_OMEGA_STORE: begin
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
                    chien_acc <= lambda_q;
                    chien_k <= (bm_l == 0) ? 0 : (bm_l - 1'b1);
                    state <= (bm_l == 0) ? ST_CHIEN_CHECK : ST_CHIEN_EVAL;
                end

                ST_CHIEN_EVAL: begin
                    chien_acc <= feedback_y ^ lambda_q;
                    if (chien_k == 0)
                        state <= ST_CHIEN_CHECK;
                    else
                        chien_k <= chien_k - 4'd1;
                end

                ST_CHIEN_CHECK: begin
                    if ((chien_acc == 8'd0) && (error_count < 8)) begin
                        error_count <= error_count + 4'd1;
                    end
                    state <= ST_CHIEN_NEXT;
                end

                ST_CHIEN_NEXT: begin
                    chien_x <= feedback_y;
                    if (chien_pos == 8'd203) begin
                        state <= ST_FORNEY_INIT;
                    end else begin
                        chien_pos <= chien_pos + 8'd1;
                        chien_acc <= lambda_q;
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
                    forney_acc <= feedback_y ^ omega_q;
                    if (forney_k == 0) begin
                        omega_value <= feedback_y ^ omega_q;
                        state <= ST_FORNEY_X2;
                    end else begin
                        forney_k <= forney_k - 5'd1;
                    end
                end

                ST_FORNEY_X2: begin
                    x2 <= feedback_y;
                    deriv_acc <= lambda_q;
                    state <= ST_FORNEY_D0;
                end

                ST_FORNEY_D0: begin
                    deriv_acc <= feedback_y ^ lambda_q;
                    state <= ST_FORNEY_D1;
                end
                ST_FORNEY_D1: begin
                    deriv_acc <= feedback_y ^ lambda_q;
                    state <= ST_FORNEY_D2;
                end
                ST_FORNEY_D2: begin
                    deriv_acc <= feedback_y ^ lambda_q;
                    bval <= feedback_y ^ lambda_q;
                    inv_acc <= 8'd1;
                    inv_bit <= 4'd7;
                    inv_mode <= 1'b1;
                    state <= ST_INV_SQUARE;
                end

                ST_FORNEY_MAG: begin
                    magnitude <= feedback_y;
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
                            syndrome_nonzero <= 1'b0;
                    state <= ST_INPUT;
                end
            endcase
        end
    end
endmodule
