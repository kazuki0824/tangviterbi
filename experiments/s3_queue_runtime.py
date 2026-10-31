"""Depth-two actual queue adapter with modeled SDK IRQ service. Fees are assumptions."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
from experiments.s3_joint_runtime import ROOT,generated,replace,CATEGORIES
from experiments.s3_owner_order_estimate import owner_variant

def queue_source():
 s=(ROOT/'experiments/s3_joint_runtime.c').read_text()
 s=s.replace('typedef int esp_err_t;\nenum {ESP_OK,ESP_ERR_TIMEOUT,ESP_ERR_NOT_FINISHED};','#include "s3_raw_queue.h"')
 s=replace(s,'typedef struct {bool active;uint64_t sequence;const uint8_t*data;unsigned host;} s3_pp_transfer;','typedef s3_raw_queue s3_pp_transfer;')
 a=s.index('static esp_err_t s3_pp_spi_reap(');b=s.index('#include "joint_owner.inc"',a)
 backend=(ROOT/'experiments/s3_queue_runtime_backend.inc').read_text()
 s=s[:a]+backend+'\n'+s[b:]
 s=replace(s,' runtime.config.watchdog.timeout_ms=5000;', ''' runtime.config.watchdog.timeout_ms=5000;
 spi_bus_config_t pins={0};for(unsigned h=0;h<2;h++)assert(s3_raw_queue_open(&tx[h],&pack,h+2,&pins,1,h?4:8,1)==ESP_OK);''')
 old='for(unsigned h=0;h<2;h++)if(irq_at[h]==event){ready[0]+=COST_IRQ_COMPLETE;charged[0][SPI_IRQ]+=COST_IRQ_COMPLETE;counts[0][SPI_IRQ]++;interrupts[0]+=COST_IRQ_COMPLETE;irq_at[h]=UINT64_MAX;}'
 new='for(unsigned h=0;h<2;h++)if(irq_at[h]==event){queue_irq(h);}'
 s=replace(s,old,new)
 return replace(s,'if(event==next_tick){for(unsigned k=0;k<2;k++)','if(event==next_tick){queue_tick(COST_TICK0);for(unsigned k=0;k<2;k++)')

def main(extended=False):
 out=ROOT/'reports/s3-queue-study';out.mkdir(exist_ok=True);source=ROOT/'reports/s3-counter-envelope/runtime.json';baseline=json.loads(source.read_text());rows=[]
 with tempfile.TemporaryDirectory() as td:
  td=Path(td);body=queue_source();(td/'queue.c').write_text(body)
  for rate,share,order in ([(40,5,'PCAB')] if extended else [(16,8,'PCAB'),(40,5,'PCAB'),(40,5,'BCPA'),(40,6,'PCAB'),(40,6,'BCPA')]):
   p=next(p for p in baseline['profiles'] if p['order']==order and (p['rows'][0]['rate'],p['rows'][0]['share'])==(rate,share))
   for extra in ((300,) if extended else (0,100,300)):
    costs=dict(p['fixed_cost_cycles']);costs['SUBMIT_DONE']+=extra;costs['REAP_DONE']+=extra
    costs['OWNER_SHELL']+=extra # explicit additional queue checks, not claimed audited
    files=generated(costs);files['joint_owner.inc']=owner_variant(order).replace('if(x->active)','if(x->count)').replace('if(!x->active)','if(x->count<2)')
    for n,t in files.items():(td/n).write_text(t)
    binary=td/'probe';chunk=32768 if rate==16 else 16384
    subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Wno-misleading-indentation','-fsanitize=undefined','-fno-sanitize-recover=all','-ffunction-sections','-Wl,--gc-sections',f'-DS3_PP_CORE0_SIXTEENTHS={share}',f'-DS3_RAW_TRANSFER_BYTES={chunk}',f'-I{td}',f'-I{ROOT/"experiments"}',f'-I{ROOT/"tests/s3_sdk_shim"}',str(td/'queue.c'),str(td/'pack.c'),str(td/'native.c'),str(ROOT/'experiments/s3_parallel_capture.c'),str(ROOT/'experiments/s3_raw_queue.c'),'-o',str(binary)],check=True)
    for prep in ((2048,) if extended else (1024,2048,3072)):
     for count in ((20000,) if extended else (100,4000) if rate==40 or (extra==0 and prep==2048) else (100,)):
      r=json.loads(subprocess.check_output([str(binary),str(rate),'512',str(count),'1','0','20000',str(prep),'1024'],text=True))
      r.update(order=order,extra_fee_cycles=extra,requested_banks=count)
      r['scenario_pass']=r['banks']==count and not any(r[k] for k in ('native_fault','pack_fault','task_fault','outcome'))
      r['cost_ledger']=[{key:{'events':v[0],'cycles':v[1]} for key,v in zip(CATEGORIES,core)} for core in r.pop('costs')]
      r['costs_used']=costs;rows.append(r)
      print(rate,share,order,extra,prep,count,r['banks'],r['scenario_pass'],flush=True)
      if not r['scenario_pass']:break
 result={'rows':rows,'hardware_proven':False,'all_SoC_costs_finalized':False,'scope':'Actual new queue adapter and packing C; modeled SDK automatic next launch; legacy IRQ/root fees with explicit extra fee sensitivity. Not a linked SDK cost audit.', 'source_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__).resolve(),ROOT/'experiments/s3_queue_runtime_backend.inc',ROOT/'experiments/s3_raw_queue.c',ROOT/'experiments/s3_raw_queue.h',ROOT/'experiments/s3_joint_runtime.c',ROOT/'experiments/s3_joint_runtime.py',ROOT/'experiments/s3_owner_order_estimate.py',source]},'generated_c_sha256':hashlib.sha256(body.encode()).hexdigest()}
 (out/('extended.json' if extended else 'runtime.json')).write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--extended',action='store_true');args=ap.parse_args();main(args.extended)
