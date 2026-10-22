"""Recompute receiver-buffer experiment results, preserving failed candidates."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(name):
 p=ROOT/name;d=json.loads(p.read_text())
 for f,h in d.get('source_sha256',{}).items():
  assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h,f
 return d

def main():
 paths=[];rows=[]
 for variant in ['heldearly','sharedhold','onehot']:
  f=f'reports/t-time-tile-dma-{variant}-full.json';paths.append(f);sim=read(f)
  pack='compact-bram-probe' if variant=='heldearly'else variant
  f=f'reports/shared-receiver-fft-tile-{pack}-pack/packed-budget.json';paths.append(f);budget=read(f)
  assert sim['checked_output_words']==119808 and sim['checked_writes']==29796
  t=next(c for c in sim['clients']if c['id']==2)
  rows.append(dict(variant=variant,full_fixture=budget['full'],TTI_finish=t['finish'],TTI_margin=2566080-t['finish'],all_declared_deadlines_pass=sim['all_declared_deadlines_pass'],clients=sim['clients']))
 assert rows[0]['clients']==rows[2]['clients']
 assert not rows[1]['all_declared_deadlines_pass'] and rows[1]['full_fixture']['excess']>0
 assert rows[2]['full_fixture']['optimistic_logic_site_lower_bound']==19404
 routes=[]
 for suffix in ['route','prebuffer-route']:
  f=f'reports/shared-receiver-fft-tile-onehot-{suffix}/summary.json';paths.append(f);r=read(f)
  assert r['pnr_exit']==125 and not r['route_completed']
  routes.append(dict(condition=suffix,exit=r['pnr_exit'],route_completed=r['route_completed'],errors=r['errors']))
 for suffix in ['offsets','contract']:
  f=f'reports/t-time-tile-dma-onehot-{suffix}.json';paths.append(f);d=read(f)
  assert d['checked_output_words']==2304 and d['checked_writes']==573
  assert d['byte_offsets']==list(range(0,32,2)) and d['delay_classes']==96
 result=dict(rows=rows,routes=routes,whole_receiver_verified=False,formal_adoptions=0,configuration_1='stopped',
  notes=['LUT-site bounds include unchanged compact BRAM observation fixture; not actual routed occupation.',
   'Onehot finite schedule and values pass; integrated legal placement and Fmax remain unverified.',
   'Sharedhold rejected before P&R due to deadline and fixed-netlist bound.',
   'Initial onehot generator SyntaxError occurred before RTL files were created; resulting missing-module/missing-file invocations were rerun after correction.'],
  evidence_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()for f in paths},
  collector_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 (ROOT/'reports/continuation-20261021h.json').write_text(json.dumps(result,indent=2)+'\n')
 print('PASS: source hashes, complete comparison, rejection gates, two placement failures')
if __name__=='__main__':main()
