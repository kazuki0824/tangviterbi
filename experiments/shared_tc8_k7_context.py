"""Prototype: add four TC8 costs and S-only uncoded-bit history to shared K7.
No scheduler, FIFO, depuncture, retune or receiver is supplied by this generator.
S is TC8PSK throughout an epoch; T contexts retain their soft/erasure interface.
"""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def generate():
 s=(ROOT/'rtl/shared_k7_context.sv').read_text()
 def rep(a,b):
  nonlocal s
  assert s.count(a)==1,(a,s.count(a));s=s.replace(a,b)
 rep('module shared_k7_context #(', 'module shared_tc8_k7_context #(')
 rep('    output reg         out_bit\n', '    output reg         out_bit,\n    input wire in_tc8, input wire[35:0] costs, input wire[3:0] b1_choice,\n    output reg out_b1\n')
 rep('    reg [7:0] soft0_q, soft1_q;', '''    reg [7:0] soft0_q, soft1_q;
    reg tc8_q;reg[35:0]costs_q;reg[3:0]b1_q;
    wire use_costs=context_id==3 && (phase ? tc8_q : in_tc8);
    wire[35:0]active_costs=phase ? costs_q : costs;''')
 rep('        for (i = 0; i < 32; i = i + 1) begin', '''        if(use_costs)begin
         bm00=active_costs[0+:9];bm01=active_costs[9+:9];
         bm10=active_costs[18+:9];bm11=active_costs[27+:9];
        end
        for (i = 0; i < 32; i = i + 1) begin''')
 rep('soft0_q <= 0; soft1_q <= 0;', 'soft0_q <= 0; soft1_q <= 0;tc8_q<=0;costs_q<=0;b1_q<=0;')
 rep('soft0_q <= soft0; soft1_q <= soft1;', 'soft0_q <= soft0; soft1_q <= soft1;tc8_q<=in_tc8;costs_q<=costs;b1_q<=b1_choice;')
 rep('            out_valid <= 0; out_bit <= 0;', '            out_valid <= 0; out_bit <= 0;out_b1<=0;')
 rep('                out_bit <= decoded[{context_id, decoded_read[context_id]}][0];', '''                out_bit <= decoded[{context_id, decoded_read[context_id]}][0];
                out_b1<=context_id==3 ? decoded_b1[decoded_read[3]][0] : 1'b0;''')
 rep('    reg [63:0] decoded [0:7];','    reg [63:0] decoded [0:7];\n    reg[63:0]decoded_b1[0:1];')
 pos=s.index('    generate for(genvar bank_id=0;')
 s=s[:pos]+'''    // Match the survivor RAM's tagged forwarding/retention latency. Only S
    // uses this history, and T ticks must never advance S's read pipeline.
    (* ram_style="block" *) reg[3:0]branch_history[0:255];
    reg[3:0]b1_ram,b1_saved,b1_pipe;reg b1_ram_valid;
    wire s_tick=tick && context_id==3;
    wire[3:0]current_b1=b1_ram_valid ? b1_ram : b1_saved;
    wire[1:0]traceback_xy=encode_pair({decision,state[3][5:1]},state[3][0]);
    always @(posedge clk)begin
     if(s_tick)b1_ram<=branch_history[read_ptr[3]];
     if(b1_ram_valid)b1_saved<=b1_ram;
     if(s_tick)b1_pipe<=current_b1;
     if(s_tick && initialized[3] && phase && tc8_q)
      branch_history[wr_ptr[3]]<=b1_q;
    end
    always @(posedge clk or negedge resetn)
     if(!resetn)b1_ram_valid<=0;else b1_ram_valid<=s_tick;
    generate for(genvar b1_bank=0;b1_bank<2;b1_bank=b1_bank+1)begin: g_uncoded_output
     always @(posedge clk)begin
      if(s_tick && tracing[3] && walk[3]>=60 && decoded_write[3]==b1_bank)
       decoded_b1[b1_bank]<={decoded_b1[b1_bank][62:0],b1_pipe[traceback_xy]};
      if(s_tick && decoded_ready[3][decoded_read[3]] && output_tick[3] && decoded_read[3]==b1_bank)
       decoded_b1[b1_bank]<={1'b0,decoded_b1[b1_bank][63:1]};
     end
    end endgenerate
''' + s[pos:]
 return s
if __name__=='__main__':print(generate(),end='')
