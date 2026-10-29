import subprocess,tempfile,unittest
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
 s=s.replace('1024u:0u','2048u:0u')
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

if __name__=='__main__':unittest.main()
