"""Generate a queue-connected task candidate from the existing task lifecycle.

The baseline remains unchanged. Exact substitutions fail if the source drifts;
SDK and host builds consume these same generated sources.
"""
import argparse,hashlib,json
from pathlib import Path
from experiments.s3_joint_runtime import ROOT,replace

def sources():
 h=(ROOT/'experiments/s3_raw_tasks.h').read_text()
 h=replace(h,'#include "s3_parallel_spi.h"','#include "s3_raw_queue.h"')
 h=replace(h,'S3_RAW_PREPARE_WORDS_PER_ITERATION=1024','S3_RAW_PREPARE_WORDS_PER_ITERATION=2048')
 h=replace(h,' s3_spi_port *ports[2]; s3_pp_transfer *transfers[2];',' s3_raw_queue *queues[2];')
 s=(ROOT/'experiments/s3_raw_tasks.c').read_text()
 s=replace(s,'#include "s3_raw_tasks.h"','#include "s3_queue_tasks.h"')
 s=replace(s,'''  if(!c->ports[i]||!c->transfers[i]||c->transfers[i]->active||
     !c->ports[i]->bulk||c->ports[i]->busy||c->ports[i]->poisoned)return false;
 if(c->ports[0]==c->ports[1]||c->transfers[0]==c->transfers[1])return false;''', '''  if(!c->queues[i]||!c->queues[i]->device||c->queues[i]->pack!=c->pack||
     c->queues[i]->host!=(i?SPI3_HOST:SPI2_HOST)||c->queues[i]->count||
     c->queues[i]->poisoned)return false;
 if(c->queues[0]==c->queues[1])return false;''')
 s=replace(s,'  s3_pp_transfer*x=r->config.transfers[i];','  s3_raw_queue*x=r->config.queues[i];')
 s=replace(s,'  if(x->active) {','  if(x->count) {')
 s=replace(s,'   esp_err_t rc=s3_pp_spi_reap(x);','   esp_err_t rc=s3_raw_queue_reap(x);')
 s=replace(s,'  if(!x->active) {','  if(x->count<2) {')
 s=replace(s,'   esp_err_t rc=s3_pp_spi_submit(x,r->config.pack,r->config.ports[i],r->config.epoch);','   esp_err_t rc=s3_raw_queue_submit(x);')
 s=replace(s,'''  for(unsigned i=0;i<2;++i)if(r->config.transfers[i]->active) {
   esp_err_t rc=s3_pp_spi_reap(r->config.transfers[i]);
   if(rc!=ESP_OK&&rc!=ESP_ERR_TIMEOUT)fault(r,RAW_TASK_SPI);
   // TIMEOUT retains the DMA lease; supervisor must drain/reset before reuse.
  }''', '''  for(unsigned i=0;i<2;++i)for(unsigned n=0;n<2&&r->config.queues[i]->count;++n) {
   esp_err_t rc=s3_raw_queue_reap(r->config.queues[i]);
   if(rc!=ESP_OK) {
    if(rc!=ESP_ERR_TIMEOUT)fault(r,RAW_TASK_SPI);
    break; // All outstanding leases survive timeout/fault; supervisor drains/resets.
   }
  }''')
 return {'s3_queue_tasks.h':h,'s3_queue_tasks.c':s}

def main(out):
 out.mkdir(parents=True,exist_ok=True);files=sources()
 for n,s in files.items():(out/n).write_text(s)
 (out/'sources.json').write_text(json.dumps(dict(source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'experiments/s3_raw_tasks.c',ROOT/'experiments/s3_raw_tasks.h']},generated_sha256={n:hashlib.sha256(s.encode()).hexdigest() for n,s in files.items()}),indent=2)+'\n')

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();main(a.output)
