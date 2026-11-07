"""Conditional engineering estimate, not measured ranges or confidence intervals."""
import json
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B=32768

def capacity(gap_us):
    return sum(B/(wire+gap_us) for wire in (409.725,819.45))

def report():
    paths=['reports/s3-pack-span/cfg/results.json',
           'reports/partition-recheck-20261023/recomputed-k7-resource-variants.json']
    rows=json.loads((ROOT/paths[0]).read_text())['rows']
    scenarios=[('light',1.0,10,10,5,20),('planning',1.1,20,20,10,80),
               ('stress',1.25,40,30,15,160)]
    cpu=[]
    for standard,rate in [('T',16),('S',40)]:
        pack=[]
        for worker in (0,1):
            values=[r['ideal_one_cycle_per_instruction_Mcycles_s'] for r in rows
                    if r['standard']==standard and r['worker']==worker and r['slice_pairs']==512]
            pack.append((min(values),max(values)))
        # Max nominal steady-state fill frequency under >=12288 samples/bank.
        # First bank may be shorter and is a separate transient obligation.
        fill=21574*rate/12288
        payload=rate*2.5
        for name,alpha,A,U0,U1,G in scenarios:
            api=payload*240*A/B
            ranges=[[(p+fill)*alpha+api+U0 for p in pack[0]],
                    [p*alpha+U1 for p in pack[1]]]
            cpu.append(dict(standard=standard,scenario=name,alpha=alpha,
                API_active_us_per_chunk=A,unclassified_Mcycles_s=[U0,U1],
                packing_Minstructions_s=pack,fill_Minstructions_s=fill,
                core_Mcycles_s=ranges,core_percent=[[v/2.4 for v in a] for a in ranges],
                core0_upper_margin_Mcycles_s=240-ranges[0][1],
                hypothetical_packing_shift_Mcycles_s_open_interval=[max(0,ranges[0][1]-240),240-ranges[1][1]],
                hypothetical_balanced_upper_core_percent=sum(a[1] for a in ranges)/4.8,
                max_unclassified_core0_at_alpha1_A20=240-pack[0][1]-fill-payload*240*20/B,
                confidence_interval=False))
    lo,hi=0.,1000.
    for _ in range(80):
        mid=(lo+hi)/2
        if capacity(mid)>=100:lo=mid
        else:hi=mid
    ledger=json.loads((ROOT/paths[1]).read_text())
    selected=next(c for c in ledger['cases'] if c['trial']=='slotaddr-154')
    assert all(selected['R_H_replacement'][k]==ledger['base_without_both_K7'][k]+selected['kernel'][k]
               for k in ledger['base_without_both_K7'])
    area=selected['R_H_replacement'];caps=dict(logic_sites_estimate=20736,FF=15552,BSRAM=46,DSP18=48)
    return dict(scope=__doc__,cpu=cpu,
        links=[dict(gap_us=g,S_MBps=capacity(g),S_spare_MBps=capacity(g)-100,
                    T_octal_MBps=B/(409.725+g),T_spare_MBps=B/(409.725+g)-40)
               for g in (0,20,40,80,160)],
        max_equal_gap_us_for_S_payload=lo,
        FPGA=dict(whole_stage_ledger=area,capacity=caps,
            net_delta_budget={k:caps[k]-area[k] for k in caps},
            logic_growth_scenarios=[dict(net_growth_pct=x,sites=area['logic_sites_estimate']*(1+x/100),
                occupancy_pct=area['logic_sites_estimate']*(1+x/100)/20736*100) for x in (0,2,5,10)],
            partial_Fmax_MHz=152.091263,
            minimum_K7_MHz=2*(25.212121+50.505)*128/127,
            design_target_MHz=1080/7,
            whole_path_scenarios=[dict(net_path_change_ns=d,Fmax_MHz=1000/(1000/152.091263+d))
                                  for d in (-.1,0,.1,.25,.5)],
            standalone_kernel_MHz=156.76437377929688,
            whole_PnR_verified=False),
        source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
        receiver_adopted=False)

if __name__=='__main__':
    out=ROOT/'reports/receiver-estimate-20261027';out.mkdir(parents=True,exist_ok=True)
    (out/'estimate.json').write_text(json.dumps(report(),indent=2)+'\n')
