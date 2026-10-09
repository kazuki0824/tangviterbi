"""TC8PSK survivor extension, ITU-R BO.1408-1 section 9/Figures 13--15.

Input is FOUR 9-bit branch costs indexed by (X,Y), plus each branch's optimal
uncoded B1. These must come from an 8PSK symbol metric unit, NOT two independent
binary LLRs. Outputs are (B1,B0). The RF synchronizer and metric unit are separate.
"""
from s3_viterbi_traceback import generate

def source():
 s=generate('modulo13-pipe').replace('module s3_viterbi_traceback','module s3_tc8psk')
 s=s.replace('    input  wire [7:0]  soft0,\n    input  wire [7:0]  soft1,','    input wire [35:0] costs,\n    input wire [3:0] b1_choice,')
 s=s.replace('output reg         out_bit','output reg [1:0]   out_bits')
 s=s.replace('    reg [7:0] soft0_q, soft1_q;', '    reg [35:0] costs_q;\n    reg [3:0] b1_q;\n    wire [35:0] active_costs=phase?costs_q:costs;\n    wire [3:0] active_b1=phase?b1_q:b1_choice;\n    reg [31:0] lane_b1, b1_partial;')
 s=s.replace('    reg [7:0] active_soft0;\n    reg [7:0] active_soft1;', '')
 s=s.replace('        active_soft0 = !phase ? soft0 : soft0_q;\n        active_soft1 = !phase ? soft1 : soft1_q;', '')
 a=s.index('        bm00 =');b=s.index('\n        for (i =',a)
 s=s[:a]+''.join(f'        bm{n:02b} = active_costs[{9*n} +: 9];\n' for n in range(4))+s[b:]
 s=s.replace("lane_decision[i] = 1'b1;", "lane_decision[i] = 1'b1;\n                lane_b1[i] = active_b1[(~coded0)&2'b11];")
 s=s.replace("lane_decision[i] = 1'b0;", "lane_decision[i] = 1'b0;\n                lane_b1[i] = active_b1[coded0];")
 s=s.replace('    reg [63:0] decoded [0:1];', '''    reg [63:0] decoded [0:1], decoded_b1[0:1];
    reg save_valid,save_bank,save_last,save_b0,save_b1;
    reg [5:0] save_index;
    (* ram_style="block" *) reg [31:0] uncoded_lo[0:255],uncoded_hi[0:255];
    reg [63:0] uncoded_q,uncoded_pipe;''')
 s=s.replace('        survivor_pipe <= survivor_q;', '        survivor_pipe <= survivor_q;\n        uncoded_q <= {uncoded_hi[read_ptr],uncoded_lo[read_ptr]};\n        uncoded_pipe <= uncoded_q;')
 s=s.replace('            survivor_hi[wr_ptr] <= lane_decision;', '            survivor_hi[wr_ptr] <= lane_decision;\n            uncoded_lo[wr_ptr] <= b1_partial;\n            uncoded_hi[wr_ptr] <= lane_b1;')
 s=s.replace('soft0_q <= 0; soft1_q <= 0;', 'costs_q <= 0; b1_q <= 0; b1_partial<=0;')
 s=s.replace('soft0_q <= soft0; soft1_q <= soft1;', 'costs_q <= costs; b1_q <= b1_choice; b1_partial<=lane_b1;')
 # Register the selected uncoded bit BEFORE the variable-position buffer
 # write. This removes a routed 64:1 selector -> 128-bit write-enable path.
 # The final write/ready is delayed together; 126+1 clocks still fit 128.
 s=s.replace('if (walk >= 60) decoded[decoded_write][123-walk] <= state[0];', '''if (walk >= 60) begin
                    save_valid<=1; save_bank<=decoded_write;
                    save_index<=6'd59-walk[5:0];
                    save_b0<=state[0]; save_b1<=uncoded_pipe[state];
                    save_last<=walk==123;
                end''')
 s=s.replace('                    decoded_ready[decoded_write] <= 1;', '')
 s=s.replace('            out_valid <= 0; out_bit <= 0;', '''            out_valid <= 0; out_bits <= 0;
            save_valid<=0;save_bank<=0;save_last<=0;
            save_b0<=0;save_b1<=0;save_index<=0;''')
 s=s.replace('            out_valid <= 0;\n            output_tick', '''            out_valid <= 0;
            save_valid<=0;
            if (save_valid) begin
                decoded[save_bank][save_index]<=save_b0;
                decoded_b1[save_bank][save_index]<=save_b1;
                if (save_last) decoded_ready[save_bank]<=1;
            end
            output_tick''')
 s=s.replace('out_bit <= decoded[decoded_read][output_pos];','out_bits <= {decoded_b1[decoded_read][output_pos],decoded[decoded_read][output_pos]};')
 # Each input cost is <=511: spread <=6*511, candidate spread <=7*511=3577<4096.
 return s

if __name__=='__main__':print(source())
