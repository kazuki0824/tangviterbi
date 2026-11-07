// Reconstructed v2 diagnostic core. Coefficients are recovered original bytes;
// this RTL is new source and is not a recovery of the original RTL hash.
module t_diag_resampler #(
    parameter integer INPUT_BITS = 16,
    parameter integer L = 64,
    parameter integer OUTPUT_SHIFT = 15,
    parameter COEFF_FILE = "coeff_residual.hex"
) (
    input wire clk, resetn,
    input wire in_valid,
    output wire in_ready,
    input wire signed [INPUT_BITS-1:0] in_i, in_q,
    output wire out_valid,
    input wire out_ready,
    output wire signed [15:0] out_i, out_q
);
    localparam integer PHASE_BITS = $clog2(L);
    localparam integer PRODUCT_BITS = INPUT_BITS + 16;
    reg [31:0] coeff [0:L*16-1];
    initial $readmemh(COEFF_FILE, coeff);
    // Split by parity: two complex taps can be read in one clock using two
    // small distributed memories. Old samples before reset are validity-masked.
    reg [2*INPUT_BITS-1:0] history_even [0:15];
    reg [2*INPUT_BITS-1:0] history_odd [0:15];
    reg [4:0] write_pos, newest, anchor;
    reg [5:0] history_valid, window_valid;
    reg [PHASE_BITS-1:0] phase_cursor, active_phase;
    reg [1:0] need_inputs;
    reg active;
    reg [3:0] pair_index;
    reg [1:0] reserved, output_count;
    reg output_read_pos, output_write_pos;
    reg [31:0] output_memory [0:1];
    wire pop = out_valid && out_ready;
    wire start = !active && reserved < 2 &&
                 (need_inputs == 0 || (need_inputs == 1 && in_valid));
    assign in_ready = resetn && !active && reserved < 2 && need_inputs != 0;
    wire push = in_valid && in_ready;
    wire [PHASE_BITS+1:0] next_phase = {2'b00, phase_cursor} + 63;
    assign out_valid = output_count != 0;
    assign {out_q, out_i} = output_memory[output_read_pos];

    wire [4:0] index0 = anchor - {pair_index, 1'b0};
    wire [3:0] even_index = index0[4:1];
    wire [3:0] odd_index = index0[4:1] - !index0[0];
    wire [2*INPUT_BITS-1:0] even_word = history_even[even_index];
    wire [2*INPUT_BITS-1:0] odd_word = history_odd[odd_index];
    wire [2*INPUT_BITS-1:0] word0 = index0[0] ? odd_word : even_word;
    wire [2*INPUT_BITS-1:0] word1 = index0[0] ? even_word : odd_word;
    reg signed [INPUT_BITS-1:0] ri0, ri1, rq0, rq1;
    reg signed [15:0] rc0, rc1;
    reg r_valid, r_first, r_last;
    reg signed [PRODUCT_BITS-1:0] pi0, pi1, pq0, pq1;
    reg p_valid, p_first, p_last;
    reg signed [39:0] ai0, ai1, aq0, aq1;
    reg finish;
    wire signed [40:0] sum_i = {ai0[39], ai0} + {ai1[39], ai1};
    wire signed [40:0] sum_q = {aq0[39], aq0} + {aq1[39], aq1};
    function [15:0] saturate;
        input signed [40:0] value;
        reg signed [40:0] shifted;
        begin
            shifted = value >>> OUTPUT_SHIFT;
            if (shifted > 32767) saturate = 16'h7fff;
            else if (shifted < -32768) saturate = 16'h8000;
            else saturate = shifted[15:0];
        end
    endfunction

    always @(posedge clk) begin
        if (push) begin
            if (write_pos[0]) history_odd[write_pos[4:1]] <= {in_q, in_i};
            else history_even[write_pos[4:1]] <= {in_q, in_i};
        end
        if (active) begin
            {rc1, rc0} <= coeff[{active_phase, pair_index}];
            {rq0, ri0} <= {pair_index, 1'b0} < window_valid ? word0 : 0;
            {rq1, ri1} <= {pair_index, 1'b1} < window_valid ? word1 : 0;
        end
        pi0 <= ri0 * rc0;
        pi1 <= ri1 * rc1;
        pq0 <= rq0 * rc0;
        pq1 <= rq1 * rc1;
        if (p_valid) begin
            ai0 <= p_first ? $signed(pi0) : ai0 + $signed(pi0);
            ai1 <= p_first ? $signed(pi1) : ai1 + $signed(pi1);
            aq0 <= p_first ? $signed(pq0) : aq0 + $signed(pq0);
            aq1 <= p_first ? $signed(pq1) : aq1 + $signed(pq1);
        end
        if (finish) output_memory[output_write_pos] <= {saturate(sum_q), saturate(sum_i)};
        if (!resetn) begin
            write_pos <= 0; newest <= 0; anchor <= 0;
            history_valid <= 0; window_valid <= 0;
            phase_cursor <= 0; active_phase <= 0; need_inputs <= 1;
            active <= 0; pair_index <= 0;
            reserved <= 0; output_count <= 0;
            output_read_pos <= 0; output_write_pos <= 0;
            r_valid <= 0; r_first <= 0; r_last <= 0;
            p_valid <= 0; p_first <= 0; p_last <= 0; finish <= 0;
        end else begin
            r_valid <= active;
            r_first <= pair_index == 0;
            r_last <= pair_index == 15;
            p_valid <= r_valid; p_first <= r_first; p_last <= r_last;
            finish <= p_valid && p_last;
            if (push) begin
                newest <= write_pos;
                write_pos <= write_pos + 1'b1;
                if (history_valid < 32) history_valid <= history_valid + 1'b1;
                need_inputs <= need_inputs - 1'b1;
            end
            if (start) begin
                active <= 1;
                pair_index <= 0;
                active_phase <= phase_cursor;
                phase_cursor <= next_phase[PHASE_BITS-1:0];
                need_inputs <= next_phase >> PHASE_BITS;
                anchor <= push ? write_pos : newest;
                window_valid <= push && history_valid < 32 ? history_valid + 1'b1 : history_valid;
            end else if (active) begin
                if (pair_index == 15) active <= 0;
                pair_index <= pair_index + 1'b1;
            end
            case ({start, pop})
                2'b10: reserved <= reserved + 1'b1;
                2'b01: reserved <= reserved - 1'b1;
            endcase
            case ({finish, pop})
                2'b10: output_count <= output_count + 1'b1;
                2'b01: output_count <= output_count - 1'b1;
            endcase
            if (pop) output_read_pos <= !output_read_pos;
            if (finish) output_write_pos <= !output_write_pos;
        end
    end
endmodule
