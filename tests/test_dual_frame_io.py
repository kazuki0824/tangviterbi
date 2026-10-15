"""Stream-only frame ownership test; no host writes/reads of active SDRAM frames."""
import hashlib,json,os,random,shutil,subprocess,tempfile,unittest
from pathlib import Path
from test_dual_fft_memory import MODEL,ROOT,packed
from dual_fft_reference import frame
BENCH=r'''`timescale 1ns/1fs
module tb;
parameter LOGN=11,FRAMES=4,HOLD=0;
localparam N=1<<LOGN,PERIOD=259875*(1<<(LOGN-11));
reg clk=0,mclk=0;always #3.086419753 clk=~clk;always #3.703703704 mclk=~mclk;
reg resetn=0,iv=0,orr=0;wire ir,ov,last,initialized,mfault;reg[31:0] id=0;reg il=0;
wire[31:0] od;wire[8:0] owners;wire[15:0] level;
wire[2:0] cmd;wire[1:0] bank;wire[10:0] a;wire cke,oe;wire[3:0] dqm;wire[31:0] dout;reg[31:0] din=0;
wire bgready,bgrv;wire[255:0] bgrd;
dual_fft_stream_memory #(.LOGN(LOGN),.INIT_CYCLES(32)) dut(clk,mclk,resetn,
 iv,ir,id,il,ov,orr,od,last,1'b0,bgready,1'b0,21'd256,256'd0,32'd0,bgrv,1'b1,bgrd,
 initialized,mfault,owners,level,cmd,bank,a,cke,dqm,oe,dout,din);
reg[31:0] inputs[0:FRAMES*N-1],expected[0:FRAMES*N-1];
integer sent=0,got=0,blocked=0,peak=0,starts=0,commits=0;
reg holding=0;reg[32:0] saved;real epoch=0,at,finish,worst=0;
always @(negedge mclk)begin
 at=epoch+(sent/N)*PERIOD+(sent%N)*123.046875;
 iv=initialized&&sent<FRAMES*N&&$realtime>=at;
 id=inputs[sent<FRAMES*N?sent:0];il=sent%N==N-1;
 orr=initialized && (!HOLD || $realtime>epoch+5*PERIOD) && cycle%19!=0;
end
always @(posedge mclk)if(resetn)begin
 if(holding&&(!ov||{last,od}!==saved))$fatal(1,"stalled output changed");
 holding=ov&&!orr;saved={last,od};
 if(level>peak)peak=level;
 if(iv&&!ir)blocked=blocked+1;
 if(iv&&ir)sent=sent+1;
 if(ov&&orr)begin
  if(got>=FRAMES*N||od!==expected[got])$fatal(1,"bin mismatch %0d %h %h",got,od,expected[got]);
  if(last!==(got%N==N-1))$fatal(1,"boundary");
  if(last)begin finish=$realtime-epoch-(got/N+1)*PERIOD;if(finish>worst)worst=finish;end
  got=got+1;
 end
 if(dut.jv&&dut.jr)begin
  if(dut.io.acknowledged[dut.js]!=0||dut.io.owner[dut.js]!=2)$fatal(1,"uncommitted start");
  starts=starts+1;
 end
 if(dut.jdone)commits=commits+1;
 if(cycle>FRAMES*PERIOD/7+2000000)$fatal(1,"timeout");
end
initial begin
 for(i=0;i<262144;i=i+1)mem[i]=32'hdeadc0de;
 for(i=0;i<4;i=i+1)begin rows[i]=0;activated[i]=-10000;precharged[i]=-10000;lastwrite[i]=-10000;end
 $readmemh("INPUT",inputs);$readmemh("EXPECTED",expected);
 repeat(5)@(negedge clk);resetn=1;wait(initialized);epoch=$realtime+100;
 wait(got==FRAMES*N);repeat(10)@(negedge mclk);
 if(sent!=FRAMES*N||starts!=FRAMES||commits!=FRAMES||owners!=0||mfault)$fatal(1,"ownership/count");
 if(HOLD&&blocked==0)$fatal(1,"no backpressure coverage");
 $display("PASS frames=%0d bins=%0d blocked_cycles=%0d peak_fifo=%0d scheduled_window_end_to_output_ns=%0.3f",FRAMES,got,blocked,peak,worst);$finish;
end
'''+MODEL.replace('65536','262144').replace('sent','model_sent')+'\nendmodule\n'

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class FrameIO(unittest.TestCase):
 def test_stream_capture_output_ownership(self):
  rows=[];files=list((ROOT/'rtl').glob('dual_fft_*.sv'))+list((ROOT/'rtl').glob('dual_burst_*.sv'))+[ROOT/'rtl/dual_sdram_burst.sv',ROOT/'rtl/dual_frame_io.sv']
  for logn,hold in ([(11,0)] if os.environ.get('DUAL_FRAME_FAST') else [(11,0),(12,0),(13,0),(11,1)]):
   with self.subTest(logn=logn,hold=hold),tempfile.TemporaryDirectory() as temp:
    p=Path(temp);n=1<<logn;rng=random.Random(2419+logn)
    samples=[(rng.randrange(-10000,10001),rng.randrange(-10000,10001)) for _ in range(4*n)]
    expected=[x for f in range(4) for x in frame(samples[f*n:(f+1)*n])]
    for name,values in [('input',samples),('expected',expected)]:
     (p/f'{name}.hex').write_text('\n'.join(f'{packed(x):08x}' for x in values)+'\n')
    (p/'tb.sv').write_text(BENCH.replace('"INPUT"',json.dumps(str(p/'input.hex'))).replace('"EXPECTED"',json.dumps(str(p/'expected.hex'))))
    subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.LOGN={logn}',f'-Ptb.HOLD={hold}','-o',str(p/'sim'),str(p/'tb.sv'),*map(str,files)],check=True)
    r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=180)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    row=dict(x.split('=') for x in next(x for x in r.stdout.splitlines() if x.startswith('PASS')).split()[1:]);row.update(logn=logn,hold=hold);rows.append(row);print(row,flush=True)
  if os.environ.get('DUAL_FRAME_REPORT'):
   Path(os.environ['DUAL_FRAME_REPORT']).write_text(json.dumps(dict(results=rows,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files+[Path(__file__),ROOT/'tests/test_dual_fft_memory.py',ROOT/'tests/test_dual_sdram.py',ROOT/'experiments/dual_fft_reference.py']}),indent=2)+'\n')
