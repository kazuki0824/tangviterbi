"""Recount the current S candidate's packing CFG; instruction envelope, not WCET."""
import argparse,gzip,hashlib,io,json,os,subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile
from ci.s3_pack_cfg_audit import graph
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,required=True);p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 raw=gzip.decompress((a.profile/'s3_raw_probe.elf.gz').read_bytes());record=json.loads((a.profile/'result.json').read_text());assert hashlib.sha256(raw).hexdigest()==record['ELF_sha256'];assert record['all_static_checks_pass']
 assert record['build']['source_sha256']['experiments/s3_parallel_pack.c']==hashlib.sha256((ROOT/'experiments/s3_parallel_pack.c').read_bytes()).hexdigest()
 elf=ROOT/'build/current-pack-audit.elf';elf.write_bytes(raw);e=ELFFile(io.BytesIO(raw));sy={s.name:s for s in e.get_section_by_name('.symtab').iter_symbols()};tc=a.toolchain.resolve();env=os.environ.copy();env['XTENSA_GNU_CONFIG']=str(tc/'lib/xtensa_esp32s3.so')
 graphs={}
 for name in ('pack_eight','s3_pp_step_impl','s3_pp_step_clocked_quantized'):
  s=sy[name];g=graph(elf,str(tc/'bin/xtensa-esp-elf-objdump'),env,s['st_value'],s['st_size']);graphs[name]={k-s['st_value']:dict(n,edges=[int(x,16)-s['st_value'] for x in n['edges']]) for k,n in g.items()}
 nodes=graphs['s3_pp_step_impl'];wrapper=graphs['s3_pp_step_clocked_quantized'];eight=graphs['pack_eight']
 # Current emitted offsets, checked against the saved graph and source paths.
 bulk={x for x in nodes if 0x199<=x<0x1ab};byte={x for x in nodes if 0x202<=x<0x220};scan={x for x in nodes if 0x6e<=x<0x9a}
 body={x for x in nodes if 0xed<=x<0x22c or 0x2d1<=x<0x300};regular=body-bulk-byte;once=set(nodes)-body
 loops={(0x97,0x6e),(0x1a8,0x199),(0x21c,0x202),(0x229,0xed)}
 active=set();done=set()
 def visit(pc):
  if pc in active:raise ValueError('unaccounted loop')
  if pc in done:return
  active.add(pc)
  for dest in nodes[pc]['edges']:
   if (pc,dest) not in loops:visit(dest)
  active.remove(pc);done.add(pc)
 visit(0)
 checks=[dict(name='all_nodes_covered_DAG_after_four_declared_backedges',passed=len(done)==len(nodes)),dict(name='declared_loop_edges_exist',passed=all(b in nodes[a]['edges'] for a,b in loops)),dict(name='bulk_loop_calls_pack_eight_once',passed=sum('pack_eight' in nodes[x]['operands'] and nodes[x]['op'].startswith('call') for x in bulk)==1),dict(name='known_region_shape',passed=(len(nodes),len(regular),len(bulk),len(byte),len(scan),len(once),len(wrapper),len(eight))==(293,118,6,11,17,158,31,39))]
 # Same visit proof as prior audit: 3 candidate banks, five writes per slow
 # pair, successful dispatch regular nodes <=1, other slice nodes <=1.
 coeff=dict(block=len(eight)+len(bulk),run=len(regular),slow_pair=len(regular)+5*len(byte),slice=len(once)+2*len(scan)+len(wrapper))
 r=dict(scope=__doc__,ELF_sha256=record['ELF_sha256'],effective_config={k:record['build'][k] for k in ('core0_sixteenths','transfer_bytes','fill_unroll')},checks=checks,coefficients=coeff,regions=dict(impl=len(nodes),regular=len(regular),bulk=len(bulk),byte=len(byte),scan=len(scan),once=len(once),wrapper=len(wrapper)),clock_callback_body_included=False,cycles_upper_bound_proven=False)
 (a.output/'results.json').write_text(json.dumps(r,indent=2)+'\n');(a.output/'cfg.json.gz').write_bytes(gzip.compress(json.dumps(graphs,indent=2).encode(),mtime=0));print(json.dumps(r,indent=2));return any(not c['passed'] for c in checks)
if __name__=='__main__':raise SystemExit(main())
