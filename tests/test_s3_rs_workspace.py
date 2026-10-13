"""Mode switch storage stays inside two distinct FFT slots, preserving guards."""
from pathlib import Path
import subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class WorkspaceTest(unittest.TestCase):
 def test_disjoint_slots_dirty_initialization_context_bounds_and_page_alignment(self):
  out=ROOT/'build/s3-rs-workspace';out.mkdir(parents=True,exist_ok=True)
  (out/'test.c').write_text(r'''
#include "s3_rs_workspace.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
struct slot0 {uint8_t before[32];s3_mode_slot0 slot;uint8_t after[32];};
struct slot1 {uint8_t before[32];s3_mode_slot1 slot;uint8_t after[32];};
static struct slot0 a;static struct slot1 b;
int main(void) {
 for(unsigned epoch=0;epoch<100;epoch++){
  memset(&a,0xa5,sizeof a);memset(&b,0x39,sizeof b);
  s3_rs_workspace_init(&a.slot,&b.slot);
  for(unsigned i=0;i<32;i++)assert(a.before[i]==0xa5&&a.after[i]==0xa5&&b.before[i]==0x39&&b.after[i]==0x39);
  for(unsigned i=0;i<5;i++){
   s3_rs_rpc_context *p=s3_rs_workspace_context(&a.slot,&b.slot,i);assert(p);
   for(unsigned j=0;j<sizeof(*p);j++)assert(((uint8_t*)p)[j]==0);
   p->epoch=(uint16_t)(epoch+1);p->batch=i;p->phase=1;
   for(unsigned j=0;j<i;j++)assert(s3_rs_workspace_context(&a.slot,&b.slot,j)->batch==j);
  }
  assert(!s3_rs_workspace_context(&a.slot,&b.slot,5));
  assert(!s3_rs_workspace_context(&a.slot,&b.slot,UINT32_MAX));
  assert((uintptr_t)a.slot.rs.rx%32==0 && (uintptr_t)a.slot.rs.tx%32==0);
  assert((uintptr_t)b.slot.rs.rx%32==0 && (uintptr_t)b.slot.rs.tx%32==0);
  assert(b.slot.rs.tables.exp[0]==1 && b.slot.rs.tables.log[2]==1);
  assert(a.slot.rs.crc[1]==UINT32_C(0x77073096));
 }
 puts("PASS 100 dirty T/S workspace initializations, five contexts, separate slot guards and 32-byte DMA alignment");
 return 0;
}''')
  subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(ROOT/'experiments'),
   str(out/'test.c'),*[str(ROOT/'experiments'/f's3_rs_{n}.c') for n in ('offload','rpc','workspace')],
   '-o',str(out/'test')],check=True)
  p=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=10)
  (out/'test.log').write_text(p.stdout+p.stderr);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
if __name__=='__main__':unittest.main()
