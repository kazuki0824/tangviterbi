"""Actual FFT + shared service/K7 connection; continuous S zero codeword.
T3 zero-codeword soft buffers are written through actual SDRAM; equalizer/interleaver/RS/TS absent; not a whole receiver test.
"""
import hashlib,json,re,subprocess,tempfile,unittest,shutil
from pathlib import Path
from test_shared_sdf_fft import TB,ROOT,ARCHIVE,ORACLE,vectors
from test_sdf_delay_cache import memory_system
from ci.shared_receiver_fft_beat_hold_evidence import FILES

def bench():
 s=TB.replace('reg resetn=0, in_valid=0, out_ready=1, external_ready=1;', 'reg resetn=0, in_valid=0, out_ready=1;')
 a=s.index('shared_sdf_fft #');b=s.index('always @(posedge clk)',a)
 s=s[:a]+r'''wire init,fault,cke,oe;wire[2:0]cmd;wire[1:0]bank;wire[10:0]address;
 wire[3:0]dqm;wire[31:0]dout,din;
 reg sv=0;wire sr,kv,kb;wire[1:0]kc;
 reg bgv=0,busy=0,commit=0;wire[3:0]bgr,bgrv;wire commit_ready;
 integer t0bits=0,t1bits=0,t2bits=0; integer writes=0;reg committed=0;reg[3:0]context_seen=0;
 always @(negedge clk)begin
  bgv=init && writes<234 && !busy;
  commit=writes==234 && !committed;
 end
 always @(posedge clk)if(resetn)begin
  if(bgv&&bgr[0])busy<=1;
  if(bgrv[0])begin busy<=0;writes<=writes+1;end
  if(commit&&commit_ready)committed<=1;
 end
 integer offered_s=0,consumed_s=0,sacc=0,checked_s=0;
 shared_receiver_fft_metadata dut(.clk(clk),.resetn(resetn),.fft_mode(selected_mode),
 .fft_in_valid(in_valid),.fft_in_ready(in_ready),.fft_in_data(in_data),
 .fft_out_valid(out_valid),.fft_out_ready(out_ready),.fft_out_data(out_data),
 .fft_out_bin(bin),.fft_frame_end(frame_end),.fft_overflow(overflow),
 .bg_valid({3'd0,bgv}),.bg_ready(bgr),.bg_rsp_valid(bgrv),.bg_write(4'b0001),.bg_address({63'd0,(21'd8192+21'(writes*8))}),.bg_data({768'd0,{32{8'd25}}}),.bg_dqm(128'd0),.bg_rsp_ready(4'hf),
 .commit_valid(commit),.commit_ready(commit_ready),.commit_addresses({21'd9056,21'd8336,21'd8192}),.commit_lengths({16'd4032,16'd2880,16'd576}),
 .rates(12'h924),.s_tc8_mode(1'b0),.s_valid(sv),.s_ready(sr),.s_data(32'd25),
 .out_valid(kv),.out_bit(kb),.out_context(kc),
 .initialized(init),.fault(fault),.sd_cmd(cmd),.sd_bank(bank),.sd_address(address),
 .sd_cke(cke),.sd_dqm(dqm),.dq_oe(oe),.dq_out(dout),.dq_in(din));
 pin_memory memory(clk,resetn,cmd,bank,address,dqm,oe,dout,din);
 always @(negedge clk)sv=init && consumed_s<offered_s;
 always @(posedge clk)if(resetn)begin
  if(init)begin
   sacc=sacc+6734;
   if(sacc>=18000)begin sacc=sacc-18000;offered_s=offered_s+1;end
  end
  if(sv&&sr)consumed_s=consumed_s+1;
  if(offered_s-consumed_s>256)$fatal(1,"S backlog");
  if(fault)$fatal(1,"joint fault");
  if(kv)begin
   context_seen[kc]=1; case(kc) 0:t0bits=t0bits+1; 1:t1bits=t1bits+1; 2:t2bits=t2bits+1; endcase
   if(kc==3 && checked_s>=64 && kb!==0)$fatal(1,"S known zero codeword");
   if(kc==3)checked_s=checked_s+1; else if(kb!==0)$fatal(1,"T zero codeword");
  end
 end
 '''+s[b:]
 s=s.replace(' if(re) ext_q<=mem[ra];\n if(we) mem[wa]<=wd;','')
 s=s.replace(' external_ready=!STALL || (cycles%97<77);','')
 s=s.replace('if(!STALL && (max_input_gap!=13 || max_output_gap!=13))','if(0)')
 s=s.replace('cycles<=cycles+1;', 'cycles<=cycles+1; if(cycles%50000==0)$display("PROGRESS cycles=%0d sent=%0d received=%0d",cycles,sent,received);')
 s=s.replace(' $finish;', ' if(t0bits!=384 || t1bits!=2432 || t2bits!=3456)$fatal(1,"T output counts %0d %0d %0d",t0bits,t1bits,t2bits); if(context_seen!=15 || !committed)$fatal(1,"T3/S coverage"); if(checked_s<1000)$fatal(1,"S coverage"); $display("S_CHECKED bits=%0d",checked_s); $finish;',1)
 m=memory_system().replace('MEM_WORDS=4096','MEM_WORDS=131072');a=m.index('module memory_system(');b=m.index('localparam MEM_WORDS',a)
 m=m[:a]+'''module pin_memory(input wire clk,resetn,input wire[2:0]cmd,
 input wire[1:0]bank,input wire[10:0]a,input wire[3:0]dqm,input wire oe,
 input wire[31:0]dout,output reg[31:0]din=0);
'''+m[b:]
 a=m.index('wire initialized');b=m.index('reg[20:0]pending_address',a);m=m[:a]+m[b:]
 a=m.index('dual_sdram_burst #');b=m.index('initial begin',a);m=m[:a]+m[b:]
 m=m.replace(' if(fault)$fatal(1,"SDRAM fault");','').replace(' if(valid&&ready)pending_address=addr;','')
 m=m.replace('base!=pending_address || ','')
 return s+m

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class FFTT3SBeatHoldTest(unittest.TestCase):
 def test_mode3_fft_and_t3_s(self):
  n=8192;words=vectors(n,'random')
  expected=sum((ORACLE.reference_fft(words[f*n:(f+1)*n],ORACLE.load_quarter())for f in range(3)),[])
  with tempfile.TemporaryDirectory()as temp:
   d=Path(temp);(d/'tb.sv').write_text(bench());(d/'input.hex').write_text(''.join(f'{w:08x}\n'for w in words))
   p=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(d/'sim'),str(d/'tb.sv'),*[str(ROOT/f)for f in FILES[:-1]]],cwd=ARCHIVE,text=True,capture_output=True)
   self.assertEqual(p.returncode,0,p.stderr)
   log=ROOT/'build/shared-receiver-fft-t3-s-beat-hold-sim.log'
   log.parent.mkdir(exist_ok=True)
   with log.open('w') as output:
    p=subprocess.run(['vvp',str(d/'sim'),f'+INPUT_HEX={d/"input.hex"}'],cwd=ARCHIVE,text=True,stdout=output,stderr=subprocess.STDOUT,timeout=900)
   p.stdout=log.read_text();p.stderr=''
   self.assertEqual(p.returncode,0,p.stdout[-3000:]+p.stderr)
  rows=[x.split()for x in p.stdout.splitlines()if x.startswith('OUT ')]
  self.assertEqual(len(rows),3*n)
  for k,row in enumerate(rows):
   self.assertEqual(int(row[2]),ORACLE.bit_reverse(k%n,13));self.assertEqual(int(row[3],16),expected[k])
  result=dict(scope=__doc__,FFT_checked_bins=len(rows),T_checked_output_bits=[384,2432,3456],S_checked_bits=int(re.search(r'S_CHECKED bits=(\d+)',p.stdout)[1]),whole_receiver_verified=False,source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()for f in FILES[:-1]+['tests/test_shared_receiver_fft_t3_s_beat_hold.py']})
  (ROOT/'reports/shared-receiver-fft-t3-s-beat-hold-test.json').write_text(json.dumps(result,indent=2)+'\n');print(result,flush=True)
