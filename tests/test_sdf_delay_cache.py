"""Current FFT + finite line adapter + actual controller, independent pin RAM.
No background clients or PHY. Measures stalls instead of assuming ideal RAM.
"""
import hashlib,json,os,re,shutil,subprocess,tempfile,unittest
from pathlib import Path
from test_shared_sdf_fft import TB,ROOT,ARCHIVE,ORACLE,vectors
from test_common_clock_sdram import BENCH


def memory_system():
    monitor=BENCH[BENCH.index('  if(wleft>0)'):BENCH.index('  if(received==REQUESTS)')]
    monitor=monitor.replace('addresses[received]','pending_address')
    return r'''
module memory_system(input wire clk,resetn,valid,output wire ready,
 input wire wr,input wire[20:0]addr,input wire[255:0]data,
 output wire rv,output wire[255:0]response);
localparam MEM_WORDS=4096;
wire initialized,fault,cke,oe;wire[2:0]cmd;wire[1:0]bank;wire[10:0]a;
wire[3:0]dqm;wire[31:0]dout;reg[31:0]din=0;
reg[20:0]pending_address;
reg[31:0]mem[0:MEM_WORDS-1];reg[3:0]opened=0;
integer rows[0:3],activated[0:3],precharged[0:3],lastwrite[0:3];
integer cycle=0,refs=0,mode_at=-10000,lastref=-10000,read_at=-10000,read_base=0;
integer wleft=0,waddr=0,wbank=0,i,j,base,max_ref_gap=0;
dual_sdram_burst #(.INIT_CYCLES(30858),.REFRESH_CYCLES(1203),.TRP(4),.TRCD(4),.TRFC(12),.TWR(4),.TMRD(4)) controller(
 clk,resetn,valid,ready,wr,addr,data,32'd0,rv,1'b1,response,initialized,fault,
 cmd,bank,a,cke,dqm,oe,dout,din);
initial begin
 for(i=0;i<MEM_WORDS;i=i+1)mem[i]=32'hbadc0ffe;
 for(i=0;i<4;i=i+1)begin rows[i]=0;activated[i]=-10000;precharged[i]=-10000;lastwrite[i]=-10000;end
end
always @(negedge clk)begin
 if(cycle+1>=read_at && cycle+1<read_at+8)din=mem[read_base+cycle+1-read_at];else din=0;
end
always @(posedge clk)begin
 cycle=cycle+1;
 if(resetn)begin
 if(fault)$fatal(1,"SDRAM fault");
 if(valid&&ready)pending_address=addr;
''' + monitor + '\nend\nend\nendmodule\n'


def bench():
    s=TB.replace('reg resetn=0, in_valid=0, out_ready=1, external_ready=1;',
      'reg resetn=0, in_valid=0, out_ready=1;wire external_ready;')
    s=s.replace('reg [31:0] ext_q,mem[0:4095],source[0:FRAMES*N-1];','wire [31:0] ext_q;reg [31:0] source[0:FRAMES*N-1];')
    s=s.replace(' if(re) ext_q<=mem[ra];\n if(we) mem[wa]<=wd;',' if(cache_fault)$fatal(1,"cache contract");')
    s=s.replace(' external_ready=!STALL || (cycles%97<77);','')
    s=s.replace('if(!STALL && (max_input_gap!=13 || max_output_gap!=13))','if(0)')
    s=s.replace('module tb;', 'module tb;wire qv,qr,qw,rv,cache_fault;wire[20:0]qa;wire[255:0]qd,rd;')
    s=s.replace('initial begin',r'''
sdf_delay_cache cache(clk,resetn,in_valid&&in_ready,external_ready,
 re,ra,ext_q,we,wa,wd,qv,qr,qw,qa,qd,rv,rd,cache_fault);
memory_system memory(clk,resetn,qv,qr,qw,qa,qd,rv,rd);
initial begin''',1)
    return s+memory_system()

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class CacheTest(unittest.TestCase):
 def test_fft_through_controller(self):
    n=8192;words=vectors(n,'random')
    expected=sum((ORACLE.reference_fft(words[f*n:(f+1)*n],ORACLE.load_quarter()) for f in range(3)),[])
    with tempfile.TemporaryDirectory() as d:
      p=Path(d);(p/'tb.sv').write_text(bench());(p/'input.hex').write_text(''.join(f'{w:08x}\n' for w in words))
      subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),
        *(str(ROOT/'rtl'/f) for f in ('shared_sdf_fft.sv','sdf_delay_cache.sv','dual_sdram_burst.sv')),
        str(ARCHIVE/'rtl/research_sdf_twiddle.sv')],cwd=ARCHIVE,check=True,timeout=30)
      run=subprocess.run(['vvp',str(p/'sim'),f'+INPUT_HEX={p/"input.hex"}'],cwd=ARCHIVE,capture_output=True,text=True,timeout=90)
      self.assertEqual(run.returncode,0,run.stdout[-3000:]+run.stderr)
    rows=[s.split() for s in run.stdout.splitlines() if s.startswith('OUT ')]
    self.assertEqual(len(rows),3*n)
    for k,row in enumerate(rows):
      self.assertEqual(int(row[2]),ORACLE.bit_reverse(k%n,13))
      self.assertEqual(int(row[3],16),expected[k],f'bin {k}')
    summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS '))
    frames=[int(x) for x in re.search(r'frame_cycles=(\d+,\d+,\d+)',summary)[1].split(',')]
    result=dict(scope=__doc__,summary=summary,checked_bins=len(rows),oracle_bit_exact=True,
      frame_cycles=frames,frame_intervals=[b-a for a,b in zip(frames,frames[1:])],
      target_symbol_clocks=160380,background_clients=False,PHY_verified=False,
      source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in
        (Path(__file__),ROOT/"rtl/sdf_delay_cache.sv",ROOT/"rtl/shared_sdf_fft.sv",ROOT/"rtl/dual_sdram_burst.sv",
         ROOT/"tests/test_common_clock_sdram.py",ROOT/"tests/test_shared_sdf_fft.py")})
    print(json.dumps(result))
    if os.environ.get('SDF_CACHE_REPORT'):Path(os.environ['SDF_CACHE_REPORT']).write_text(json.dumps(result,indent=2)+'\n')
