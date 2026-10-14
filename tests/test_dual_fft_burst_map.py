from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class BurstMap(unittest.TestCase):
    def test_all_modes_directions_bursts_and_beats(self):
        bench='''module tb;
reg[3:0] logn;reg second,wr;reg[20:0] base;reg[4:0] tile;
reg[7:0] burst;reg[2:0] beat;wire valid;wire[20:0] addr;
wire[9:0] idx;wire[12:0] phase;wire[2:0] kl,lb;wire[7:0] bc;
integer n,s,w,t,b,i,nt,nb;
dual_fft_burst_map dut(logn,second,wr,base,tile,burst,beat,valid,addr,idx,phase,kl,lb,bc);
initial begin
base=21'd32768;
for(n=11;n<=13;n=n+1)for(s=0;s<2;s=s+1)for(w=0;w<2;w=w+1)begin
 logn=n;second=s;wr=w;tile=0;burst=0;beat=0;#1;
 nt=(1<<n)/(8*(1<<(n==13?7:6)));nb=bc;
 for(t=0;t<nt;t=t+1)for(b=0;b<nb;b=b+1)for(i=0;i<8;i=i+1)begin
  tile=t;burst=b;beat=i;#1;
  if(!valid)$fatal(1,"valid mapping rejected");
  $display("A %0d %0d %0d %0d %0d %0d %0d %0d %0d",n,s,w,t,b,i,addr,idx,phase);
 end
 tile=nt;#1;if(valid)$fatal(1,"out of bounds tile accepted");
end
base=1;tile=0;burst=0;#1;if(valid)$fatal(1,"unaligned frame accepted");
$finish;
end endmodule'''
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'tb.sv').write_text(bench)
            subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/dual_fft_burst_map.sv')],check=True,timeout=30)
            r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        seen={}
        for line in r.stdout.splitlines():
            if not line.startswith('A '):continue
            n,s,w,t,b,i,addr,idx,phase=map(int,line.split()[1:]);size=1<<n
            a,bn={11:(32,64),12:(64,64),13:(64,128)}[n];lanes=8 if not s else 8*bn//a
            if not s:
                row=b;lane=i;expected_addr=32768+row*a+t*8;expected_idx=row*8+lane
                self.assertEqual(phase,((t*8+lane)*row*(8192//size))%8192)
            elif not w:
                lane=b//(a//8);point=(b%(a//8))*8+i
                expected_addr=32768+(t*lanes+lane)*a+(point//8)*8;expected_idx=point*lanes+lane
            else:
                point=b//(lanes//8);lane=(b%(lanes//8))*8+i
                expected_addr=32768+point*bn+t*lanes+(lane//8)*8;expected_idx=point*lanes+lane
            self.assertEqual((addr,idx),(expected_addr,expected_idx))
            key=(n,s,w);seen.setdefault(key,[]).append(addr+i)
        for (n,s,w),values in seen.items():self.assertEqual(sorted(values),list(range(32768,32768+(1<<n))))
        self.assertEqual(len(seen),12)
if __name__=='__main__':unittest.main()
