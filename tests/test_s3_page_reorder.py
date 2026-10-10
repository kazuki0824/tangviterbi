"""External payload lifetime: no visibility before write ack, ordered retire."""
from pathlib import Path
import json
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ReorderTest(unittest.TestCase):
    def test_reordering_wrap_backpressure_and_faults(self):
        out = ROOT / 'build/s3-page-reorder'
        out.mkdir(parents=True, exist_ok=True)
        tb = r'''module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0;reg[15:0] epoch=17,e0=17,e1=17;
reg[1:0] req=0,done=0;wire[1:0] grant,active;
reg[31:0] a0=0,a1=0;wire[3:0] s0,s1,slot;
reg abort=0,retire=0;wire valid,fault;wire[31:0] off;
s3_page_reorder #(.RESET_SEQUENCE(20'hffff8)) dut(
 clk,rst,epoch,req,grant,a0,a1,e0,e1,s0,s1,done,abort,
 valid,off,slot,retire,active,fault);
integer n,pages=0,cycles=0;reg[31:0] expected=32'hffff8000;
reg[31:0] pending[0:1];integer wait0=0,wait1=0;
reg[31:0] rng=32'h43798432;
// Scoreboard simulates memory acknowledgments, independently of page metadata.
reg[31:0] stored[0:15];reg[15:0] stored_valid=0;
task reset;begin
 @(negedge clk);rst=0;req=0;done=0;retire=0;abort=0;e0=17;e1=17;
 repeat(3)@(negedge clk);rst=1;@(negedge clk);
end endtask
task reserve(input integer port,input[31:0] addr);begin
 @(negedge clk);if(port==0)a0=addr;else a1=addr;req=1<<port;
 #1;if(!grant[port])$fatal(1,"grant missing");
 @(negedge clk);req=0;
end endtask
task finish(input integer port);begin @(negedge clk);done=1<<port;@(negedge clk);done=0;end endtask
task poison;begin repeat(2)@(negedge clk);if(!fault||valid||grant)$fatal(1,"not poisoned");end endtask
initial begin
 reset();reserve(0,32'hffff8000);reserve(1,32'hffff9000);
 finish(1);if(valid)$fatal(1,"later page leaked before oldest ack");
 repeat(20)@(negedge clk);if(valid)$fatal(1,"unacknowledged memory leaked");
 finish(0);#1;if(!valid||off!=32'hffff8000)$fatal(1,"oldest missing");
 retire=1;@(negedge clk);retire=0;
 if(!valid||off!=32'hffff9000)$fatal(1,"second page missing");
 reset();a0=32'h00008000;req=1;#1;if(grant[0])$fatal(1,"future window accepted");
 @(negedge clk);req=0;if(fault)$fatal(1,"future backpressure poisoned");
 reset();for(n=0;n<16;n=n+1)begin reserve(0,32'hffff8000+4096*n);finish(0);end
 a0=32'h00008000;req=1;#1;if(grant[0])$fatal(1,"full ring overwritten");
 @(negedge clk);req=0;if(fault)$fatal(1,"full ring is ordinary backpressure");
 // Hundreds of pointer wraps, delayed external-memory acks and consumer stalls.
 reset();n=0;expected=32'hffff8000;pages=0;wait0=0;wait1=0;
 while(pages<4096)begin
  @(negedge clk);req=0;done=0;retire=0;
  rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);
  if(!active[0]&&n<4096)begin a0=32'hffff8000+4096*n;req[0]=1;end
  if(!active[1]&&n+(req[0]?1:0)<4096)begin a1=32'hffff8000+4096*(n+(req[0]?1:0));req[1]=1;end
  #1;
  // Do not advance the stimulus producer for an unaccepted request.
  if(req[0]&&!grant[0])req[0]=0;
  if(req[1]&&!grant[1])req[1]=0;
  if(active[0])begin if(wait0==0)done[0]=1;else wait0=wait0-1;end
  if(active[1])begin if(wait1==0)done[1]=1;else wait1=wait1-1;end
  if(valid&&rng[2:0]!=0)begin
   if(off!==expected||!stored_valid[slot]||stored[slot]!==expected)$fatal(1,"order/ownership");
   retire=1;
  end
  @(posedge clk);
  if(req[0]&&grant[0])begin pending[0]=a0;wait0=3+rng[7:4];n=n+1;end
  if(req[1]&&grant[1])begin pending[1]=a1;wait1=1+rng[11:8];n=n+1;end
  if(done[0])begin stored[pending[0][15:12]]=pending[0];stored_valid[pending[0][15:12]]=1;end
  if(done[1])begin stored[pending[1][15:12]]=pending[1];stored_valid[pending[1][15:12]]=1;end
  if(retire)begin stored_valid[slot]=0;expected=expected+4096;pages=pages+1;end
  #1;if(fault)$fatal(1,"unexpected fault at %0d/%0d",pages,n);
  cycles=cycles+1;if(cycles>200000)$fatal(1,"deadlock");
 end
 reset();reserve(0,32'hffff8000);a1=32'hffff8000;req=2;poison(); // duplicate
 reset();a0=32'hffff7000;req=1;poison(); // already retired/old
 reset();a0=32'hffff8001;req=1;poison(); // byte alignment
 reset();a0=32'hffff8000;e0=16;req=1;poison(); // old epoch
 reset();done=1;poison(); // completion without owner
 reset();retire=1;poison(); // read without committed page
 reset();reserve(0,32'hffff8000);abort=1;poison();
 $display("PASS ordered pages=%0d including offset wrap and seven faults",pages);$finish;
end
endmodule'''
        (out / 'tb.sv').write_text(tb)
        c = subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', str(out/'sim'),
                            str(ROOT/'rtl/s3_page_reorder.sv'), str(out/'tb.sv')],
                           text=True, capture_output=True)
        self.assertEqual(c.returncode, 0, c.stderr)
        r = subprocess.run(['vvp', 'sim'], cwd=out, text=True, capture_output=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
        (out/'result.json').write_text(json.dumps(dict(pages=4096,address_span_bytes=4096*4096,
            output=r.stdout.strip(),scope='page ownership/ack/order metadata, not payload memory',
            physical_memory_included=False,receiver_adopted=False),indent=2)+'\n')

if __name__ == '__main__':
    unittest.main()
