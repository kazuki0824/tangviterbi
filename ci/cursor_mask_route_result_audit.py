"""Verify saved fixed-input route results; never promote partial fit to whole receiver."""
import gzip,hashlib,json,math
from pathlib import Path
from ci.gowin_ff_site_audit import audit
ROOT=Path(__file__).resolve().parents[1]
def main():
 base=json.loads((ROOT/'reports/controller-cursor-mask/route-result.json').read_text())
 rows=[]
 for name in ('cursor-mask-timingweight20','cursor-mask-timingweight10-seed2'):
  p=ROOT/'reports'/name;r=json.loads((p/'result.json').read_text());pnr=json.loads(gzip.decompress((p/'pnr.json.gz').read_bytes()));raw=gzip.decompress((p/'routed.json.gz').read_bytes());routed=json.loads(raw)
  cells=next(iter(routed['modules'].values()))['cells'];actual=pnr['fmax']['dut.clk']['achieved'];target=1080/7;minimum=2*(25.212121+50.505)*128/127
  checks=[dict(name='same_'+k,passed=r[k]==base[k]) for k in ('mapped_sha256','backend_source_sha256','chipdb_sha256')]
  checks += [dict(name='routed_hash',passed=hashlib.sha256(raw).hexdigest()==r['routed_sha256']),dict(name='physical_site_recount',passed=audit(cells)==r['physical_sites']),dict(name='same_STA_result',passed=pnr['fmax']==r['fmax']),dict(name='complete_route_log',passed=r['route_completed'] and 'Routing complete.' in (p/'route.log').read_text()),dict(name='exit_matches_target_STA',passed=(r['exit']==0)==(actual>=target)),dict(name='scope_not_whole_receiver',passed=r['whole_receiver_verified'] is False)]
  row=dict(trial=name,checks=checks,MHz=actual,minimum_MHz=minimum,target_MHz=target,minimum_pass=actual>=minimum,target_pass=actual>=target,target_margin_percent=(actual/target-1)*100,minimum_margin_percent=(actual/minimum-1)*100,logic_sites=r['physical_sites']['packed_logic_with_ram_blockers'],logic_delta_from_baseline=r['physical_sites']['packed_logic_with_ram_blockers']-base['physical_sites']['packed_logic_with_ram_blockers'],BSRAM=pnr['utilization']['BSRAM']['used'],FF=pnr['utilization']['DFF']['used'],whole_receiver_verified=False)
  rows.append(row)
 assert all(c['passed'] for r in rows for c in r['checks'])
 out=ROOT/'reports/cursor-mask-route-comparison';out.mkdir(exist_ok=True)
 result=dict(rows=rows,all_checks_pass=True,receiver_adopted=False,baseline_MHz=base['fmax']['dut.clk']['achieved'],caveat='Different rebuilt binary/compiler from baseline; same pinned netlist, backend source and chipdb. Compare retained outputs, not a seed-only causal experiment.')
 (out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
