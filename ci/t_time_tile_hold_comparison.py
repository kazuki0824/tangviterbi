"""Collect measured hold-lifetime experiments; no deadline inferred from unittest exit."""
import gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text())
def main():
 rows=[];inputs=[]
 for name,test in [('aligned','aligned'),('noalu','aligned'),('firstwrite','firstwrite'),('held','held'),('heldearly','heldearly'),('held-grace16','held-grace16')]:
  p=f'reports/shared-receiver-fft-tile-{name}-pack'
  audit=f'{p}/ff-site-audit.json';gate=f'{p}/placement-gate.json';budget=f'{p}/packed-budget.json'
  data=f'reports/t-time-tile-dma-{test}-full.json'
  a,g,b,d=map(read,(audit,gate,budget,data));inputs.extend([audit,gate,budget,data])
  for evidence in [b,d]:
   for path,digest in evidence['source_sha256'].items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,path
  c=a['core_without_probe'];t=next(x for x in d['clients']if x['id']==2)
  rows.append(dict(variant=name,RTL_test_reused=name=='noalu',core=c,probe_inclusive=a['full_with_probe'],placement_gate=g['exit_code'],TTI_finish=t['finish'],TTI_margin=2566080-t['finish'],finite_deadlines_pass=d['all_declared_deadlines_pass'],data_words=d['checked_output_words'],writes=d['checked_writes'],source_hashes_verified=True))
 standalone={}
 for name in ['held','heldearly','heldearly-seed2']:
  p=f'reports/t-time-tile-dma-{name}-route/summary.json';d=read(p);inputs.append(p)
  for path,digest in d['source_sha256'].items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,path
  standalone[name]={k:d[k]for k in ['route_completed','partial_target_pass','logic_with_ram_blockers','FF_sites_with_ram_blockers','fmax','BSRAM']}
 for name in ['firstwrite','held','heldearly']:
  p=f'reports/t-time-tile-dma-{name}-offsets.json';d=read(p);inputs.append(p)
  for path,digest in d['source_sha256'].items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,path
  assert d['checked_output_words']==2304 and d['checked_writes']==573
 seed_maps=[f'reports/t-time-tile-dma-{n}-route/mapped.json.gz'for n in ['heldearly','heldearly-seed2']]
 assert json.loads(gzip.decompress((ROOT/seed_maps[0]).read_bytes()))==json.loads(gzip.decompress((ROOT/seed_maps[1]).read_bytes()))
 inputs.extend(seed_maps)
 result=dict(early_seed_maps_identical=True,scope=__doc__,rows=rows,standalone=standalone,formal_receiver_adoptions=0,configuration_1_stopped=True,whole_receiver_verified=False,
  input_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in inputs},collector_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 (ROOT/'reports/continuation-20261021f.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
