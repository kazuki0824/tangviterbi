"""Branch-aware disassembly and conservative executed-instruction accounting.
This is NOT cycle-accurate emulation or WCET analysis. Pinned SDK ELF only.
"""
import argparse,gzip,hashlib,json,os,re,subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]
ROW=re.compile(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(\S+)\s*(.*)$')
def graph(elf,tool,env,start,size):
 end=start+size;pending=[start];nodes={}
 while pending:
  pc=pending.pop()
  if pc in nodes:continue
  if not start<=pc<end:raise ValueError('internal edge leaves function')
  dis=subprocess.check_output([tool,'-d',f'--start-address={pc}',f'--stop-address={end}',str(elf)],env=env,text=True)
  rows=[]
  for line in dis.splitlines():
   m=ROW.match(line)
   if m:rows.append((int(m[1],16),len(m[2])//2,m[3],m[4]))
  if not rows or rows[0][0]!=pc:raise ValueError('decode does not begin at leader')
  for addr,length,op,args in rows:
   if addr in nodes:break
   if op.startswith('.') or length not in (2,3,4):raise ValueError('data/invalid length on reachable path')
   fall=addr+length;edges=[];call=None
   if op.startswith('ret'):pass
   elif op=='j' or op.startswith('b'):
    m=re.search(r'\b([0-9a-f]+)\s+<',args)
    if not m:raise ValueError('unrecognized branch '+op+' '+args)
    edges=[int(m[1],16)]
    if op!='j':edges.append(fall)
   else:
    edges=[fall]
    if op.startswith('call'):call=args
   nodes[addr]=dict(address=hex(addr),bytes=length,op=op,operands=args,edges=[hex(x) for x in edges],call=call)
   if op=='j' or op.startswith(('b','ret','call')):
    pending.extend(edges);break
 return nodes

def main():
 p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);tc=a.toolchain.resolve();env=os.environ.copy();env['XTENSA_GNU_CONFIG']=str(tc/'lib/xtensa_esp32s3.so')
 profile=ROOT/'reports/s3-pack-span/sdk/n16r8-late-stacks-no-phy-nvs-raw-only-spi';data=gzip.decompress((profile/'s3_raw_probe.elf.gz').read_bytes());elf=out/'sdk.elf';elf.write_bytes(data)
 # These ranges and visit bounds are audited against this exact binary.
 expected=json.loads((ROOT/'reports/s3-pack-span/sdk-loop-summary.json').read_text())['ELF_sha256']
 if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('unreviewed ELF')
 with elf.open('rb') as f:
  e=ELFFile(f);symbols={s.name:(int(s['st_value']),int(s['st_size'])) for s in e.get_section_by_name('.symtab').iter_symbols() if s.name in ('s3_pp_step_impl','s3_pp_step_clocked','esp_timer_get_time','systimer_hal_get_counter_value','systimer_ticks_to_us')}
 tool=str(tc/'bin/xtensa-esp-elf-objdump');graphs={name:graph(elf,tool,env,*location) for name,location in symbols.items()}
 nodes=graphs['s3_pp_step_impl'];wrapper=graphs['s3_pp_step_clocked']
 def inside(pc,lo,hi):return lo<=pc<hi
 bulk={pc for pc in nodes if inside(pc,0x40376db1,0x40376dc3)}
 byte={pc for pc in nodes if inside(pc,0x40376e1a,0x40376e38)}
 scan={pc for pc in nodes if inside(pc,0x40376c86,0x40376cb2)}
 body={pc for pc in nodes if inside(pc,0x40376d05,0x40376e44) or inside(pc,0x40376ed9,0x40376f08)}
 regular=body-bulk-byte;once=set(nodes)-body
 # Only these four back edges form loops. Remove them and verify a DAG; backward
 # helper jumps need not be loops and are retained in this check.
 loop_edges={(0x40376caf,0x40376c86),(0x40376dc0,0x40376db1),(0x40376e34,0x40376e1a),(0x40376e41,0x40376d05)}
 active=set();done=set()
 def visit(pc):
  if pc in active:raise ValueError('unaccounted CFG cycle')
  if pc in done:return
  active.add(pc)
  for target in nodes[pc]['edges']:
   dest=int(target,16)
   if (pc,dest) not in loop_edges:visit(dest)
  active.remove(pc);done.add(pc)
 visit(symbols['s3_pp_step_impl'][0])
 checks=[dict(name='all_impl_nodes_covered',passed=len(done)==len(nodes)),dict(name='bulk_six',passed=len(bulk)==6),dict(name='loop_edges_exist',passed=all(hex(v) in nodes[u]['edges'] for u,v in loop_edges)),dict(name='partition_disjoint',passed=len(regular|bulk|byte|once)==len(nodes) and not (scan&body))]
 impl_calls=[n for n in nodes.values() if n['call'] is not None]
 wrapper_calls=[n for n in wrapper.values() if n['call'] is not None]
 checks.append(dict(name='only_accounted_calls',passed=
  len(impl_calls)==2 and sum(n['op']=='call8' and '<pack_eight>' in n['operands'] for n in impl_calls)==1 and sum(n['op']=='callx8' for n in impl_calls)==1 and
  len(wrapper_calls)==2 and sum(n['op']=='call8' and '<s3_pp_step_impl>' in n['operands'] for n in wrapper_calls)==1 and sum(n['op']=='callx8' for n in wrapper_calls)==1))
 # Candidate scan visits <=3, all remaining prologue/epilogue nodes <=1.
 # Every successful dispatch traverses regular nodes <=1; byte loop <=5 times
 # per slow pair. Summing all mutually exclusive nodes is conservative.
 coeff=dict(block=45,run=len(regular),slow_pair=len(regular)+5*len(byte),slice=len(once)+2*len(scan)+len(wrapper))
 rows=[];paths=json.loads((ROOT/'reports/s3-pack-span/path-counts.json').read_text())
 for case in paths['rows']:
  for standard,cores in case['rates'].items():
   for worker,rates in enumerate(cores):
    count=coeff['block']*rates['blocks_s']+coeff['run']*rates['runs_s']+coeff['slow_pair']*rates['slow_pairs_s']+coeff['slice']*rates['slices_s']
    rows.append(dict(bank_samples=case['bank_samples'],first=case['first'],slice_pairs=case['slice_pairs'],standard=standard,worker=worker,conservative_instruction_count_per_s=count,ideal_one_cycle_per_instruction_Mcycles_s=count/1e6,clock_calls_per_s=rates['clock_reads_s'],additional_costs=['both clock callback bodies','RF owner and SPI owner work','calling context outside clocked step','cache/bus/pipeline stalls and interrupt/context costs']))
 clock_names=['esp_timer_get_time','systimer_hal_get_counter_value','systimer_ticks_to_us']
 clock_min=sum(len(graphs[name]) for name in clock_names)
 timer=graphs['systimer_hal_get_counter_value']
 wait_loop=[pc for pc in timer if 0x40383994<=pc<=0x4038399a]
 retry_loop=[pc for pc in timer if 0x403839ac<=pc<=0x403839b9]
 checks.append(dict(name='clock_loops',passed=len(wait_loop)==3 and len(retry_loop)==6))
 clock=dict(scope='Candidate callback only; not wired to native capture or workers',minimum_no_retry_instructions=clock_min,additional_wait_iteration_instructions=len(wait_loop),additional_consistency_retry_instructions=len(retry_loop),wait_retry_upper_bound_known=False,adapter_wrapper_and_stalls_included=False,tick_conversion_target='systimer_ticks_to_us after normal pinned SDK timer initialization')
 report=dict(scope=__doc__,clock_candidate=clock,ELF_sha256=expected,coefficients=coeff,region_nodes=dict(impl=len(nodes),wrapper=len(wrapper),regular=len(regular),bulk=len(bulk),byte_loop=len(byte),candidate_scan=len(scan),once=len(once)),checks=checks,rows=rows,cycles_upper_bound_proven=False,visit_assumptions=['successful ready-job path, valid current source invariants','three candidate banks scanned','five byte writes per slow pair','number of runs/blocks/slow pairs/slices from instrumented C cases'],call_bodies_included=['pack_eight'],clock_callback_body_included=False)
 (out/'results.json').write_text(json.dumps(report,indent=2)+'\n')
 (out/'cfg.json').write_text(json.dumps({name:list(g.values()) for name,g in graphs.items()},indent=2)+'\n')
 print(json.dumps(dict(coefficients=coeff,regions=report['region_nodes'],checks=checks),indent=2));return any(not c['passed'] for c in checks)
if __name__=='__main__':raise SystemExit(main())
