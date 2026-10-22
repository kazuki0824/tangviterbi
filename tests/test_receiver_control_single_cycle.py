"""Find a legal single-cycle DMA-op-change -> accepted SDRAM request witness.
This rejects blanket multicycle exceptions for the entire request path; it does
not classify every mapped arc, prove remaining-counter multicycle timing, or
replace routed STA.
"""
import contextlib,hashlib,io,json,os,re
import test_t_time_tile_dma_onehot as base
MONITOR=r'''
integer mon_cycle=0,op_one_cycle=0,phase_one_cycle=0;
reg op_changed=0,phase_changed=0;reg[1:0]old_op,old_phase;
always @(posedge clk)begin
 mon_cycle=mon_cycle+1;
 if(rst && ev && ready[2])begin
  if(!qv || !qr)$fatal(1,"accepted tile request not forwarded");
  if(op_changed)op_one_cycle=op_one_cycle+1;
  if(phase_changed)phase_one_cycle=phase_one_cycle+1;
 end
 old_op=engine.op;old_phase=engine.phase;
 #1;op_changed=rst&&(engine.op!=old_op);phase_changed=rst&&(engine.phase!=old_phase);
end
'''
class SingleCycleTest(base.TileDMATest):
 def test_real_data_and_deadlines(self):
  tb,engine,env=base.TB,base.ENGINE,dict(os.environ)
  try:
   base.ENGINE=engine+MONITOR
   base.TB=tb.replace('if(all_done)begin', 'if(all_done)begin\n $display("SINGLE_CYCLE op=%0d phase=%0d",op_one_cycle,phase_one_cycle);\n if(op_one_cycle==0)$fatal(1,"no single-cycle op witness");')
   os.environ.update(TTI_TILE_COUNT='6',TTI_COMPETING='0',TTI_DMA_REPORT='reports/control-path-witness.json')
   output=io.StringIO()
   with contextlib.redirect_stdout(output):super().test_real_data_and_deadlines()
   text=output.getvalue();print(text,flush=True)
   m=re.search(r'SINGLE_CYCLE op=(\d+) phase=(\d+)',text);self.assertIsNotNone(m)
   counts=list(map(int,m.groups()));self.assertGreater(counts[0],0)
   p=base.ROOT/os.environ['TTI_DMA_REPORT'];r=json.loads(p.read_text())
   r.update(scope=__doc__,op_change_to_accept_one_cycle=counts[0],phase_change_to_accept_one_cycle=counts[1],blanket_multicycle_exception_justified=False)
   r['source_sha256']['tests/test_receiver_control_single_cycle.py']=hashlib.sha256((base.ROOT/'tests/test_receiver_control_single_cycle.py').read_bytes()).hexdigest()
   p.write_text(json.dumps(r,indent=2)+'\n')
  finally:
   base.TB,base.ENGINE=tb,engine;os.environ.clear();os.environ.update(env)
