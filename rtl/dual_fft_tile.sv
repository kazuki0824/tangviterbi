// Two 4 KiB banks; in-place radix-2 DIT, N=32/64/128 and 1..16 lanes.
// Physical layout: point<<config_lane_bits | lane. Natural-order DMA ports.
// Two clocks per butterfly: synchronous two-port READ then multiply/add/WRITE.
// External synchronous twiddle ROM: W128[index], signed Q1.16 (18 bits).
// Per-stage /2 normalization, nearest rounding with ties away from zero,
// saturation and sticky overflow. FFT/N output; no missing bins/samples.
// config_logn must stay stable during load. start follows the final load.
module dual_fft_tile(
 input wire clk,resetn,input wire[2:0] config_logn,config_lane_bits,
 input wire dma_bank,start_bank,
 input wire load_valid,output wire load_ready,input wire[9:0] load_index,
 input wire[31:0] load_data,input wire start,output wire busy,output reg done,
 input wire read_valid,input wire[9:0] read_index,
 output reg read_out_valid,output wire[31:0] read_data,
 output wire[5:0] twiddle_index,input wire signed[17:0] twiddle_real,twiddle_imag,
 output reg overflow
);
 localparam IDLE=0,READ=1,WRITE=2;
 reg[1:0] state;reg[2:0] stage,logn,lane_bits;reg[5:0] butterfly;
 reg bank;reg[3:0] lane;reg read_bank;
 (* ram_style="block" *) reg[31:0] memory0[0:1023];
 (* ram_style="block" *) reg[31:0] memory1[0:1023];
 reg[31:0] qa0,qb0,qa1,qb1;
 wire[31:0] qa=bank?qa1:qa0,qb=bank?qb1:qb0;
 wire[6:0] mask=(7'd1<<(stage-1))-1'b1;
 wire[6:0] ia=({1'b0,butterfly}&mask)|(({1'b0,butterfly}&~mask)<<1);
 wire[6:0] ib=ia|(mask+1'b1);
 assign twiddle_index=(butterfly&mask[5:0])<<(7-stage);
 function[6:0] reverse_index;
  input[6:0] index;input[2:0] bits;
  integer k;begin reverse_index=0;for(k=0;k<7;k=k+1)
   if(k<bits)reverse_index=reverse_index|( {6'b0,index[k]} << (bits-1-k));end
 endfunction
 wire config_ok=config_logn>=5 && config_logn<=7 && config_lane_bits<=4 && ({1'b0,config_logn}+{1'b0,config_lane_bits})<=10;
 assign busy=state!=IDLE;
 wire dma_available=state==IDLE || dma_bank!=bank;
 assign load_ready=dma_available && config_ok && !start && !read_valid;
 wire loading=load_valid&&load_ready;
 wire[9:0] lane_mask=(10'd1<<config_lane_bits)-1'b1;
 wire[9:0] dma_address=loading ? ({3'b0,reverse_index(load_index>>config_lane_bits,config_logn)}<<config_lane_bits)|(load_index&lane_mask) : read_index;
 wire[9:0] aa=({3'b0,ia}<<lane_bits)|lane;
 wire[9:0] ab=({3'b0,ib}<<lane_bits)|lane;
 wire signed[15:0] ar=qa[15:0],ai=qa[31:16],br=qb[15:0],bi=qb[31:16];
 wire signed[33:0] rr=br*twiddle_real,ii=bi*twiddle_imag;
 wire signed[33:0] ri=br*twiddle_imag,ir=bi*twiddle_real;
 wire signed[34:0] tr={rr[33],rr}-{ii[33],ii},ti={ri[33],ri}+{ir[33],ir};
 wire signed[35:0] ax={{20{ar[15]}},ar},ay={{20{ai[15]}},ai};
 wire signed[35:0] rp=(ax<<<16)+{tr[34],tr},rm=(ax<<<16)-{tr[34],tr};
 wire signed[35:0] ip=(ay<<<16)+{ti[34],ti},im=(ay<<<16)-{ti[34],ti};
 function signed[35:0] rounded;
  input signed[35:0] x;
  // Arithmetic shift floors negative values. Bias one less for negative
  // inputs to preserve nearest/ties-away without abs/negate carry chains.
  begin rounded=(x+(x<0 ? 36'sd65535 : 36'sd65536))>>>17;end
 endfunction
 function[15:0] clamp;
  input signed[35:0] x;reg signed[35:0] y;
  begin y=rounded(x);clamp=y>32767 ? 16'h7fff : y < -32768 ? 16'h8000 : y[15:0];end
 endfunction
 wire clipping=rounded(rp)>32767 || rounded(rp)<-32768 || rounded(rm)>32767 || rounded(rm)<-32768 ||
               rounded(ip)>32767 || rounded(ip)<-32768 || rounded(im)>32767 || rounded(im)<-32768;
 wire[31:0] da=state==WRITE ? {clamp(ip),clamp(rp)} : load_data;
 wire[31:0] db={clamp(im),clamp(rm)};
 // Four physical RAM ports: each of two banks has two ports. Compute
 // owns both ports of its bank; DMA gets port A of the other bank.
 wire compute0=busy && !bank,compute1=busy && bank;
 wire dma_read=read_valid && dma_available && !start;
 wire[9:0] a0=compute0?aa:dma_address,a1=compute1?aa:dma_address;
 always @(posedge clk)begin
  if(compute0 && state==WRITE)memory0[a0]<=da;
  else if(!compute0 && loading && !dma_bank)memory0[a0]<=load_data;
  if((compute0 && state==READ)||(!compute0 && dma_read && !dma_bank))qa0<=memory0[a0];
 end
 always @(posedge clk)begin
  if(compute0 && state==WRITE)memory0[ab]<=db;
  if(compute0 && state==READ)qb0<=memory0[ab];
 end
 always @(posedge clk)begin
  if(compute1 && state==WRITE)memory1[a1]<=da;
  else if(!compute1 && loading && dma_bank)memory1[a1]<=load_data;
  if((compute1 && state==READ)||(!compute1 && dma_read && dma_bank))qa1<=memory1[a1];
 end
 always @(posedge clk)begin
  if(compute1 && state==WRITE)memory1[ab]<=db;
  if(compute1 && state==READ)qb1<=memory1[ab];
 end
 assign read_data=read_bank?qa1:qa0;
 always @(posedge clk)begin
  if(!resetn)begin state<=IDLE;stage<=1;logn<=5;lane_bits<=0;lane<=0;bank<=0;read_bank<=0;butterfly<=0;done<=0;read_out_valid<=0;overflow<=0;end
  else begin
   done<=0;read_out_valid<=dma_read;if(dma_read)read_bank<=dma_bank;
   case(state)
    IDLE:if(start && config_ok)begin state<=READ;stage<=1;logn<=config_logn;lane_bits<=config_lane_bits;lane<=0;bank<=start_bank;butterfly<=0;overflow<=0;end
    READ:state<=WRITE;
    WRITE:begin
     overflow<=overflow|clipping;
     if(butterfly==((7'd1<<(logn-1))-1))begin
      butterfly<=0;
      if(stage==logn)begin
       if(lane==((5'd1<<lane_bits)-1))begin state<=IDLE;done<=1;end
       else begin lane<=lane+1'b1;stage<=1;state<=READ;end
      end
      else begin stage<=stage+1'b1;state<=READ;end
     end else begin butterfly<=butterfly+1'b1;state<=READ;end
    end
   endcase
  end
 end
endmodule
