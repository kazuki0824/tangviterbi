// Address-only adapter for 32-byte BL8 DMA; this is not the DMA scheduler.
// mode_log=11/12/13; second_pass selects FFT along N1 rather than N2.
// write_back selects natural-order tile output, otherwise input bit-reversal
// is performed by dual_fft_tile on load. Caller owns frame/tile lifetime.
module dual_fft_burst_map(input wire[3:0] mode_log,input wire second_pass,write_back,
 input wire[20:0] frame_base,input wire[4:0] tile,input wire[7:0] burst,
 input wire[2:0] beat,output reg valid,output reg[20:0] memory_address,
 output reg[9:0] tile_index,output reg[12:0] cross_phase,
 output reg[2:0] kernel_log,lane_bits,output reg[7:0] burst_count);
 reg[3:0] la,lb;reg[9:0] row,lane,start_col,index;
 reg[12:0] product;integer k;
 always @* begin
  la=mode_log==11?5:6;lb=mode_log==13?7:6;
  kernel_log=second_pass?la[2:0]:lb[2:0];
  lane_bits=second_pass ? (3+lb-la) : 3;
  burst_count=8'd1<<lb;
  valid=mode_log>=11 && mode_log<=13 && frame_base[2:0]==0 && burst<burst_count &&
        (second_pass ? ({5'd0,tile}<<(lane_bits))<(10'd1<<lb) : tile<(6'd1<<(la-3)));
  row=0;lane=0;start_col=0;index=0;product=0;cross_phase=0;tile_index=0;memory_address=frame_base;
  if(!second_pass)begin
   row={2'd0,burst};lane={7'd0,beat};start_col={5'd0,tile}<<3;
   memory_address=frame_base+({11'd0,row}<<la)+start_col;
   tile_index=(row<<3)|lane;
   // Explicit small shift/add avoids consuming an extra DSP for addressing.
   index=start_col+lane;
   for(k=0;k<6;k=k+1)if(index[k])product=product+({3'd0,row}<<k);
   cross_phase=product<<(13-mode_log);
  end else begin
   start_col={5'd0,tile}<<lane_bits;
   if(!write_back)begin
    lane={2'd0,burst}>>(la-3);
    row=(({2'd0,burst}&((10'd1<<(la-3))-1))<<3)|beat;
    memory_address=frame_base+({11'd0,(start_col+lane)}<<la)+(row&10'h3f8);
    tile_index=(row<<lane_bits)|lane;
   end else begin
    row={2'd0,burst}>>(lane_bits-3);
    lane=(({2'd0,burst}&((10'd1<<(lane_bits-3))-1))<<3)|beat;
    memory_address=frame_base+({11'd0,row}<<lb)+start_col+(lane&10'h3f8);
    tile_index=(row<<lane_bits)|lane;
   end
  end
 end
endmodule
