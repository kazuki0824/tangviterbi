"""Two independent input ports, delayed tagged memory acks and real payloads."""
from pathlib import Path
import json
import random
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]

class StoreTest(unittest.TestCase):
    def test_payload_order_and_memory_completion(self):
        out=ROOT/'build/s3-rx-page-store'
        out.mkdir(parents=True,exist_ok=True)
        rng=random.Random(0x2911)
        raw=rng.randbytes(64*4096)
        tokens=[[],[]]
        for p in range(64):
            t=tokens[p%2]
            t.extend([(1<<32)|(0xd711<<16)|17,(2<<32)|p*4096,(3<<32)|4096])
            t.extend(((8<<32) if w==1023 else 0)|int.from_bytes(raw[p*4096+4*w:p*4096+4*w+4],'little') for w in range(1024))
        for port in range(2):
            (out/f't{port}.hex').write_text(''.join(f'{t:09x}\n' for t in tokens[port]))
        tb=r'''module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0;reg[1:0] iv=0;wire[1:0] ir;
reg[35:0] t0=0,t1=0;reg upstream=0,mr=0,av=0,at=0,retire=0;
wire mv,mt,pv,fault;wire[13:0] ma;wire[31:0] md,po;wire[3:0] ps;
s3_rx_page_store dut(clk,rst,16'd17,iv,ir,t0,t1,upstream,mv,mr,ma,md,mt,av,at,pv,po,ps,retire,fault);
reg[35:0] input0[0:32863],input1[0:32863];
reg[31:0] memory[0:16383];
reg[13:0] qaddr[0:1][0:4095];reg[31:0] qdata[0:1][0:4095];
integer due[0:1][0:4095];integer head0=0,head1=0,tail0=0,tail1=0;
integer n0=0,n1=0,cycles=0,pages=0,read_index=0,f,reads=0;
reg consume=0;reg[31:0] rng=32'h94713287;
reg was_stalled=0;reg[46:0] held;
reg offer0=0,offer1=0;
task reset;begin
 @(negedge clk);rst=0;iv=0;av=0;retire=0;upstream=0;repeat(3)@(negedge clk);rst=1;@(negedge clk);
end endtask
initial begin
 $readmemh("t0.hex",input0);$readmemh("t1.hex",input1);f=$fopen("output.hex","w");reset();
 while(pages<64)begin
  @(negedge clk);rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);
  if(!offer0&&n0<32864&&rng[1:0]!=0)offer0=1;
  if(!offer1&&n1<32864&&rng[3:2]!=0)offer1=1;
  iv={offer1,offer0};if(n0<32864)t0=input0[n0];if(n1<32864)t1=input1[n1];
  mr=rng[5:4]!=0;av=0;at=0;retire=0;consume=0;
  if(head0!=tail0 && due[0][head0%4096]<=cycles && rng[7])begin av=1;at=0;end
  else if(head1!=tail1 && due[1][head1%4096]<=cycles && rng[8])begin av=1;at=1;end
  if(pv&&rng[11:9]!=0)begin
   if(po!==4096*pages)$fatal(1,"page order");
   consume=1;retire=read_index==1023;
  end
  @(posedge clk);
  if(was_stalled && (!mv || {mt,ma,md}!==held))$fatal(1,"memory offer changed while stalled");
  was_stalled=mv&&!mr;held={mt,ma,md};
  if(iv[0]&&ir[0])begin n0=n0+1;offer0=0;end
  if(iv[1]&&ir[1])begin n1=n1+1;offer1=0;end
  if(av)begin
   if(at)begin memory[qaddr[1][head1%4096]]=qdata[1][head1%4096];head1=head1+1;end
   else begin memory[qaddr[0][head0%4096]]=qdata[0][head0%4096];head0=head0+1;end
  end
  if(mv&&mr)begin
   if(mt)begin
    qaddr[1][tail1%4096]=ma;qdata[1][tail1%4096]=md;due[1][tail1%4096]=cycles+1+rng[16:12];tail1=tail1+1;
   end else begin
    qaddr[0][tail0%4096]=ma;qdata[0][tail0%4096]=md;due[0][tail0%4096]=cycles+32+rng[16:12];tail0=tail0+1;
   end
  end
  if(consume)begin
   $fdisplay(f,"%08x",memory[ps*1024+read_index]);reads=reads+1;
   if(retire)begin pages=pages+1;read_index=0;end else read_index=read_index+1;
  end
  #1;if(fault)$fatal(1,"unexpected store fault at pages=%0d input=%0d/%0d",pages,n0,n1);
  cycles=cycles+1;if(cycles>300000)$fatal(1,"deadlock");
 end
 $fclose(f);if(reads!=65536 || head0!=tail0 || head1!=tail1)$fatal(1,"unretired data");
 reset();av=1;at=0;repeat(3)@(negedge clk);
 if(!fault||mv||pv||ir)$fatal(1,"unowned ack not poisoned");
 reset();upstream=1;repeat(3)@(negedge clk);upstream=0;repeat(3)@(negedge clk);
 if(!fault||mv||pv||ir)$fatal(1,"upstream fault not sticky");
 $display("PASS 64 payload pages and delayed/reversed port acknowledgments");$finish;
end
endmodule'''
        (out/'tb.sv').write_text(tb)
        sources=['s3_page_guard.sv','s3_page_reorder.sv','s3_rx_page_store.sv']
        c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),
             *[str(ROOT/'rtl'/p) for p in sources],str(out/'tb.sv')],text=True,capture_output=True)
        self.assertEqual(c.returncode,0,c.stderr)
        r=subprocess.run(['vvp','sim'],cwd=out,text=True,capture_output=True,timeout=45)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        got=b''.join(int(s,16).to_bytes(4,'little') for s in (out/'output.hex').read_text().split())
        self.assertEqual(len(got),len(raw))
        # Word-level first mismatch avoids printing megabytes of byte diffs.
        for i in range(0,len(raw),4):self.assertEqual(got[i:i+4],raw[i:i+4],f'byte offset {i}')
        (out/'result.json').write_text(json.dumps(dict(pages=64,checked_payload_bytes=len(raw),
            output=r.stdout.strip(),scope='tagged behavioral memory backend, not physical PSRAM',
            receiver_adopted=False),indent=2)+'\n')

if __name__=='__main__':unittest.main()
