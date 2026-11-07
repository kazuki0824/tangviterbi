"""Check every 16-bit length at padded-device-boundary neighbours in RTL."""
import hashlib,json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TB=r'''
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0;reg[62:0]addresses=0;reg[47:0]lengths=0;
wire ready;
t_soft_reader dut(.clk(clk),.resetn(resetn),.commit_valid(1'b0),.commit_ready(ready),
 .commit_addresses(addresses),.commit_lengths(lengths),.req_ready(1'b0),
 .rsp_valid(1'b0),.rsp_data(256'd0),.soft_ready(1'b0));
integer len,delta,ctx,start_burst,address,alignment,limit,checks=0;
reg expected;
initial begin
 repeat(3)@(negedge clk);resetn=1;
 for(len=0;len<65536;len=len+1)begin
  ctx=len%3;
  for(delta=-2;delta<=3;delta=delta+1)begin
   start_burst=delta==3 ? 0 : 262144-((len+31)/32)+delta;
   if(start_burst>=0 && start_burst<262144)begin
    for(alignment=0;alignment<=1;alignment=alignment+1)begin
     address=start_burst*8+(alignment ? 7 : 0);
     limit=address+((len+31)/32)*8;
     expected=len==0 || (address%8==0 && limit<=2097152);
     addresses=0;lengths=0;
     addresses[ctx*21+:21]=address;lengths[ctx*16+:16]=len;
     #1;if(ready!==expected)$fatal(1,"range len=%0d word=%0d expected=%0d",len,address,expected);
     checks=checks+1;
    end
   end
  end
 end
 $display("PASS all 65536 lengths boundary/alignment checks=%0d",checks);$finish;
end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class RangeTest(unittest.TestCase):
 def test_all_lengths_near_device_end(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(TB)
   subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/t_soft_reader.sv')],check=True)
   r=subprocess.run(['vvp',str(p/'sim')],text=True,capture_output=True,timeout=90)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS all 65536',r.stdout);print(r.stdout.strip())
  if os.environ.get('T_SOFT_RANGE_REPORT'):
   files=[Path(__file__),ROOT/'rtl/t_soft_reader.sv']
   Path(os.environ['T_SOFT_RANGE_REPORT']).write_text(json.dumps(dict(scope=__doc__,summary=r.stdout.strip(),source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest()for f in files}),indent=2)+'\n')
