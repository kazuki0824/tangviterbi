"""Move synchronous DFFE/DFFRE controls into existing identity LUTs only.
Preserves positive-edge state transitions and INIT; changes physical timing.
"""
import copy,gzip,hashlib,json,sys
from pathlib import Path

def fold(netlist):
 out=copy.deepcopy(netlist);m=out['modules']['shared_receiver_fft_tile_probe'];cells=m['cells'];records=[]
 consumers={}
 for n,c in cells.items():
  for port,bits in c['connections'].items():
   if c['port_directions'].get(port)=='input':
    for bit in bits:consumers.setdefault(bit,[]).append((n,port))
 for name,lut in list(cells.items()):
  if not name.startswith('ff_input_identity_')or lut['type']!='LUT1':continue
  f=lut['connections']['F'][0]
  users=[(n,c)for n,c in cells.items()if c['type']in ['DFFE','DFFRE']and c['connections']['D']==[f]]
  if len(users)!=1:continue
  fn,ff=users[0];assert consumers[f]==[(fn,'D')],(name,consumers[f]);oldff=copy.deepcopy(ff);oldlut=copy.deepcopy(lut);reset=ff['type']=='DFFRE';width=4 if reset else 3
  assert int(lut['parameters']['INIT'],2)==2
  ports=dict(I0=lut['connections']['I0'],I1=ff['connections']['Q'],I2=ff['connections']['CE'],F=lut['connections']['F'])
  if reset:ports['I3']=ff['connections']['RESET']
  # Truth table: reset dominates CE, otherwise hold Q or capture D.
  value=0
  for i in range(1<<width):
   d,q,ce=(i>>0)&1,(i>>1)&1,(i>>2)&1;r=(i>>3)&1 if reset else 0
   value|=(0 if r else d if ce else q)<<i
  lut.update(type=f'LUT{width}',parameters={'INIT':format(value,f'0{1<<width}b')},connections=ports,port_directions={p:'output'if p=='F'else'input'for p in ports})
  ff['type']='DFF'
  for p in ['CE','RESET']:
   ff['connections'].pop(p,None);ff['port_directions'].pop(p,None)
  records.append(dict(lut=name,ff=fn,original_lut=oldlut,original_ff=oldff))
 restored=copy.deepcopy(out)
 for r in records:
  restored['modules']['shared_receiver_fft_tile_probe']['cells'][r['lut']]=r['original_lut']
  restored['modules']['shared_receiver_fft_tile_probe']['cells'][r['ff']]=r['original_ff']
 assert restored==netlist
 return out,records

def main():
 src,dest=map(Path,sys.argv[1:]);raw=gzip.decompress(src.read_bytes())if src.suffix=='.gz'else src.read_bytes();m=json.loads(raw);out,records=fold(m)
 dest.write_text(json.dumps(out));proof=dict(input_sha256=hashlib.sha256(raw).hexdigest(),output_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),transform_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),changed=len(records),original_graph_restored_exactly=True,records=records)
 dest.with_suffix('.controls-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print('changed',len(records))
if __name__=='__main__':main()
