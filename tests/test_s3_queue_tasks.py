import hashlib,json,subprocess,tempfile,unittest
from pathlib import Path
from experiments.s3_queue_tasks_source import sources
from experiments.s3_joint_runtime import ROOT,replace

def host_source():
 s=(ROOT/'tests/s3_raw_tasks_host.c').read_text()
 s=replace(s,'#include "s3_raw_tasks.h"','#include "s3_queue_tasks.h"')
 s=replace(s,'static s3_spi_port ports[2];static s3_pp_transfer transfers[2];','static s3_raw_queue queues[2];static unsigned depth_two_seen;')
 a=s.index('esp_err_t s3_pp_spi_reap(');b=s.index('static void*entry(',a)
 s=s[:a]+'''esp_err_t s3_raw_queue_reap(s3_raw_queue*x){
 assert(core==0&&x->count);++reaps;
 if(mode==4||(!atomic_load(&rf_stopped)&&x->count==1))return ESP_ERR_TIMEOUT;
 --x->count;return ESP_OK;
}
esp_err_t s3_raw_queue_submit(s3_raw_queue*x){
 assert(core==0&&x->pack==&pack&&x->count<2);++submits;++x->count;
 if(x->count==2)++depth_two_seen;
 return mode==4?ESP_ERR_INVALID_STATE:ESP_OK;
}
'''+s[b:]
 s=replace(s,'assert(*budget==(polls%7==0?1024u:0u));*budget=0;', '''unsigned expected=polls%7<2?1024u:0u;
 if(mode==0&&polls%7==2)expected=512;
 assert(*budget==expected);
 *budget=mode==0&&polls%7==0?512:0; // Only actually consumed words reduce the shared budget.''')
 s=replace(s,'memset(ports,0,sizeof(ports));memset(transfers,0,sizeof(transfers));','memset(queues,0,sizeof(queues));depth_two_seen=0;')
 s=replace(s,'ports[i].bulk=true;','queues[i].device=(void*)(uintptr_t)(i+1);queues[i].host=i?SPI3_HOST:SPI2_HOST;queues[i].pack=&pack;')
 s=replace(s,'.ports={&ports[0],&ports[1]},.transfers={&transfers[0],&transfers[1]},','.queues={&queues[0],&queues[1]},')
 s=s.replace('transfers[0].active','queues[0].count').replace('transfers[1].active','queues[1].count')
 s=replace(s,'!queues[0].count&&!queues[1].count);','!queues[0].count&&!queues[1].count&&depth_two_seen);')
 return s

class QueueTasks(unittest.TestCase):
 def test_generated_task_lifecycle_and_depth_two_drain(self):
  with tempfile.TemporaryDirectory() as td:
   td=Path(td)
   for n,s in sources().items():(td/n).write_text(s)
   (td/'host.c').write_text(host_source())
   exe=td/'test'
   subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pthread','-fsanitize=undefined','-fno-sanitize-recover=all','-DESP_PLATFORM',f'-I{td}',f'-I{ROOT/"experiments"}',f'-I{ROOT/"tests/s3_sdk_shim"}',str(td/'s3_queue_tasks.c'),str(td/'host.c'),'-o',str(exe)],check=True)
   subprocess.run([str(exe)],check=True,timeout=30)
 def test_target_source_cost_partition_and_runtime_accounting(self):
  from experiments.s3_queue_owner_runtime import owner_body
  folder=ROOT/'reports/s3-queue-owner'
  for name,source in sources().items():self.assertEqual((folder/'sdk'/name).read_text(),source)
  audit=json.loads((folder/'instructions.json').read_text());runtime=json.loads((folder/'runtime.json').read_text())
  for d in (audit,runtime):
   for p,h in d['source_sha256'].items():self.assertEqual(hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),h,p)
  self.assertEqual(runtime['owner_source_sha256'],hashlib.sha256(owner_body().encode()).hexdigest())
  for path in audit['paths'].values():
   self.assertEqual(path['instructions'],path['own_instructions']+sum(path['witness'].count(int(pc,16))*fee for pc,fee in path['callee_instructions'].items()))
  witness=audit['paths']['owner_control']['witness']
  self.assertEqual(sum(witness.count(p) for p in (0x246,0x25c,0x2af,0x2e6,0x31b)),7)
  for row in runtime['rows']:
   self.assertEqual(row['owner_extra_cycles'],0)
   for k,v in audit['replacement_fees_cycles'].items():self.assertEqual(row['costs_used'][k],v)
   for c in (0,1):
    self.assertEqual(sum(v['cycles'] for v in row['cost_ledger'][c].values()),row['charged_cycles'][c])
    self.assertEqual(row['charged_cycles'][c]+row['stall_cycles'][c],row['accounted_until_cycles'][c])
   self.assertEqual(row['checked_bytes'],sum(row['transfers_done'])*16384)
   self.assertEqual(row['outcome'],0)
   self.assertLessEqual(row['peak_arena_bytes'],131072)
  self.assertTrue(any(r['requested_banks']==20000 and r['scenario_pass'] for r in runtime['rows']))
  self.assertFalse(runtime['all_SoC_costs_finalized'])

 def test_combined_memory_evidence(self):
  r=json.loads((ROOT/'reports/s3-queue-owner/memory.json').read_text())
  for p,h in r['source_sha256'].items():self.assertEqual(hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),h,p)
  self.assertTrue(r['all_static_checks_pass']);self.assertTrue(r['memory_necessary_pass'])
  self.assertTrue(all(c['ok'] for c in r['checks']))
  self.assertEqual(len(r['control_and_packing_CFGs_match_cost_probe']),8)
  d=r['driver_lower_bound'];t=d['type_sizes']
  self.assertEqual(d['per_port_queue_bytes'],2*(t['Queue_t']+2*t['spi_trans_priv_t']))
  self.assertEqual(d['two_port_known_allocation_lower_bound'],1584)
  self.assertEqual(d['total_internal_after_known_driver_upper_bound'],16820)
  self.assertTrue(d['not_counted'])
  self.assertFalse(r['hardware_boot_executed']);self.assertFalse(r['receiver_adopted'])

if __name__=='__main__':unittest.main()
