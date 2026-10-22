"""Ingress queue oracle checks all five wrapper lanes through real arbitration."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TB = r'''
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0;reg[4:0]v=0,w=0,rr=31;
reg[104:0]a=0;reg[1279:0]d=0;reg[159:0]m=0;
wire[4:0]ready,rv;wire[255:0]rd;wire initialized,fault;
wire er;wire[31:0]fft;wire[2:0]cmd;wire[1:0]bank;
wire[10:0]address;wire cke,oe;wire[3:0]dqm;wire[31:0]dq;
sdf_sdram_service dut(clk,resetn,1'b0,er,1'b0,12'd0,fft,1'b0,12'd0,32'd0,
 v,ready,w,a,d,m,rv,rr,rd,initialized,fault,cmd,bank,address,cke,dqm,oe,dq,32'h13579bdf);
reg[4:0]occupied=0,ew=0;
reg[20:0]ea[0:4];reg[255:0]ed[0:4];reg[31:0]em[0:4];
integer accepted[0:4],issued[0:4],completed[0:4];
integer cycle,i,j,seed=715,stalls=0;
initial begin
 for(i=0;i<5;i=i+1)begin accepted[i]=0;issued[i]=0;completed[i]=0;end
 for(cycle=0;cycle<60000;cycle=cycle+1)begin
  @(negedge clk);resetn=(cycle>2);
  v=cycle<55000 ? $random(seed) : 0;w=$random(seed);w[1]=0;
  rr=(cycle%17<8) ? 0 : 31;
  for(i=0;i<5;i=i+1)begin
   a[i*21+:21]=($random(seed)&21'h1ffff8);
   m[i*32+:32]=$random(seed);
   for(j=0;j<8;j=j+1)d[i*256+j*32+:32]=$random(seed);
  end
  @(posedge clk);
  if(resetn)begin
   for(i=0;i<5;i=i+1)begin
    if(dut.held_valid[i] && !dut.held_ready[i])stalls=stalls+1;
    if(dut.held_valid[i] && dut.held_ready[i])begin
     if(!occupied[i])$fatal(1,"spurious request lane %0d",i);
     if(dut.held_address[i*21+:21]!==ea[i] || dut.held_write[i]!==ew[i] ||
      dut.held_data[i*256+:256]!==ed[i] || dut.held_dqm[i*32+:32]!==em[i])
      $fatal(1,"descriptor corrupt lane %0d",i);
     occupied[i]=0;issued[i]=issued[i]+1;
    end
    if(v[i] && ready[i])begin
     if(occupied[i])$fatal(1,"overflow lane %0d",i);
     occupied[i]=1;ea[i]=a[i*21+:21];ew[i]=w[i];
     ed[i]=(i==1) ? 256'd0 : d[i*256+:256];
     em[i]=(i==1) ? 32'd0 : m[i*32+:32];accepted[i]=accepted[i]+1;
    end
    if(rv[i] && rr[i])completed[i]=completed[i]+1;
   end
  end
  #1;if(fault)$fatal(1,"service fault");
 end
 for(i=0;i<5;i=i+1)begin
  if(occupied[i] || accepted[i]<50 || accepted[i]!=issued[i] || issued[i]!=completed[i])
   $fatal(1,"lane %0d unfinished accepted %0d issued %0d complete %0d",i,accepted[i],issued[i],completed[i]);
  $display("lane %0d accepted/issued/completed=%0d",i,completed[i]);
 end
 if(stalls<10000)$fatal(1,"stall coverage");
 $display("PASS five lanes, stalls=%0d",stalls);$finish;
end
endmodule
'''


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'), 'Icarus required')
class BackgroundHoldTest(unittest.TestCase):
    def test_all_lanes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            # The collector applies the same rename before reading the wrapper.
            original = (ROOT / 'rtl/sdf_sdram_service.sv').read_text()
            (p / 'service.sv').write_text(original.replace(
                'module sdf_sdram_service(', 'module sdf_sdram_service_unbuffered('))
            (p / 'tb.sv').write_text(TB)
            subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', str(p / 'sim'),
                            str(p / 'tb.sv'), str(p / 'service.sv'),
                            str(ROOT / 'experiments/sdf_background_hold_service.sv'),
                            *(str(ROOT / 'rtl' / f) for f in ('sdram_request_slot.sv',
                              'sdf_delay_cache.sv', 'sdram_client_arbiter.sv', 'dual_sdram_burst.sv'))], check=True)
            result = subprocess.run(['vvp', str(p / 'sim')], capture_output=True,
                                    text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS five lanes', result.stdout)
            print(result.stdout.strip())
