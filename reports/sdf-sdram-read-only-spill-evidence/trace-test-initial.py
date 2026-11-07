"""Cycle trace equivalence for the dedicated T spill read port; illegal write guard.
Uses arbitrary shared DQ samples, not an independent physical SDRAM model.
"""
import hashlib,json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REFERENCE=ROOT/'reports/sdf-sdram-read-only-spill-evidence/reference-service.sv'
CANDIDATE=ROOT/'experiments/read_only_spill_service.sv'
TB=r'''
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,compare=1;reg[4:0]cv=0,cw=0,crr=0,waiting=0;
reg[104:0]ca=0;reg[1279:0]cd=0;reg[159:0]cm=0;
wire[4:0]ar,br,av,bv;wire[255:0]ad,bd;
wire[31:0]ard,brd,ao,bo;reg[31:0]din=0;
wire aready,bready,ai,bi,af,bf,acke,bcke,aoe,boe;
wire[2:0]acmd,bcmd;wire[1:0]abank,bbank;wire[10:0]aa,ba;wire[3:0]am,bm;
reg[31:0]rng=32'h23456789;
integer cycles=0,total=0,i,j,done[0:4],accepted=0,stalled=0;
'''
PORTS=r'''(
 .clk(clk),.resetn(resetn),.sample_accept(1'b0),.external_ready(Pready),
 .read_enable(1'b0),.read_address(12'd0),.read_data(Prd),
 .write_enable(1'b0),.write_address(12'd0),.write_data(32'd0),
 .bg_valid(cv),.bg_ready(Pr),.bg_write(cw),.bg_address(ca),.bg_data(cd),.bg_dqm(cm),
 .bg_rsp_valid(Pv),.bg_rsp_ready(crr),.bg_rsp_data(Pd),.initialized(Pi),.fault(Pf),
 .sd_cmd(Pcmd),.sd_bank(Pbank),.sd_address(Pa),.sd_cke(Pcke),.sd_dqm(Pm),
 .dq_oe(Poe),.dq_out(Po),.dq_in(din));
'''
# Map two identical external port bundles to the reference and candidate.
def port_text(prefix):
 s=PORTS
 for name in ('ready','bank','cmd','cke','rd','oe','a','r','v','d','i','f','m','o'):
  s=s.replace('P'+name, prefix+name)
 return s
TB+= 'generic_service baseline'+port_text('a')+'sdf_sdram_service candidate'+port_text('b')+r'''
task random_step;
 begin rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);end
endtask
always @(negedge clk)if(resetn && compare)begin
 random_step();din=rng;crr=rng[4:0];
 if(cycles%211<30)crr=0;
 for(i=0;i<5;i=i+1)if(!cv[i] && !waiting[i] && done[i]<100)begin
  random_step();ca[i*21+:21]={rng[20:3],3'd0};
  cw[i]=i==1 ? 1'b0 : i==0 ? 1'b1 : rng[0];
  random_step();cm[i*32+:32]=rng;
  for(j=0;j<8;j=j+1)begin random_step();cd[i*256+j*32+:32]=rng;end
  cv[i]=1;
 end
end
always @(posedge clk)begin
 cycles=cycles+1;
 if(resetn && compare)begin
  for(i=0;i<5;i=i+1)begin
   if(cv[i] && ar[i])begin cv[i]<=0;waiting[i]<=1;accepted=accepted+1;end
   if(av[i] && !crr[i])stalled=stalled+1;
   if(av[i] && crr[i])begin waiting[i]<=0;done[i]=done[i]+1;total=total+1;end
  end
 end
 #1;
 if(resetn && compare)begin
  if({ar,av,ai,aready,af,acmd,abank,aa,acke,am,aoe}!==
     {br,bv,bi,bready,bf,bcmd,bbank,ba,bcke,bm,boe})$fatal(1,"trace control mismatch %0d",cycles);
  if(aoe && ao!==bo)$fatal(1,"DQ write mismatch");
  if(|av && ad!==bd)$fatal(1,"read/ack response mismatch");
  if(af || bf)$fatal(1,"unexpected legal traffic fault");
 end
 if(cycles>200000)$fatal(1,"timeout");
end
initial begin
 for(i=0;i<5;i=i+1)done[i]=0;
 repeat(3)@(negedge clk);resetn=1;
 wait(total==500);@(negedge clk);compare=0;cv=0;crr=31;
 if(accepted!=500 || stalled==0)$fatal(1,"coverage");
 cv=2;cw=2;
 repeat(3)begin @(negedge clk);if(br[1])$fatal(1,"illegal write acknowledged");end
 if(!bf)$fatal(1,"missing read-only fault");
 cv=0;cw=0;resetn=0;repeat(3)@(negedge clk);
 if(bf)$fatal(1,"fault reset");
 $display("PASS completed=%0d accepted=%0d stalled=%0d cycles=%0d illegal_write_blocked=1",total,accepted,stalled,cycles);$finish;
end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class ReadOnlySpillTest(unittest.TestCase):
 def test_reference_trace_and_illegal_write(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(TB)
   (p/'reference.sv').write_text(REFERENCE.read_text().replace('module sdf_sdram_service(', 'module generic_service('))
   subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),str(p/'reference.sv'),str(CANDIDATE),
    *(str(ROOT/'rtl'/f) for f in ('sdf_delay_cache.sv','sdram_client_arbiter.sv','dual_sdram_burst.sv'))],check=True,timeout=30)
   run=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=30)
   self.assertEqual(run.returncode,0,run.stdout+run.stderr);self.assertIn('PASS completed=500',run.stdout)
  result=dict(scope=__doc__,summary=run.stdout.strip(),source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in
    (Path(__file__),REFERENCE,CANDIDATE,ROOT/'rtl/sdf_delay_cache.sv',ROOT/'rtl/sdram_client_arbiter.sv',ROOT/'rtl/dual_sdram_burst.sv')})
  print(result['summary'])
  if os.environ.get('READ_ONLY_SPILL_REPORT'):Path(os.environ['READ_ONLY_SPILL_REPORT']).write_text(json.dumps(result,indent=2)+'\n')
