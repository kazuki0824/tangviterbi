"""Summarize logged router1 work without interpreting timeout as infeasibility."""
import hashlib,json,re
from pathlib import Path
R=Path(__file__).resolve().parents[1]
out={}
for label in ['arbiter-parallel','arbiter-matrix','controller-bank-parallel','controller-client-lookahead','arbiter-matrix-extended']:
 d=R/'reports'/label
 result=d/'route-result.json'
 if not result.exists():raise RuntimeError(f'{label}: collector has not finished')
 rows=[]
 for line in (d/'route.log').read_text().splitlines():
  m=re.fullmatch(r'Info:\s+(\d+)\s*\|\s*(\d+)\s+(\d+)\s*\|\s*(\d+)\s+(\d+)\s*\|\s*(\d+)\s*\|\s*([\d.]+)\s+([\d.]+)\|',line)
  if m:
   v=m.groups();rows.append({'iteration':int(v[0]),'remaining_arcs':int(v[5]),'router_logged_seconds':float(v[7])})
 r=json.loads(result.read_text());assert rows
 out[label]={'result':r,'last_logged_progress':rows[-1],'minimum_logged_remaining':min(rows,key=lambda x:x['remaining_arcs']),'last_ten_progress_rows':rows[-10:],'interpretation':'Completion and timing are separate; counts are sampled progress, not convergence bounds. Wall time includes placement and host contention.','sha256':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [d/'route.log',result]}}
(R/'reports/arbiter-route-progress.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:{'completed':v['result']['route_completed'],'last':v['last_logged_progress'],'minimum':v['minimum_logged_remaining']}for k,v in out.items()},indent=2))
