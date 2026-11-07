"""Sixteen paced frames through actual SDF/cache/controller with synthetic load.
Covers all 13 FFT slot phases; does not cover every refresh/traffic phase.
"""
import hashlib,json,math,os,re,shutil,subprocess,tempfile,unittest
from pathlib import Path
from test_sdf_cache_contention import contention_bench
from test_shared_sdf_fft import ROOT,ARCHIVE,ORACLE,vectors


def extended_bench():
 s=contention_bench()
 s=s.replace('FRAMES=4, CHECK=3*N','FRAMES=16, CHECK=15*N')
 s=s.replace('frame_cycle[0:2]','frame_cycle[0:14]')
 s=s.replace('cycles>1200000','cycles>4000000')
 s=s.replace('sent<=sent+1;', '''sent<=sent+1;
   if(sent%N==N-1)$display("ACCEPT_FRAME index=%0d cycle=%0d",sent/N,cycles);''')
 s=s.replace('if(frame_end && received<CHECK)frame_cycle[received/N]<=cycles;', '''if(frame_end && received<CHECK)begin
   frame_cycle[received/N]<=cycles;
   $display("FRAME index=%0d cycle=%0d epoch=%0d latency=%0d",received/N,cycles,epoch,cycles-epoch-(received/N)*160380);
  end''')
 s=s.replace('if(PACED && offered-sent>peak_input)', '''if(epoch>=0 && (cycles-epoch)%160380==0 && cycles>epoch)begin
  $display("SNAP symbol=%0d input_pending=%0d peak=%0d",(cycles-epoch)/160380,offered-sent,peak_input);
  memory.report();
 end
 if(PACED && offered-sent>peak_input)''')
 return s

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class PhaseSweepTest(unittest.TestCase):
 def test_thirteen_slot_phases(self):
  n=8192
  # Four deterministic but distinct groups: no zero flush frames or repeated group.
  words=sum((vectors(n,f'phase{g}'+'x'*g) for g in range(4)),[])
  expected=sum((ORACLE.reference_fft(words[f*n:(f+1)*n],ORACLE.load_quarter()) for f in range(15)),[])
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(extended_bench());(p/'input.hex').write_text(''.join(f'{w:08x}\n' for w in words))
   subprocess.run(['iverilog','-g2012','-s','tb','-Ptb.FFT_FIRST=1','-Ptb.PACED=1','-o',str(p/'sim'),str(p/'tb.sv'),
    *(str(ROOT/'rtl'/f) for f in ('shared_sdf_fft.sv','sdf_delay_cache.sv','dual_sdram_burst.sv')),
    str(ARCHIVE/'rtl/research_sdf_twiddle.sv')],cwd=ARCHIVE,check=True,timeout=30)
   run=subprocess.run(['vvp',str(p/'sim'),f'+INPUT_HEX={p/"input.hex"}'],cwd=ARCHIVE,capture_output=True,text=True,timeout=300)
   self.assertEqual(run.returncode,0,run.stdout[-3000:]+run.stderr)
  records={k:[] for k in ('FRAME','ACCEPT_FRAME','SNAP','BG','LOAD','INPUT_QUEUE')}
  checked=0
  for line in run.stdout.splitlines():
   fields=line.split()
   if fields and fields[0]=='OUT':
    self.assertEqual(int(fields[1]),checked)
    self.assertEqual(int(fields[2]),ORACLE.bit_reverse(checked%n,13))
    self.assertEqual(int(fields[3],16),expected[checked],f'bin {checked}')
    checked+=1
   elif fields and fields[0] in records:
    records[fields[0]].append({k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',line)})
  self.assertEqual(checked,15*n);self.assertEqual(len(records['FRAME']),15)
  self.assertEqual(len(records['ACCEPT_FRAME']),16)
  for r in records['BG']:self.assertEqual(r['arrived'],r['finished']+r['pending'])
  frames=records['FRAME'];latencies=[r['latency'] for r in frames]
  phases=[(r['epoch']+r['index']*160380)%13 for r in frames]
  self.assertEqual(len(set(phases)),13)
  intervals=[b['cycle']-a['cycle'] for a,b in zip(frames,frames[1:])]
  report=dict(scope=__doc__,checked_bins=checked,oracle_bit_exact=True,frames=frames,
   accepted_frames=records['ACCEPT_FRAME'],symbol_snapshots=records['SNAP'],
   background_snapshots=records['BG'],load_snapshots=records['LOAD'],input_queue=records['INPUT_QUEUE'][-1],
   input_slot_phases=phases,frame_intervals=intervals,latency_range=[min(latencies),max(latencies)],
   latency_change_after_13_symbols=latencies[13]-latencies[0],
   slot_phase_period=13//math.gcd(160380,13),all_refresh_phases_covered=False,
   source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in
    (Path(__file__),ROOT/'tests/test_sdf_cache_contention.py',ROOT/'tests/test_sdf_delay_cache.py',
     ROOT/'tests/test_shared_sdf_fft.py',ROOT/'tests/test_common_clock_sdram.py',
     ROOT/'rtl/sdf_delay_cache.sv',ROOT/'rtl/shared_sdf_fft.sv',ROOT/'rtl/dual_sdram_burst.sv')})
  print(json.dumps({k:v for k,v in report.items() if k not in ('background_snapshots','source_sha256')}))
  if os.environ.get('SDF_PHASE_REPORT'):Path(os.environ['SDF_PHASE_REPORT']).write_text(json.dumps(report,indent=2)+'\n')
