"""Independent history, ownership and overlapping capture checks for T buffer."""
import os,shutil,unittest
from unittest.mock import patch
import test_dual_t_time_dma as base

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class BufferedTime(unittest.TestCase):
 def test_histories_and_stalls(self):
  self._run(False)
 def test_overlap_capture_with_processing(self):
  self._run(True)
 def _run(self,pipeline):
  bench='`include "'+str(base.ROOT/'rtl/dual_t_buffered_time_dma.sv')+'"\n'+base.BENCH.replace('dual_t_time_dma #','dual_t_buffered_time_dma #').replace('dut.MAXD','dut.time_dma.MAXD')
  old='if(frame>0 && got<(frame-1)*N+sent+4 && !(ov&&ordy))$fatal(1,"overwrite before delivery");'
  assert old in bench
  bench=bench.replace(old,'')
  monitor=r'''integer inner_sent=0;
always @(posedge clk)if(resetn)begin
 if(start&&ready&&!drain)inner_sent=0;
 if(dut.time_dma.in_valid&&dut.time_dma.in_ready)begin
  if(frame>0 && got<(frame-1)*N+inner_sent+4 && !(ov&&ordy))$fatal(1,"inner overwrite before delivery");
  for(integer lane=0;lane<4;lane=lane+1)
   if(dut.time_dma.in_data[lane*8+:8]!==input_byte(frame,inner_sent+lane))$fatal(1,"buffer corrupted input");
  inner_sent=inner_sent+4;
 end
end
'''
  bench=bench.replace('initial begin\n $readmemh',monitor+'initial begin\n $readmemh')
  if pipeline:
   bench=bench.replace('wait(done);@(negedge clk);','wait(ready);@(negedge clk);',1)
   bench=bench.replace(' || !result)',')')
   bench=bench.replace('wait(done);@(negedge clk);','wait(done&&got==FRAMES*N);@(negedge clk);')
   bench=bench.replace('integer inner_sent=0;', 'integer inner_sent=0,overlap_count=0;\nalways @(posedge clk)if(resetn&&start&&ready&&!drain&&dut.child_busy)overlap_count=overlap_count+1;')
   bench=bench.replace(' $display("PASS',' if(overlap_count==0)$fatal(1,"no overlapping capture coverage");\n $display("PASS')
  with patch.object(base,'BENCH',bench),patch.dict(os.environ):
   os.environ.pop('DUAL_T_TIME_REPORT',None)
   if pipeline:os.environ['DUAL_T_FAST']='1'
   base.TimeDMA().test_natural_order_and_ownership()
