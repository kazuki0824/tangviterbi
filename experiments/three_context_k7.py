"""Three T contexts, sixteen ACS, four atomic clocks; ping-pong metric banks.

Reuses the verified full-width traceback, retaining eight-bit soft inputs.
This is a partial kernel, without scheduler, depuncture or external IO.
"""
from pathlib import Path


def generate(split_banks=True):
    s = (Path(__file__).resolve().parents[1] / 'rtl/shared_k7_context.sv').read_text()
    s = s.replace('module shared_k7_context', 'module three_context_k7')
    s = s.replace('[0:3]', '[0:2]').replace('[0:255]', '[0:191]')
    s = s.replace('reset_context<4', 'reset_context<3')
    s = s.replace('bank_id<8', 'bank_id<6').replace('decoded [0:7]', 'decoded [0:5]')
    start = s.index('    reg slot_active;')
    end = s.index('    integer reset_context;', start)
    s = s[:start] + '''    reg [1:0] slot_phase;
    wire slot_active = slot_phase != 0;
    reg [1:0] held_context;
    wire [1:0] context_id = slot_active ? held_context : slot_context;
    wire tick = resetn && (slot_active || (slot_valid && slot_context < 3));
    assign slot_ready = resetn && !slot_active && slot_context < 3;
    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin slot_phase<=0; held_context<=0; end
        else if (tick) begin
            slot_phase<=slot_phase+1'b1;
            if (!slot_active) held_context<=slot_context;
        end
    end
''' + s[end:]
    s = s.replace('reg phase;', 'wire [1:0] phase = slot_phase;\n    reg active_step;\n    reg generation [0:2];')
    s = s.replace('reg init_phase;', '')
    s = s.replace('reg [METRIC_W-1:0] metric_shadow [0:15];', '')
    s = s.replace('lane_metric [0:31]', 'lane_metric [0:15]')
    s = s.replace('reg [31:0] lane_decision;', 'reg [15:0] lane_decision;')
    s = s.replace('(phase || (!slot_active && in_valid))', '(slot_active ? active_step : in_valid)')
    s = s.replace('reg [31:0] decision_partial;', 'reg [47:0] decision_partial;')
    s = s.replace('initialized[context_id] && phase &&', 'step_enable && phase == 3 &&')
    s = s.replace("lane_decision = 32'b0;", "lane_decision = 16'b0;")
    s = s.replace('i < 32', 'i < 16')
    s = s.replace('(phase ? 16 : 0) + (i >> 1)', '8*phase + (i >> 1)')
    s = s.replace('src0 = selected_metrics[i >> 1];', 'src0 = selected_metrics[(phase[0] ? 8 : 0) + (i >> 1)];')
    s = s.replace('src1 = phase ? selected_metrics[48 + (i >> 1)] : selected_metrics[32 + (i >> 1)];', 'src1 = selected_metrics[32 + (phase[0] ? 8 : 0) + (i >> 1)];')
    start = s.index('    reg pending_hi_valid;')
    end = s.index('    always @(posedge clk) begin\n        if (tick) begin', start)
    s = s[:start] + '''    generate for(genvar lane=0;lane<16;lane=lane+1)begin : g_metric
        (* ram_style = "distributed" *) reg [METRIC_W-1:0] bank [0:31];
        wire [METRIC_W-1:0] lo = bank[{context_id,generation[context_id],1'b0,phase[1]}];
        wire [METRIC_W-1:0] hi = bank[{context_id,generation[context_id],1'b1,phase[1]}];
        assign selected_metrics[lane] = lo;
        assign selected_metrics[16+lane] = lo;
        assign selected_metrics[32+lane] = hi;
        assign selected_metrics[48+lane] = hi;
        for(genvar ct=0;ct<3;ct=ct+1)begin : g_context
            for(genvar q=0;q<4;q=q+1)begin : g_tap
                assign metrics[64*ct+16*q+lane] = bank[8*ct+4*generation[ct]+q];
            end
        end
        always @(posedge clk)if(tick)begin
            if(!initialized[context_id])bank[{context_id,1'b0,phase}]<=0;
            else if(step_enable)bank[{context_id,~generation[context_id],phase}]<=lane_metric[lane];
        end
    end endgenerate

''' + s[end:]
    s = s.replace('tick && initialized[context_id] && phase', 'tick && step_enable && phase == 3')
    s = s.replace('<= decision_partial;', '<= decision_partial[31:0];')
    s = s.replace('<= lane_decision;', '<= {lane_decision,decision_partial[47:32]};', 1)
    s = s.replace('phase <= 0; initialized[reset_context] <= 0; init_phase <= 0;', 'active_step<=0; generation[reset_context]<=0; initialized[reset_context]<=0;')
    start = s.index('            if (!initialized[context_id]) begin')
    end = s.index('\n            if (start_trace)', start)
    s = s[:start] + '''            if(!slot_active) active_step<=in_valid && initialized[context_id];
            if (!initialized[context_id]) begin
                if(phase==3)initialized[context_id]<=1;
            end else if(step_enable)begin
                if(phase==0)begin soft0_q<=soft0; soft1_q<=soft1; erasure_q<=erasure; end
                if(phase<3)decision_partial[16*phase+:16]<=lane_decision;
                else begin
                    generation[context_id]<=~generation[context_id];
                    wr_ptr[context_id]<=wr_ptr[context_id]+1;
                    if(accepted[context_id]<128)accepted[context_id]<=accepted[context_id]+1;
                end
            end
''' + s[end:]
    if split_banks:
        s=s.replace('reg [METRIC_W-1:0] bank [0:31];', 'reg [METRIC_W-1:0] lo_bank [0:15];\n        (* ram_style = "distributed" *) reg [METRIC_W-1:0] hi_bank [0:15];')
        s=s.replace("bank[{context_id,generation[context_id],1'b0,phase[1]}]", "lo_bank[{context_id,generation[context_id],phase[1]}]")
        s=s.replace("bank[{context_id,generation[context_id],1'b1,phase[1]}]", "hi_bank[{context_id,generation[context_id],phase[1]}]")
        s=s.replace('bank[8*ct+4*generation[ct]+q]', '(q<2 ? lo_bank[4*ct+2*generation[ct]+(q%2)] : hi_bank[4*ct+2*generation[ct]+(q%2)])')
        s=s.replace("if(!initialized[context_id])bank[{context_id,1'b0,phase}]<=0;\n            else if(step_enable)bank[{context_id,~generation[context_id],phase}]<=lane_metric[lane];", """if(!initialized[context_id])begin
                if(!phase[1])lo_bank[{context_id,1'b0,phase[0]}]<=0;
                else hi_bank[{context_id,1'b0,phase[0]}]<=0;
            end else if(step_enable)begin
                if(!phase[1])lo_bank[{context_id,~generation[context_id],phase[0]}]<=lane_metric[lane];
                else hi_bank[{context_id,~generation[context_id],phase[0]}]<=lane_metric[lane];
            end""")
    # Remove obsolete two-phase comments and unused normalization state.
    start = s.index('    // Two phases update')
    end = s.index('    wire [1:0] phase', start)
    s = s[:start] + '    // Read old generation throughout all four phases; flip at commit.\n' + s[end:]
    s = s.replace('    reg norm_q;','').replace(' norm_q <= 0;', '')
    s = s.replace('    wire normalize = phase ? norm_q : selected_metrics[0][METRIC_W-1];','')
    s = s.replace('            // phase 0 produces states 0..31 and phase 1 states 32..63.', '            // Each phase produces sixteen consecutive destination states.')
    return s


if __name__ == '__main__':
    print(generate(), end='')
