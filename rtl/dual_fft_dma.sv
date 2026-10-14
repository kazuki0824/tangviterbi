// Complete two-pass frame DMA. Two tile banks: FREE -> LOAD -> READY ->
// COMPUTE -> STORE -> FREE. A bank is not released until SDRAM write ACK.
// Input, intermediate and output frames must be disjoint, aligned and in RAM.
// One burst outstanding. This deliberately exposes all transfer/CDC overhead
// to the cycle test; no assumed MB/s service is substituted for RTL handshakes.
module dual_fft_dma(
 input wire clk,resetn,start,input wire[3:0] mode_log,
 input wire[20:0] input_base,middle_base,output_base,
 output reg busy,done,fault,overflow,
 output wire req_valid,input wire req_ready,output wire req_write,
 output wire[20:0] req_address,output wire[255:0] req_data,
 input wire rsp_valid,output wire rsp_ready,input wire[255:0] rsp_data);
 localparam FREE=0,LOADING=1,READY=2,COMPUTE=3,STORING=4;
 localparam IDLE=0,RREQ=1,RWAIT=2,LOAD=3,FETCH=4,SAMPLE=5,
            CROSS=6,WREQ=7,WWAIT=8;
 reg[2:0] owner[0:1];reg[4:0] tile_id[0:1];
 reg[3:0] mode;reg pass;reg[20:0] ib,mb,ob;
 reg[4:0] next_tile,stored;wire[4:0] tile_count=mode==11?5'd4:5'd8;
 reg[3:0] state;reg dma_bank,compute_bank;reg[7:0] burst;
 reg[2:0] beat,saved_beat;reg prefetched,write_pending;reg[255:0] buffer;
 wire writing=state>=FETCH;
 wire map_valid;wire[20:0] address;wire[9:0] index;
 wire[12:0] cross_phase;wire[2:0] kernel_log,lane_bits;wire[7:0] burst_count;
 dual_fft_burst_map mapper(mode,pass,writing,writing?(pass?ob:mb):(pass?mb:ib),
     tile_id[dma_bank],burst,beat,map_valid,address,index,cross_phase,kernel_log,lane_bits,burst_count);
 wire tile_busy,tile_done,load_ready,read_valid,tile_overflow;wire[31:0] read_data;
 wire[5:0] tw_index;wire signed[17:0] tr,ti,cr,ci;
 // Separate coefficient read ports are required while the other bank computes.
 // Each ROM is 2 BSRAM: two tile banks + both ROMs total 8 BSRAM.
 dual_fft_twiddle fft_rom(clk,{1'b0,tw_index,6'd0},tr,ti);
 dual_fft_twiddle cross_rom(clk,cross_phase,cr,ci);
 wire launch=busy&&!tile_busy&&!tile_done&&(owner[0]==READY||owner[1]==READY);
 wire launch_bank=owner[0]==READY?1'b0:1'b1;
 dual_fft_tile kernel(clk,resetn,kernel_log,lane_bits,dma_bank,launch_bank,
     state==LOAD,load_ready,index,buffer[beat*32+:32],launch,tile_busy,tile_done,
     (state==FETCH)||(state==SAMPLE&&pass&&saved_beat!=7)||(state==CROSS&&cross_valid&&saved_beat!=7),index,read_valid,read_data,tw_index,tr,ti,tile_overflow);
 wire cross_ready,cross_valid,cross_overflow;wire[31:0] cross_data;
 dual_fft_cross multiply(clk,resetn,state==SAMPLE&&read_valid&&!pass,cross_ready,
     read_data[15:0],read_data[31:16],cr,ci,cross_valid,1'b1,cross_data,cross_overflow);
 // Launch the next read while the current burst is loaded into tile RAM.
 // The CDC mailbox retains write payload while the next burst is gathered.
 wire prefetch=state==LOAD&&!prefetched&&burst!=burst_count-1;
 assign req_valid=state==RREQ||state==WREQ||prefetch;
 assign req_write=state==WREQ;assign req_address=prefetch ? address+(pass?21'd8:(mode==11?21'd32:21'd64)) : address;assign req_data=buffer;
 assign rsp_ready=state==RWAIT||write_pending;
 wire[21:0] size=22'd1<<mode_log;
 wire valid_config=mode_log>=11&&mode_log<=13&&
     input_base[2:0]==0&&middle_base[2:0]==0&&output_base[2:0]==0&&
     {1'b0,input_base}+size<=22'd2097152&&{1'b0,middle_base}+size<=22'd2097152&&{1'b0,output_base}+size<=22'd2097152&&
     ({1'b0,input_base}+size<=middle_base||{1'b0,middle_base}+size<=input_base)&&
     ({1'b0,input_base}+size<=output_base||{1'b0,output_base}+size<=input_base)&&
     ({1'b0,middle_base}+size<=output_base||{1'b0,output_base}+size<=middle_base);
 always @(posedge clk)begin
  if(!resetn)begin
   busy<=0;done<=0;fault<=0;overflow<=0;owner[0]<=FREE;owner[1]<=FREE;
   tile_id[0]<=0;tile_id[1]<=0;mode<=11;pass<=0;ib<=0;mb<=0;ob<=0;
   next_tile<=0;stored<=0;state<=IDLE;dma_bank<=0;compute_bank<=0;burst<=0;beat<=0;saved_beat<=0;buffer<=0;prefetched<=0;write_pending<=0;
  end else begin
   done<=0;
   if(prefetch&&req_ready)prefetched<=1;
   if(write_pending&&rsp_valid)write_pending<=0;
   if(start&&!busy)begin
    if(!valid_config)fault<=1;
    else begin
     busy<=1;fault<=0;overflow<=0;mode<=mode_log;ib<=input_base;mb<=middle_base;ob<=output_base;
     pass<=0;next_tile<=0;stored<=0;owner[0]<=FREE;owner[1]<=FREE;state<=IDLE;
    end
   end
   if(launch)begin compute_bank<=launch_bank;owner[launch_bank]<=COMPUTE;end
   if(tile_done)begin owner[compute_bank]<=STORING;overflow<=overflow|tile_overflow;end
   if(cross_valid)overflow<=overflow|cross_overflow|(tile_done&&tile_overflow);
   if(busy)case(state)
    IDLE:begin
     burst<=0;beat<=0;
     if(stored==tile_count)begin
      if(pass)begin busy<=0;done<=1;end
      else begin pass<=1;next_tile<=0;stored<=0;end
     end else if(owner[0]==STORING||owner[1]==STORING)begin
      dma_bank<=owner[0]==STORING?0:1;state<=FETCH;
     end else if(next_tile<tile_count&&(owner[0]==FREE||owner[1]==FREE))begin
      dma_bank<=owner[0]==FREE?0:1;
      tile_id[owner[0]==FREE?0:1]<=next_tile;owner[owner[0]==FREE?0:1]<=LOADING;
      next_tile<=next_tile+1'b1;state<=RREQ;
     end
    end
    RREQ:if(req_ready)state<=RWAIT;
    RWAIT:if(rsp_valid)begin buffer<=rsp_data;beat<=0;prefetched<=0;state<=LOAD;end
    LOAD:if(load_ready)begin
     if(beat==7)begin
      beat<=0;
      if(burst==burst_count-1)begin owner[dma_bank]<=READY;state<=IDLE;end
      else begin burst<=burst+1'b1;state<=(prefetched||(prefetch&&req_ready))?RWAIT:RREQ;end
     end else beat<=beat+1'b1;
    end
    FETCH:begin state<=SAMPLE;saved_beat<=0;if(pass)beat<=1;end
    SAMPLE:if(read_valid)begin
     if(pass)begin
      buffer[saved_beat*32+:32]<=read_data;
      if(saved_beat==7)begin beat<=0;state<=WREQ;end
      else begin saved_beat<=saved_beat+1'b1;beat<=beat+1'b1;end
     end else if(cross_ready)begin saved_beat<=beat;beat<=beat+1'b1;state<=CROSS;end
    end
    CROSS:if(cross_valid)begin
     buffer[saved_beat*32+:32]<=cross_data;
     if(saved_beat==7)begin beat<=0;state<=WREQ;end
     else state<=SAMPLE;
    end
    WREQ:if(req_ready)begin
     write_pending<=1;
     if(burst==burst_count-1)state<=WWAIT;
     else begin burst<=burst+1'b1;state<=FETCH;end
    end
    WWAIT:if(rsp_valid)begin
     owner[dma_bank]<=FREE;stored<=stored+1'b1;state<=IDLE;
    end
   endcase
  end
 end
endmodule
