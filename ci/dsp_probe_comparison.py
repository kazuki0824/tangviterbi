"""Collect fixture experiments without treating a necessary bound as placement."""
import gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text())
def main():
 rows=[];paths=[]
 for name in ['dsp-probe','compact-dsp-probe','compact-dsp-probe-sa','compact-bram-probe','compact-bram-probe-prebuffer','compact-bram-probe-prebuffer-sa']:
  p=f'reports/shared-receiver-fft-tile-{name}-route';summary=read(p+'/summary.json');gate=read(p+'/placement-gate.json');full=gate.get('full',gate)
  for f,digest in summary['source_sha256'].items():assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==digest,f
  assert not summary['route_completed']
  rows.append(dict(variant=name,bound=full['optimistic_logic_site_lower_bound'],margin=-full['excess'],pnr_exit=summary['pnr_exit'],route_completed=False,errors=summary['errors'],source_hashes_verified=True))
  paths.extend([p+'/summary.json',p+'/placement-gate.json',p+'/command.json'])
  if 'prebuffer'in name:
   proof=read(p+'/mapped.identity-proof.json');assert proof['original_graph_restored_exactly']and proof['identity_truth_table_verified'];assert proof['inserted_count']==2900
   paths.append(p+'/mapped.identity-proof.json')
 contract=read('reports/dsp-probe-contract.json')
 for f,digest in contract['source_sha256'].items():assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==digest,f
 paths.extend(['reports/dsp-probe-contract.json','reports/dsp-scan-probe-tests.log','reports/compact-dsp-scan-probe-tests.log','reports/bram-observation-probe-tests.log','reports/gowin-materialize-ff-inputs-tests.log'])
 result=dict(scope=__doc__,rows=rows,configuration_1_stopped=True,formal_receiver_adoptions=0,whole_receiver_verified=False,
  unchanged_receiver_core_netlists=contract['standalone_core_netlists_identical'],physical_capacity=dict(LUT=20736,FF=15552,BSRAM=46,MULT18=48),
  input_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in paths},collector_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 (ROOT/'reports/continuation-20261021g.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
