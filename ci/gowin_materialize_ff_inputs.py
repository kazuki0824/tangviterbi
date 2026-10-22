"""Insert identity LUTs for FF D inputs lacking a distinct local LUT/ALU source.
No original cell, control, port or net is removed. Reverse transformation must
reconstruct the input JSON exactly; INIT=2 is the identity truth table.
"""
import collections,copy,gzip,hashlib,json,re,sys
from pathlib import Path

def transform(original):
 result=copy.deepcopy(original)
 top=next(n for n,m in result['modules'].items()if int(str(m.get('attributes',{}).get('top','0')),2)==1)
 module=result['modules'][top];cells=module['cells'];drivers=collections.Counter();ffs=collections.defaultdict(list)
 bits=[b for c in cells.values()for v in c['connections'].values()for b in v if isinstance(b,int)];fresh=max(bits)+1
 for name,c in cells.items():
  t=c['type'];ports=c['connections']
  if re.fullmatch('LUT[1-4]',t)and 'F'in ports:drivers[ports['F'][0]]+=1
  elif t=='ALU'and 'SUM'in ports:drivers[ports['SUM'][0]]+=1
  if t.startswith('DFF'):ffs[ports['D'][0]].append(name)
 inserted=[]
 for bit,names in ffs.items():
  for ff in sorted(names)[drivers[bit]:]:
   name=f'ff_input_identity_{len(inserted)}';assert name not in cells and name not in module['netnames']
   cells[name]=dict(hide_name=0,type='LUT1',parameters={'INIT':'10'},attributes={'codex_identity_ff_input':'1'},port_directions={'I0':'input','F':'output'},connections={'I0':[bit],'F':[fresh]})
   cells[ff]['connections']['D']=[fresh]
   module['netnames'][name]=dict(hide_name=0,bits=[fresh],attributes={})
   inserted.append(dict(cell=name,ff=ff,old_D=bit,new_D=fresh));fresh+=1
 verify(original,result,top,inserted)
 return result,top,inserted

def verify(original,result,top,inserted):
 restored=copy.deepcopy(result);m=restored['modules'][top]
 for x in inserted:
  c=m['cells'].pop(x['cell']);assert c['type']=='LUT1'and c['parameters']=={'INIT':'10'}
  assert c['connections']=={'I0':[x['old_D']],'F':[x['new_D']]}
  assert m['cells'][x['ff']]['connections']['D']==[x['new_D']]
  m['cells'][x['ff']]['connections']['D']=[x['old_D']];m['netnames'].pop(x['cell'])
 assert restored==original,'Original graph changed beyond listed identity buffers'
 assert [(2>>i)&1 for i in range(2)]==[0,1]

if __name__=='__main__':
 source,dest=map(Path,sys.argv[1:]);raw=source.read_bytes();original=json.loads(gzip.decompress(raw)if source.suffix=='.gz'else raw)
 result,top,inserted=transform(original);dest.write_text(json.dumps(result))
 report=dict(input_sha256=hashlib.sha256(raw).hexdigest(),output_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),transform_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),original_graph_restored_exactly=True,identity_truth_table_verified=True,inserted_count=len(inserted),inserted=inserted)
 dest.with_suffix('.identity-proof.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k!='inserted'}))
