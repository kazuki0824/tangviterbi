"""Exact zero-weight erased branches for the proven binary traceback engine."""
from s3_viterbi_traceback import generate

def source():
 s=generate('modulo13-pipe').replace('module s3_viterbi_traceback','module s3_viterbi_erasure')
 s=s.replace('    output reg         out_valid,', '    input wire [1:0] erasure,\n    output reg         out_valid,')
 s=s.replace('    reg [7:0] soft0_q, soft1_q;', '    reg [7:0] soft0_q, soft1_q;\n    reg [1:0] erasure_q;\n    wire [1:0] active_erasure=phase?erasure_q:erasure;')
 for i in range(4):
  a=('{1\'b0, '+('~' if i&2 else '')+'active_soft0}')
  b=('{1\'b0, '+('~' if i&1 else '')+'active_soft1}')
  s=s.replace(f'bm{i:02b} = {a} + {b};',f'bm{i:02b} = (active_erasure[1] ? 9\'d0 : {a}) + (active_erasure[0] ? 9\'d0 : {b});')
 s=s.replace('soft0_q <= 0; soft1_q <= 0;', 'soft0_q <= 0; soft1_q <= 0; erasure_q<=0;')
 s=s.replace('soft0_q <= soft0; soft1_q <= soft1;', 'soft0_q <= soft0; soft1_q <= soft1; erasure_q<=erasure;')
 return s
if __name__=='__main__':print(source())
