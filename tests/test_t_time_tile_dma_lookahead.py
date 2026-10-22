"""Full finite tile oracle with raw per-client address lookup before selection."""
import test_t_time_tile_dma_onehot as base
class TileDMATest(base.TileDMATest):
 def test_real_data_and_deadlines(self):
  files,tb,memory=base.FILES,base.TB,base.memory_system
  try:
   base.FILES=[f.replace('sdram_client_arbiter_tile_grace.sv','sdram_client_arbiter_lookahead.sv').replace('dual_sdram_refresh_predecode.sv','dual_sdram_client_lookahead.sv')for f in files]
   base.TB=tb.replace('wire qv,qr,qw,qrv,qrr;', 'wire[5:0]lookup_selected;wire qv,qr,qw,qrv,qrr;').replace('qv,qr,qw,qa,qd,mask,qrv,qrr,rd);','qv,qr,qw,qa,qd,mask,qrv,qrr,rd,lookup_selected);').replace('memory(clk,rst,qv,qr,qw,qa,qd,qrv,rd);','memory(clk,rst,qv,qr,qw,qa,qd,qrv,rd,aa,lookup_selected);')
   def wrapped():
    return memory().replace('output wire rv,output wire[255:0]response);','output wire rv,output wire[255:0]response,input wire[125:0]lookup_address,input wire[5:0]lookup_selected);').replace('cmd,bank,a,cke,dqm,oe,dout,din);','cmd,bank,a,cke,dqm,oe,dout,din,lookup_address,lookup_selected);')
   base.memory_system=wrapped
   super().test_real_data_and_deadlines()
  finally:base.FILES,base.TB,base.memory_system=files,tb,memory
