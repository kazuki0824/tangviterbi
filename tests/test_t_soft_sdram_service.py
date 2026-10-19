"""Compare the integrated wrapper against the original separate reader/service.
Finite synthetic traffic; not an independent SDRAM pin model or real-K7 test.
"""
import hashlib,json,os,re,shutil,subprocess,tempfile,unittest
from pathlib import Path
from tests.test_t_soft_reader_service import TB
ROOT=Path(__file__).resolve().parents[1]
FILES=['t_soft_reader.sv','sdf_sdram_service.sv','sdf_delay_cache.sv',
       'sdram_client_arbiter.sv','dual_sdram_burst.sv','t_soft_sdram_service.sv']
EXTRA=r'''
wire ccommit_ready;wire[1:0]clive;wire creuse,csoft_valid,cfault,cinitialized,cer;
wire[1:0]ccontext;wire[7:0]csoft_data;wire[3:0]cready,crsp_valid;
wire[255:0]crsp_data;wire[31:0]crdata,cdq;wire[2:0]ccmd;
wire[1:0]cbank;wire[10:0]caddress;wire ccke,coe;wire[3:0]cdqm;
t_soft_sdram_service candidate(
 .clk(clk),.resetn(resetn),.sample_accept(take),.external_ready(cer),
 .read_enable(re),.read_address(ra),.read_data(crdata),
 .write_enable(we),.write_address(wa),.write_data(wd),
 .bg_valid({v[4:2],v[0]}),.bg_ready(cready),.bg_write({w[4:2],w[0]}),
 .bg_address({a[104:42],a[20:0]}),.bg_data({data[1279:512],data[255:0]}),
 .bg_dqm({mask[159:64],mask[31:0]}),.bg_rsp_valid(crsp_valid),
 .bg_rsp_ready(4'b1111),.bg_rsp_data(crsp_data),
 .commit_valid(commit),.commit_ready(ccommit_ready),
 .commit_addresses({21'd12800,21'd10496,21'd8192}),
 .commit_lengths({16'd11520,16'd9216,16'd9216}),
 .bank_live(clive),.reuse_blocked(creuse),.soft_valid(csoft_valid),.soft_ready(1'b1),
 .soft_context(ccontext),.soft_data(csoft_data),.initialized(cinitialized),.fault(cfault),
 .sd_cmd(ccmd),.sd_bank(cbank),.sd_address(caddress),.sd_cke(ccke),.sd_dqm(cdqm),
 .dq_oe(coe),.dq_out(cdq),.dq_in(32'h12345678));
always @(negedge clk)begin
 #2;if(cycle>4)begin
  if({commit_ready,live,reuse,sv,sc,sd,initialized,(sf|rf),er,rdata,
    br[4:2],br[0],bv[4:2],bv[0],cmd,bank,sa,cke,dqm,oe}!==
    {ccommit_ready,clive,creuse,csoft_valid,ccontext,csoft_data,cinitialized,cfault,cer,crdata,
    cready,crsp_valid,ccmd,cbank,caddress,ccke,cdqm,coe})$fatal(1,"integrated control/cache/soft mismatch cycle %0d",cycle);
  if(oe && dq!==cdq)$fatal(1,"write payload/mask mapping mismatch");
  if(|bv && bd!==crsp_data)$fatal(1,"response data mismatch");
 end
end
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class IntegratedServiceTest(unittest.TestCase):
 def test_cycle_equivalence_thirteen_phases(self):
  traces=[]
  tb=TB.replace('parameter FFT_PHASE=0;',"parameter FFT_PHASE=0;\nreg[31:0]payload_rng=32'h821719;integer j;")
  tb=tb.replace('v[i]=1;w[i]=', '''for(j=0;j<8;j=j+1)begin
   payload_rng=payload_rng^(payload_rng<<13);payload_rng=payload_rng^(payload_rng>>17);payload_rng=payload_rng^(payload_rng<<5);
   data[i*256+j*32+:32]=payload_rng;
  end
  mask[i*32+:32]=payload_rng;
  v[i]=1;w[i]=''')
  tb=tb.replace('endmodule',EXTRA+'\nendmodule')
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(tb)
   for phase in range(13):
    with self.subTest(phase=phase):
     subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.FFT_PHASE={phase}','-o',str(p/'sim'),str(p/'tb.sv'),*(str(ROOT/'rtl'/f)for f in FILES)],check=True)
     r=subprocess.run(['vvp',str(p/'sim')],text=True,capture_output=True,timeout=90)
     self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('RESULT',r.stdout)
     values={k:int(v)for k,v in re.findall(r'(\w+)=(\d+)',r.stdout)}
     traces.append(dict(phase=phase,**values));print('phase',phase,r.stdout.splitlines()[0],flush=True)
  result=dict(scope=__doc__,traces=traces,all_finite_deadlines_pass=all(not t['deadline_missed']for t in traces),cycle_equivalence_pass=True,
    source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest()for f in [Path(__file__),ROOT/'tests/test_t_soft_reader_service.py',*(ROOT/'rtl'/x for x in FILES)]},whole_receiver_verified=False,formal_routes=0)
  if os.environ.get('T_SOFT_INTEGRATED_REPORT'):Path(os.environ['T_SOFT_INTEGRATED_REPORT']).write_text(json.dumps(result,indent=2)+'\n')
