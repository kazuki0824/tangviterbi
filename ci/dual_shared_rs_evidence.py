#!/usr/bin/env python3
"""Reproduce GW2A synthesis of the corrected three-stream RS wrapper.

No P&R/STA claim. Uses the caller's Yosys version and records it. Direct mapped
FF-driver matching is only a necessary site bound; it ignores legal packing.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from s3_rs_isdb import source

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def characterize(path):
    net=json.loads(path.read_text());cells=net['modules']['dual_shared_rs']['cells']
    types=Counter(c['type'] for c in cells.values());drivers={}
    for name,c in cells.items():
        for port,bits in c['connections'].items():
            if c['port_directions'][port]=='output':
                for bit in bits:drivers[bit]=(name,c['type'],port)
    shared=set();lut=sum(types[t] for t in ('LUT1','LUT2','LUT3','LUT4'))
    ff=sum(v for t,v in types.items() if t.startswith('DFF'))
    for c in cells.values():
        if c['type'].startswith('DFF'):
            d=drivers.get(c['connections']['D'][0],('','',''))
            if (d[1] in ('LUT1','LUT2','LUT3','LUT4') and d[2]=='F') or (d[1]=='ALU' and d[2]=='SUM'):
                shared.add(d[0])
    return dict(tool=net['creator'],mapped_cell_counts=dict(types),LUT=lut,ALU=types['ALU'],FF=ff,
                BSRAM=sum(types[t] for t in ('SPX9','DPX9B','SDPX9B','SP','DP','SDP')),
                maximum_possible_FF_driver_pairs=len(shared),
                necessary_logic_sites=lut+types['ALU']+ff-len(shared),
                mapped_netlist_sha256=digest(path),
                placed=False,timing_verified=False)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--yosys',default='yosys');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();b=ROOT/'build/dual-shared-rs-evidence';b.mkdir(parents=True,exist_ok=True)
    rows=[]
    for compact in (True,False):
        tag='BRAM_tables' if compact else 'register_tables'
        rtl=b/f'{tag}.sv';net=b/f'{tag}.json';log=b/f'{tag}.log'
        rtl.write_text(source(True,compact))
        script=b/f'{tag}.ys'
        script.write_text(f'read_verilog -sv {ROOT}/rtl/dual_shared_rs.sv {rtl}\n'
                          f'synth_gowin -top dual_shared_rs -family gw2a -nowidelut -json {net}\ncheck -assert\nstat\n')
        run=subprocess.run([a.yosys,'-Q','-l',str(log),'-s',str(script)],capture_output=True,text=True,timeout=180)
        if run.returncode:raise RuntimeError(run.stderr+run.stdout[-2000:])
        if 'End of script.' not in log.read_text():raise RuntimeError('incomplete synthesis log')
        rows.append(dict(implementation=tag,decoder_sha256=digest(rtl),synthesis_log_sha256=digest(log),**characterize(net)))
    result=dict(wrapper_sha256=digest(ROOT/'rtl/dual_shared_rs.sv'),implementations=rows,
        qualification='Standalone mapped netlists only. Queues/SDRAM/serializer excluded. Necessary site bound is not legal placement or Fmax.')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
