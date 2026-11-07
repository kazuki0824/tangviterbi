"""Compiled queued task control accounting, separate from leaf operation fees."""
import argparse,gzip,hashlib,io,json,math
from pathlib import Path
from elftools.elf.elffile import ELFFile
from ci.s3_sdk_cost_audit import Binary,ROOT
from ci.s3_receiver_cost_audit import bounded
from experiments.s3_queue_tasks_source import sources

def binary(tc):
 b=Binary(tc);folder=ROOT/'reports/s3-queue-owner/sdk'
 for name,source in sources().items():assert (folder/name).read_text()==source,name
 b.raw=gzip.decompress((folder/'s3_queue_owner_probe.elf.gz').read_bytes())
 b.sha=hashlib.sha256(b.raw).hexdigest();b.elf=ELFFile(io.BytesIO(b.raw))
 b.symbols={s.name:s for s in b.elf.get_section_by_name('.symtab').iter_symbols()}
 b.path=ROOT/'build/queue-owner.elf';b.path.write_bytes(b.raw)
 b.cache=ROOT/'build/queue-owner-graphs.json'
 b.graphs=json.loads(b.cache.read_text())['graphs'] if b.cache.exists() and json.loads(b.cache.read_text())['sha']==b.sha else {}
 return b

def audit(tc):
 b=binary(tc);out={}
 out['clock']=bounded(b,'s3_cycle_clock_read',forced={8:0xa,0xd:0xf},blocked=[0x28])
 clock=out['clock']['instructions']
 out['poll_control']=bounded(b,'poll_rf',blocked=[0x34,0x46],callees={0x22:0})
 out['pack_wrapper']=bounded(b,'pack_slice',forced={0x3a:0x50},callees={0x31:0})
 out['feed_normal']=bounded(b,'feed',forced={0x32:0x34},blocked=[0x1c,0x4d],callees={0xf:clock})
 reset=json.loads((ROOT/'reports/s3-sdk-cost-ledger/results.json').read_text())['roots']['5']['wdt_feed_0']['inclusive_instructions']
 out['feed_due']=bounded(b,'feed',forced={0x32:0x34},blocked=[0x1c,0x55],callees={0xf:clock,0x50:reset})
 g=b.graph('s3_raw_task_entry');calls={p:0 for p,n in g.items() if n['op'].startswith('call')}
 poll_sites=(0x246,0x25c,0x2af,0x2e6,0x31b)
 calls.update({p:out['poll_control']['instructions'] for p in poll_sites})
 calls.update({0x265:clock,0x332:out['feed_normal']['instructions'],0x3ea:out['feed_normal']['instructions']})
 out['owner_control']=bounded(b,'s3_raw_task_entry',entry=0x231,terminal_edge=(0x335,0x231),blocked=[0x338,0x272,0x290,0x2d8,0x308],backedges={(0x329,0x2b8):1},callees=calls)
 out['worker_control']=bounded(b,'s3_raw_task_entry',entry=0x3cc,terminal_edge=(0x3ed,0x3cc),blocked=[0x421,0x3f0],callees=calls)
 witness=out['owner_control']['witness']
 assert sum(witness.count(p) for p in poll_sites)==7
 assert witness.count(0x265)==1 and witness.count(0x332)==1
 assert out['pack_wrapper']['instructions']==25 and clock==21
 old=json.loads((ROOT/'reports/s3-receiver-cost-ledger/instructions.json').read_text())['paths']
 # Native operation fees remain unchanged; wrapper work moves entirely into owner.
 cycle=lambda n:(n*11+9)//10
 fees=dict(OWNER_SHELL=cycle(out['owner_control']['instructions']),WORKER_SHELL=cycle(out['worker_control']['instructions']),RF_BASE=cycle(old['native_quiet']['instructions']),WDT=cycle(out['feed_due']['instructions']-out['feed_normal']['instructions'])+cycle(reset))
 sizes={n:int(b.symbols[n]['st_size']) for n in ('owner_runtime','owner_queues','owner_pack','owner_capture')}
 return dict(paths=out,replacement_fees_cycles=fees,seven_poll_control_bodies_in_owner=True,RF_BASE_excludes_poll_control=True,ELF_sha256=b.sha,static_sizes=sizes,scope='Normal receive loop, actual PCAB two-port for-loop, per-iteration 2048 words and per-poll cap1024. Leaf operations charged by their existing ledgers; all poll control bodies charged in owner once. RF-off lifecycle tested but not timed here.',hardware_wcet=False,all_SoC_costs_finalized=False,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'ci/s3_receiver_cost_audit.py',ROOT/'experiments/s3_queue_tasks_source.py',ROOT/'experiments/s3_raw_tasks.c',ROOT/'experiments/s3_raw_tasks.h',ROOT/'reports/s3-queue-owner/sdk/s3_queue_owner_probe.elf.gz',ROOT/'reports/s3-queue-owner/sdk/s3_queue_tasks.c',ROOT/'reports/s3-queue-owner/sdk/s3_queue_tasks.h',ROOT/'reports/s3-receiver-cost-ledger/instructions.json',ROOT/'reports/s3-sdk-cost-ledger/results.json']})

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--toolchain',type=Path,required=True);ap.add_argument('--inspect',nargs='*');a=ap.parse_args();b=binary(a.toolchain.resolve())
 if a.inspect:
  for name in a.inspect:
   print(name)
   for pc,n in sorted(b.graph(name).items()):
    if len(n['edges'])!=1 or n['op'].startswith(('call','loop')) or any(dst<pc for dst in n['edges']):print(hex(pc),n['op'],n['args'],[hex(x) for x in n['edges']])
 else:
  r=audit(a.toolchain.resolve());(ROOT/'reports/s3-queue-owner/instructions.json').write_text(json.dumps(r,indent=2)+'\n');print(r['replacement_fees_cycles']);print({k:v['instructions'] for k,v in r['paths'].items()})
