"""Recount packed FFT/K7/tile core after separating the CAD observation probe.
Usage: python ci/t_time_tile_packed_budget.py reports/shared-receiver-fft-tile-route
The directory's pack-command.json records the independent --pack-only command.
"""
import collections,gzip,hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ci.shared_receiver_fft_tile_evidence import FILES

def read(path):
 return json.loads(path.read_bytes() if path.exists() else gzip.decompress(Path(str(path)+'.gz').read_bytes()))
def main():
 p=Path(sys.argv[1]);m=read(p/'mapped.json')['modules']['shared_receiver_fft_tile_probe']['cells']
 regs={k for k,v in m.items()if v['type'].startswith('DFF') and FILES[-1] in v.get('attributes',{}).get('src','')}
 r=read(p/'packed.json')['modules']['top']['cells']
 h={k:v for k,v in r.items()if k in regs or k.startswith('digest') or k.removesuffix('_passthrough_lut$')in regs}
 a={k:v for k,v in r.items()if k not in h}
 counts=lambda x:dict(collections.Counter(v['type']for v in x.values()))
 ac,hc,tc=counts(a),counts(h),counts(r)
 logic=lambda c:sum(v for k,v in c.items()if re.fullmatch('LUT[1-4]|ALU',k))
 ff=lambda c:sum(v for k,v in c.items()if k.startswith('DFF'))
 assert ff(hc)==len(regs),(ff(hc),len(regs))
 result=dict(scope='Packed physical primitives, observation probe excluded. Not placed or routed. Gate applies only to this mapped candidate.',core_cells=ac,harness_cells=hc,total_cells=tc,harness_registers=len(regs),logic_with_ram_blockers=logic(ac)+4*ac.get('RAM16SDP4',0),FF_sites_with_ram_blockers=ff(ac)+6*ac.get('RAM16SDP4',0),logic_capacity=20736,whole_receiver_verified=False,source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()for f in FILES+['ci/shared_receiver_fft_tile_evidence.py','ci/t_time_tile_packed_budget.py']})
 result['logic_excess']=result['logic_with_ram_blockers']-20736
 (p/'packed-budget.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items()if not k.endswith('cells')and k!='source_sha256'}))
if __name__=='__main__':main()
