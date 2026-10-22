"""Four contexts, one 32-ACS datapath. Atomic two-clock slots, explicit idle service.

The scheduler supplies context slots, including idle slots to drain traceback.
No full-receiver admission or physical timing guarantee is implied.
"""
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from s3_viterbi_erasure import source

BANKED = ('initialized','wr_ptr','accepted','read_ptr','walk','state','tracing',
          'priming','prime_extra','decoded_write','decoded_read','decoded_ready',
          'output_tick','output_pos','survivor_q','survivor_pipe')

def generate(metric_ram=False, narrow=False, shift_output=False, local_shift=False, paired_metrics=False, slot_address=False):
    s=source().replace('module s3_viterbi_erasure','module shared_k7_context')
    s=s.replace('    input  wire        in_valid,', '''    input wire slot_valid,
    output wire slot_ready,
    input wire [1:0] slot_context,
    output reg [1:0] out_context,
    input  wire        in_valid,''')
    # Extract declarations of banked scalar/vector registers before rewriting
    # references, to keep widths and names mechanically tied to the baseline.
    declarations=[]
    pattern=r'    reg (\[[^;\n]+?\]\s+)?([^;\n]+);'
    def decl(m):
        width=m.group(1) or ''
        names=[x.strip() for x in m.group(2).split(',')]
        selected=[n for n in names if n in BANKED]
        if not selected:return m.group(0)
        for n in selected:declarations.append(f'    reg {width}{n} [0:3];')
        remaining=[n for n in names if n not in BANKED]
        return ('    reg '+width+', '.join(remaining)+';') if remaining else ''
    s=re.sub(pattern,decl,s)
    assert len(declarations)==len(BANKED),(len(declarations),declarations)
    for name in BANKED:s=re.sub(r'\b'+name+r'\b',name+'[context_id]',s)
    s=s.replace('reg [METRIC_W-1:0] metrics [0:63];','reg [METRIC_W-1:0] metrics [0:255];')
    s=re.sub(r'metrics\[([^\]]+)\]',r'metrics[64*context_id + (\1)]',s)
    for name in ('survivor_lo','survivor_hi'):
        s=s.replace(f'{name} [0:255]',f'{name} [0:1023]')
        s=re.sub(name+r'\[(wr_ptr\[context_id\]|read_ptr\[context_id\])\]',name+r'[256*context_id + \1]',s)
    s=s.replace('decoded [0:1]','decoded [0:7]')
    s=s.replace('decoded[decoded_write[context_id]]','decoded[2*context_id+decoded_write[context_id]]')
    s=s.replace('decoded[decoded_read[context_id]]','decoded[2*context_id+decoded_read[context_id]]')
    s=s.replace('    localparam [METRIC_W-1:0] INF', '\n'.join(declarations)+'''
    reg slot_active;
    reg [1:0] held_context;
    wire [1:0] context_id = slot_active ? held_context : slot_context;
    wire tick = resetn && (slot_active || slot_valid);
    assign slot_ready = resetn && !slot_active;
    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin slot_active<=0; held_context<=0; end
        else if (slot_active) slot_active<=0;
        else if (slot_valid) begin slot_active<=1; held_context<=slot_context; end
    end
    integer reset_context;
    localparam [METRIC_W-1:0] INF''')
    s=s.replace('(phase || in_valid)', '(phase || (!slot_active && in_valid))')
    s=s.replace('assign in_ready = initialized[context_id] && !phase;',
                'assign in_ready = slot_ready && initialized[context_id] && !phase;')
    s=s.replace('if (resetn) begin','if (tick) begin')
    s=s.replace('if (resetn && initialized[context_id]', 'if (tick && initialized[context_id]')
    # All read pipeline registers are context local and advance on local ticks.
    s=s.replace('        survivor_q[context_id] <=', '        if (tick) begin\n        survivor_q[context_id] <=')
    marker='''            survivor_hi[256*context_id + wr_ptr[context_id]] <= lane_decision;
        end
    end'''
    assert marker in s
    s=s.replace(marker,marker[:-7]+'    end\n    end',1)
    start=s.index('        if (!resetn) begin\n            phase <=')
    end=s.index('        end else begin',start)
    reset=s[start:end].replace('context_id','reset_context')
    reset=reset.replace('if (!resetn) begin','if (!resetn) begin\n            out_context<=0;\n            for(reset_context=0;reset_context<4;reset_context=reset_context+1)begin')
    s=s[:start]+reset+'            end\n'+s[end:]
    start=s.index('        end else begin',start)
    s=s[:start]+s[start:].replace('''            out_valid <= 0;
            output_tick''','''            out_valid <= 0;
            if (tick) begin
            out_context <= context_id;
            output_tick''',1)
    pos=s.rindex('        end\n    end\nendmodule')
    s=s[:pos]+'            end\n'+s[pos:]
    # A bank-indexed read register cannot be absorbed into a physical BRAM
    # port. Keep one synchronous RAM output and tag it; cache its previous
    # context value, with a bypass on consecutive ticks of the same context.
    old = '        survivor_q[context_id] <= {survivor_hi[256*context_id + read_ptr[context_id]], survivor_lo[256*context_id + read_ptr[context_id]]};'
    assert old in s
    s=s.replace(old, '')
    s=s.replace('survivor_pipe[context_id] <= survivor_q[context_id];',
                'survivor_pipe[context_id] <= current_survivor_q;')
    s=s.replace('    integer i;', """    reg [63:0] ram_q;
    reg [1:0] ram_context;
    reg ram_valid;
    wire [63:0] current_survivor_q = ram_valid && ram_context == context_id
                                    ? ram_q : survivor_q[context_id];
    always @(posedge clk) begin
        if (tick) ram_q <= {survivor_hi[256*context_id+read_ptr[context_id]],
                            survivor_lo[256*context_id+read_ptr[context_id]]};
        if (ram_valid) survivor_q[ram_context] <= ram_q;
    end
    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin ram_context<=0; ram_valid<=0; end
        else begin ram_valid<=tick; if(tick)ram_context<=context_id; end
    end
    integer i;""")
    if metric_ram:
        s=s.replace('    reg [METRIC_W-1:0] metrics [0:255];',
                    '    wire [METRIC_W-1:0] metrics [0:255];\n    wire [METRIC_W-1:0] selected_metrics [0:63];')
        begin=s.index('    generate for (metric_slot=0; metric_slot<64;')
        end=s.index('    for (metric_slot=0; metric_slot<16;',begin)
        s=s[:begin]+"""    generate for (metric_slot=0; metric_slot<64; metric_slot=metric_slot+1) begin : g_metric_state
        (* ram_style = "distributed" *) reg [METRIC_W-1:0] bank [0:3];
        assign selected_metrics[metric_slot] = bank[context_id];
        // Simulation observability; unused constant-index taps are removed by synthesis.
        for(genvar context_tap=0;context_tap<4;context_tap=context_tap+1)begin : g_tap
            assign metrics[64*context_tap+metric_slot] = bank[context_tap];
        end
        always @(posedge clk) begin
            if (tick) begin
                if (!initialized[context_id]) begin
                    if (init_phase == (metric_slot >= 32)) bank[context_id] <= 0;
                end else if (step_enable && (phase == (metric_slot >= 32)))
                    bank[context_id] <= lane_metric[metric_slot % 32];
            end
        end
    end
"""+s[end:]
        s=re.sub(r'metrics\[64\*context_id \+ \(([^]]+)\)\]',r'selected_metrics[\1]',s)
    if paired_metrics:
        if not metric_ram:raise ValueError('paired_metrics requires metric_ram')
        begin=s.index('    genvar metric_slot;')
        end=s.index('    always @(posedge clk) begin\n        if (tick) begin',begin)
        s=s[:begin]+"""    reg pending_hi_valid;
    reg [1:0] pending_hi_context;
    always @(posedge clk or negedge resetn)begin
        if(!resetn)begin pending_hi_valid<=0;pending_hi_context<=0;end
        else begin
            pending_hi_valid<=tick && ((!initialized[context_id] && init_phase) ||
                                      (initialized[context_id] && phase));
            if(tick)pending_hi_context<=context_id;
        end
    end
    generate for(genvar bank_lane=0;bank_lane<16;bank_lane=bank_lane+1)begin : g_paired_metric
        (* ram_style = "distributed" *) reg [METRIC_W-1:0] lo_bank[0:7];
        (* ram_style = "distributed" *) reg [METRIC_W-1:0] hi_bank[0:7];
        reg [METRIC_W-1:0] pending_lo,pending_hi;
        wire [METRIC_W-1:0] lo_read=lo_bank[{context_id,phase}];
        wire [METRIC_W-1:0] hi_read=hi_bank[{context_id,phase}];
        assign selected_metrics[bank_lane]=lo_read;
        assign selected_metrics[16+bank_lane]=lo_read;
        assign selected_metrics[32+bank_lane]=hi_read;
        assign selected_metrics[48+bank_lane]=hi_read;
        for(genvar ct=0;ct<4;ct=ct+1)begin : g_tap
            assign metrics[64*ct+bank_lane]=lo_bank[2*ct];
            assign metrics[64*ct+16+bank_lane]=lo_bank[2*ct+1];
            assign metrics[64*ct+32+bank_lane]=hi_bank[2*ct];
            assign metrics[64*ct+48+bank_lane]=pending_hi_valid && pending_hi_context==ct
                ? pending_hi : hi_bank[2*ct+1];
        end
        always @(posedge clk)begin
            if(tick && ((!initialized[context_id] && !init_phase) ||
                        (step_enable && !phase)))begin
                pending_lo<=initialized[context_id] ? lane_metric[16+bank_lane] : 13'd0;
                lo_bank[{context_id,1'b0}]<=initialized[context_id] ? lane_metric[bank_lane] : 13'd0;
            end else if(tick && ((!initialized[context_id] && init_phase) ||
                                (initialized[context_id] && phase)))
                lo_bank[{context_id,1'b1}]<=pending_lo;
            // Upper group 48..63 retires one global clock later. No added slot.
            if(pending_hi_valid)hi_bank[{pending_hi_context,1'b1}]<=pending_hi;
            else if(tick && ((!initialized[context_id] && init_phase) ||
                            (initialized[context_id] && phase)))
                hi_bank[{context_id,1'b0}]<=initialized[context_id] ? lane_metric[bank_lane] : 13'd0;
            if(tick && ((!initialized[context_id] && init_phase) ||
                        (initialized[context_id] && phase)))
                pending_hi<=initialized[context_id] ? lane_metric[16+bank_lane] : 13'd0;
        end
    end endgenerate

"""+s[end:]
        s=s.replace('src0 = phase ? metric_shadow[i >> 1] : selected_metrics[i >> 1];',
                    'src0 = selected_metrics[i >> 1];')
    if slot_address:
        if not paired_metrics:raise ValueError('slot_address requires paired_metrics')
        # An accepted step's phase equals the atomic slot phase. Idle/init
        # slots do not consume these read values. Keep the ACS phase register
        # out of the high-fanout distributed RAM address network.
        s=s.replace('lo_bank[{context_id,phase}]','lo_bank[{context_id,slot_active}]')
        s=s.replace('hi_bank[{context_id,phase}]','hi_bank[{context_id,slot_active}]')
    if shift_output:
        s=s.replace('decoded[2*context_id+decoded_write[context_id]][123-walk[context_id]] <= state[context_id][0];',
                    'decoded[2*context_id+decoded_write[context_id]] <= {decoded[2*context_id+decoded_write[context_id]][62:0],state[context_id][0]};')
        s=s.replace('out_bit <= decoded[2*context_id+decoded_read[context_id]][output_pos[context_id]];',
                    "out_bit <= decoded[2*context_id+decoded_read[context_id]][0];\n                decoded[2*context_id+decoded_read[context_id]] <= {1'b0,decoded[2*context_id+decoded_read[context_id]][63:1]};")
    if local_shift:
        if not shift_output:raise ValueError('local_shift requires shift_output')
        s=s.replace('if (walk[context_id] >= 60) decoded[2*context_id+decoded_write[context_id]] <= {decoded[2*context_id+decoded_write[context_id]][62:0],state[context_id][0]};','')
        s=s.replace("decoded[2*context_id+decoded_read[context_id]] <= {1'b0,decoded[2*context_id+decoded_read[context_id]][63:1]};",'')
        s=s.replace('endmodule',"""    generate for(genvar bank_id=0;bank_id<8;bank_id=bank_id+1)begin : g_output_bank
        always @(posedge clk) begin
            if(tick && tracing[context_id] && walk[context_id]>=60 &&
               {context_id,decoded_write[context_id]} == bank_id)
                decoded[bank_id] <= {decoded[bank_id][62:0],state[context_id][0]};
            if(tick && decoded_ready[context_id][decoded_read[context_id]] &&
               output_tick[context_id] && {context_id,decoded_read[context_id]} == bank_id)
                decoded[bank_id] <= {1'b0,decoded[bank_id][63:1]};
        end
    end endgenerate
endmodule""")
    if narrow:
        for ptr in ('read_ptr','wr_ptr'):
            s=s.replace('256*context_id + '+ptr+'[context_id]', '{context_id, '+ptr+'[context_id]}')
            s=s.replace('256*context_id+'+ptr+'[context_id]', '{context_id, '+ptr+'[context_id]}')
        for ptr in ('decoded_read','decoded_write'):
            s=s.replace('2*context_id+'+ptr+'[context_id]', '{context_id, '+ptr+'[context_id]}')
        s=s.replace('123-walk[context_id]', "7'd123-walk[context_id]")
    return s

if __name__=='__main__':print(generate('--metric-ram' in sys.argv, '--narrow' in sys.argv, '--shift-output' in sys.argv, '--local-shift' in sys.argv, '--paired-metrics' in sys.argv, '--slot-address' in sys.argv))
