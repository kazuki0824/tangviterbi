"""PSRAM command protocol, buffered payloads, deadlines and fail-stop cases."""
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]

class PsramTest(unittest.TestCase):
    def run_tb(self,name,body,extra=()):
        out=ROOT/'build/s3-psram'/name
        out.mkdir(parents=True,exist_ok=True)
        (out/'tb.sv').write_text(body)
        sources=['rtl/s3_psram_burst.sv','tests/fixtures/w955_pair_model.sv',*extra]
        c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),
             *[str(ROOT/p) for p in sources],str(out/'tb.sv')],text=True,capture_output=True)
        self.assertEqual(c.returncode,0,c.stderr)
        r=subprocess.run(['vvp','sim'],cwd=out,text=True,capture_output=True,timeout=45)
        (out/'simulation.log').write_text(r.stdout+r.stderr)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertIn('PASS',r.stdout)
        return out,r.stdout

    def test_buffered_pair_payload_and_ack(self):
        # 256 KiB exact data through 1024 physical 256-byte write bursts and
        # 1024 read bursts. Interleave producers, independently delayed dies,
        # random consumer stalls and read/write arbitration.
        tb=r'''module tb;
reg clk=0;always #5 clk=~clk;reg rst=0;
wire cv,cr,cw,wv,wr,rv,bd,bi,bf,pr,pc,pk,pd,pw,re;
wire[20:0] ca;wire[31:0] wd,rd;wire[15:0] tf,ts,x0,x1;wire[1:0] xv;
reg iv=0,it=0,rr=0,rt=0;reg[20:0] ia=0,ra=0;reg[31:0] id=0;
wire ir,av,at,rready,rvalid,rlast,qf;wire[31:0] rdata;
s3_psram_queue queue(clk,rst,1'b0,iv,ir,it,ia,id,av,at,rr,rready,ra,
 rvalid,rt,rdata,rlast,cv,cr,cw,ca,wv,wr,wd,rv,rd,bd,bf,qf);
s3_psram_burst #(.POWERUP_CYCLES(16),.RESET_CYCLES(2)) dut(
 clk,rst,1'b0,cv,cw,ca,cr,wv,wd,wr,rv,rd,bd,bi,bf,
 pr,pc,pk,pd,pw,tf,ts,re,xv,x0,x1,1'b0);
integer mw,mreads,bursts,maxcs;
w955_pair_model #(.DIE0_DELAY(1),.DIE1_DELAY(3)) model(
 clk,rst,pr,pc,pk,pd,pw,tf,ts,1'b0,1'b0,1'b0,xv,x0,x1,mw,mreads,bursts,maxcs);
function[31:0] pattern(input integer a);begin pattern=(32'h9e3779b9*a)^32'h9ac9f710^(a>>3);end endfunction
integer n[0:1],acked[0:1],cycles=0,read_block=0,read_word=0,total_reads=0,f;
integer outstanding=0,issued_reads=0,first_cycle,last_cycle,acks=0;
reg[31:0] rng=32'h18039287;reg[53:0] held;reg was_stalled=0;
reg[20:0] chosen_address;
initial begin
 n[0]=0;n[1]=0;acked[0]=0;acked[1]=0;
 f=$fopen("output.hex","w");repeat(3)@(negedge clk);rst=1;
 while(!bi)begin @(negedge clk);if(bf)$fatal(1,"init failure");end
 first_cycle=cycles;
 while(total_reads<65536)begin
  @(negedge clk);rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);
  // Each port sends alternating 64-word blocks at no more than one word per
  // five clocks (20 Mword/s ceiling). Faster producer has 2x opportunity.
  if(!iv)begin
   it=(cycles%10==0);iv=(cycles%5==0)&&n[it]<32768;
   ia=((n[it]/64)*128)+(it?64:0)+(n[it]%64);id=pattern(ia);
  end
  rr=0;rt=rng[3:0]!=0;
  if(!outstanding&&read_block<1024&&acked[read_block%2]>=(read_block/2+1)*64)begin
   rr=1;ra=read_block*64;
  end
  @(posedge clk);
  if(was_stalled&&(!iv||{it,ia,id}!==held))$fatal(1,"source instability");
  was_stalled=iv&&!ir;held={it,ia,id};
  if(iv&&ir)begin n[it]=n[it]+1;#0.01;iv=0;end
  if(av)begin
   acked[at]=acked[at]+1;acks=acks+1;
   if(acks>mw)$fatal(1,"ack before DDR write completion");
  end
  if(rr&&rready)begin outstanding=1;issued_reads=issued_reads+1;end
  if(rvalid&&rt)begin
   if(rdata!==pattern(read_block*64+read_word))$fatal(1,"read mismatch block=%d word=%d got=%h expected=%h",read_block,read_word,rdata,pattern(read_block*64+read_word));
   if(rlast!==(read_word==63))$fatal(1,"read boundary");
   $fdisplay(f,"%08x",rdata);total_reads=total_reads+1;
   if(rlast)begin read_block=read_block+1;read_word=0;outstanding=0;end else read_word=read_word+1;
  end
  #1;if(qf||bf)$fatal(1,"fault cycles=%d ack=%d/%d",cycles,acked[0],acked[1]);
  cycles=cycles+1;if(cycles>1000000)$fatal(1,"deadlock");
 end
 $fclose(f);if(n[0]!=32768||n[1]!=32768||acks!=65536||issued_reads!=1024)$fatal(1,"counts");
 $display("PASS bytes=262144 writes=%0d reads=%0d bursts=%0d cycles=%0d max_cs_cycles=%0d",mw,total_reads,bursts,cycles,maxcs);$finish;
end
endmodule'''
        out,log=self.run_tb('payload',tb,['rtl/s3_psram_queue.sv'])
        got=b''.join(int(x,16).to_bytes(4,'little') for x in (out/'output.hex').read_text().split())
        expected=b''.join((((0x9e3779b9*a)^0x9ac9f710^(a>>3))&0xffffffff).to_bytes(4,'little') for a in range(65536))
        self.assertEqual(hashlib.sha256(got).hexdigest(),hashlib.sha256(expected).hexdigest())
        (out/'result.json').write_text(json.dumps(dict(checked_bytes=len(got),sha256=hashlib.sha256(got).hexdigest(),
             simulation=log.strip(),scope='clock-pair protocol/queue oracle; physical IO not simulated',receiver_adopted=False),indent=2)+'\n')

    def test_controller_fail_stop(self):
        tb=r'''module tb;
reg clk=0;always #5 clk=~clk;reg rst=0,abort=0,cv=0,cw=0,wv=1,suppress=0,badcr=0,badid=0,pf=0;
reg[20:0] ca=0;wire cr,wr,rv,done,init,fault,pr,pc,pk,pd,pw,re;
wire[31:0] rd;wire[15:0] tf,ts,x0,x1;wire[1:0] xv;integer mw,mr,mb,maxcs;
s3_psram_burst #(.POWERUP_CYCLES(16),.RESET_CYCLES(2)) dut(
 clk,rst,abort,cv,cw,ca,cr,wv,32'habcdef01,wr,rv,rd,done,init,fault,
 pr,pc,pk,pd,pw,tf,ts,re,xv,x0,x1,pf);
w955_pair_model model(clk,rst,pr,pc,pk,pd,pw,tf,ts,suppress,badcr,badid,xv,x0,x1,mw,mr,mb,maxcs);
integer i,j,failures=0;
task reset;begin
 @(negedge clk);rst=0;abort=0;pf=0;cv=0;cw=0;ca=0;wv=1;suppress=0;badcr=0;badid=0;
 repeat(3)@(negedge clk);rst=1;
end endtask
task ready;begin
 j=0;while(!init)begin @(negedge clk);j=j+1;if(fault||j>1000)$fatal(1,"init");end
end endtask
task stopped;begin
 j=0;while(!fault)begin @(negedge clk);j=j+1;if(j>200)$fatal(1,"missing fault");end
 repeat(5)@(negedge clk);
 if(!pc||pk||pr||cr||rv||wr||init||done)$fatal(1,"not fail stop");
 repeat(200)@(negedge clk);if(!fault)$fatal(1,"not sticky");failures=failures+1;
end endtask
initial begin
 reset();badcr=1;stopped();
 reset();badid=1;stopped();
 reset();suppress=1;stopped();
 reset();ready();cv=1;ca=1;@(negedge clk);cv=0;stopped();
 reset();ready();cv=1;cw=1;@(negedge clk);cv=0;wv=0;stopped();
 reset();ready();cv=1;cw=0;@(negedge clk);cv=0;suppress=1;stopped();
 reset();ready();abort=1;stopped();
 reset();ready();pf=1;stopped();
 reset();ready();if(failures!=8)$fatal(1,"count");
 $display("PASS 8 bounded sticky fault cases and full-reset recovery");$finish;
end
endmodule'''
        self.run_tb('faults',tb)

    def test_physical_ddr_byte_order_and_die_phase(self):
        tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0,ckclk=0;always #5 clk=~clk;initial begin #2.5;forever #5 ckclk=~ckclk;end
reg rst=0,cv=0,cw=0;reg[20:0] ca=0;wire cr,wr,rv,done,init,fault,pr,pc,pk,pd,pw,re,pf;
wire[31:0] rd;wire[15:0] tf,ts,x0,x1;wire[1:0] xv;
wire[1:0] ck,ckn,cs,rreset;wire[15:0] dq;wire[1:0] rwds;
integer sent=0,received=0,block=0,cycles=0,transactions=0,mincycles=999,maxcycles=0,startcycle;
function[31:0] pattern(input integer a);begin pattern=(32'hc1577a39*a)^32'hfbca1034^(a<<4);end endfunction
wire[31:0] wd=pattern(block*64+sent);
s3_psram_burst #(.POWERUP_CYCLES(16),.RESET_CYCLES(2)) dut(
 clk,rst,1'b0,cv,cw,ca,cr,1'b1,wd,wr,rv,rd,done,init,fault,
 pr,pc,pk,pd,pw,tf,ts,re,xv,x0,x1,pf);
s3_psram_phy phy(clk,ckclk,rst,pr,pc,pk,pd,pw,tf,ts,re,xv,x0,x1,pf,ck,ckn,cs,rreset,dq,rwds);
w955_ddr_model #(.OUTPUT_DELAY(DELAY0)) m0(rreset[0],cs[0],ck[0],ckn[0],dq[7:0],rwds[0]);
w955_ddr_model #(.OUTPUT_DELAY(DELAY1)) m1(rreset[1],cs[1],ck[1],ckn[1],dq[15:8],rwds[1]);
always @(posedge clk)begin
 cycles<=cycles+1;
 if(wr)sent<=sent+1;
 if(rv)begin
  if(rd!==pattern(block*64+received))$fatal(1,"physical DDR mismatch block=%d word=%d got=%h expected=%h",block,received,rd,pattern(block*64+received));
  received<=received+1;
 end
 if(cycles>20000)$fatal(1,"timeout");
 if(rst&&(fault||pf))$fatal(1,"PHY/controller fault cycles=%0d block=%0d received=%0d",cycles,block,received);
end
integer pass,b;
initial begin
 repeat(3)@(negedge clk);rst=1;while(!init)@(negedge clk);
 for(pass=0;pass<2;pass=pass+1)begin
  for(b=0;b<16;b=b+1)begin
   @(negedge clk);block=b;sent=0;received=0;cv=1;cw=pass==0;ca=b*64;startcycle=cycles;
   @(negedge clk);cv=0;while(!done)@(negedge clk);
   if(pass==0&&sent!=64)$fatal(1,"short write");
   if(pass==1&&received!=64)$fatal(1,"short read");
   if(cycles-startcycle<mincycles)mincycles=cycles-startcycle;
   if(cycles-startcycle>maxcycles)maxcycles=cycles-startcycle;
   transactions=transactions+1;
  end
 end
 $display("PASS DDR bytes=4096 transactions=%0d min_cycles=%0d max_cycles=%0d",transactions,mincycles,maxcycles);$finish;
end
endmodule'''
        cases=[]
        for d0,d1 in [(1.0,1.0),(1.0,4.2),(5.5,1.0),(4.2,5.5)]:
            with self.subTest(delay0=d0,delay1=d1):
                out,log=self.run_tb(f'ddr-{d0}-{d1}',tb.replace('DELAY0',str(d0)).replace('DELAY1',str(d1)),
                    ['rtl/s3_psram_phy.sv','tests/fixtures/gowin_ddr_model.sv','tests/fixtures/w955_ddr_model.sv'])
                cases.append(dict(die_delays_ns=[d0,d1],output=log.strip()))
        (ROOT/'build/s3-psram/ddr-results.json').write_text(json.dumps(dict(cases=cases,
            scope='independent functional pin model; no analog eye or real silicon test',receiver_adopted=False),indent=2)+'\n')

if __name__=='__main__':unittest.main()
