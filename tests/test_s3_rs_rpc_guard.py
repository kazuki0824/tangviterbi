"""Actual C-produced RPC pages into FPGA guard, with independent CRC faults."""
from pathlib import Path
import ctypes as c,hashlib,json,subprocess,sys,unittest
import test_s3_rs_rpc as rpc
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from s3_rs_rpc_guard_registered import source as registered_source

class GuardTest(unittest.TestCase):
 def test_c_pages_crc_semantics_lengths_timeout_and_reset(self):
    self.check(False)
 def test_registered_payload_same_cycles(self):
    self.check(True)
 def test_registered_bit_ranges_same_cycles(self):
    self.check(True,True)
 def check(self,registered,bit_ranges=False):
    rpc.RpcTest.setUpClass();host=rpc.RpcTest();host.setUp()
    cases=[];good=[]
    def add(p,kind,batch,mask=0,length=4096,last=True):
        cases.append((bytes(p),kind,batch,mask,length,last))
    for batch in (0,1,2,3,0xffffffff):
        _,syn,roots=host.records(batch);ctx=rpc.Context();tx=rpc.Page()
        self.assertEqual(host.solve(ctx,rpc.page(1,syn,batch=batch),tx,batch=batch),1)
        good.append(bytes(tx));add(tx,2,batch)
        self.assertEqual(host.roots(ctx,rpc.page(3,roots,batch=batch),tx),1)
        good.append(bytes(tx));add(tx,4,batch)
    # Valid upstream failure records must remain failed, with zero payload.
    _,syn,roots=host.records(0);syn[0]=bytes(2)+bytes([1])+bytes(16)
    roots[0]=bytes(2)+bytes([255])+bytes(9)
    ctx=rpc.Context();tx=rpc.Page();self.assertEqual(host.solve(ctx,rpc.page(1,syn),tx),1)
    failed_lambda=bytes(tx);add(tx,2,0)
    self.assertEqual(host.roots(ctx,rpc.page(3,roots),tx),1)
    failed_mags=bytes(tx);add(tx,4,0)
    # Corrupt protected header, payload, boundaries and padding without CRC repair.
    for p in good[:2]:
        kind=p[3]
        for offset in list(range(16))+[16,18,19,2463,2464,2667,2668,4095]:
            bad=bytearray(p);bad[offset]^=1;add(bad,kind,0,2)
    # Recomputed CRC cannot make malformed semantics/identity acceptable.
    mutations=[(0,0,1),(2,2,1),(3,3,1),(4,18,1),(6,203,1),(8,1,1),
               (16,1,8),(17,1,8),(18,2,8),(4095,1,16)]
    for p in good[:2]:
        kind=p[3]
        for offset,value,error in mutations:
            bad=bytearray(p);bad[offset]=value;add(rpc.crc_page(bad),kind,0,error)
    for offset,value in ((19,9),(20,0),(28,1),(16+203*13,202)):
        bad=bytearray(good[0]);bad[offset]=value;add(rpc.crc_page(bad),2,0,8)
    bad=bytearray(failed_lambda);bad[20]=1;add(rpc.crc_page(bad),2,0,8)
    for offset,value in ((27,1),(16+203*12,202)):
        bad=bytearray(good[1]);bad[offset]=value;add(rpc.crc_page(bad),4,0,8)
    bad=bytearray(failed_mags);bad[19]=1;add(rpc.crc_page(bad),4,0,8)
    for length in (1,15,16,101,4095):add(good[0],2,0,4,length)
    add(good[0],2,0,4,4096,False)
    # End with known-good data after every failure and dirty-reset scenarios.
    add(good[0],2,0)
    name='s3-rs-rpc-guard'+('-registered' if registered else '')+('-ranges' if bit_ranges else '')
    out=ROOT/'build'/name;out.mkdir(parents=True,exist_ok=True)
    (out/'pages.hex').write_text(''.join(f'{b:02x}\n' for p,*_ in cases for b in p))
    setup='\n'.join(f"kinds[{i}]=8'd{k};batches[{i}]=32'h{b:08x};masks[{i}]=6'd{m};lengths[{i}]={l};lasts[{i}]={int(last)};"
                     for i,(_,k,b,m,l,last) in enumerate(cases))
    (out/'tb.sv').write_text(f'''module tb;
reg clk=0;always #5 clk=~clk;reg rst=0,cv=0,iv=0,il=0,rr=0;
reg[7:0]kind=2,data=0;reg[31:0]batch=0;wire cr,ir,rv;wire[5:0]errors;
s3_rs_rpc_guard #(.GAP_CYCLES(32)) dut(clk,rst,cv,cr,kind,16'd17,batch,iv,ir,data,il,rv,rr,errors);
reg[7:0]pages[0:{4096*len(cases)-1}],kinds[0:{len(cases)-1}];reg[31:0]batches[0:{len(cases)-1}];
reg[5:0]masks[0:{len(cases)-1}];integer lengths[0:{len(cases)-1}];reg lasts[0:{len(cases)-1}];
integer t,j,checks=0,commits=0,cycle=0;reg[5:0]held;
task reset_guard;begin @(negedge clk);rst=0;iv=0;cv=0;rr=0;repeat(3)@(negedge clk);rst=1;end endtask
task configure;begin
 @(negedge clk);if(!cr)$fatal(1,"config blocked");cv=1;
 @(negedge clk);cv=0;if(!ir)$fatal(1,"not receiving");
end endtask
initial begin
 $readmemh("pages.hex",pages);{setup}
 reset_guard();
 for(t=0;t<{len(cases)};t=t+1)begin
  kind=kinds[t];batch=batches[t];configure();
  for(j=0;j<lengths[t];j=j+1)begin
   @(negedge clk);iv=0;
   if(j%137==0)repeat(3)@(negedge clk);
   if(rv)$fatal(1,"early page publication");
   data=pages[t*4096+j];il=(j==lengths[t]-1)&&lasts[t];iv=1;
   @(posedge clk);if(!ir)$fatal(1,"lost byte");checks=checks+1;
  end
  @(negedge clk);iv=0;il=0;
  if(!rv)$fatal(1,"no result case=%0d",t);
  if(masks[t]==0 && errors!=0)$fatal(1,"good page rejected case=%0d errors=%0h",t,errors);
  if(masks[t]!=0 && (errors&masks[t])!=masks[t])$fatal(1,"bad page accepted case=%0d errors=%0h mask=%0h",t,errors,masks[t]);
  if(errors==0)commits=commits+1;
  held=errors;
  // Held completion rejects new bytes/config until acknowledged.
  iv=1;cv=1;repeat(7)begin @(negedge clk);if(!rv||errors!==held||ir||cr)$fatal(1,"unstable result");end
  iv=0;cv=0;rr=1;@(negedge clk);rr=0;
 end
 // Partial input then silence expires; no fake complete page is published.
 kind=2;batch=0;configure();@(negedge clk);iv=1;data=8'h52;
 @(negedge clk);iv=0;repeat(35)@(negedge clk);
 if(!rv||!errors[5])$fatal(1,"missing timeout");
 reset_guard();configure();@(negedge clk);iv=1;data=8'h52;
 @(negedge clk);iv=0;reset_guard();
 if(rv||ir||!cr)$fatal(1,"dirty reset");
 $display("PASS pages=%0d bytes=%0d committed=%0d timeout=1 dirty_reset=1",{len(cases)},checks,commits);$finish;
end
endmodule''')
    paths=[str(ROOT/'rtl/s3_rs_rpc_guard.sv'),'tb.sv']
    if registered:
        (out/'guard.sv').write_text(registered_source(bit_ranges))
        (out/'reference.sv').write_text((ROOT/'rtl/s3_rs_rpc_guard.sv').read_text().replace('module s3_rs_rpc_guard','module reference_guard'))
        compare='''wire xcr,xir,xrv;wire[5:0]xe;
reference_guard #(.GAP_CYCLES(32)) refguard(clk,rst,cv,xcr,kind,16'd17,batch,iv,xir,data,il,xrv,rr,xe);
always @(posedge clk)begin #1;if(rst)begin
 if(cr!==xcr||ir!==xir||rv!==xrv||(rv&&errors!==xe))$fatal(1,"registered guard mismatch");
end end
endmodule'''
        (out/'tb.sv').write_text((out/'tb.sv').read_text().replace('endmodule',compare))
        paths=['guard.sv','reference.sv','tb.sv']
    for command in (['iverilog','-g2012','-s','tb','-o','sim',*paths],['vvp','sim']):
        p=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=120)
        with (out/'simulation.log').open('a') as f:f.write(p.stdout+p.stderr)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
    self.assertIn('PASS',p.stdout)
    result=dict(result='pass',pages=len(cases),accepted_pages=sum(m==0 for _,_,_,m,_,_ in cases),
        checked_bytes=sum(l for _,_,_,_,l,_ in cases),valid_C_producer_pages=12,
        crc_oracle='Python zlib CRC32/ISO-HDLC, independent of C and RTL',
        timeout_checked=True,dirty_reset_checked=True,held_result_checked=True,
        payload_storage_implemented=False,ownership_scheduler_implemented=False,
        registered_payload=registered,explicit_bit_ranges=bit_ranges,cycle_equivalence_to_original_checked=registered,
        receiver_adopted=False,safe_to_flash=False,
        sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
          [ROOT/'rtl/s3_rs_rpc_guard.sv',ROOT/'tests/test_s3_rs_rpc_guard.py',ROOT/'experiments/s3_rs_rpc.c',
           ROOT/'experiments/s3_rs_rpc_guard_registered.py']})
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':unittest.main()
