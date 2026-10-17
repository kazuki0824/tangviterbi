"""Necessary arithmetic only: NOT complete FFT RTL or receiver validation."""
from math import ceil
import json
MODES={1:(2048,259.875),2:(4096,519.750),3:(8192,1039.500)}
def mode_screen(mode):
    n,p=MODES[mode]
    hold=13*96*(1<<(mode-1))*6
    internal=min(n-1,4095)
    external=n-1-internal
    return dict(mode=mode,n=n,period_us=p,hold_bytes=hold,
        all_sdf_delay_bytes=(n-1)*4,all_sdf_bsram_min=ceil((n-1)*4/2048),
        hybrid_internal_bytes=internal*4,hybrid_bsram_min=ceil(internal*4/2048),
        hybrid_external_bytes=external*4,
        external_stage_MBps=2*n*4/(p*1e-6)/1e6 if external else 0,
        hold_spill_MBps=2*hold/(p*1e-6)/1e6)
def report():
    m=mode_screen(3)
    base=271.266-189.137
    return dict(receiver_adopted=False,full_sta=None,
      native_s3_rf_verified=None,fft_output_order_verified=None,
      modes=[mode_screen(i) for i in MODES],
      candidates=[
       dict(name="old_tile",bsram_budget=44,traffic_MBps=271.266,qualified=False),
       dict(name="all_onchip_sdf_ideal",bsram_budget=52,traffic_MBps=base,qualified=False),
       dict(name="hybrid_sdf_ideal",bsram_budget=44,traffic_MBps=base+m["external_stage_MBps"],qualified=False),
       dict(name="hybrid_plus_hold_spill_ideal",bsram_budget=29,traffic_MBps=base+m["external_stage_MBps"]+m["hold_spill_MBps"],qualified=False)])
if __name__=="__main__":
    print(json.dumps(report(),indent=2))
