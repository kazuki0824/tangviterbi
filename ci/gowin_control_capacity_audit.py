"""Necessary aggregate bounds only; neither placement proof nor root-cause proof."""
import collections,gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PAIRS=[('DFFS','DFFR'),('DFFSE','DFFRE'),('DFFP','DFFC'),('DFFPE','DFFCE'),('DFFNS','DFFNR'),('DFFNSE','DFFNRE'),('DFFNP','DFFNC'),('DFFNPE','DFFNCE')]
TYPES={t:a for a,b in PAIRS for t in [a,b]}
def signature(cell):
 p=cell['connections']
 lsr=next((tuple(p[k])for k in ['SET','RESET','PRESET','CLEAR']if k in p),())
 return (TYPES.get(cell['type'],cell['type']),tuple(p.get('CLK',[])),tuple(p.get('CE',[])),lsr)
def audit(cells):
 ffs={n:c for n,c in cells.items()if c['type'].startswith('DFF')}
 groups=collections.Counter(signature(c)for c in ffs.values())
 demand=collections.Counter(c['connections']['D'][0]for c in ffs.values())
 alus=[c for c in cells.values()if c['type']=='ALU']
 supply=collections.Counter(c['connections']['SUM'][0]for c in alus if c['connections'].get('SUM'))
 paired=sum(min(n,demand[net])for net,n in supply.items())
 ram=sum(c['type']=='RAM16SDP4'for c in cells.values())
 # 6 FF/ALU slots per tile on this fixed device; RAM blocks all six.
 constrained=len(ffs)+len(alus)-paired+6*ram
 return dict(FF=len(ffs),control_groups=len(groups),odd_groups=sum(n%2 for n in groups.values()),
  control_pair_slot_lower_bound=sum(2*((n+1)//2)for n in groups.values()),
  control_pair_slots_with_RAM=sum(2*((n+1)//2)for n in groups.values())+6*ram,
  ALU=len(alus),maximum_ALU_FF_pairings_ignoring_control=paired,RAM16SDP4=ram,
  six_slice_lower_bound=constrained,six_slice_capacity=15552,six_slice_headroom=15552-constrained,
  failed_FF_group_size=groups[signature(ffs['dut.fft.in_valid_DFFRE_Q'])] if 'dut.fft.in_valid_DFFRE_Q'in ffs else None,
  full_group_histogram=sorted(collections.Counter(groups.values()).items()),
  scope=__doc__)
def main():
 result={}
 for variant in ['compact-bram-probe','onehot']:
  p=ROOT/f'reports/shared-receiver-fft-tile-{variant}-pack/packed.json.gz'
  c=json.loads(gzip.decompress(p.read_bytes()))['modules']['top']['cells']
  result[variant]=audit(c);result[variant]['input_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
 source=ROOT/'reports/placement-control-audit'
 result['backend']=dict(commit='e2fe86b3ce6feaa3f09d8db5c0971c1cda3fc641',sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in source.glob('*.cc')})
 result['auditor_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 (source/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 for v in ['compact-bram-probe','onehot']:print(v,{k:x for k,x in result[v].items()if k not in ['full_group_histogram','input_sha256','scope']})
if __name__=='__main__':main()
