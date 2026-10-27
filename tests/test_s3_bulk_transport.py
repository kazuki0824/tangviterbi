"""Actual C descriptors + SPI CDC and bulk->page RTL (not throughput proof)."""
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class BulkTransportTest(unittest.TestCase):
    def test_raw_only_C_descriptor_and_lease(self):
        self.check_C_descriptor_and_lease(['-DS3_RAW_ONLY_SPI=1'])

    def test_C_descriptor_and_lease(self):
        self.check_C_descriptor_and_lease([])

    def check_C_descriptor_and_lease(self, extra):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp)/'host'
            subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                '-fsanitize=undefined','-fno-sanitize-recover=all']+extra+['-Itests/s3_sdk_shim',
                '-Iexperiments','experiments/s3_transport.c','experiments/s3_spi_transport.c',
                'tests/s3_bulk_transport_host.c','-o',str(exe)],cwd=ROOT,check=True)
            subprocess.run([str(exe)],check=True)

    def simulate(self, lanes, kind='normal', chunk=32768):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);rng=random.Random(811+lanes)
            raw=bytearray();want=[];frames=2 if kind=='normal' else 1
            size=chunk if kind!='truncated' else 128
            for frame in range(frames):
                offset=(0xfffff000+frame*chunk)&0xffffffff
                epoch=17 if kind!='epoch' else 18
                length=chunk if kind!='length' else 4096
                payload=rng.randbytes(size)
                raw.extend(bytes.fromhex('d711')+epoch.to_bytes(2,'big')+
                           offset.to_bytes(4,'big')+length.to_bytes(2,'big')+payload)
                if kind=='overrun':raw.extend(b'\x00')
                if kind=='normal':
                    for p in range(chunk//4096):
                        want.extend([(1<<32)|0xd7110011,(2<<32)|((offset+p*4096)&0xffffffff),(3<<32)|4096])
                        for i in range(p*4096,(p+1)*4096,4):
                            want.append(((8<<32) if i%4096==4092 else 0)|int.from_bytes(payload[i:i+4],'little'))
            if not want:want=[0]
            (out/'wire.hex').write_text(''.join(f'{x:02x}\n' for x in raw))
            (out/'want.hex').write_text(''.join(f'{x:09x}\n' for x in want))
            tb=r'''`timescale 1ns/1ps
module tb;
localparam LANES=@LANES@, FRAME_BYTES=@FRAME_BYTES@, FRAMES=@FRAMES@, NORMAL=@NORMAL@;
reg clk=0;always #5.050505 clk=~clk;
reg sck=0,cs=0,rst=1;reg[LANES-1:0]dq=0;
wire rv,rr,ov,sv,sr,sf;wire[35:0]rt,st;
s3_spi_rx #(.LANES(LANES),.WRITE_BYTES(@CHUNK@)) rx(sck,cs,clk,rst,dq,rv,rr,rt,ov);
s3_bulk_page_split #(.WRITE_BYTES(@CHUNK@)) split(clk,rst,16'd17,rv,rr,rt,sv,sr,st,sf);
reg consume=1;
wire gr,gs,gd,gc,gf,greq;wire[1:0]stream;wire[31:0]offset,data;
s3_page_guard guard(clk,rst,16'd17,sv,gr,st,1'b1,gs,stream,offset,gd,consume,data,gc,gf,greq);
assign sr=gr;
reg[7:0]wire_data[0:@RAW_LAST@];reg[35:0]want[0:@WANT_LAST@];
integer got=0,commits=0,i,k,f;reg[31:0]rng=32'hbed73120;
reg stalled=0;reg[35:0]held;
always @(negedge clk) begin
 rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);consume=rng[2:0]!=0;
end
always @(posedge clk) if(rst) begin
 if(NORMAL && (ov||sf||gf)) $fatal(1,"unexpected fault %b%b%b",ov,sf,gf);
 if(NORMAL && stalled && (!sv || st!==held)) $fatal(1,"unstable stalled output");
 stalled=sv&&!sr;held=st;
 if(NORMAL && sv&&sr) begin
  if(got>=@WANT_COUNT@ || st!==want[got]) $fatal(1,"token mismatch %0d",got);
  got=got+1;
 end
 if(gc) commits=commits+1;
end
initial begin
 $readmemh("wire.hex",wire_data);$readmemh("want.hex",want);
 #1;rst=0;#1;cs=1;#38;rst=1;#100;
 for(f=0;f<FRAMES;f=f+1) begin
  cs=0;
  for(i=0;i<FRAME_BYTES;i=i+1) begin
   for(k=8-LANES;k>=0;k=k-LANES) begin
    dq=wire_data[f*FRAME_BYTES+i]>>k;#6.25;sck=1;#6.25;sck=0;
   end
  end
  cs=1;#250;
 end
 if(NORMAL) begin
  #2000;
  if(got!=@WANT_COUNT@ || commits!=@COMMITS@) $fatal(1,"missing output tokens=%0d commits=%0d",got,commits);
 end else begin
  #2800000;
  if(!(ov||sf||gf)) $fatal(1,"negative case escaped detection");
 end
 $display("PASS lanes=%0d normal=%0d tokens=%0d commits=%0d faults=%b%b%b",LANES,NORMAL,got,commits,ov,sf,gf);
 $finish;
end
endmodule
'''
            fields={'CHUNK':chunk,'COMMITS':frames*chunk//4096,'LANES':lanes,'FRAME_BYTES':len(raw)//frames,'FRAMES':frames,
                    'NORMAL':int(kind=='normal'),'RAW_LAST':len(raw)-1,
                    'WANT_LAST':len(want)-1,'WANT_COUNT':len(want)}
            for key,value in fields.items():tb=tb.replace('@'+key+'@',str(value))
            (out/'tb.sv').write_text(tb)
            subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim')]+[
                str(ROOT/'rtl'/f) for f in ['s3_async_fifo.sv','s3_spi_rx.sv','s3_bulk_page_split.sv','s3_page_guard.sv']]+[str(out/'tb.sv')],check=True,capture_output=True,text=True)
            run=subprocess.run(['vvp','sim'],cwd=out,text=True,capture_output=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            print(kind,run.stdout.strip())

    def test_octal_quad_lossless_wrap_and_page_commit(self):
        for lanes in (4,8):
            with self.subTest(lanes=lanes):self.simulate(lanes)

    def test_short_frames_and_rejection(self):
        for lanes in (4,8):
            for kind in ("normal","length","epoch","truncated","overrun"):
                with self.subTest(lanes=lanes,kind=kind):self.simulate(lanes,kind,16384)

    def test_malformed_and_truncated_frames_poison_epoch(self):
        for lanes in (4,8):
            for kind in ('length','epoch','truncated','overrun'):
                with self.subTest(lanes=lanes,kind=kind):self.simulate(lanes,kind)

if __name__=='__main__':unittest.main()
