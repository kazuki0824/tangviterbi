"""Reroute saved legal placement; no new placement or whole-receiver claim."""
import argparse,gzip,hashlib,json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--cad',type=Path,required=True);p.add_argument('--router',choices=['router1','router2'],default='router2');p.add_argument('--timing-ripup',action='store_true');p.add_argument('--replay-placement',action='store_true');a=p.parse_args()
 suffix=a.router+('-ripup' if a.timing_ripup else '')+('-replay' if a.replay_placement else '')
 out=ROOT/'reports'/('cursor-mask-fixed-'+suffix);out.mkdir(exist_ok=True)
 work=ROOT/'build'/('cursor-mask-fixed-'+suffix);work.mkdir(exist_ok=True)
 source=ROOT/'reports/controller-cursor-mask/routed.json.gz';data=json.loads(gzip.decompress(source.read_bytes()));m=next(iter(data['modules'].values()))
 before={k:(v['type'],v['connections'],v['parameters'],v['attributes'].get('NEXTPNR_BEL')) for k,v in m['cells'].items()}
 for n in m['netnames'].values():n.get('attributes',{}).pop('ROUTING',None)
 m['settings'].pop('route',None)
 if a.replay_placement:
  # Gowin's saved BEL import calls notifyBelChange before prePlace initializes
  # its fast_logic_cell grid. Replay every saved BEL as a user constraint so
  # normal prePlace initialization runs before any placement bindings.
  m['settings'].pop('place',None)
  for c in m['cells'].values():
   attr=c['attributes'];attr['BEL']=attr.pop('NEXTPNR_BEL');attr.pop('BEL_STRENGTH',None)
 m['settings']['router/tmg_ripup']='1 ' if a.timing_ripup else '0 '
 inp=work/'placed.json';inp.write_text(json.dumps(data))
 cad=a.cad.resolve();db=cad/'share/nextpnr/himbaechel/gowin/chipdb-GW2A-18C.bin'
 digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 assert digest(db)=='28e74084da573c220ace2dd9ca381abf0f31db6be6599b81761dfc2416b4e8a3'
 cmd=[str(cad/'bin/nextpnr-himbaechel'),'--json',str(inp),'--device','GW2AR-LV18QN88C8/I7','--vopt','family=GW2A-18C','--no-pack','--no-place','--freq',str(1080/7),'--seed','1','--router',a.router,'--report',str(out/'pnr.json'),'--write',str(work/'routed.json')]
 if a.replay_placement:
  cmd.remove('--no-place');cmd+=['--placer','heap']
 if a.timing_ripup:cmd.append('--tmg-ripup')
 (out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 result=dict(source_sha256=digest(source),input_sha256=digest(inp),chipdb_sha256=digest(db),router=a.router,timing_ripup=a.timing_ripup,replay_placement=a.replay_placement,whole_receiver_verified=False,timeout_seconds=None,scope=__doc__,version=subprocess.check_output([str(cad/'bin/nextpnr-himbaechel'),'--version'],stderr=subprocess.STDOUT,text=True).strip())
 start=time.monotonic()
 with (out/'route.log').open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
 result.update(exit=r.returncode,seconds=time.monotonic()-start)
 log=(out/'route.log').read_text();result['route_completed']='Routing complete.' in log;result['errors']=[l for l in log.splitlines() if l.startswith('ERROR:') or 'Assertion failure' in l or 'terminate called' in l]
 if (out/'pnr.json').exists():result['fmax']=json.loads((out/'pnr.json').read_text()).get('fmax');(out/'pnr.json.gz').write_bytes(gzip.compress((out/'pnr.json').read_bytes(),mtime=0));(out/'pnr.json').unlink()
 if (work/'routed.json').exists():
  after=next(iter(json.loads((work/'routed.json').read_text())['modules'].values()))
  unchanged=before=={k:(v['type'],v['connections'],v['parameters'],v['attributes'].get('NEXTPNR_BEL')) for k,v in after['cells'].items()}
  result['same_cell_types_connections_parameters_BELs']=unchanged
  result['routed_sha256']=digest(work/'routed.json')
  if not unchanged:raise ValueError('Reroute changed netlist or placement')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
