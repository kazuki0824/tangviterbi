"""Optimistic LUT-site lower bound for a fixed packed Gowin netlist.
Each FF needs the colocated LUT/ALU D source. One driver can pair with at
most one FF; remaining FFs each require a distinct passthrough LUT site.
This does not prove an RTL or all architectures impossible.
"""
import collections,gzip,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):
 p=Path(p)
 return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz'else p.read_bytes())
def audit(cells):
 drivers=collections.Counter()
 ffs=collections.Counter()
 for c in cells.values():
  t=c['type'];ports=c['connections']
  if re.fullmatch('LUT[1-4]',t) and 'F'in ports:
   drivers[ports['F'][0]]+=1
  elif t=='ALU' and 'SUM'in ports:drivers[ports['SUM'][0]]+=1
  if t.startswith('DFF'):ffs[ports['D'][0]]+=1
 unmatched=sum(max(0,n-drivers[b])for b,n in ffs.items())
 counts=collections.Counter(c['type']for c in cells.values())
 logic=sum(v for k,v in counts.items()if re.fullmatch('LUT[1-4]|ALU',k))
 # Storage LUTs are already materialized by pack_ssram; the other four are blocked.
 ram=counts['RAM16SDP4']
 base=logic+4*ram
 return dict(FF=sum(ffs.values()),packed_logic_with_ram_blockers=base,
  minimum_extra_passthrough_LUTs=unmatched,optimistic_logic_site_lower_bound=base+unmatched,
  capacity=20736,excess=base+unmatched-20736,
  scope='Fixed netlist; optimistic pairing, no CE/reset/adjacency constraints. Not a lower bound over alternative mapping or RTL.')
def scope_cells(directory):
 p=Path(directory)
 mapped=read(p/'mapped.json.gz');top=next(n for n,m in mapped['modules'].items()if int(str(m.get('attributes',{}).get('top','0')),2)==1)
 m=mapped['modules'][top]['cells']
 regs={n for n,c in m.items()if c['type'].startswith('DFF') and 'probe.sv' in c.get('attributes',{}).get('src','').split('|')[0]}
 packed=read(p/'packed.json.gz')['modules']['top']['cells']
 harness={n for n in packed if n in regs or n.startswith('digest') or n.removesuffix('_passthrough_lut$')in regs}
 return packed,{n:c for n,c in packed.items()if n not in harness},regs
if __name__=='__main__':
 import sys
 p=Path(sys.argv[1]);allcells,core,regs=scope_cells(p)
 r=dict(full_with_probe=audit(allcells),core_without_probe=audit(core),harness_registers=len(regs),
        input_sha256={n:hashlib.sha256((p/n).read_bytes()).hexdigest()for n in ('mapped.json.gz','packed.json.gz')},
        auditor_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 (p/'ff-site-audit.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
