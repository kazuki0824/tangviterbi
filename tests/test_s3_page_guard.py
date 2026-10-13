from pathlib import Path
import subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class GuardTest(unittest.TestCase):
    def test_commit_and_poison(self):
        out=ROOT/'build/s3-page-guard';out.mkdir(parents=True,exist_ok=True)
        tb='''module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0,valid=0,pr=1,dr=1;reg [35:0] token;
wire ready,start,dv,commit,fault,request;wire [1:0] stream;wire [31:0] offset,data;
s3_page_guard #(.MAX_FRAME_CYCLES(8192)) dut(clk,rst,16'd17,valid,ready,token,pr,start,stream,offset,dv,dr,data,commit,fault,request);
integer writes=0,commits=0,starts=0,i,j;
always @(posedge clk) if(rst) begin
 if(dv&&dr) begin if(data!==writes) $fatal(1,"payload");writes=writes+1;end
 if(commit) commits=commits+1;
 if(start) starts=starts+1;
end
task reset;begin
 @(negedge clk);rst=0;valid=0;repeat(3)@(negedge clk);rst=1;writes=0;commits=0;starts=0;
end endtask
task send(input [35:0] t);begin
 @(negedge clk);valid=1;token=t;@(posedge clk);while(!ready)@(posedge clk);
 @(negedge clk);valid=0;
end endtask
task header;begin send(36'h1d7110011);send(36'h200001000);send(36'h300001000);end endtask
task check_fault;begin
 repeat(3)@(negedge clk);
 if(!fault||commits!=0) $fatal(1,"bad page committed");
 if(ready||dv) $fatal(1,"poison not latched");
end endtask
initial begin
 reset();header();
 for(i=0;i<1024;i=i+1) begin
  if(i%13==0) begin dr=0;repeat(3)@(negedge clk);dr=1;end
  send({i==1023?4'h8:4'h0,32'(i)});
 end
 repeat(3)@(negedge clk);
 if(fault||commits!=1||writes!=1024||starts!=1||stream!=1||offset!=4096)$fatal(1,"good page");
 reset();send(36'h1d7110010);check_fault(); // stale epoch
 reset();send(36'h1d71b0011);check_fault(); // RX guard rejects read
 reset();send(36'h1d7110011);send(36'h200000001);check_fault();
 reset();send(36'h1d7110011);send(36'h200000000);send(36'h300000fff);check_fault();
 reset();header();send(36'h800000000);check_fault(); // premature last
 reset();header();for(i=0;i<1023;i=i+1)send({4'h0,32'(i)});
 send(36'h0000003ff);check_fault(); // missing last
 reset();header();send(36'h1d7110011);check_fault(); // aborted CS then new header
 reset();header();repeat(8200)@(negedge clk);check_fault();
 reset();send(36'h1d7110011);send(36'h200000000);pr=0;
 repeat(8200)@(negedge clk);check_fault();pr=1;
 $display("PASS good page and nine poisoned epochs");$finish;
end
initial begin #400000;$fatal(1,"timeout");end
endmodule
'''
        (out/'tb.sv').write_text(tb)
        c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),str(ROOT/'rtl/s3_page_guard.sv'),str(out/'tb.sv')],capture_output=True,text=True)
        self.assertEqual(c.returncode,0,c.stderr)
        r=subprocess.run(['vvp','sim'],cwd=out,capture_output=True,text=True,timeout=15)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        (out/'result.txt').write_text(r.stdout)
if __name__=='__main__':unittest.main()
