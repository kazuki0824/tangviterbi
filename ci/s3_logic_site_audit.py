#!/usr/bin/env python3
"""Necessary logic-site bound for a packed, narrow-LUT Gowin netlist.

Pinned nextpnr e2fe86b3, GowinImpl::slice_valid: a real FF sharing a site
with a LUT/ALU must have D connected to that cell's F/SUM net. Each such
driver can share its site with at most one FF. All other FFs need an empty
logic site (postPlace inserts a pass-through LUT there). Ignoring controls,
adjacency and the 6-of-8 FF/ALU restriction only makes this bound optimistic.

BLOCKER_LUT cells are placeholders for ALUs and must NOT be counted twice.
The final routed report removes those placeholders: its LUT4 and ALU counts
must be added for occupied logic positions. This is a necessary bound for
THIS mapped netlist/tool, not a lower bound on every implementation of RTL.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

PRIMARY_SOURCE='https://github.com/YosysHQ/nextpnr/blob/e2fe86b3/himbaechel/uarch/gowin/gowin.cc'
LUTS={'LUT1','LUT2','LUT3','LUT4'}

def audit(path,capacity=8640):
    raw=path.read_bytes();design=json.loads(raw)
    modules=design['modules']
    if set(modules)!={'top'}:raise ValueError('expected nextpnr packed top')
    cells=modules['top']['cells'];types=Counter(c['type'] for c in cells.values())
    # Wide LUT outputs and distributed memories require another matching
    # model. Refuse to overstate this restricted proof's coverage.
    excluded=[t for t in types if t.startswith('MUX2_LUT') or t.startswith('RAM16') or t=='BLOCKER_FF']
    if excluded:raise ValueError('unsupported site-sharing primitives: '+str(excluded))
    drivers={}
    for name,c in cells.items():
        for p,bits in c['connections'].items():
            if c['port_directions'][p]=='output':
                for bit in bits:
                    if bit in drivers:raise ValueError('multiply driven net')
                    drivers[bit]=(name,c['type'],p)
    logic=sum(types[t] for t in LUTS);alu=types['ALU'];ff=0;shared=set();inputs=Counter()
    for name,c in cells.items():
        if c['type'].startswith('DFF'):
            ff+=1
            d=drivers.get(c['connections']['D'][0],('external','external','external'))
            inputs[d[1]]+=1
            if (d[1] in LUTS and d[2]=='F') or (d[1]=='ALU' and d[2]=='SUM'):
                shared.add(d[0])
    if types['BLOCKER_LUT']!=alu:raise ValueError('unexpected packed ALU blocker accounting')
    bound=logic+alu+ff-len(shared)
    return dict(packed_json_sha256=hashlib.sha256(raw).hexdigest(),
        LUT_cells=logic,ALU_cells=alu,ALU_blockers_excluded=types['BLOCKER_LUT'],
        fabric_FFs=ff,maximum_LUT_or_ALU_FF_pairs=len(shared),
        minimum_additional_FF_sites=ff-len(shared),
        minimum_required_logic_sites=bound,available_logic_sites=capacity,
        minimum_site_utilization_percent=bound*100/capacity,
        minimum_site_deficit=max(0,bound-capacity),
        mapped_netlist_ruled_out=bound>capacity,
        FF_D_driver_types=dict(inputs),reference=PRIMARY_SOURCE,
        limitations=['narrow LUT mapping only','no retiming/resynthesis/transformation allowed in this bound',
                    'passing this bound does not prove placement or timing','CE/reset/clock/adjacency restrictions ignored'])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('packed_json',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=audit(a.packed_json)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
