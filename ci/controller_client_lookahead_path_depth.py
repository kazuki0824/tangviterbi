"""Structural LUT/ALU depth between the previously measured critical endpoints.
Not delay analysis: no routing, pin delays, sensitization, or global worst-path claim.
"""
import functools,gzip,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
START='dut.tile.op_DFF_Q_2';END='dut.memory.service.controller.state_DFFR_Q_1'
def depth(path):
 raw=gzip.decompress(path.read_bytes());cells=json.loads(raw)['modules']['top']['cells']
 start=cells[START]['connections']['Q'][0];end=cells[END]['connections']['D'][0]
 drivers={}
 for name,c in cells.items():
  typ=c['type']
  if typ not in ['LUT1','LUT2','LUT3','LUT4','ALU']:continue
  inputs=[]
  for port,di in c['port_directions'].items():
   if di!='input':continue
   if typ.startswith('LUT'):
    j=int(port[1:]);init=int(c['parameters']['INIT'],2);width=int(typ[-1])
    if not any(((init>>i)^(init>>(i^(1<<j))))&1 for i in range(1<<width)):continue
   inputs+=c['connections'][port]
  for port,di in c['port_directions'].items():
   if di=='output':
    for b in c['connections'][port]:drivers[b]=(name,inputs)
 visiting=set()
 @functools.lru_cache(None)
 def visit(b):
  if b==start:return (0,[])
  if b not in drivers:return (-1,[])
  if b in visiting:raise AssertionError('combinational loop')
  visiting.add(b);name,ins=drivers[b];best=(-1,[])
  for i in ins:
   d,p=visit(i)
   if d>=0 and d+1>best[0]:best=(d+1,p+[name])
  visiting.remove(b);return best
 d,p=visit(end)
 return dict(source=str(path.relative_to(R)),sha256=hashlib.sha256(raw).hexdigest(),stages=d,path=p)
x={'scope':__doc__,'launch':START,'capture':END,'baseline':depth(R/'reports/shared-receiver-fft-tile-folded-controls-route/packed.json.gz'),'parallel':depth(R/'reports/controller-client-lookahead/packed.json.gz')}
(R/'reports/controller-client-lookahead/structural-depth.json').write_text(json.dumps(x,indent=2)+'\n');print({k:x[k]['stages']for k in ['baseline','parallel']})
