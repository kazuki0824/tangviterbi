"""Independent zlib CRC/channel-error oracle for bounded RS batch RPC."""
import ctypes as c
import hashlib,json,struct,subprocess,sys,unittest,zlib
from pathlib import Path
import test_s3_rs_offload as host
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from check_isdb_rs import vectors,encode,gf
class Context(c.Structure):
 _fields_=[('batch',c.c_uint32),('epoch',c.c_uint16),('phase',c.c_uint8),
           ('failed',c.c_uint8*204),('solution',host.Solution*204)]
Page=c.c_uint8*4096
def crc_page(p):
 p=bytearray(p);p[12:16]=bytes(4);p[12:16]=struct.pack('<I',zlib.crc32(p));return p
def page(kind,records,epoch=17,batch=0):
 p=bytearray(4096);p[:12]=struct.pack('<2sBBHHI',b'RS',1,kind,epoch,204,batch)
 payload=b''.join(records);p[16:16+len(payload)]=payload;return crc_page(p)
def syndrome(received):
 result=[];root=1
 for _ in range(16):
  s=0
  for byte in received:s=gf(s,root)^byte
  result.append(s);root=gf(root,2)
 return bytes(result)
class RpcTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.out=ROOT/'build/s3-rs-rpc';cls.out.mkdir(parents=True,exist_ok=True)
  subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fPIC','-shared',
   '-I'+str(ROOT/'experiments'),str(ROOT/'experiments/s3_rs_offload.c'),str(ROOT/'experiments/s3_rs_rpc.c'),
   '-o',str(cls.out/'rpc.so')],check=True)
  cls.lib=c.CDLL(str(cls.out/'rpc.so'));u8=c.POINTER(c.c_uint8);u32=c.POINTER(c.c_uint32)
  cls.lib.s3_rs_tables_init.argtypes=[c.POINTER(host.Tables)]
  cls.lib.s3_rs_rpc_crc_init.argtypes=[u32]
  cls.lib.s3_rs_rpc_syndromes.argtypes=[c.POINTER(host.Tables),u32,c.POINTER(Context),c.c_uint16,c.c_uint32,u8,u8]
  cls.lib.s3_rs_rpc_roots.argtypes=[c.POINTER(host.Tables),u32,c.POINTER(Context),u8,u8]
  cls.lib.s3_rs_rpc_ack.argtypes=[c.POINTER(Context),c.c_uint16,c.c_uint32]
  cls.lib.s3_rs_rpc_reset.argtypes=[c.POINTER(Context)]
  cls.cases=[]
  for name,received,payload in vectors():
   original=encode(payload);errors=[(i,a^b) for i,(a,b) in enumerate(zip(received,original)) if a!=b]
   cls.cases.append((name,received,original,syndrome(received),errors))
 def setUp(self):
  self.tables=host.Tables();self.crc=(c.c_uint32*256)()
  self.lib.s3_rs_tables_init(c.byref(self.tables));self.lib.s3_rs_rpc_crc_init(self.crc)
 def solve(self,ctx,rx,tx,epoch=17,batch=0):
  return self.lib.s3_rs_rpc_syndromes(c.byref(self.tables),self.crc,c.byref(ctx),epoch,batch,Page.from_buffer_copy(rx),tx)
 def roots(self,ctx,rx,tx):
  return self.lib.s3_rs_rpc_roots(c.byref(self.tables),self.crc,c.byref(ctx),Page.from_buffer_copy(rx),tx)
 def records(self,batch):
  cases=[self.cases[(batch*204+i)%len(self.cases)] for i in range(204)]
  syn=[struct.pack('<HB',i,0)+case[3] for i,case in enumerate(cases)]
  roots=[struct.pack('<HB8sB',i,len(case[4]),bytes(p for p,_ in case[4]),0) for i,case in enumerate(cases)]
  return cases,syn,roots
 def verify(self,p,kind,batch):
  self.assertEqual(bytes(p),bytes(crc_page(p)))
  self.assertEqual(bytes(p[:12]),struct.pack('<2sBBHHI',b'RS',1,kind,17,204,batch))
 def test_five_inflight_batches_and_immutable_ownership(self):
  contexts=[Context() for _ in range(5)];out=Page();expect=[]
  for batch,ctx in enumerate(contexts):
   cases,syn,roots=self.records(batch);expect.append((cases,roots))
   self.assertEqual(self.solve(ctx,page(1,syn,batch=batch),out,batch=batch),1)
   self.verify(out,2,batch);self.assertEqual(ctx.phase,1)
   for i,case in enumerate(cases):
    record=bytes(out[16+i*13:29+i*13]);self.assertEqual(record[:4],struct.pack('<HBB',i,0,len(case[4])))
    # Known channel error positions must be exact roots of the wire locator.
    for position,_ in case[4]:
     x=1
     for _ in range((position+52)%255):x=gf(x,2)
     acc=0
     for coefficient in record[4:][::-1]:acc=gf(acc,x)^coefficient
     self.assertEqual(acc,0)
   before=bytes(ctx);output=bytes(out)
   self.assertEqual(self.solve(ctx,page(1,syn,batch=batch),out,batch=batch),0)
   self.assertEqual(bytes(ctx),before);self.assertEqual(bytes(out),output)
   self.assertEqual(self.lib.s3_rs_rpc_ack(c.byref(ctx),17,batch),0)
  # Independent contexts permit out-of-order completion, not slot reuse.
  for batch in (4,1,3,0,2):
   ctx=contexts[batch];cases,roots=expect[batch]
   self.assertEqual(self.roots(ctx,page(3,roots,batch=batch),out),1);self.verify(out,4,batch)
   for i,case in enumerate(cases):
    record=bytes(out[16+i*12:28+i*12]);self.assertEqual(record[:3],struct.pack('<HB',i,0))
    mags=record[3:11];self.assertEqual(mags,bytes(m for _,m in case[4]).ljust(8,b'\0'))
    corrected=case[1].copy()
    for k,(position,_) in enumerate(case[4]):corrected[position]^=mags[k]
    self.assertEqual(corrected,case[2])
   self.assertEqual(self.roots(ctx,page(3,roots,batch=batch),out),0)
   self.assertEqual(self.lib.s3_rs_rpc_ack(c.byref(ctx),18,batch),0)
   self.assertEqual(self.lib.s3_rs_rpc_ack(c.byref(ctx),17,batch+1),0)
   self.assertEqual(self.lib.s3_rs_rpc_ack(c.byref(ctx),17,batch),1)
   self.assertEqual(self.lib.s3_rs_rpc_ack(c.byref(ctx),17,batch),0)
  r=dict(codewords=1020,distinct_independent_vectors=262,contexts=5,context_bytes=c.sizeof(Context),
   GF_tables_bytes=c.sizeof(host.Tables),CRC_tables_bytes=c.sizeof(self.crc),page_bytes=4096,
   working_set_bytes=5*c.sizeof(Context)+c.sizeof(host.Tables)+c.sizeof(self.crc)+8192,
   working_set_excludes_stack_RTOS_DMA_descriptors=True,receiver_adopted=False,hardware_IO_implemented=False,
   source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
     [ROOT/'experiments/s3_rs_rpc.c',ROOT/'experiments/s3_rs_rpc.h',ROOT/'tests/test_s3_rs_rpc.py']})
  (self.out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 def test_crc_semantics_and_atomic_rejection(self):
  _,syn,roots=self.records(0);good=page(1,syn);ctx=Context();out=Page(*([0xa5]*4096))
  # Every header byte, record boundaries, payload and padded tail are covered.
  cases=[]
  for offset in list(range(16))+[16,18,19,3872,3891,3892,4095]:
   p=good.copy();p[offset]^=1;cases.append(p)
  for offset,value in [(0,0),(2,2),(3,3),(4,18),(6,203),(8,1),(16,1),(18,2),(4095,1)]:
   p=good.copy();p[offset]=value;cases.append(crc_page(p))
  for p in cases:
   before=bytes(ctx);output=bytes(out)
   self.assertEqual(self.solve(ctx,p,out),0)
   self.assertEqual(bytes(ctx),before);self.assertEqual(bytes(out),output)
  self.assertEqual(self.solve(ctx,good,out),1);before=bytes(ctx);output=bytes(out)
  for offset,value in [(3,1),(4,18),(8,1),(18,9),(19,204),(27,1),(4095,1)]:
   p=page(3,roots);p[offset]=value;p=crc_page(p)
   self.assertEqual(self.roots(ctx,p,out),0);self.assertEqual(bytes(ctx),before);self.assertEqual(bytes(out),output)
  self.lib.s3_rs_rpc_reset(c.byref(ctx));self.assertEqual(bytes(ctx),bytes(c.sizeof(ctx)))
  self.assertEqual(self.roots(ctx,page(3,roots),out),0)
  self.assertEqual(self.solve(ctx,good,out,epoch=18),0)
 def test_upstream_and_locator_failures_do_not_publish_partial_corrections(self):
  cases,syn,roots=self.records(0);syn[0]=struct.pack('<HB16s',0,1,bytes(16))
  roots[0]=struct.pack('<HB8sB',0,255,bytes(8),0)
  # For a nonzero-error case, zero roots cannot satisfy the locator degree.
  index=next(i for i,v in enumerate(cases) if i and v[4])
  roots[index]=struct.pack('<HB8sB',index,0,bytes(8),0)
  ctx=Context();out=Page();self.assertEqual(self.solve(ctx,page(1,syn),out),1)
  self.assertEqual(bytes(out[18:29]),bytes([1])+bytes(10))
  self.assertEqual(self.roots(ctx,page(3,roots),out),1)
  for i in (0,index):self.assertEqual(bytes(out[16+i*12:28+i*12]),struct.pack('<HB8sB',i,1,bytes(8),0))
if __name__=='__main__':unittest.main()
