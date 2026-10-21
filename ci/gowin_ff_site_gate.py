"""Reject provably over-capacity fixed packed candidates before placement.
Exit 2: core exceeds capacity; exit 3: only the observation wrapper exceeds it.
Exit 0 merely passes this necessary condition, never qualifies placement/timing.
"""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ci.gowin_ff_site_audit import audit,scope_cells
p=Path(sys.argv[1]);full,core,_=scope_cells(p)
f,c=audit(full),audit(core)
code=2 if c['excess']>0 else 3 if f['excess']>0 else 0
r=dict(exit_code=code,core=c,with_probe=f,necessary_condition_only=True)
(p/'placement-gate.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(dict(exit_code=code,core_excess=c['excess'],with_probe_excess=f['excess'])))
sys.exit(code)
