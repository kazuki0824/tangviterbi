"""Reconstruct isolated LUT/FF pair groups; name locality is descriptive, not a timing proof."""
import collections,gzip,json,re
from pathlib import Path
R=Path(__file__).resolve().parents[1];out={}
for name,rel,expected in [('prebuffer','paired-packed.json.gz',4058),('folded','folded-graph/paired-packed.json.gz',4077)]:
 x=json.loads(gzip.decompress((R/'reports/placement-compatible-pairs'/rel).read_bytes()));cells=next(iter(x['modules'].values()))['cells'];sinks=collections.defaultdict(list)
 for n,c in cells.items():
  if c['type'].startswith('DFF'):sinks[c['connections']['D'][0]].append(n)
 groups=collections.defaultdict(list)
 for n,c in cells.items():
  if not re.fullmatch('LUT[1-4]',c['type']) or 'F'not in c['connections']:continue
  users=sinks[c['connections']['F'][0]]
  if not users:continue
  assert len(users)==1
  fn=users[0];f=cells[fn];key=(f['type'],*(tuple(f['connections'].get(p,[]))for p in ('CLK','CE','SET','RESET','PRESET','CLEAR')))
  groups[key].append((n,fn))
 pairs=[]
 for group in groups.values():
  group.sort()
  pairs.extend((group[i],group[i+1])for i in range(0,len(group)-1,2))
 assert len(pairs)==expected
 def prefix(n):return '.'.join(n.split('.')[:2]) if n.startswith('dut.') else n.split('.')[0]
 cross=[p for p in pairs if prefix(p[0][1])!=prefix(p[1][1])]
 identity=[p for p in pairs if any(c[0].startswith('ff_input_identity_')for c in p)]
 out[name]={'double_clusters':len(pairs),'different_FF_name_prefix':len(cross),'pairs_including_identity_LUT':len(identity),'different_prefix_examples':cross[:8],'interpretation':'Name-prefix difference is a descriptive locality hint, not receiver/probe attribution or evidence that a pair is illegal. Packer sorts LUT names and does not optimize connectivity distance.'}
(R/'reports/placement-compatible-pairs-timing/locality.json').write_text(json.dumps(out,indent=2)+'\n');print({k:{q:v[q]for q in ('double_clusters','different_FF_name_prefix','pairs_including_identity_LUT')}for k,v in out.items()})
