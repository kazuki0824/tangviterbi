"""Verify dynamic diagnostic evidence and the limited control-fold transformation."""
import copy,gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(f):
 p=ROOT/f
 if not p.exists():p=Path(str(p)+'.gz')
 d=json.loads(gzip.decompress(p.read_bytes())if p.suffix=='.gz'else p.read_bytes())
 if isinstance(d,dict):
  for name,h in d.get('source_sha256',{}).items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
 return d

def main():
 normal=read('reports/placement-dynamic-audit/comparison.json');pre=read('reports/placement-dynamic-prebuffer/comparison.json');fold=read('reports/placement-dynamic-folded-controls/summary.json')
 assert normal['same_failure']and pre['same_failure']and fold['same_failure_as_official']
 root='reports/shared-receiver-fft-tile-folded-controls-route/'
 original=read('reports/shared-receiver-fft-tile-onehot-prebuffer-route/mapped.json.gz');changed=read(root+'mapped.json.gz');proof=read(root+'mapped.controls-proof.json')
 assert proof['transform_sha256']==hashlib.sha256((ROOT/'ci/gowin_fold_identity_controls.py').read_bytes()).hexdigest()
 restored=copy.deepcopy(changed);cells=changed['modules']['shared_receiver_fft_tile_probe']['cells'];ports=changed['modules']['shared_receiver_fft_tile_probe']['ports']
 for r in proof['records']:
  f,l=cells[r['ff']],cells[r['lut']];old=r['original_ff'];reset=old['type']=='DFFRE'
  assert f['type']=='DFF' and f['parameters']==old['parameters']
  assert l['type']==('LUT4'if reset else'LUT3')and int(l['parameters']['INIT'],2)==0xac
  assert all(l['connections']['F'][0]not in p['bits']for p in ports.values())
  restored['modules']['shared_receiver_fft_tile_probe']['cells'][r['ff']]=old
  restored['modules']['shared_receiver_fft_tile_probe']['cells'][r['lut']]=r['original_lut']
 assert restored==original and len(proof['records'])==2393
 gate=read(root+'placement-gate.json');assert gate['full']['optimistic_logic_site_lower_bound']==19404
 assert gate['control']['control_groups']==226
 summary=read(root+'summary.json');assert summary['pnr_exit']==125 and not summary['route_completed']
 rows=[]
 for name,r in [('normal',normal['runs']['instrumented']),('prebuffer',pre['runs']['instrumented']),('folded_controls',fold)]:
  rows.append(dict(name=name,exit=r['exit'],target_rejections={k:v['target']for k,v in r['counters'].items()},all_rejections={k:v['all']for k,v in r['counters'].items()}))
 out=dict(rows=rows,control_fold_count=2393,graph_restored_exactly=True,no_changed_LUT_net_is_top_port=True,whole_receiver_verified=False,formal_adoptions=0,configuration_1='stopped',scope='Counts are first rejection per slice_valid call, not unique sites/cells or proof of global infeasibility.',collector_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 (ROOT/'reports/continuation-20261022.json').write_text(json.dumps(out,indent=2)+'\n');print('PASS: source hashes, consistent failures, transformation graph and scope')
if __name__=='__main__':main()
