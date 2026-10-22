"""Actual tile data path + SDRAM controller/arbiter; other clients are proxies.
The global tile/config descriptor supplier remains a testbench, not receiver RTL.
Memory contains deterministic arbitrary history; cold-fill validity is untested.
"""
import hashlib,json,os,re,shutil,subprocess,tempfile,unittest
from pathlib import Path
from experiments.t_time_block_layout import allocation,spans
from experiments.t_time_three_buffer_schedule import requests
from test_t_time_three_buffer_controller import TB
from test_sdf_delay_cache import memory_system
ROOT=Path(__file__).resolve().parents[1]
FILES=['experiments/t_time_tile_store.sv','experiments/t_time_tile_dma_direct.sv',
 'experiments/sdram_client_arbiter_lease128_direct.sv','experiments/dual_sdram_refresh_predecode.sv']
def initial_byte(address):
 word=(0xbadc0ffe^((address//4)*0x9e3779b9))&0xffffffff
 return (word>>(8*(address%4)))&255

def fixture(tiles,batch=100,competition=False):
 entries,ring,scratch=allocation(3,[4]*13)
 streams,meta=requests(batch=batch,competing=competition)
 # The actual engine replaces the old synthetic transform producer only.
 streams[2]=[]
 start_base=ring+((batch-1)%3)*scratch
 configs=[];expected=[];writes=[]
 for tile in range(tiles):
  tile_base=start_base+tile*96
  out=[[None]*96 for _ in range(16)]
  for c,(_,_,depth,base,size) in enumerate(entries[tile*16:tile*16+16]):
   current=bytes(initial_byte(tile_base+t*29952+c*6+j)for t in range(16)for j in range(6))
   if not depth:
    configs.append(1<<93);result=current
   else:
    ws=((batch-1)*16)%size*6;rs=(((batch-1)*16-depth)%size)*6
    configs.append(base|((base+size*6)<<23)|((base+ws)<<47)|((base+rs)<<70))
    fresh={(ws+k)%(size*6):v for k,v in enumerate(current)}
    # Per-byte reference addresses; no BL8 grouping or alignment algorithm.
    result=bytes(fresh.get((rs+k)%(size*6),initial_byte(base+(rs+k)%(size*6)))for k in range(96))
    for k,a in enumerate(spans(base,ws,96,size*6)):
     writes.append((a//4,int.from_bytes(current[k*32:(k+1)*32],'little')))
   for t in range(16):out[t][c*6:c*6+6]=result[t*6:t*6+6]
  for t in range(16):
   for offset in range(0,96,4):expected.append(int.from_bytes(bytes(out[t][offset:offset+4]),'little'))
  for t in range(16):
   for offset in range(0,96,32):writes.append(((tile_base+t*29952+offset)//4,int.from_bytes(bytes(out[t][offset:offset+32]),'little')))
 return streams,meta,configs,expected,writes,start_base

ENGINE=r'''
reg evstart=0,running=0;wire erstart,ecfg,ev,ew,edone,collision;
wire[20:0]ea;wire[255:0]ed;
integer tile_number=0,config_number=0,checked=0,wrchecked=0,t,b,ma;
reg[93:0]configs[0:TILES*16-1];reg[31:0]expected[0:TILES*384-1];
reg[276:0]expected_writes[0:WRITES-1];
wire[93:0]conf=config_number<TILES*16?configs[config_number]:94'd0;
wire[5:0]av=(v&6'b111011)|{3'd0,ev,2'd0};
wire[5:0]aw=(w&6'b111011)|{3'd0,ew,2'd0};
wire[125:0]aa={addr[125:63],ea,addr[41:0]};
t_time_tile_dma engine(clk,rst,evstart,erstart,23'(SCRATCH_BASE+tile_number*96),16'd29952,
 config_number<TILES*16,ecfg,conf[93],conf[22:0],conf[46:23],conf[69:47],conf[92:70],
 ev,ready[2],ew,ea,ed,rv[2],result,edone,collision);
initial begin
 $readmemh("configs.hex",configs);$readmemh("expected.hex",expected);$readmemh("writes.hex",expected_writes);
end
always @(negedge clk)if(start>=0&&!running&&tile_number<TILES&&erstart)evstart=1;
always @(posedge clk)begin
 if(evstart&&erstart)begin running<=1;evstart<=0;end
 if(ecfg&&config_number<TILES*16)config_number<=config_number+1;
 if(collision)$fatal(1,"tile read/write collision");
 if(ev&&ready[2]&&ew)begin
  if(wrchecked>=WRITES || {ed,ea}!==expected_writes[wrchecked])$fatal(1,"write mismatch at %0d address %0d expected %0d",wrchecked,ea,expected_writes[wrchecked][20:0]);
  wrchecked=wrchecked+1;
 end
 if(edone)begin
  for(t=0;t<16;t=t+1)for(b=0;b<24;b=b+1)begin
   ma=(SCRATCH_BASE+tile_number*96+t*29952)/4+b;
   if(memory.mem[ma]!==expected[checked])$fatal(1,"output mismatch tile %0d time %0d word %0d actual %h expected %h",tile_number,t,b,memory.mem[ma],expected[checked]);
   checked=checked+1;
  end
  tile_number<=tile_number+1;running<=0;finish[2]=cycle-start;
  if(tile_number==TILES-1)begin
   if(wrchecked!=WRITES)$fatal(1,"write count");
   $display("ENGINE tiles=%0d finish=%0d checked_words=%0d checked_writes=%0d",TILES,cycle-start,checked,wrchecked);
   if(cycle-start>2566080)begin misses[2]=1;late[2]=cycle-start-2566080;end
  end
 end
end
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class TileDMATest(unittest.TestCase):
 def test_real_data_and_deadlines(self):
  tiles=int(os.environ.get('TTI_TILE_COUNT','6'));competition=os.environ.get('TTI_COMPETING','0')=='1'
  streams,meta,configs,expected,writes,start_base=fixture(tiles,competition=competition)
  flat=[x for stream in streams for x in stream];counts=list(map(len,streams));start=0;init=[]
  for i,n in enumerate(counts):init.append(f'pos[{i}]={start};ending[{i}]={start+n};');start+=n
  tb=TB.replace('COUNT',str(len(flat))).replace('INIT',''.join(init))
  tb=tb.replace('v,ready,w,addr,1536\'d0',"av,ready,aw,aa,{768'd0,ed,512'd0}")
  tb=tb.replace('if(rv[i])begin','if(i!=2&&rv[i])begin')
  tb=tb.replace('if(all_done)begin','if(tile_number<TILES||running)all_done=0;\n  if(all_done)begin')
  decl=tb[tb.index('reg[117:0]'):tb.index('initial begin')]
  tb=tb.replace(decl,'',1).replace('sdram_client_arbiter arb',decl+ENGINE+'\nsdram_client_arbiter arb',1)
  tb=tb.replace('TILES',str(tiles)).replace('WRITES',str(len(writes))).replace('SCRATCH_BASE',str(start_base))
  tb+=memory_system().replace('MEM_WORDS=4096','MEM_WORDS=2097152').replace("mem[i]=32'hbadc0ffe;","mem[i]=32'hbadc0ffe^(i*32'h9e3779b9);")
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(tb)
   packed=[(deadline<<86)|(release<<54)|(post<<38)|(pre<<22)|(wr<<21)|(address//4)for release,wr,address,pre,post,deadline in flat]
   for name,data,width in [('requests',packed,30),('configs',configs,24),('expected',expected,8),('writes',[(data<<21)|a for a,data in writes],70)]:
    (p/f'{name}.hex').write_text(''.join(f'{x:0{width}x}\n'for x in data))
   r=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),*[str(ROOT/f)for f in FILES],str(p/'tb.sv')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run(['vvp',str(p/'sim')],cwd=d,capture_output=True,text=True,timeout=480)
   print(r.stdout,flush=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
  clients=[dict(zip(('id','finish','late_requests','max_lateness'),map(int,v)))for v in re.findall(r'CLIENT id=(\d+) finish=(\d+) late_requests=(\d+) max_lateness=(\d+)',r.stdout)]
  self.assertEqual(len(clients),6);self.assertIn(f'checked_words={tiles*384}',r.stdout)
  paths=FILES+['tests/test_t_time_tile_dma_direct.py','tests/test_t_time_three_buffer_controller.py','tests/test_sdf_delay_cache.py','tests/test_common_clock_sdram.py','experiments/t_time_three_buffer_schedule.py','experiments/t_time_block_layout.py']
  report=dict(scope=__doc__,tiles=tiles,competition=competition,clients=clients,
    full_epoch=tiles==312,all_declared_deadlines_pass=all(c['late_requests']==0 for c in clients),
    checked_output_words=len(expected),checked_writes=len(writes),descriptor_supplier_is_RTL=False,
    whole_receiver_verified=False,source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()for f in paths})
  target=os.environ.get('TTI_DMA_REPORT','reports/t-time-tile-dma-static-smoke.json')
  (ROOT/target).write_text(json.dumps(report,indent=2)+'\n')
