"""Verify completed folded router1 result and distinguish physical slots from report LUTs."""
import collections,gzip,hashlib,json,math
from pathlib import Path
from ci.gowin_ff_site_audit import audit
R=Path(__file__).resolve().parents[1];d=R/'reports/placement-compatible-pairs-folded-extended'
def read(n):return json.loads(gzip.decompress((d/(n+'.gz')).read_bytes()))
t=read('pnr.json');net=read('routed.json');c=next(iter(net['modules'].values()))['cells'];r=json.loads((d/'result.json').read_text());assert r['route_completed'] and r['exit']==1
log=(d/'route.log').read_text();assert 'Routing complete.'in log
f=t['fmax']['dut.clk']['achieved'];a=audit(c);assert a['packed_logic_with_ram_blockers']==19423 and a['FF']==8662
path=t['critical_paths'][0]['path'];s=collections.Counter()
for arc in path:s[arc['type']]+=arc['delay']
assert math.isclose(1000/sum(s.values()),f,rel_tol=1e-6)
counts=collections.Counter(v['type']for v in c.values());lut_only=sum(counts[k]for k in ('LUT1','LUT2','LUT3','LUT4'))
assert lut_only==t['utilization']['LUT4']['used']==15411
assert lut_only+counts['ALU']+4*counts['RAM16SDP4']==19423
out={'route_completed':True,'routed_MHz':f,'target_MHz':1080/7,'target_pass':f>=1080/7,'K7_stall_free_minimum_MHz':152.626638,'K7_minimum_pass':f>=152.626638,'required_period_reduction_ns':sum(s.values())-1000/(1080/7),'path_delay_ns_by_type':dict(s),'launch':path[0]['from'],'capture':path[-1]['to'],'logic_stages':sum(x['type']=='logic'for x in path),'physical_site_audit':a,'reported_LUTs_without_removed_blockers':lut_only,'ALU_positions':counts['ALU'],'RAM_extra_blocked_LUT_positions':4*counts['RAM16SDP4'],'whole_receiver_verified':False,'sha256':{n:hashlib.sha256(gzip.decompress((d/(n+'.gz')).read_bytes())).hexdigest()for n in ('pnr.json','routed.json')}}
assert not out['target_pass'] and not out['K7_minimum_pass']
(d/'audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
