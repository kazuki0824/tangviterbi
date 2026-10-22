"""Real BL8 controller + existing arbiter, exact TTI request address trace.
TTI values/transposition are checked separately. Other clients are proxies.
No synthesized producer, core timing closure, RF, RS/TS or electrical PHY proof.
"""
import hashlib,json,re,subprocess,tempfile,unittest,shutil
from pathlib import Path
from experiments.t_time_three_buffer_schedule import requests
from test_sdf_delay_cache import memory_system
ROOT=Path(__file__).resolve().parents[1]
FILES=['rtl/sdram_client_arbiter.sv','experiments/dual_sdram_refresh_predecode.sv']
TB=r'''
module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0;reg[5:0]v=0,w=0,busy=0;wire[5:0]ready,rv;
reg[125:0]addr=0;wire[255:0]result;
wire qv,qr,qw,qrv,qrr;wire[20:0]qa;wire[255:0]qd,rd;wire[31:0]mask;
sdram_client_arbiter arb(clk,rst,v,ready,w,addr,1536'd0,192'd0,rv,6'h3f,result,qv,qr,qw,qa,qd,mask,qrv,qrr,rd);
memory_system memory(clk,rst,qv,qr,qw,qa,qd,qrv,rd);
reg[117:0]descriptors[0:COUNT-1];
integer pos[0:5],ending[0:5],ready_at[0:5],finish[0:5],misses[0:5],late[0:5];
integer cycle=0,start=-1,i,j,eligible,deadline,lateness,all_done;
initial begin
 $readmemh("requests.hex",descriptors);
 INIT
 for(i=0;i<6;i=i+1)begin ready_at[i]=0;finish[i]=0;misses[i]=0;late[i]=0;end
 repeat(3)@(negedge clk);rst=1;
end
always @(negedge clk)if(start>=0)begin
 for(j=0;j<6;j=j+1)if(!busy[j]&&pos[j]<ending[j])begin
  eligible=start+descriptors[pos[j]][85:54];
  if(ready_at[j]>eligible)eligible=ready_at[j];
  eligible=eligible+descriptors[pos[j]][37:22];
  if(cycle>=eligible)begin
   v[j]=1;w[j]=descriptors[pos[j]][21];addr[j*21+:21]=descriptors[pos[j]][20:0];
  end
 end
end
always @(posedge clk)begin
 cycle=cycle+1;
 if(rst && memory.initialized && start<0)start=cycle;
 if(start>=0)begin
  for(i=0;i<6;i=i+1)begin
   if(v[i]&&ready[i])begin busy[i]=1;v[i]<=0;end
   if(rv[i])begin
    deadline=descriptors[pos[i]][117:86];lateness=cycle-start-deadline;
    if(lateness>0)misses[i]=misses[i]+1;
    if(lateness>late[i])late[i]=lateness;
    ready_at[i]=cycle+descriptors[pos[i]][53:38];
    finish[i]=ready_at[i]-start;pos[i]=pos[i]+1;busy[i]=0;
   end
  end
  all_done=1;
  for(i=0;i<6;i=i+1)if(pos[i]!=ending[i] || busy[i] || cycle<ready_at[i])all_done=0;
  if(all_done)begin
   for(i=0;i<6;i=i+1)$display("CLIENT id=%0d finish=%0d late_requests=%0d max_lateness=%0d",i,finish[i],misses[i],late[i]);
   $display("DONE clocks=%0d refresh_gap=%0d",cycle-start,memory.max_ref_gap);$finish;
  end
 end
 if(cycle>12000000)$fatal(1,"timeout");
end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class ControllerScheduleTest(unittest.TestCase):
 def test_three_buffer_trace(self):
  results=[]
  for serial,competition in [(False,False),(True,False),(False,True)]:
   streams,meta=requests(serialized_bytes=serial,competing=competition)
   counts=list(map(len,streams));flat=[x for stream in streams for x in stream];start=0;init=[]
   for i,n in enumerate(counts):init.append(f'pos[{i}]={start};ending[{i}]={start+n};');start+=n
   tb=TB.replace('COUNT',str(len(flat))).replace('INIT',''.join(init))
   # The original pin model consumes every response. Arbiter does too here;
   # no client response backpressure is used in this timing experiment.
   tb+=memory_system().replace('MEM_WORDS=4096','MEM_WORDS=2097152')
   with tempfile.TemporaryDirectory() as d:
    p=Path(d);(p/'tb.sv').write_text(tb)
    packed=[(deadline<<86)|(release<<54)|(post<<38)|(pre<<22)|(wr<<21)|(address//4) for release,wr,address,pre,post,deadline in flat]
    (p/'requests.hex').write_text(''.join(f'{x:030x}\n'for x in packed))
    r=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),*[str(ROOT/f)for f in FILES],str(p/'tb.sv')],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stderr)
    r=subprocess.run(['vvp',str(p/'sim')],cwd=d,capture_output=True,text=True,timeout=180)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr);print(meta,flush=True);print(r.stdout,flush=True)
    clients=[dict(zip(('id','finish','late_requests','max_lateness'),map(int,values)))for values in re.findall(r'CLIENT id=(\d+) finish=(\d+) late_requests=(\d+) max_lateness=(\d+)',r.stdout)]
    self.assertEqual(len(clients),6)
    results.append(dict(**meta,clients=clients,all_declared_deadlines_pass=all(c['late_requests']==0 and c['finish']<=meta['epoch_clocks']for c in clients)))
  files=FILES+['experiments/t_time_three_buffer_schedule.py','experiments/t_time_block_layout.py','tests/test_t_time_three_buffer_controller.py','tests/test_sdf_delay_cache.py','tests/test_common_clock_sdram.py']
  report=dict(scope=__doc__,cases=results,source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()for f in files},whole_receiver_verified=False)
  (ROOT/'reports/t-time-three-buffer-controller.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':unittest.main()
