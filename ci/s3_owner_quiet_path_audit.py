"""Count a declared prepared/non-settling RF poll path; not a cycle bound."""
import argparse,gzip,hashlib,io,json,os
from pathlib import Path
from elftools.elf.elffile import ELFFile
from ci.s3_pack_cfg_audit import graph
ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);a=p.parse_args()
 tc=a.toolchain.resolve();env=dict(os.environ,XTENSA_GNU_CONFIG=str(tc/'lib/xtensa_esp32s3.so'))
 profile=ROOT/'reports/s3-spi-running-guard/sdk-S/image'
 raw=gzip.decompress((profile/'s3_raw_probe.elf.gz').read_bytes())
 record=json.loads((profile/'result.json').read_text())
 assert hashlib.sha256(raw).hexdigest()==record['ELF_sha256'] and record['all_static_checks_pass']
 for source in ('experiments/s3_raw_tasks.c','experiments/s3_native_capture.c','experiments/s3_cycle_clock.c'):
  assert hashlib.sha256((ROOT/source).read_bytes()).hexdigest()==record['build']['source_sha256'][source]
 elf=ELFFile(io.BytesIO(raw));sy={s.name:s for s in elf.get_section_by_name('.symtab').iter_symbols()}
 path=ROOT/'build/owner-quiet.elf';path.write_bytes(raw)
 # Every conditional branch reached must be declared. No default assumptions.
 choices={
  'poll_rf':{0x15:0x17,0x20:0x36},
  'clock_now':{9:0xc,0x18:0x1b,0x1b:0x1e,0x21:0x24,0x27:0x29,0x29:0x2c,0x3b:0x54},
  's3_cycle_clock_read':{8:0xa,0xd:0xf,0x1d:0x30},
  'healthy':{},'mmio_read':{},
  's3_native_poll_budget':{0xd:0x10,0x13:0x16,0x19:0x1c,0x1f:0x22,0x30:0x33,
   0x59:0x67,0x88:0x2c1,0x2c7:0x2ca,0x2ca:0x2d0,0x2ef:0x366,0x36a:0x474}}
 traces={}
 for name,branches in choices.items():
  s=sy[name];base=s['st_value'];g=graph(path,str(tc/'bin/xtensa-esp-elf-objdump'),env,base,s['st_size'])
  pc=base;nodes=[];seen=set();used=set()
  while True:
   assert pc not in seen;seen.add(pc);n=g[pc];offset=pc-base
   nodes.append(dict(offset=offset,op=n['op'],operands=n['operands']))
   edges=[int(x,16) for x in n['edges']]
   if not edges:assert n['op']=='retw.n';break
   if len(edges)==2:
    pc=base+branches[offset];used.add(offset);assert pc in edges
   else:assert len(edges)==1;pc=edges[0]
  assert used==set(branches)
  traces[name]=dict(own_instructions=len(nodes),nodes=nodes)
 count=lambda n:traces[n]['own_instructions']
 # callback identities are the raw runtime source contract, not inferred by
 # pretending an indirect call is free; their bodies are explicitly included.
 assert sum(n['op'].startswith('call') for n in traces['clock_now']['nodes'])==1
 native_calls=[n for n in traces['s3_native_poll_budget']['nodes'] if n['op'].startswith('call')]
 assert len(native_calls)==4
 assert sum('<clock_now>' in n['operands'] for n in native_calls)==2
 clock=count('clock_now')+count('s3_cycle_clock_read')
 poll=count('poll_rf')+count('s3_native_poll_budget')+2*clock+count('healthy')+count('mmio_read')
 guard=json.loads((ROOT/'reports/s3-spi-running-guard/path-cost/results.json').read_text())
 spi=sum(r['new_running'] for r in guard['rows'] if r['standard']=='S')
 result=dict(scope=__doc__,ELF_sha256=record['ELF_sha256'],traces=traces,
  clock_including_callback_instructions=clock,RF_poll_including_callbacks_instructions=poll,
  seven_RF_polls_instructions=7*poll,two_running_SPI_reaps_instructions=spi,
  partial_iteration_instructions=7*poll+spi,
  partial_iteration_cycles_at_alpha1_1=(7*poll+spi)*1.1,
  conditions=['Valid capture, prepared=true, settling=false, written<12288, within age deadline.',
   'Clock upper high word zero, no wrap during clock_now; no clock fault.',
   'Raw callbacks: healthy, mmio_read, s3_cycle_clock_read; both SPI commands running.',
   'Seven calls describe one such owner iteration, not every iteration or a steady-state average.'],
  exclusions=['Packing, fill, collect, owner glue, feed and its clock read, separate collect clock.',
   'Switch/settling/accept/prepare paths, completed SPI and submit.',
   'MMIO stalls, IRQ, bus contention, window exceptions, measured cycles.'],
  source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
   ('ci/s3_owner_quiet_path_audit.py','experiments/s3_raw_tasks.c','experiments/s3_native_capture.c','experiments/s3_cycle_clock.c')},
  CPU_estimate_reduced=False)
 out=ROOT/'reports/s3-owner-quiet-path';out.mkdir(exist_ok=True)
 (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k!='traces'},indent=2))
if __name__=='__main__':main()
