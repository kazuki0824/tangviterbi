"""Run the queue-connected owner source with its compiled control costs."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
from experiments.s3_joint_runtime import ROOT,generated,replace,function,CATEGORIES
from experiments.s3_queue_audited_runtime import audited_source
from experiments.s3_queue_tasks_source import sources

def owner_body():
 body=function(sources()['s3_queue_tasks.c'],'owner_iteration')
 body=body.replace('s3_raw_queue*x=r->config.queues[i]','s3_raw_queue*x=r->config.transfers[i]')
 body=replace(body,'s3_raw_queue_reap(x)','s3_pp_spi_reap(x)')
 return replace(body,'s3_raw_queue_submit(x)','s3_pp_spi_submit(x,r->config.pack,r->config.ports[i],r->config.epoch)')

def main():
 out=ROOT/'reports/s3-queue-owner';out.mkdir(exist_ok=True)
 costfile=out/'instructions.json';record=json.loads(costfile.read_text())
 old=json.loads((ROOT/'reports/s3-queue-study/inline-runtime.json').read_text())
 costs=dict(next(r for r in old['rows'] if r['requested_banks']==20000)['costs_used'])
 costs.update(record['replacement_fees_cycles'])
 source=audited_source();body=owner_body();rows=[]
 with tempfile.TemporaryDirectory() as td:
  td=Path(td);(td/'queue.c').write_text(source)
  files=generated(costs);files['joint_owner.inc']=body
  files['pack.c']=replace(files['pack.c'],'#include "s3_iq10_block.h"','#include "s3_iq10_inline.h"')
  for n,s in files.items():(td/n).write_text(s)
  exe=td/'probe'
  subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Wno-misleading-indentation','-fsanitize=undefined','-fno-sanitize-recover=all','-ffunction-sections','-Wl,--gc-sections','-DS3_PP_CORE0_SIXTEENTHS=5','-DS3_RAW_TRANSFER_BYTES=16384',f'-I{td}',f'-I{ROOT/"experiments"}',f'-I{ROOT/"tests/s3_sdk_shim"}',str(td/'queue.c'),str(td/'pack.c'),str(td/'native.c'),str(ROOT/'experiments/s3_parallel_capture.c'),str(ROOT/'experiments/s3_raw_queue.c'),'-o',str(exe)],check=True)
  for stall in (0,1,2,5,10,15,20,30):
   for count in ((100,4000,20000) if stall==0 else (100,4000)):
    r=json.loads(subprocess.check_output([str(exe),'40','512',str(count),'1',str(stall),'20000','2048','1024'],text=True))
    r.update(order='PCAB',requested_banks=count,owner_extra_cycles=0)
    r['scenario_pass']=r['banks']==count and not any(r[k] for k in ('native_fault','pack_fault','task_fault','outcome'))
    r['cost_ledger']=[{key:{'events':v[0],'cycles':v[1]} for key,v in zip(CATEGORIES,core)} for core in r.pop('costs')]
    r['costs_used']=costs;rows.append(r);print(stall,count,r['banks'],r['scenario_pass'],flush=True)
    if not r['scenario_pass']:break
 result=dict(rows=rows,scope='Actual queue task owner control flow; compiled owner/poll/worker fees; instruction model and explicit stall sensitivity, not silicon timing.',hardware_proven=False,all_SoC_costs_finalized=False,owner_source_sha256=hashlib.sha256(body.encode()).hexdigest(),source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),costfile,ROOT/'experiments/s3_queue_tasks_source.py',ROOT/'experiments/s3_raw_tasks.c',ROOT/'experiments/s3_raw_tasks.h',ROOT/'experiments/s3_queue_audited_runtime.py',ROOT/'reports/s3-queue-study/inline-runtime.json']})
 (out/'runtime.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
