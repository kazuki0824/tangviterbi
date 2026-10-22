"""Exact payload counts for retaining transmitted soft bytes before depuncture.
No claim about SDRAM service, signal arrival burst or address lifetime.
"""
from fractions import Fraction as F
import json

def run():
 rows=[]
 for mode in (1,2,3):
  for bits in (2,4,6):
   soft=13*96*(2**(mode-1))*bits
   for rate in (F(1,2),F(2,3),F(3,4),F(5,6),F(7,8)):
    steps=soft*rate
    assert steps.denominator==1
    rows.append(dict(mode=mode,bits_per_carrier=bits,rate=str(rate),transmitted_soft_bytes=soft,steps=int(steps),expanded_pair_bits=int(steps)*18))
 maximum=max(rows,key=lambda r:r['expanded_pair_bits'])
 period=F('1039.5')
 payload=F(29952)/period
 return dict(scope=__doc__,rows=rows,maximum=maximum,
  T_max_symbol_soft_bytes=29952,T_double_buffer_soft_bytes=59904,
  T_max_soft_MBps=float(payload),
  T_extra_full_spill_read_write_MBps=float(2*payload),
  S_QPSK_soft_MBps=57.72,
  combined_max_input_soft_MBps=float(payload+F('57.72')),
  source_soft_precision_bits=8,quantization_or_decimation_changed=False,
  double_buffer_allocated_in_actual_memory_map=False,
  source_ring_lifetime_proven=False,all_client_SDRAM_deadlines_verified=False,
  instruction='Do not alias a deinterleaver ring after it is overwritten. Prove read lifetime or allocate/cost an output buffer. These counts do not certify physical memory service.')
if __name__=='__main__':print(json.dumps(run(),indent=2))
