"""Collect completed buffer experiments without promoting partial success to receiver feasibility."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(name):
 p=ROOT/name;d=json.loads(p.read_text())
 for f,h in d.get('source_sha256',{}).items():
  assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h,(name,f)
 return d

def main():
 result=dict(whole_receiver_verified=False,adopted_routes=0,configuration_1_stopped=True,variants={})
 for v in ('shared','shared256','halfword','direct','direct-grace'):
  source=f'reports/t-time-tile-dma-{v}-full.json';d=read(source)
  result['variants'][v]=dict(evidence=source,checked_output_words=d['checked_output_words'],checked_writes=d['checked_writes'],clients=d['clients'],declared_deadlines_pass=d['all_declared_deadlines_pass'],tile_margin_clocks=2566080-d['clients'][2]['finish'])
 for v in ('shared','halfword','direct'):
  r=read(f'reports/t-time-tile-dma-{v}-route/summary.json')
  result['variants'][v]['standalone']=dict(logic=r['logic_with_ram_blockers'],FF=r['FF_sites_with_ram_blockers'],fmax=r['fmax'],target_pass=r['partial_target_pass'])
 for v in ('shared','halfword','direct','grace'):
  r=read(f'reports/shared-receiver-fft-tile-{v}-pack/packed-budget.json')
  result['variants']['direct-grace' if v=='grace'else v]['connected_pack']=dict(logic=r['logic_with_ram_blockers'],FF_sites=r['FF_sites_with_ram_blockers'],capacity=r['logic_capacity'],excess=r['logic_excess'],placed=False,routed=False)
 result['integrated_CAD']={}
 for v in ('route','heap','noctrl','noctrl-bounded'):
  r=read(f'reports/shared-receiver-fft-tile-grace-{v}/summary.json')
  result['integrated_CAD'][v]={k:r[k]for k in ('pnr_exit','route_completed','partial_target_pass')}
 paths=['ci/t_time_tile_buffer_comparison.py','tests/test_sdram_client_arbiter_grace.py','tests/test_sdram_client_arbiter.py','reports/sdram-client-arbiter-grace.log','reports/sdram-client-arbiter-grace-old-contract.log']
 result['additional_sha256']={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()for f in paths}
 (ROOT/'reports/continuation-20261021d.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result['integrated_CAD']))
if __name__=='__main__':main()
