"""Arithmetic for a lower common core clock; not a PLL/receiver qualification."""
from fractions import Fraction as F
import json

def run():
 clock=F(1080,7);t=F(4992*6*7,8)/F('1039.5');s=F('28.86')*2*F(7,8);k=2*(t+s)
 t_rs=t*1000000/(204*8);s_rs=F('28.86')*1000000*2/(203*8);tmcc=F('28.86')*1000000/(39936*8)
 # Preserve dual_s3_deadlines.py's wrapper + decoder interval, not bare 2667.
 rs=(t_rs+s_rs+tmcc)*2672/1000000
 return dict(core_MHz=float(clock),memory_MHz=135,PLL_count_hypothesis=2,
  PLL_placement_verified=False,PLL_lock_verified=False,
  pll_parameters=dict(FCLKIN=27,IDIV_SEL=6,FBDIV_SEL=39,ODIV_SEL=4,PFD_MHz=float(F(27,7)),VCO_MHz=float(clock*4)),
  K7_required_MHz=float(k),K7_arithmetic_utilization_percent=float(100*k/clock),K7_extra_Mclock_s=float(clock-k),
  FFT_active_required_MHz=float(13*F(512,63)),FFT_active_utilization_percent=float(100*13*F(512,63)/clock),
  shared_RS_mean_required_MHz=float(rs),shared_RS_mean_utilization_percent=float(100*rs/clock),
  RS_cycles=2672,RS_service_us=float(F(2672)/clock),
  warning='Arithmetic necessary conditions only. Recompute bus traces/CDC/WCET at new frequency. Previous 162MHz schedule not transferable. PLL table says untested; calculator warns it cannot decipher GW2AR name although parameters match requested frequency.')
if __name__=='__main__':print(json.dumps(run(),indent=2))
