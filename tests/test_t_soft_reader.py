"""Independent byte/address queue oracle with finite bank reuse and response stalls."""
import hashlib, json, os, shutil, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TB=r'''
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,cv=0;wire cr;reg[62:0]ca=0;reg[47:0]cl=0;
wire[1:0]live;wire reuse,qv,rr,sv,fault;wire[20:0]qa;wire[1:0]sc;wire[7:0]sd;
reg qr=0,rv=0,sr=0;reg[255:0]rd=0;
t_soft_reader dut(clk,resetn,cv,cr,ca,cl,live,reuse,qv,qr,qa,rv,rr,rd,sv,sr,sc,sd,fault);
reg[7:0]expected[0:2][0:20000];integer n[0:2],used[0:2];
integer left[0:39][0:2],offsets[0:39][0:2];
integer read_symbol=0,request_context,pending_symbol=-1,request_length;
integer sym=0,cycle,i,j,k,len,base,idx,delay_left=-1,accepted=0,completed=0,reuses=0,stalls=0,seed=1903;
reg[20:0]held;reg pending=0;reg[1:0]last_ctx;reg[7:0]last_data;reg was_stalled=0;
function[7:0]value;input integer byte_address;begin value=((byte_address*13)^(byte_address>>7)^91)&255;end endfunction
initial begin
 for(i=0;i<3;i=i+1)begin n[i]=0;used[i]=0;end
 for(cycle=0;cycle<50000;cycle=cycle+1)begin
  @(negedge clk);resetn=cycle>2;
  cv=sym<40;ca=0;cl=0;
  for(i=0;i<3;i=i+1)begin
   len=(sym*37+i*53)%193;
   if(sym%7==0 && i==0)len=0;
   base=(sym%2)*4096+i*256;
   ca[i*21+:21]=base;cl[i*16+:16]=len;
  end
  qr=!pending && (cycle%7!=0);
  sr=cycle>1800 && cycle%11<7;
  if(pending && delay_left==0)rv=1;
  if(pending && delay_left>0)delay_left=delay_left-1;
  @(posedge clk);
  if(resetn)begin
   if(was_stalled && (!sv || sc!==last_ctx || sd!==last_data))$fatal(1,"unstable output");
   was_stalled=sv&&!sr;last_ctx=sc;last_data=sd;
   if(reuse)reuses=reuses+1;
   if(sv && !sr)stalls=stalls+1;
   if(sv && sr)begin
    if(used[sc]>=n[sc] || sd!==expected[sc][used[sc]])$fatal(1,"byte mismatch ctx %0d index %0d",sc,used[sc]);
    used[sc]=used[sc]+1;
   end
   if(cv && cr)begin
    if(sym>=2 && (left[sym-2][0]!=0 || left[sym-2][1]!=0 || left[sym-2][2]!=0 ||
      (pending && pending_symbol==sym-2)))$fatal(1,"premature bank reuse");
    for(i=0;i<3;i=i+1)begin
     len=cl[i*16+:16];base=ca[i*21+:21]*4;left[sym][i]=len;offsets[sym][i]=0;
     for(j=0;j<len;j=j+1)begin expected[i][n[i]]=value(base+j);n[i]=n[i]+1;end
    end
    sym=sym+1;
   end
   if(qv && qr)begin
    if(qa[2:0]!=0)$fatal(1,"unaligned word request");
    // Independent metadata cursor checks exact WORD address and tail length.
    while(read_symbol<sym && left[read_symbol][0]==0 && left[read_symbol][1]==0 && left[read_symbol][2]==0)read_symbol=read_symbol+1;
    request_context=(qa%4096)/256;
    if(read_symbol>=sym || request_context>2)$fatal(1,"unexpected region");
    if(qa!=(read_symbol%2)*4096+request_context*256+offsets[read_symbol][request_context]/4 ||
      left[read_symbol][request_context]==0)$fatal(1,"wrong request address/order");
    request_length=left[read_symbol][request_context]<32 ? left[read_symbol][request_context]:32;
    left[read_symbol][request_context]=left[read_symbol][request_context]-request_length;
    offsets[read_symbol][request_context]=offsets[read_symbol][request_context]+32;
    pending_symbol=read_symbol;
    held=qa;pending=1;delay_left=17+cycle%19;accepted=accepted+1;
    for(j=0;j<32;j=j+1)rd[j*8+:8]=value(qa*4+j);
   end
   if(rv && rr)begin pending=0;completed=completed+1;end
  end
  #1;if(fault)$fatal(1,"fault");
  if(!pending)rv=0;
 end
 for(i=0;i<3;i=i+1)if(used[i]!=n[i])$fatal(1,"not drained");
 if(sym!=40 || live || accepted!=completed || reuses<100 || stalls<100)$fatal(1,"coverage/drain");
 // Reject byte-address confusion and out-of-device padded burst ranges.
 @(negedge clk);cv=1;ca=1;cl=1;#1;if(cr)$fatal(1,"unaligned accepted");
 @(posedge clk);#1;if(!fault)$fatal(1,"no alignment fault");
 @(negedge clk);cv=0;resetn=0;@(negedge clk);resetn=1;
 ca=21'h1ffff8;cl=33;cv=1;#1;if(cr)$fatal(1,"range overflow accepted");
 @(posedge clk);#1;if(!fault)$fatal(1,"no range fault");
 $display("PASS symbols=%0d requests=%0d reuse_blocked=%0d output_stalls=%0d bytes=%0d/%0d/%0d",sym,completed,reuses,stalls,n[0],n[1],n[2]);$finish;
end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class ReaderTest(unittest.TestCase):
 def test_bytes_stalls_tails_and_bank_reuse(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(TB)
   subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/t_soft_reader.sv')],check=True)
   r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=30)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS',r.stdout);print(r.stdout.strip())
  if os.environ.get('T_SOFT_READER_REPORT'):
   files=[Path(__file__),ROOT/'rtl/t_soft_reader.sv']
   Path(os.environ['T_SOFT_READER_REPORT']).write_text(json.dumps(dict(scope=__doc__,summary=r.stdout.strip(),source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest()for f in files}),indent=2)+'\n')
