"""Close the compatible-pair experiment without conflating timeout, stop and timing failure."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];P=R/'reports'
def read(n):return json.loads((P/n).read_text())
initial=read('placement-compatible-pairs/result.json');pre=read('placement-compatible-pairs-extended/result.json');fold=read('placement-compatible-pairs-folded-extended/result.json');r2=read('placement-compatible-pairs-router2/result.json');stop=read('placement-compatible-pairs-router2/intentional-stop.json');physical=read('placement-compatible-pairs-folded-extended/audit.json');timing=read('placement-compatible-pairs-timing/comparison.json')
assert all(x['exit']=='timeout' for x in initial['runs'].values())
assert pre['exit']=='timeout' and not pre['route_completed']
assert fold['exit']==1 and fold['route_completed'] and not physical['target_pass']
assert r2['exit']==130 and r2['intentional_stop'] and not r2['route_completed']
assert stop['iterations_since_best']>=150 and stop['last_iteration'][2]>stop['best_iteration'][2]
assert hashlib.sha256((P/'placement-compatible-pairs-router2/route.log').read_bytes()).hexdigest()==r2['log_sha256']
for name in ('graph-comparison.json','folded-graph/graph-comparison.json'):
 g=read('placement-compatible-pairs/'+name);assert all(g[k]for k in ('cells_identical','ports_identical','netnames_identical'))
result={'case_1':'stopped; not modified','case_2_adopted_receivers':0,'case_2_adopted_routes':0,'universal_impossibility_proven':False,'placement_obstacle_cleared_for_folded_fixture':True,'current_measured_failure':'routed clock below target and K7 minimum','initial_600_second_runs':initial['runs'],'prebuffer_1800':pre,'folded_1800':fold,'folded_router2':r2,'router2_stop':stop,'routed_audit':physical,'estimated_timing_audit':timing,'locality_audit':read('placement-compatible-pairs-timing/locality.json')}
result['endpoint_sources']=[]
for directory,names in [('placement-dynamic-prebuffer',['dut.tile.aligning_DFFR_Q','dut.memory.service.controller.state_DFFR_Q_1']),('placement-dynamic-folded-controls',['dut.tile.op_DFF_Q_2','dut.memory.service.controller.state_DFFR_Q_1'])]:
 x=read(directory+'/mapped.json');m=next(m for m in x['modules'].values()if names[0]in m.get('cells',{}))
 for name in names:
  c=m['cells'][name];q=c['connections']['Q'][0];aliases=[{'name':n,'indices':[i for i,b in enumerate(v['bits'])if b==q]}for n,v in m['netnames'].items()if q in v['bits']]
  result['endpoint_sources'].append({'condition':directory,'cell':name,'source_attribute':c.get('attributes',{}).get('src'),'Q_aliases':aliases})
result['unfinished']=['whole receiver area and timing','full FIR/sync/TMCC/equalizer/demap/T-S interleavers/RS/TS integration and precision','TTI descriptor/three-buffer rotation/cold-fill RTL','all modes/rates/layers/phases/arrival envelopes and long-term dynamic deadlines','S3 lossless capture/packing/DMA/IRQ/core WCET','physical lanes/pins/independent-clock synchronization','SDRAM min/max pad/PLL/tri-state STA','RF-to-TS hardware qualification']
result['source_sha256']={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [Path(__file__),R/'ci/gowin_pair_routed_audit.py',R/'ci/gowin_pair_timing_audit.py',R/'ci/gowin_pair_locality_audit.py']}
(P/'continuation-20261022b.json').write_text(json.dumps(result,indent=2)+'\n');print({'routed_MHz':physical['routed_MHz'],'physical_positions':physical['physical_site_audit']['packed_logic_with_ram_blockers'],'router2_final_overused':stop['last_iteration'][2],'formal_adoption':0})
