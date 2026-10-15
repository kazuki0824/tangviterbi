"""Natural LLR source for real T DMA; no Python SDRAM descriptors for T."""
import json
from test_dual_t_time_dma import expected_byte


def connect(bench,folder,mode,layers,frames):
    layers=list(layers)+[(0,0)]*(3-len(layers))
    n=13*96*(1<<(mode-1))*6;period=259875*(1<<(mode-1))
    (folder/'t_expected.hex').write_text('\n'.join(f'{expected_byte(f,i,mode,layers):02x}' for f in range(frames) for i in range(n))+'\n')
    import re
    params=','.join(f'.S{i}({s}),.I{i}({length})' for i,(s,length) in enumerate(layers))
    bench=re.sub(r'dual_fft_s_memory #\([^\n]+\)',f'dual_fft_ts_memory #(.INIT_CYCLES(32),.MODE({mode}),{params})',bench)
    bench=bench.replace('dut.memory.memory.','dut.memory.')
    bench=bench.replace('sclast,sslast,sfault,spackets,sowners);',
        'sclast,sslast,sfault,spackets,sowners,tstart,tsready,tdrain,tiv,tir,tid,tov,tor,tod,tlast,tsettled,tresult,tdone,tbusy,tfault);')
    defs=f'''localparam TN={n},TPERIOD={period};
reg[7:0] texpected[0:FRAMES*TN-1];
initial $readmemh({json.dumps(str(folder/'t_expected.hex'))},texpected);
reg tstart=0,tdrain=0,tiv=0,tor=1;reg[31:0] tid=0;
wire tsready,tir,tov,tlast,tsettled,tresult,tdone,tbusy,tfault;wire[31:0] tod;
integer tstarted=0,tframe=0,tsent=TN,tgot=0,tproduced=0,tcaptured=0;
integer tpeak=0,tcompute_misses=0,toutput_misses=0,tdrained=0,treads=0,twrites=0;
real tworst=0,tfinish;
always @(negedge mclk)begin
 if(active)while(tproduced<FRAMES && $realtime-epoch>=tproduced*TPERIOD)tproduced=tproduced+1;
 if(tproduced-tcaptured>tpeak)tpeak=tproduced-tcaptured;
 tstart=active&&tsready&&!tdrained&&(tstarted<tproduced || (tstarted==FRAMES&&tresult));
 tdrain=tstarted==FRAMES && tsready && tresult;
 tiv=!tdrain && tsent<TN;
 for(integer lane=0;lane<4;lane=lane+1)tid[lane*8+:8]=(tframe*73+(tsent+lane)*19+((tsent+lane)/251)*11)&255;
end
always @(posedge mclk)if(resetn)begin
 if(tfault)$fatal(1,"T DMA fault");
 if(tdone)begin
  if(tgot==FRAMES*TN)tdrained=1;
  else begin
   tfinish=$realtime-epoch-tframe*TPERIOD;
   if(tfinish>tworst)tworst=tfinish;
   if(tfinish>TPERIOD)tcompute_misses=tcompute_misses+1;
  end
 end
 if(tstart&&tsready&&!tdrain)begin tframe=tstarted;tstarted=tstarted+1;tsent=0;end
 if(tiv&&tir)begin tsent=tsent+4;if(tsent==TN)tcaptured=tcaptured+1;end
 if(tov&&tor)begin
  for(integer lane=0;lane<4;lane=lane+1)if(tgot>=FRAMES*TN || tod[lane*8+:8]!==texpected[tgot+lane])$fatal(1,"T byte mismatch %0d got %h expected %h",tgot,tod,texpected[tgot]);
  if(tlast!==(tgot%TN==TN-4))$fatal(1,"T boundary");
  if(tlast && $realtime-epoch>(tgot/TN+2)*TPERIOD)toutput_misses=toutput_misses+1;
  tgot=tgot+4;
 end
 if(dut.ttime.req_valid&&dut.ttime.req_ready)begin
  if(dut.ttime.req_write)twrites=twrites+1;else treads=treads+1;
 end
end
'''
    bench=bench.replace('wait(received==REQUESTS && sreceived==SREQ);','wait(received==REQUESTS && sreceived==SREQ && tdrained);')
    bench=bench.replace(' $display("QUEUE', ''' deadline_misses[0]=tcompute_misses+toutput_misses;
 $display("TREAL frames=%0d output_bytes=%0d reads=%0d writes=%0d pending_input_frames=%0d pending_input_bytes=%0d compute_misses=%0d output_misses=%0d worst_release_to_done_ns=%0.3f",FRAMES,tgot,treads,twrites,tpeak,tpeak*TN,tcompute_misses,toutput_misses,tworst);
 $display("QUEUE''')
    return bench,defs
