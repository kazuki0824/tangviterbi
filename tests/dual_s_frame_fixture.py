"""Byte-source fixture for the real S DMA; no SDRAM address stimulus."""
import json
from test_dual_s_frame_dma import reference


def connect(bench, folder, superframes):
    # The legacy watchdog scales only with the number of T FFT frames. A
    # short Mode-3 run can end that watchdog before one S bank can drain.
    # Extend only the deadlock watchdog; the S reuse deadline below is unchanged.
    old='if(corecycles>FRAMES*250000)$fatal(1,"timeout");'
    new=f'if(corecycles>FRAMES*250000 && $realtime-epoch>{(superframes+3)*77952*4000/28.86:.6f})$fatal(1,"timeout");'
    assert old in bench
    bench=bench.replace(old,new)
    incoming, expected = reference(superframes)
    for name, values in [('s_input_bytes', incoming), ('s_output_bytes', expected)]:
        (folder/f'{name}.hex').write_text('\n'.join(f'{x:02x}' for x in values)+'\n')
    bench=bench.replace('dual_fft_memory_clients #','dual_fft_s_memory #')
    bench=bench.replace("sv,sready,sw,sa,sd,sm,srv,1'b1,srd);",
                        'siv,sir,sid,sov,sor,sod,sclast,sslast,sfault,spackets,sowners);')
    bench=bench.replace('dut.memory.', 'dut.memory.memory.')
    defs=f'''localparam SINPUT={len(incoming)},SREQ={len(expected)};
reg[7:0] sinput[0:SINPUT-1],sexpected[0:SREQ-1];
integer ssent=0,sreceived=0,sproduced=0,speak=0,smisses=0,sexternal=0;
integer swrites=0,sreads=0,sended=0;
real sfinish[0:{superframes-1}];
reg siv=0;reg[7:0] sid=0;
wire sir,sov,sclast,sslast,sfault;wire[7:0] sod;wire[1:0] spackets;wire[3:0] sowners;
// A declared finite output-service contract, 1 byte every 16 memory clocks.
reg sor=0;
initial begin
 $readmemh({json.dumps(str(folder/'s_input_bytes.hex'))},sinput);
 $readmemh({json.dumps(str(folder/'s_output_bytes.hex'))},sexpected);
end
always @(negedge mclk)begin
 sor=cycle%16==0;
 if(active)while(sproduced<SINPUT && $realtime-epoch>=(sproduced+1)*4000.0/28.86)sproduced=sproduced+1;
 siv=ssent<sproduced;
 if(ssent<SINPUT)sid=sinput[ssent];
 if(spackets>speak)speak=spackets;
 if(sproduced-ssent>sexternal)sexternal=sproduced-ssent;
end
always @(posedge mclk)if(resetn)begin
 if(sfault)$fatal(1,"S DMA fault");
 if(siv&&sir)ssent=ssent+1;
 if(dut.sframe.req_valid&&dut.sframe.req_ready)begin
  if(dut.sframe.req_write)swrites=swrites+1;else sreads=sreads+1;
 end
 if(sov&&sor)begin
  if(sreceived>=SREQ||sod!==sexpected[sreceived])$fatal(1,"S byte permutation %0d",sreceived);
  if(sclast!==(sreceived%204==203)||sslast!==(sreceived%78336==78335))$fatal(1,"S output boundary");
  if(sslast)begin sfinish[sended]=$realtime-epoch;sended=sended+1;end
  sreceived=sreceived+1;
 end
end
'''
    # Historical S per-CW deadlines do not apply to an inter-superframe DMA.
    # It must drain each bank before its scheduled reuse two SFs after capture starts.
    checks=f'''smisses=sexternal>1;
 for(integer sf=0;sf<{superframes};sf=sf+1)begin
  if(sfinish[sf]>(sf+2)*77952*4000.0/28.86)smisses=smisses+1;
  $display("SFRAME sf=%0d finish_ns=%0.3f deadline_ns=%0.3f",sf,sfinish[sf],(sf+2)*77952*4000.0/28.86);
 end
 $display("SDMA writes=%0d reads=%0d input_pending=%0d packet_peak=%0d",swrites,sreads,sexternal,speak);
'''
    bench=bench.replace('deadline_misses[1]=smisses;',checks+'deadline_misses[1]=smisses;')
    return bench, defs
