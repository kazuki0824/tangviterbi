"""Actual stream capture/output concurrent with real T/S memory clients."""
import hashlib,json,os,random,shutil,subprocess,tempfile,unittest
from pathlib import Path
from test_dual_frame_io import BENCH,ROOT,packed,frame
from dual_t_time_fixture import connect as tconnect
from dual_s_frame_fixture import connect as sconnect

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class FrameTS(unittest.TestCase):
 def test_concurrent_streams(self):
  rows=[]
  files=sorted((ROOT/'rtl').glob('dual_*.sv'))
  for logn in map(int,os.environ.get('DUAL_FRAME_TS_MODES','11,12,13').split(',')):
   frames=int(os.environ.get('DUAL_FRAME_TS_FRAMES',str(48>>(logn-11))))
   with self.subTest(logn=logn),tempfile.TemporaryDirectory() as temp:
    p=Path(temp);n=1<<logn;mode=logn-10;rng=random.Random(2519+logn)
    samples=[(rng.randrange(-10000,10001),rng.randrange(-10000,10001)) for _ in range(frames*n)]
    expected=[x for f in range(frames) for x in frame(samples[f*n:(f+1)*n])]
    for name,values in [('input',samples),('expected',expected)]:
     (p/f'{name}.hex').write_text('\n'.join(f'{packed(x):08x}' for x in values)+'\n')
    _,sd=sconnect('if(corecycles>FRAMES*250000)$fatal(1,"timeout");',p,1)
    _,td=tconnect('',p,mode,[(3,4>>(mode-1)),(3,8>>(mode-1)),(7,16>>(mode-1))],frames)
    b=BENCH.replace('262144','2097152').replace('+2000000', '+4000000').replace('parameter LOGN=11,FRAMES=4,HOLD=0;',f'parameter LOGN=11,FRAMES={frames},HOLD=0;')
    start=b.index('dual_fft_stream_memory #');end=b.index('reg[31:0] inputs',start)
    ports='''dual_fft_stream_ts_memory #(.MODE(LOGN-10),.I0(4>>(LOGN-11)),.I1(8>>(LOGN-11)),.I2(16>>(LOGN-11)),.INIT_CYCLES(32)) dut(clk,mclk,resetn,
 iv,ir,id,il,ov,orr,od,last,owners,1'b0,bgready,1'b0,21'd256,256'd0,bgrv,1'b1,bgrd,
 initialized,mfault,cmd,bank,a,cke,dqm,oe,dout,din,32'd0,level,
 siv,sir,sid,sov,sor,sod,sclast,sslast,sfault,spackets,sowners,
 tstart,tsready,tdrain,tiv,tir,tid,tov,tor,tod,tlast,tsettled,tresult,tdone,tbusy,tfault);
wire active=initialized;
'''
    b=b[:start]+ports+sd+td+b[end:]
    b=b.replace('dut.j','dut.memory.j').replace('dut.io.','dut.memory.io.')
    b=b.replace('wait(got==FRAMES*N);','wait(got==FRAMES*N && sreceived==SREQ && tdrained);')
    b=b.replace(' $display("PASS', ''' $display("CLIENTS t_compute_misses=%0d t_output_misses=%0d t_pending_frames=%0d t_worst_ns=%0.3f s_pending_bytes=%0d s_finish_ns=%0.3f",tcompute_misses,toutput_misses,tpeak,tworst,sexternal,sfinish[0]);
 $display("PASS''').replace('last_sample_to_output_bound_ns','scheduled_window_end_to_output_ns')
    b=b.replace('"INPUT"',json.dumps(str(p/'input.hex'))).replace('"EXPECTED"',json.dumps(str(p/'expected.hex')))
    (p/'tb.sv').write_text(b)
    subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.LOGN={logn}','-o',str(p/'sim'),str(p/'tb.sv'),*map(str,files)],check=True)
    r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=600)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    row={'logn':logn}
    for line in r.stdout.splitlines():
     if line.startswith(('PASS ','CLIENTS ')):row.update(dict(x.split('=') for x in line.split()[1:]))
    row['deadline_admitted']=int(row['blocked_cycles'])==0 and int(row['t_compute_misses'])==0 and int(row['t_output_misses'])==0 and int(row['t_pending_frames'])<=1 and float(row['scheduled_window_end_to_output_ns'])<=2*259875*(1<<(logn-11)) and int(row['s_pending_bytes'])<=1 and float(row['s_finish_ns'])<=2*77952*4000/28.86
    rows.append(row);print(row,flush=True)
  if os.environ.get('DUAL_FRAME_TS_REPORT'):
   Path(os.environ['DUAL_FRAME_TS_REPORT']).write_text(json.dumps(dict(results=rows,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files+[Path(__file__),ROOT/'tests/test_dual_frame_io.py',ROOT/'tests/dual_t_time_fixture.py',ROOT/'tests/dual_s_frame_fixture.py',ROOT/'tests/test_dual_t_time_dma.py',ROOT/'tests/test_dual_s_frame_dma.py',ROOT/'tests/test_dual_fft_memory.py',ROOT/'tests/test_dual_sdram.py',ROOT/'experiments/dual_fft_reference.py']}),indent=2)+'\n')
