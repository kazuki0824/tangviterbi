"""Fold the verified modulo13-pipe T decoder without changing its soft inputs.

16/22/32 ACS lanes update the same 64-state K7 trellis in 4/3/2 clocks.
The original block traceback and the 13-bit exact modulo comparison are kept.
This is one convolutional context; hierarchy scheduling is not implemented here.
"""
from pathlib import Path
from experiments.s3_viterbi_traceback import generate as baseline


def generate(lanes, pipeline=False, compact_survivor=False, onehot=False, erasures=False, registered_costs=False, shift_output=False):
    if lanes not in (16, 22, 32):
        raise ValueError('lanes must be 16, 22 or 32')
    groups = (64 + lanes - 1) // lanes
    shadow_first = lanes // 2
    src = baseline('modulo13-pipe')
    src = src.replace('module s3_viterbi_traceback', 'module folded_t_viterbi')
    start = src.index('    // Two phases')
    end = src.index('    reg [7:0] soft0_q', start)
    src = src[:start] + f'''    // Preserve old low predecessors overwritten before their last use.
    // Fixed per-phase indices avoid a dynamic 64:1 metric read crossbar.
    reg [1:0] phase, init_phase;
    reg initialized;
    reg [METRIC_W-1:0] metrics [0:63];
    reg [METRIC_W-1:0] metric_shadow [{shadow_first}:31];
    reg [METRIC_W-1:0] lane_metric [0:{lanes-1}];
    reg [{lanes-1}:0] lane_decision;
    wire step_enable = initialized && ((phase != 0) || in_valid);
    wire commit_step = step_enable && (phase == {groups-1});
''' + src[end:]
    src = src.replace('reg [31:0] decision_partial;', 'reg [63:0] decision_partial;')
    src = src.replace('wire start_trace = initialized && phase && (accepted >= 127)',
                      'wire start_trace = commit_step && (accepted >= 127)')
    src = src.replace('assign in_ready = initialized && !phase;', 'assign in_ready = initialized && (phase == 0);')
    start = src.index('    always @* begin')
    end = src.index('    always @(posedge clk) begin\n        survivor_q', start)
    acs = '''    always @* begin
        active_soft0 = (phase == 0) ? soft0 : soft0_q;
        active_soft1 = (phase == 0) ? soft1 : soft1_q;
        bm00 = {1'b0, active_soft0} + {1'b0, active_soft1};
        bm01 = {1'b0, active_soft0} + {1'b0, ~active_soft1};
        bm10 = {1'b0, ~active_soft0} + {1'b0, active_soft1};
        bm11 = {1'b0, ~active_soft0} + {1'b0, ~active_soft1};
    end
'''
    # Each lane gets its own arithmetic, with only the phase-specific source
    # metrics/branch labels selected ahead of it. Tie chooses predecessor 0.
    for lane in range(lanes):
        acs += f'''    wire [METRIC_W-1:0] result_{lane};
    reg [METRIC_W-1:0] a_{lane}, b_{lane};
    reg [8:0] c_{lane}, d_{lane};
    wire [METRIC_W-1:0] x_{lane} = a_{lane} + c_{lane};
    wire [METRIC_W-1:0] y_{lane} = b_{lane} + d_{lane};
    wire signed [METRIC_W-1:0] diff_{lane} = y_{lane} - x_{lane};
    always @* begin
        a_{lane}=0; b_{lane}=0; c_{lane}=0; d_{lane}=0;
        case (phase)
'''
        for phase in range(groups):
            dest = phase * lanes + lane
            if dest >= 64:
                continue
            p0 = dest >> 1
            shift = (p0 << 1) | (dest & 1)
            label = ''.join(str((shift & g).bit_count() & 1) for g in (0o171, 0o133))
            complement = ''.join('1' if c == '0' else '0' for c in label)
            source = f'metric_shadow[{p0}]' if phase else f'metrics[{p0}]'
            acs += f"          2'd{phase}: begin a_{lane}={source}; b_{lane}=metrics[{p0+32}]; c_{lane}=bm{label}; d_{lane}=bm{complement}; end\n"
        acs += f'''          default: begin end
        endcase
        lane_metric[{lane}] = (diff_{lane} < 0) ? y_{lane} : x_{lane};
        lane_decision[{lane}] = (diff_{lane} < 0);
    end
'''
    for slot in range(64):
        acs += f'''    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == {slot//lanes}) metrics[{slot}] <= 0;
        end else if (step_enable && phase == {slot//lanes})
            metrics[{slot}] <= lane_metric[{slot%lanes}];
    end
'''
    for slot in range(shadow_first, 32):
        acs += f'''    always @(posedge clk)
        if (resetn && initialized && step_enable && phase == 0)
            metric_shadow[{slot}] <= metrics[{slot}];
'''
    tail = 64 - lanes * (groups - 1)
    acs += f"    wire [63:0] decision_word = {{lane_decision[{tail-1}:0], decision_partial[{64-tail-1}:0]}};\n"
    src = src[:start] + acs + src[end:]
    src = src.replace('if (resetn && initialized && phase) begin', 'if (resetn && commit_step) begin')
    src = src.replace('survivor_lo[wr_ptr] <= decision_partial;', 'survivor_lo[wr_ptr] <= decision_word[31:0];')
    src = src.replace('survivor_hi[wr_ptr] <= lane_decision;', 'survivor_hi[wr_ptr] <= decision_word[63:32];')
    start = src.index('            if (!initialized) begin\n                init_phase')
    end = src.index('\n            if (start_trace)', start)
    control = f'''            if (!initialized) begin
                if (init_phase == {groups-1}) initialized <= 1;
                else init_phase <= init_phase + 1;
            end else if (step_enable) begin
                if (phase == 0) begin soft0_q <= soft0; soft1_q <= soft1; end
                case (phase)
'''
    for phase in range(groups-1):
        control += f"                  2'd{phase}: decision_partial[{phase*lanes} +: {lanes}] <= lane_decision;\n"
    control += f'''                  default: begin end
                endcase
                if (commit_step) begin
                    phase <= 0; wr_ptr <= wr_ptr + 1;
                    if (accepted < 128) accepted <= accepted + 1;
                end else phase <= phase + 1;
            end
'''
    src = src[:start] + control + src[end:]
    if pipeline:
        # Issue groups on 0..G-1, retire on 1..G. The final retirement
        # completes a step; no issue of the next step can see stale metrics.
        for lane in range(lanes):
            marker = f"    wire signed [METRIC_W-1:0] diff_{lane} = y_{lane} - x_{lane};"
            replacement = f"""    reg [METRIC_W-1:0] xq_{lane}, yq_{lane};
    always @(posedge clk) begin xq_{lane} <= x_{lane}; yq_{lane} <= y_{lane}; end
    wire signed [METRIC_W-1:0] diff_{lane} = yq_{lane} - xq_{lane};"""
            src = src.replace(marker, replacement)
            src = src.replace(f"? y_{lane} : x_{lane};", f"? yq_{lane} : xq_{lane};")
        src = src.replace(f"(phase == {groups-1});", f"(phase == {groups});", 1)
        for slot in range(64):
            src = src.replace(f"else if (step_enable && phase == {slot//lanes})\n            metrics[{slot}]",
                              f"else if (step_enable && phase == {slot//lanes+1})\n            metrics[{slot}]")
        for phase in range(groups-1):
            src = src.replace(f"2'd{phase}: decision_partial[{phase*lanes}",
                              f"3'd{phase+1}: decision_partial[{phase*lanes}")
        src = src.replace('reg [1:0] phase, init_phase;', 'reg [2:0] phase, init_phase;')
    if compact_survivor:
        if lanes != 16:
            raise ValueError('packed survivor needs four 16-bit write phases')
        # One 16K-bit memory, four writes/trellis step; traceback reads only
        # its selected quadrant and takes two clocks per reverse step.
        start = src.index('    (* ram_style = "block" *) reg [31:0] survivor_lo')
        end = src.index('    reg [7:0] read_ptr;', start)
        src = src[:start] + '''    (* ram_style = "block" *) reg [15:0] survivor [0:1023];
    reg [15:0] survivor_q;
''' + src[end:]
        src = src.replace('wire decision = survivor_pipe[state];', 'wire decision = survivor_q[state[3:0]];')
        start = src.index('    always @(posedge clk) begin\n        survivor_q')
        end = src.index('    // Traceback always', start)
        delay = int(pipeline)
        src = src[:start] + f'''    wire [1:0] write_quadrant = phase - {delay};
    always @(posedge clk) begin
        survivor_q <= survivor[{{read_ptr, state[5:4]}}];
        if (resetn && step_enable && phase >= {delay} && phase < {delay+4})
            survivor[{{wr_ptr,write_quadrant}}] <= lane_decision;
    end
''' + src[end:]
        src = src.replace('            prime_extra <= 0;\n','')
        start = src.index('            if (start_trace) begin')
        end = src.index('            if (decoded_ready', start)
        src = src[:start] + '''            if (start_trace) begin
                read_ptr <= wr_ptr - 4; state <= 0; walk <= 0;
                priming <= 1; tracing <= 1;
            end else if (tracing) begin
                if (priming) priming <= 0;
                else begin
                    read_ptr <= read_ptr - 1;
                    state <= {decision, state[5:1]};
                    walk <= walk + 1; priming <= 1;
                    if (walk >= 60) decoded[decoded_write][123-walk] <= state[0];
                    if (walk == 123) begin
                        tracing <= 0; decoded_write <= ~decoded_write;
                        decoded_ready[decoded_write] <= 1;
                    end
                end
            end

''' + src[end:]
    if onehot:
        import re
        slots = groups + int(pipeline)
        src = src.replace('    reg initialized;', f'reg [{slots-1}:0] phase_hot;\n    reg initialized;')
        marker = '    wire commit_step'
        src = src.replace(marker, f'''    always @(posedge clk) begin
        if (!resetn) phase_hot <= 1;
        else if (step_enable) phase_hot <= {{phase_hot[{slots-2}:0],phase_hot[{slots-1}]}};
    end
''' + marker)
        for lane in range(lanes):
            pattern = rf"        a_{lane}=0; b_{lane}=0; c_{lane}=0; d_{lane}=0;\n        case \(phase\).*?        endcase"
            old = re.search(pattern,src,re.S).group(0)
            assignments = dict(a=[],b=[],c=[],d=[])
            for phase in range(groups):
                dest=phase*lanes+lane
                if dest>=64: continue
                pred=dest//2;shift=(pred<<1)|(dest&1)
                label=''.join(str((shift&g).bit_count()&1) for g in (0o171,0o133))
                comp=''.join('1' if c=='0' else '0' for c in label)
                vals=[f'metric_shadow[{pred}]' if phase else f'metrics[{pred}]',f'metrics[{pred+32}]','bm'+label,'bm'+comp]
                for key,value in zip(assignments,vals):
                    width='METRIC_W' if key in ('a','b') else '9'
                    assignments[key].append(f'({{{{{width}{{phase_hot[{phase}]}}}}}} & {value})')
            new='\n'.join(f"        {key}_{lane} = "+' | '.join(vals)+';' for key,vals in assignments.items())
            src=src.replace(old,new)
        src=re.sub(r'(?<!init_)phase == (\d+)',lambda m:'phase_hot['+m[1]+']',src)
    if erasures:
        src=src.replace('    output reg         out_valid,', '    input wire [1:0] erasure,\n    output reg         out_valid,')
        first='phase_hot[0]' if onehot else '(phase == 0)'
        src=src.replace('    reg [7:0] soft0_q, soft1_q;', '    reg [7:0] soft0_q, soft1_q;\n    reg [1:0] erasure_q;\n    wire [1:0] active_erasure='+first+' ? erasure : erasure_q;')
        for i in range(4):
            a="{1'b0, "+('~' if i&2 else '')+'active_soft0}'
            b="{1'b0, "+('~' if i&1 else '')+'active_soft1}'
            src=src.replace(f'bm{i:02b} = {a} + {b};', f"bm{i:02b} = (active_erasure[1] ? 9'd0 : {a}) + (active_erasure[0] ? 9'd0 : {b});")
        src=src.replace('soft0_q <= 0; soft1_q <= 0;', 'soft0_q <= 0; soft1_q <= 0; erasure_q <= 0;')
        src=src.replace('soft0_q <= soft0; soft1_q <= soft1;', 'soft0_q <= soft0; soft1_q <= soft1; erasure_q <= erasure;')
    if registered_costs:
        if not (lanes == 16 and pipeline and compact_survivor and onehot and erasures):
            raise ValueError('registered costs supported for 16-lane packed pipelined erasure variant')
        import re
        src=src.replace('reg [4:0] phase_hot;', 'reg [5:0] phase_hot;')
        src=src.replace('{phase_hot[3:0],phase_hot[4]}', '{phase_hot[4:0],phase_hot[5]}')
        src=src.replace('wire commit_step = step_enable && (phase_hot[4]);', 'wire commit_step = step_enable && (phase_hot[5]);')
        src=re.sub(r'else if \(step_enable && phase_hot\[(\d+)\]\)', lambda m:'else if (step_enable && phase_hot['+str(int(m[1])+1)+'])',src)
        lines=[]
        for line in src.splitlines():
            if re.match(r'\s+[abcd]_\d+ = ',line):
                line=re.sub(r'phase_hot\[(\d+)\]',lambda m:'phase_hot['+str(int(m[1])+1)+']',line)
            line=re.sub(r"3'd(\d+): decision_partial",lambda m:"3'd"+str(int(m[1])+1)+': decision_partial',line)
            lines.append(line)
        src='\n'.join(lines)+'\n'
        src=src.replace('write_quadrant = phase - 1;', 'write_quadrant = phase - 2;')
        src=src.replace('phase >= 1 && phase < 5', 'phase >= 2 && phase < 6')
        start=src.index('    always @* begin\n        active_soft0')
        end=src.index('    wire [METRIC_W-1:0] result_0;',start)
        block=src[start:end]
        block=block.replace('always @* begin','always @(posedge clk) if (resetn && in_valid && in_ready) begin')
        block='\n'.join(line for line in block.splitlines() if not re.match(r'\s+active_soft[01] = ',line))+'\n'
        block=block.replace('active_erasure','erasure').replace('active_soft0','soft0').replace('active_soft1','soft1')
        block=re.sub(r'(bm[01]{2}) = ',r'\1 <= ',block)
        src=src[:start]+block+src[end:]
    if shift_output:
        src=src.replace('decoded[decoded_write][123-walk] <= state[0];', 'decoded[decoded_write] <= {decoded[decoded_write][62:0],state[0]};')
        src=src.replace('out_bit <= decoded[decoded_read][output_pos];', "out_bit <= decoded[decoded_read][0];\n                decoded[decoded_read] <= {1'b0,decoded[decoded_read][63:1]};")
    return src


if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lanes',type=int,choices=(16,22,32),required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--pipeline',action='store_true')
    p.add_argument('--compact-survivor',action='store_true')
    p.add_argument('--onehot',action='store_true')
    p.add_argument('--erasures',action='store_true')
    p.add_argument('--registered-costs',action='store_true')
    p.add_argument('--shift-output',action='store_true')
    a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(generate(a.lanes,a.pipeline,a.compact_survivor,a.onehot,a.erasures,a.registered_costs,a.shift_output))
