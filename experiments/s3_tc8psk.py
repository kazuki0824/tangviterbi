"""TC8PSK survivor extension, ITU-R BO.1408-1 section 9/Figures 13--15.

Input is FOUR 9-bit branch costs indexed by (X,Y), plus each branch's optimal
uncoded B1. These must come from an 8PSK symbol metric unit, NOT two independent
binary LLRs. Outputs are (B1,B0). The RF synchronizer and metric unit are separate.
"""
from s3_viterbi_traceback import generate

def source(compact_output=False,compact_b1=False,lanes=32,metric_q15=False):
 if lanes not in (22,32):raise ValueError('supported ACS lane counts are 22 and 32')
 if lanes==22:compact_output=compact_b1=True
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
 if compact_b1:
  # B1 is the chosen uncoded bit for one of four coded (X,Y) branches.
  # A traceback already reconstructs that branch from destination state and
  # predecessor decision, so storing 64 separate B1 bits per row is redundant.
  s=s.replace('    reg [31:0] lane_b1, b1_partial;', '')
  s=s.replace("\n                lane_b1[i] = active_b1[(~coded0)&2'b11];", '')
  s=s.replace('\n                lane_b1[i] = active_b1[coded0];', '')
  s=s.replace(' b1_partial<=0;', '').replace(' b1_partial<=lane_b1;', '')
  s=s.replace('    (* ram_style="block" *) reg [31:0] uncoded_lo[0:255],uncoded_hi[0:255];\n    reg [63:0] uncoded_q,uncoded_pipe;', '''    (* ram_style="block" *) reg [3:0] branch_choice[0:255];
    reg [3:0] uncoded_q,uncoded_pipe;
    wire [1:0] traceback_xy=encode_pair({survivor_pipe[state],state[5:1]},state[0]);''')
  s=s.replace('uncoded_q <= {uncoded_hi[read_ptr],uncoded_lo[read_ptr]};','uncoded_q <= branch_choice[read_ptr];')
  s=s.replace('            uncoded_lo[wr_ptr] <= b1_partial;\n            uncoded_hi[wr_ptr] <= lane_b1;',
      '            branch_choice[wr_ptr] <= b1_q;')
  s=s.replace('save_b1<=uncoded_pipe[state];','save_b1<=uncoded_pipe[traceback_xy];')
 if compact_output:
  # One synchronous 128x2 SDP block replaces 256 individually enabled FFs
  # and their variable-position write/read multiplexers. The old registered
  # output and the memory read have the same edge and enable, so this adds
  # no output cycle. The valid bit still masks unwritten/reset contents.
  s=s.replace('    reg [63:0] decoded [0:1], decoded_b1[0:1];',
      '    (* ram_style="block" *) reg [1:0] decoded_mem[0:127];')
  s=s.replace('                decoded[save_bank][save_index]<=save_b0;\n                decoded_b1[save_bank][save_index]<=save_b1;\n','')
  s=s.replace('            out_valid <= 0; out_bits <= 0;', '            out_valid <= 0;')
  s=s.replace('                out_bits <= {decoded_b1[decoded_read][output_pos],decoded[decoded_read][output_pos]};\n','')
  s=s.replace('    // Traceback always moves toward older rows.', '''    always @(posedge clk) begin
        if (resetn && save_valid)
            decoded_mem[{save_bank,save_index}] <= {save_b1,save_b0};
        if (resetn && decoded_ready[decoded_read] && output_tick)
            out_bits <= decoded_mem[{decoded_read,output_pos}];
    end

    // Traceback always moves toward older rows.''')
 if lanes==22:s=_fold_22(s)
 if metric_q15:
  # Exact modulo arithmetic, not sample/cost requantization. Only valid
  # behind s3_tc8psk_metric(COST_SHIFT=22), signed Q1.15 I/Q. See the
  # machine-checked geometric bound and path-pair proof in
  # experiments/s3_tc8psk_metric_bound.py and reports/s3-fec-compaction.md.
  # The two candidates merging into one state differ by a seven-symbol
  # impulse: XOR labels 3,1,0,3,3,2,3. Their absolute cost difference is
  # at most 4*363+2*256=1964 < 2048, half of the 12-bit modulus.
  s=s.replace('parameter integer METRIC_W = 13','parameter integer METRIC_W = 12')
  s=s.replace('METRIC_W != 13','METRIC_W != 12')
  s=s.replace('All 64 path metrics remain 13 bits.',
      'All 64 path metrics use the fixed Q15/SHIFT22 12-bit modulo contract.')
  s='// REQUIRES s3_tc8psk_metric COST_SHIFT=22, Q1.15 I/Q; arbitrary costs are NOT supported.\n'+s
 # Each input cost is <=511: spread <=6*511, candidate spread <=7*511=3577<4096.
 return s

def _fold_22(s):
 """Three cycles/symbol, 22+22+20 states, same 64-state trellis and costs."""
 def rep(old,new):
  nonlocal s
  if old not in s:raise ValueError('missing TC8PSK fold anchor: '+old)
  s=s.replace(old,new)
 rep('    reg phase;','    reg [1:0] phase;')
 rep('    reg init_phase;','    reg [1:0] init_phase;')
 rep('metric_shadow [0:15]','metric_shadow [0:10]')
 rep('lane_metric [0:31]','lane_metric [0:21]')
 rep('reg [31:0] lane_decision','reg [21:0] lane_decision')
 rep('reg [31:0] decision_partial','reg [43:0] decision_partial')
 rep('(phase || in_valid)','((phase != 0) || in_valid)')
 rep('initialized && phase && (accepted >= 127)','initialized && (phase == 2) && (accepted >= 127)')
 rep("lane_decision = 32'b0", "lane_decision = 22'b0")
 rep('i < 32','i < 22')
 rep('p0_state = (phase ? 16 : 0) + (i >> 1);',
     'p0_state = (phase == 0 ? 0 : phase == 1 ? 11 : 22) + (i >> 1);')
 # Elaborate constant trellis labels before multiplexing the phase. Doing
 # the offset addition inside encode_pair would infer redundant adders.
 rep('coded0 = encode_pair(p0_state[5:0], i[0]);',
     'coded0 = phase == 0 ? encode_pair(i >> 1, i[0]) : phase == 1 ? encode_pair(11+(i >> 1), i[0]) : encode_pair(22+(i >> 1), i[0]);')
 rep('src1 = phase ? metrics[48 + (i >> 1)] : metrics[32 + (i >> 1)];',
     'src1 = phase == 0 ? metrics[32 + (i >> 1)] : phase == 1 ? metrics[43 + (i >> 1)] : i < 20 ? metrics[54 + (i >> 1)] : 0;')
 rep('(metric_slot >= 32)','(metric_slot / 22)')
 rep('metric_slot % 32','metric_slot % 22')
 rep('metric_slot<16','metric_slot<11')
 rep('''            if (resetn && initialized && step_enable && !phase)
                metric_shadow[metric_slot] <= metrics[16 + metric_slot];''','''            if (resetn && initialized && step_enable) begin
                if (phase == 0) metric_shadow[metric_slot] <= metrics[11 + metric_slot];
                else if (phase == 1 && metric_slot < 10)
                    metric_shadow[metric_slot] <= metrics[22 + metric_slot];
            end''')
 rep('if (resetn && initialized && phase)', 'if (resetn && initialized && phase == 2)')
 rep('survivor_lo[wr_ptr] <= decision_partial;', 'survivor_lo[wr_ptr] <= decision_partial[31:0];')
 rep('survivor_hi[wr_ptr] <= lane_decision;', 'survivor_hi[wr_ptr] <= {lane_decision[19:0],decision_partial[43:32]};')
 rep('''                init_phase <= ~init_phase;
                if (init_phase) initialized <= 1;''','''                if (init_phase == 2) initialized <= 1;
                else init_phase <= init_phase + 1'b1;''')
 rep('                    decision_partial <= lane_decision;', '                    decision_partial[21:0] <= lane_decision;')
 rep('''                    phase <= 1;
                end else begin
                    phase <= 0;''','''                    phase <= 1;
                end else if (phase == 1) begin
                    decision_partial[43:22] <= lane_decision;
                    phase <= 2;
                end else begin
                    phase <= 0;''')
 s=s.replace('''    // Two phases update the 64 metrics in place. Phase 0 would overwrite
    // predecessors 16..31 needed by phase 1, so only that quarter is saved.
    // The shadow snapshot and first-half writes use the same clock edge;
    // nonblocking assignments preserve the old predecessor generation.''','''    // Three in-place updates write states 0..21, 22..43 and 44..63.
    // Before the first write preserve old states 11..21; before the second
    // preserve 22..31 in the same eleven shadow registers. The last update
    // has twenty useful lanes. All 64 path metrics remain 13 bits.''')
 s=s.replace('// phase 0 produces states 0..31 and phase 1 states 32..63.',
     '// Destinations are phase*22+i; phase2 lanes20/21 are not stored.')
 return s

if __name__=='__main__':print(source())
