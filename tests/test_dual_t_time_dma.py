"""Natural-order T bytes, carrier histories, finite ownership and real DMA requests."""
import hashlib,json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def source_byte(frame,index):
    return (frame*73+index*19+(index//251)*11)&255


def expected_byte(frame,index,mode,layers):
    r=1<<(mode-1);seg,within=divmod(index,96*r*6);carrier=within//6
    cursor=0
    for count,length in layers:
        if cursor<=seg<cursor+count:
            delay=length*(95-(5*carrier)%96)
            return 0 if frame<delay else source_byte(frame-delay,index)
        cursor+=count
    raise AssertionError(index)


BENCH=r'''`timescale 1ns/1ps
module tb;
parameter MODE=1,S0=3,I0=4,S1=3,I1=8,S2=7,I2=16,FRAMES=12,STALLS=1;
localparam N=13*96*(1<<(MODE-1))*6;
reg clk=0,resetn=0;always #5 clk=~clk;
reg start=0,drain=0,iv=0,ordy=0;wire ready,ir,ov,last,settled,result,done,busy,fault;
reg[31:0] id=0;wire[31:0] od;
wire qv,qr,qw,sr;wire[20:0] qa;wire[255:0] qd;wire[31:0] qm;
reg sv=0,pending=0;reg[255:0] sd=0;
reg[255:0] mem[0:262143];reg touched[0:262143];
reg[7:0] expected[0:FRAMES*N-1];
integer frame=0,sent=0,got=0,cycle=0,delay=0,writes=0,reads=0,b=0,k=0;
integer began=0,worst=0,elapsed=0,started=0;
reg holding=0,qholding=0;reg[32:0] saved;reg[309:0] qsaved;
assign qr=!pending && (!STALLS || cycle%19>3);
dual_t_time_dma #(.MODE(MODE),.S0(S0),.I0(I0),.S1(S1),.I1(I1),.S2(S2),.I2(I2)) dut(
 clk,resetn,start,ready,drain,iv,ir,id,ov,ordy,od,last,settled,result,done,busy,fault,
 qv,qr,qw,qa,qd,qm,sv,sr,sd);
function[7:0] input_byte(input integer f,i);input_byte=f*73+i*19+(i/251)*11;endfunction
always @(negedge clk)begin
 iv=!drain && sent<N && (!STALLS||cycle%13!=0);
 for(integer lane=0;lane<4;lane=lane+1)id[lane*8+:8]=input_byte(frame,sent+lane);
 ordy=!STALLS||cycle%101>32;
end
always @(posedge clk)if(resetn)begin
 cycle<=cycle+1;
 if(fault)$fatal(1,"T DMA fault");
 if(holding && (!ov || {last,od}!==saved))$fatal(1,"output changed while stalled");
 holding<=ov&&!ordy;saved<={last,od};
 if(qholding && (!qv || {qw,qa,qd,qm}!==qsaved))$fatal(1,"request changed while stalled");
 qholding<=qv&&!qr;qsaved<={qw,qa,qd,qm};
 if(iv&&ir)begin
  // Previous result at this natural position must have left first.
  if(frame>0 && got<(frame-1)*N+sent+4 && !(ov&&ordy))$fatal(1,"overwrite before delivery");
  sent<=sent+4;
 end
 if(ov&&ordy)begin
  for(integer lane=0;lane<4;lane=lane+1)if(got>=FRAMES*N || od[lane*8+:8]!==expected[got+lane])$fatal(1,"T byte %0d got=%0h expected=%0h",got,od,expected[got]);
  if(settled!==((got/N)>=dut.MAXD))$fatal(1,"warmup flag");
  if(last!==(got%N==N-4))$fatal(1,"symbol boundary");
  got<=got+4;
 end
 if(qv&&qr)begin
  if(qa[9:8]==0 || qa[2:0]!=0)$fatal(1,"partition/alignment");
  pending<=1;delay<=STALLS?10+cycle%17:10;
  if(qw)begin
   for(b=0;b<32;b=b+1)if(!qm[b])mem[qa>>3][8*b+:8]<=qd[8*b+:8];
   touched[qa>>3]<=1;sd<=0;writes<=writes+1;
  end else begin sd<=touched[qa>>3]?mem[qa>>3]:256'hdeadc0de;reads<=reads+1;end
 end
 if(pending&&!sv)begin if(delay==0)sv<=1;else delay<=delay-1;end
 if(sv&&sr)begin sv<=0;pending<=0;end
 if(cycle>FRAMES*N*30+100000)$fatal(1,"timeout");
end
initial begin
 $readmemh("EXPECTED",expected);
 for(k=0;k<262144;k=k+1)begin touched[k]=0;mem[k]=256'hdeadc0de;end
 repeat(4)@(negedge clk);resetn=1;
 for(frame=0;frame<FRAMES;frame=frame+1)begin
  @(negedge clk);sent=0;start=1;began=cycle;
  @(negedge clk);start=0;
  wait(done);@(negedge clk);
  elapsed=cycle-began;if(elapsed>worst)worst=elapsed;
  if(sent!=N || got!=frame*N || !ready || !result)$fatal(1,"frame ownership/count %0d sent=%0d got=%0d",frame,sent,got);
 end
 @(negedge clk);drain=1;start=1;
 @(negedge clk);start=0;
 wait(done);@(negedge clk);
 if(got!=FRAMES*N || result || !ready)$fatal(1,"final drain");
 $display("PASS frames=%0d bytes=%0d reads=%0d writes=%0d worst_cycles=%0d",FRAMES,got,reads,writes,worst);
 $finish;
end
endmodule
'''

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class TimeDMA(unittest.TestCase):
    def test_natural_order_and_ownership(self):
        cases=[(1,[(3,4),(3,8),(7,16)],12,1),
               (2,[(1,0),(4,4),(8,8)],12,1),
               (3,[(13,1),(0,0),(0,0)],98,0),
               (3,[(13,0),(0,0),(0,0)],3,1)]
        if os.environ.get('DUAL_T_FAST'):cases=cases[:1]
        results=[]
        for mode,layers,frames,stalls in cases:
            with self.subTest(mode=mode,layers=layers),tempfile.TemporaryDirectory() as temp:
                p=Path(temp);n=13*96*(1<<(mode-1))*6
                (p/'expected.hex').write_text('\n'.join(f'{expected_byte(f,i,mode,layers):02x}' for f in range(frames) for i in range(n))+'\n')
                bench=BENCH.replace('"EXPECTED"',json.dumps(str(p/'expected.hex')))
                (p/'tb.sv').write_text(bench)
                args=['iverilog','-g2012','-s','tb',f'-Ptb.MODE={mode}',f'-Ptb.FRAMES={frames}',f'-Ptb.STALLS={stalls}']
                for j,(s,il) in enumerate(layers):args += [f'-Ptb.S{j}={s}',f'-Ptb.I{j}={il}']
                files=[ROOT/'rtl/dual_t_time_dma.sv',ROOT/'rtl/dual_vector_exchange.sv',ROOT/'rtl/dual_vector_exchange_pipelined.sv']
                subprocess.run(args+['-o',str(p/'sim'),str(p/'tb.sv'),*map(str,files)],check=True,timeout=60)
                run=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=600)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                line=next(x for x in run.stdout.splitlines() if x.startswith('PASS'))
                metrics={k:int(v) for k,v in (x.split('=') for x in line.split()[1:])}
                metrics.update(mode=mode,layers=layers,stalls=stalls)
                results.append(metrics);print(metrics,flush=True)
        if os.environ.get('DUAL_T_TIME_REPORT'):
            Path(os.environ['DUAL_T_TIME_REPORT']).write_text(json.dumps(dict(results=results,
                scope='Fixed configurations; independent carrier histories. Abstract memory and valid/ready sources, not RF timing admission.',
                source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files+[Path(__file__)]}),indent=2)+'\n')
