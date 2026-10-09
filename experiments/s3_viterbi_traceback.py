"""Generate a receiver-oriented block traceback experiment from the ACS baseline.

The production benchmark is preserved. 124 reverse trellis steps yield 64
chronological decoded bits every 64 accepted input steps. A 256-row survivor
ring avoids collision with the producer. No claim of error-free decoding beyond
the convolutional code's correction capability or whole-receiver timing.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def generate():
    src = (ROOT / "rtl/viterbi_k7_32acs.sv").read_text()
    src = src.replace("module viterbi_k7_32acs", "module s3_viterbi_traceback")
    start = src.index("    reg [5:0] wr_ptr;")
    end = src.index("    integer i;", start)
    src = src[:start] + '''    reg [7:0] wr_ptr;
    reg [7:0] accepted;
    reg norm_q;
    reg [31:0] decision_partial;
    wire normalize = phase ? norm_q : metrics[0][METRIC_W-1];
    (* ram_style = "block" *) reg [31:0] survivor_lo [0:255];
    (* ram_style = "block" *) reg [31:0] survivor_hi [0:255];
    reg [63:0] survivor_q;
    reg [7:0] read_ptr;
    reg [6:0] walk;
    reg [5:0] state;
    reg tracing, priming;
    reg [63:0] decoded [0:1];
    reg decoded_write, decoded_read;
    reg [1:0] decoded_ready;
    reg output_tick;
    reg [5:0] output_pos;
    wire start_trace = initialized && phase && (accepted >= 127) &&
                      (wr_ptr[5:0] == 63);
    wire decision = survivor_q[state];

''' + src[end:]
    src = src.replace("            cand0 = {1'b0, src0} + branch0;",
                      "            cand0 = src0 == INF ? {1'b0, INF} : {1'b0, src0} + branch0;")
    src = src.replace("            cand1 = {1'b0, src1} + branch1;",
                      "            cand1 = src1 == INF ? {1'b0, INF} : {1'b0, src1} + branch1;")
    # Subtract 2^(W-2), not a complete min-tree; reachable metric spread is
    # bounded by six branch costs once all 64 states are reachable.
    key = "                lane_decision[i] = 1'b0;\n            end"
    src = src.replace(key, key + '''
            if (normalize && lane_metric[i] != INF)
                lane_metric[i] = lane_metric[i] - (1 << (METRIC_W-2));''')
    start = src.index("    always @(posedge clk) begin\n        // At the output edge")
    src = src[:start] + '''    always @(posedge clk) begin
        survivor_q <= {survivor_hi[read_ptr], survivor_lo[read_ptr]};
        if (resetn && initialized && phase) begin
            survivor_lo[wr_ptr] <= decision_partial;
            survivor_hi[wr_ptr] <= lane_decision;
        end
    end

    // Traceback always moves toward older rows. The first 60 steps converge
    // from state zero; the next 64 are saved in reverse index order. Writer
    // never reaches these rows before the complete block has been decoded.
    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            phase <= 0; initialized <= 0; init_phase <= 0;
            soft0_q <= 0; soft1_q <= 0; decision_partial <= 0;
            wr_ptr <= 0; accepted <= 0; norm_q <= 0;
            read_ptr <= 0; walk <= 0; state <= 0;
            tracing <= 0; priming <= 0; decoded_write <= 0;
            decoded_read <= 0; decoded_ready <= 0; output_pos <= 0; output_tick <= 0;
            out_valid <= 0; out_bit <= 0;
        end else begin
            out_valid <= 0;
            output_tick <= ~output_tick;
            if (!initialized) begin
                init_phase <= ~init_phase;
                if (init_phase) initialized <= 1;
            end else if (step_enable) begin
                if (!phase) begin
                    soft0_q <= soft0; soft1_q <= soft1;
                    decision_partial <= lane_decision;
                    norm_q <= metrics[0][METRIC_W-1];
                    phase <= 1;
                end else begin
                    phase <= 0;
                    wr_ptr <= wr_ptr + 1;
                    if (accepted < 128) accepted <= accepted + 1;
                end
            end

            if (start_trace) begin
                read_ptr <= wr_ptr - 4; state <= 0; walk <= 0;
                priming <= 1; tracing <= 0;
            end else if (priming) begin
                read_ptr <= read_ptr - 1;
                priming <= 0; tracing <= 1;
            end else if (tracing) begin
                read_ptr <= read_ptr - 1;
                state <= {decision, state[5:1]};
                walk <= walk + 1;
                if (walk >= 60) decoded[decoded_write][123-walk] <= state[0];
                if (walk == 123) begin
                    tracing <= 0;
                    decoded_write <= ~decoded_write;
                    decoded_ready[decoded_write] <= 1;
                end
            end

            if (decoded_ready[decoded_read] && output_tick) begin
                out_valid <= 1;
                out_bit <= decoded[decoded_read][output_pos];
                output_pos <= output_pos + 1;
                if (output_pos == 63) begin
                    decoded_read <= ~decoded_read;
                    decoded_ready[decoded_read] <= 0;
                end
            end
        end
    end
endmodule
'''
    return src


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("output", type=Path)
    args = p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(generate())
