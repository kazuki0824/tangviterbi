"""FPGA-only branch-cost precision experiments; not lossless vs SHIFT22.

Native RF transfer and Q15 symbol inputs are unchanged. The new rounding is
inside the FPGA, never an extra SoC quantizer used to fit a link bandwidth.
Arithmetic is exact for each selected quantizer, but BER equivalence with the
old quantizer is NOT implied. This is an experimental, unadopted candidate.
"""
from pathlib import Path
from s3_tc8psk import source as tc_source
from s3_tc8psk_metric_bound import bound as original_bound
ROOT=Path(__file__).resolve().parents[1]
def bound(shift):
 if shift not in (22,23,24,25):raise ValueError('unsupported precision experiment')
 old=original_bound();q=1<<shift
 delta={0:0,**{k:(v+q-1)//q for k,v in old['absolute_projection_difference_bounds'].items()}}
 b=sum(delta[x] for x in old['encoder_impulse_label_xor'])
 width=b.bit_length()+1
 # Largest absolute projection on the complete signed-Q15 input square.
 maximum_projection=65536*23170
 maximum_cost=(maximum_projection+(q>>1))>>shift
 return dict(cost_shift=shift,branch_cost_bits=maximum_cost.bit_length(),maximum_cost=maximum_cost,
  rounded_branch_difference_bounds=delta,merging_candidate_difference_bound=b,
  metric_width=width,half_modulus=1<<(width-1),
  geometric_vertices=old['vertices'],absolute_projection_difference_bounds=old['absolute_projection_difference_bounds'],
  encoder_impulse_label_xor=old['encoder_impulse_label_xor'],
  native_RF_precision_changed=False,Q15_symbol_precision_changed=False,
  FPGA_branch_cost_quantization_changed=shift!=22,BER_equivalence_to_shift22_verified=False,
  receiver_adopted=False)
def metric_source(shift):
 b=bound(shift);bits=b['branch_cost_bits']
 s=(ROOT/'rtl/s3_tc8psk_metric_folded.sv').read_text()
 s=s.replace('parameter COST_SHIFT=22',f'parameter COST_SHIFT={shift}')
 s=s.replace('COST_SHIFT<1 || COST_SHIFT>30',f'COST_SHIFT!={shift}')
 # The full input-domain projection bound proves these upper bits are zero.
 # Explicit narrowing makes that fact visible to synthesis, not merely to us.
 narrowed='rounded[8:0]' if bits==9 else f"{{{9-bits}'d0,rounded[{bits-1}:0]}}"
 s=s.replace("quantize=rounded>511?9'd511:rounded[8:0];",f"quantize={narrowed};")
 s=s.replace('// No input decimation or new quantization.',
  '// Native input is unchanged; FPGA branch-cost rounding precision is changed.')
 return f'// Experimental FPGA SHIFT{shift} cost quantizer; BER must be checked separately.\n'+s
def viterbi_source(shift,lanes=32):
 b=bound(shift);width=b['metric_width']
 s=tc_source(True,True,lanes,True)
 s=s.replace('COST_SHIFT=22',f'COST_SHIFT={shift}').replace('Q15/SHIFT22',f'Q15/SHIFT{shift}')
 s=s.replace('parameter integer METRIC_W = 12',f'parameter integer METRIC_W = {width}')
 s=s.replace('METRIC_W != 12',f'METRIC_W != {width}').replace('12-bit modulo contract',f'{width}-bit modulo contract')
 return s
if __name__=='__main__':
 import json
 print(json.dumps({shift:bound(shift) for shift in (22,23,24,25)},indent=2))
