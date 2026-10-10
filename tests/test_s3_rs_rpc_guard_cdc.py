"""90 MHz staging reader -> 27 MHz guard, with real C RPC payloads."""
from pathlib import Path
import ctypes as c,hashlib,json,re,subprocess,sys,unittest
import test_s3_rs_rpc as rpc
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from s3_rs_rpc_guard_registered import source

class GuardCdcTest(unittest.TestCase):
 def test_independent_clocks_full_pages_backpressure_fault_reset(self):
    rpc.RpcTest.setUpClass();host=rpc.RpcTest();host.setUp();cases=[]
    for batch in range(5):
        _,syn,roots=host.records(batch);ctx=rpc.Context();tx=rpc.Page()
        self.assertEqual(host.solve(ctx,rpc.page(1,syn,batch=batch),tx,batch=batch),1)
        cases.append((bytes(tx),2,batch,0,4096))
        self.assertEqual(host.roots(ctx,rpc.page(3,roots,batch=batch),tx),1)
        cases.append((bytes(tx),4,batch,0,4096))
    good=cases[0][0]
    bad=bytearray(good);bad[100]^=1;cases.append((bad,2,0,2,4096))
    cases.append((good,2,1,1,4096));cases.append((good,2,0,4,1000));cases.append((good,2,0,0,4096))
    out=ROOT/'build/s3-rs-rpc-guard-cdc';out.mkdir(parents=True,exist_ok=True)
    (out/'guard.sv').write_text(source(True))
    (out/'pages.hex').write_text(''.join(f'{b:02x}\n' for p,*_ in cases for b in p))
    setup='\n'.join(f'kind[{i}]={k};batch[{i}]={b};mask[{i}]={m};length[{i}]={l};' for i,(_,k,b,m,l) in enumerate(cases))
    (out/'tb.sv').write_text(f'''`timescale 1ns/1ps
module tb;
reg wclk=0,clk=0;always #(50.0/9.0)wclk=~wclk;always #(500.0/27.0)clk=~clk;
reg rst=0,cv=0,iv=0,last=0,rr=0;reg[7:0]data=0,ckind=2;reg[31:0]cbatch=0;
wire cr,ir,rv;wire[5:0]errors;
s3_rs_rpc_guard_cdc #(.GAP_CYCLES(32)) dut(wclk,clk,rst,cv,cr,ckind,16'd17,cbatch,iv,ir,data,last,rv,rr,errors);
reg[7:0]pages[0:{4096*len(cases)-1}],kind[0:{len(cases)-1}];reg[31:0]batch[0:{len(cases)-1}];
reg[5:0]mask[0:{len(cases)-1}];integer length[0:{len(cases)-1}];
integer t,j,blocked=0,bytes_sent=0,waited;realtime started,maximum=0,elapsed;reg[5:0]held;
task clean_reset;begin
 @(negedge wclk);rst=0;iv=0;cv=0;rr=0;last=0;repeat(6)@(negedge clk);rst=1;repeat(3)@(negedge clk);
end endtask
task start_page;begin
 @(negedge clk);if(!cr)$fatal(1,"config blocked");cv=1;
 @(negedge clk);cv=0;started=$realtime;
end endtask
task send_byte;input[7:0]b;input final_byte;begin
 @(negedge wclk);iv=1;data=b;last=final_byte;
 @(posedge wclk);while(!ir)begin blocked=blocked+1;@(posedge wclk);end
 bytes_sent=bytes_sent+1;@(negedge wclk);iv=0;last=0;
end endtask
initial begin
 $readmemh("pages.hex",pages);{setup}
 clean_reset();
 for(t=0;t<{len(cases)};t=t+1)begin
  ckind=kind[t];cbatch=batch[t];start_page();
  for(j=0;j<length[t];j=j+1)begin
   if(j%197==0)repeat(3)@(negedge wclk);
   send_byte(pages[t*4096+j],j==length[t]-1);
  end
  waited=0;while(!rv)begin @(negedge clk);waited=waited+1;if(waited>512)$fatal(1,"no result");end
  elapsed=$realtime-started;if(mask[t]==0&&elapsed>maximum)maximum=elapsed;
  if(mask[t]==0&&errors!=0)$fatal(1,"good page case=%0d errors=%0h",t,errors);
  if(mask[t]!=0&&(errors&mask[t])!=mask[t])$fatal(1,"bad page case=%0d errors=%0h",t,errors);
  held=errors;repeat(7)begin @(negedge clk);if(!rv||errors!==held||cr)$fatal(1,"unstable result");end
  rr=1;@(negedge clk);rr=0;
  if(mask[t]!=0)clean_reset();
 end
 // FIFO may still contain an old byte on a dirty stop. Reset both domains.
 ckind=2;cbatch=0;start_page();send_byte(8'h52,0);clean_reset();
 start_page();send_byte(8'h52,0);repeat(40)@(negedge clk);
 if(!rv||!errors[5])$fatal(1,"missing cross-clock timeout");clean_reset();
 if(rv||!cr)$fatal(1,"reset leaked result");
 if(blocked<10000)$fatal(1,"insufficient backpressure");
 $display("PASS pages=%0d bytes=%0d blocked_writer_cycles=%0d max_good_page_ns=%0.3f",{len(cases)},bytes_sent,blocked,maximum);$finish;
end
endmodule''')
    paths=[ROOT/'rtl/s3_async_fifo.sv',ROOT/'rtl/s3_rs_rpc_guard_cdc.sv',out/'guard.sv',out/'tb.sv']
    for cmd in (['iverilog','-g2012','-s','tb','-o','sim',*map(str,paths)],['vvp','sim']):
        p=subprocess.run(cmd,cwd=out,capture_output=True,text=True,timeout=120)
        with (out/'simulation.log').open('a') as f:f.write(p.stdout+p.stderr)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
    match=re.search(r'PASS pages=(\d+) bytes=(\d+) blocked_writer_cycles=(\d+) max_good_page_ns=([.\d]+)',p.stdout)
    self.assertIsNotNone(match,p.stdout)
    result=dict(result='pass',write_clock_MHz=90,check_clock_MHz=27,pages=int(match[1]),
        bytes=int(match[2]),blocked_writer_cycles=int(match[3]),max_good_page_ns=float(match[4]),
        cfg_and_result_clock_domain='27 MHz; ownership/descriptor/result CDC not integrated',
        data_FIFO_capacity_words=128,prefetch_output_words=2,payload_word_bits=9,
        stream_requires_backpressure=True,whole_page_storage_implemented=False,
        receiver_adopted=False,safe_to_flash=False,
        sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
          paths+[ROOT/'rtl/s3_rs_rpc_guard.sv',ROOT/'experiments/s3_rs_rpc_guard_registered.py',Path(__file__)]})
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':unittest.main()
