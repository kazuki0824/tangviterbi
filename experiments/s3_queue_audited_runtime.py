"""Same C lifecycle, with N16R8 SDK path costs and one chained IRQ charge."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
from experiments.s3_queue_runtime import queue_source
from experiments.s3_joint_runtime import ROOT,generated,replace,CATEGORIES
from experiments.s3_owner_order_estimate import owner_variant

def audited_source():
 s=queue_source()
 s=replace(s,'static uint64_t irq_service_until;','static uint64_t irq_service_until;static uint64_t irq_path_counts[4];')
 s=replace(s,'unsigned fee=launches[h]++?COST_IRQ_START:COST_IRQ_FIRST;', 'bool first=!launches[h]++;irq_path_counts[first?0:1]++;unsigned fee=first?COST_IRQ_FIRST:COST_IRQ_START;')
 s=replace(s,'irq_service_until=start+charge;', 'irq_path_counts[charge==COST_IRQ_CHAIN?3:2]++;irq_service_until=start+charge;')
 marker=' printf("\\\"prepare_per_iteration'
 # Insert a distinct set of ISR invocation frequencies, not two fees for one ISR.
 at=s.index(marker)
 s=s[:at]+' printf("\\\"irq_path_counts\\\":[%llu,%llu,%llu,%llu],",(unsigned long long)irq_path_counts[0],(unsigned long long)irq_path_counts[1],(unsigned long long)irq_path_counts[2],(unsigned long long)irq_path_counts[3]);\n'+s[at:]
 s=replace(s,'charge+=COST_IRQ_START;events++;','charge=COST_IRQ_CHAIN;')
 s=replace(s,'done?COST_REAP_DONE:230','done?COST_REAP_DONE:COST_REAP_EMPTY')
 s=replace(s,'COST_REAP_DONE-230','COST_REAP_DONE-COST_REAP_EMPTY')
 return s

def main(inline=False):
 out=ROOT/'reports/s3-queue-study';costfile=out/'sdk-n16r8/costs.json'
 fees=json.loads(costfile.read_text())['fees_cycles']
 base=json.loads((ROOT/'reports/s3-counter-envelope/runtime.json').read_text())
 rows=[];source=audited_source()
 inline_file=ROOT/'reports/s3-inline-packing/slice-costs.json'
 inline_fees=json.loads(inline_file.read_text())['fees_cycles'] if inline else {}
 with tempfile.TemporaryDirectory() as td:
  td=Path(td);(td/'queue.c').write_text(source)
  for share in (5,6):
   for order in ('PCAB','BCPA'):
    p=next(p for p in base['profiles'] if p['order']==order and (p['rows'][0]['rate'],p['rows'][0]['share'])==(40,share))
    for shell_extra in (0,100,300):
     costs=dict(p['fixed_cost_cycles'])
     for key,name in {'SUBMIT_DONE':'submit_done','SUBMIT_EMPTY':'submit_empty','REAP_DONE':'reap_done','REAP_EMPTY':'reap_empty','IRQ_START':'spi_irq_start','IRQ_FIRST':'spi_irq_first','IRQ_COMPLETE':'spi_irq_complete','IRQ_CHAIN':'spi_irq_chain'}.items():costs[key]=fees[name]
     costs.update(inline_fees)
     costs['OWNER_SHELL']+=shell_extra
     files=generated(costs);files['joint_owner.inc']=owner_variant(order).replace('if(x->active)','if(x->count)').replace('if(!x->active)','if(x->count<2)')
     if inline:files['pack.c']=replace(files['pack.c'],'#include \"s3_iq10_block.h\"','#include \"s3_iq10_inline.h\"')
     for n,t in files.items():(td/n).write_text(t)
     binary=td/'probe'
     subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Wno-misleading-indentation','-fsanitize=undefined','-fno-sanitize-recover=all','-ffunction-sections','-Wl,--gc-sections',f'-DS3_PP_CORE0_SIXTEENTHS={share}','-DS3_RAW_TRANSFER_BYTES=16384',f'-I{td}',f'-I{ROOT/"experiments"}',f'-I{ROOT/"tests/s3_sdk_shim"}',str(td/'queue.c'),str(td/'pack.c'),str(td/'native.c'),str(ROOT/'experiments/s3_parallel_capture.c'),str(ROOT/'experiments/s3_raw_queue.c'),'-o',str(binary)],check=True)
     for prep in (1024,2048,3072):
      for count in (100,4000):
       r=json.loads(subprocess.check_output([str(binary),'40','512',str(count),'1','0','20000',str(prep),'1024'],text=True))
       r.update(order=order,owner_extra_cycles=shell_extra,requested_banks=count)
       r['scenario_pass']=r['banks']==count and not any(r[k] for k in ('native_fault','pack_fault','task_fault','outcome'))
       r['cost_ledger']=[{key:{'events':v[0],'cycles':v[1]} for key,v in zip(CATEGORIES,core)} for core in r.pop('costs')]
       r['costs_used']=costs;rows.append(r)
       print(share,order,shell_extra,prep,count,r['banks'],r['scenario_pass'],flush=True)
       if not r['scenario_pass']:break
     if share==5 and order=='PCAB' and shell_extra==300:
      r=json.loads(subprocess.check_output([str(binary),'40','512','20000','1','0','20000','2048','1024'],text=True))
      r.update(order=order,owner_extra_cycles=shell_extra,requested_banks=20000)
      r['scenario_pass']=r['banks']==20000 and not any(r[k] for k in ('native_fault','pack_fault','task_fault','outcome'))
      r['cost_ledger']=[{key:{'events':v[0],'cycles':v[1]} for key,v in zip(CATEGORIES,core)} for core in r.pop('costs')]
      r['costs_used']=costs;rows.append(r);print('extended',r['banks'],r['scenario_pass'],flush=True)
 result=dict(rows=rows,inline_packing=inline,scope='New SDK submit/reap and chained ISR costs; legacy non-SPI fees. Owner-only extra-fee sensitivity. Inline costs applied only when inline_packing=true.',hardware_proven=False,all_SoC_costs_finalized=False,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),costfile,ROOT/'experiments/s3_queue_runtime.py',ROOT/'experiments/s3_queue_runtime_backend.inc',ROOT/'experiments/s3_joint_runtime.py',ROOT/'experiments/s3_joint_runtime.c',ROOT/'experiments/s3_raw_queue.c',ROOT/'experiments/s3_owner_order_estimate.py',ROOT/'reports/s3-counter-envelope/runtime.json']},generated_c_sha256=hashlib.sha256(source.encode()).hexdigest())
 if inline:
  for p in (inline_file,ROOT/'experiments/s3_iq10_inline.h'):result['source_sha256'][str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
 (out/('inline-runtime.json' if inline else 'audited-runtime.json')).write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--inline',action='store_true');args=ap.parse_args();main(args.inline)
