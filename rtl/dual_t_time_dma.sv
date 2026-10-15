// Time deinterleaver after frequency deinterleaving/demapping. Each carrier is
// six unchanged 8-bit LLRs, segment-major then carrier-major then bit order.
// Stream ports carry four consecutive bytes per word, earliest in bits [7:0].
// Fixed legal mode/layer parameters; runtime TMCC reconfiguration is outside.
// One finite symbol RAM holds both incoming and reordered outgoing bytes.
// A new symbol exchanges its bytes with the previous result: the old byte must
// be consumed before its location is reused. drain_only emits the final result.
// Upstream must retain a complete symbol and honor ready (not raw unstoppably
// arriving RF). No claim of a complete capture/demapper/decoder pipeline.
module dual_t_time_dma #(
 parameter integer MODE=1,S0=3,I0=4,S1=3,I1=8,S2=7,I2=16,
 parameter [22:0] BASE=0
)(input wire clk,resetn,
 input wire start_valid,output wire start_ready,input wire drain_only,
 input wire in_valid,output wire in_ready,input wire[31:0] in_data,
 output wire out_valid,input wire out_ready,output wire[31:0] out_data,
 output wire out_last,output reg out_settled,
 output reg result_ready,output reg symbol_done,output wire busy,output wire fault,
 output wire req_valid,input wire req_ready,output wire req_write,
 output wire[20:0] req_address,output wire[255:0] req_data,output wire[31:0] req_dqm,
 input wire rsp_valid,output wire rsp_ready,input wire[255:0] rsp_data);
 function integer max2(input integer a,b);max2=a>b?a:b;endfunction
 function integer minpos(input integer a,b);
  minpos=a==0?b:b==0?a:a<b?a:b;
 endfunction
 localparam R=1<<(MODE-1),N=13*96*R*6,AW=$clog2(N),DEPTH=1<<AW;
 localparam MAXI=max2(S0?I0:0,max2(S1?I1:0,S2?I2:0));
 localparam MIN_I=minpos(S0?I0:0,minpos(S1?I1:0,S2?I2:0));
 localparam STEP=MIN_I?MIN_I:1,MAXD=95*MAXI,GMAX=MAXD/STEP,GN=GMAX+1;
 localparam IDLE=0,PRIME=1,SWAP=2,PLAN=3,META=4,LAUNCH=5,ACTIVE=6,FINISH=7;
 reg[2:0] state;
 reg draining,old_sent,old_valid;reg[AW-1:0] position;
 reg[10:0] processed;reg[8:0] group_id;
 reg[9:0] feed_position,return_position;reg feed_valid;
 reg[33:0] plans[0:GN-1],meta_q;
 reg[22:0] group_base,span;
 wire[22:0] base=group_base;
 wire[22:0] aligned_span=(span+23'd31)&23'h7fffe0;
 reg[22:0] cursors[0:GN-1],cursor_q;
 wire[31:0] ram_q;reg[1:0] read_lane;
 wire[9:0] length=meta_q[9:0];
 wire[22:0] offset=processed==0?23'd0:cursor_q;
 wire[10:0] delay_symbols=group_id*STEP;
 function integer legal_i(input integer v);
  legal_i=v==0||v==4/R||v==8/R||v==16/R;
 endfunction
 function integer ring_bytes(input integer unused);
  integer j,t,count,total;
  begin
   total=0;
   for(j=1;j<GN;j=j+1)begin
    t=j*STEP;count=0;
    if(S0 && I0 && t%I0==0 && t/I0<=95)count=count+S0*R*6;
    if(S1 && I1 && t%I1==0 && t/I1<=95)count=count+S1*R*6;
    if(S2 && I2 && t%I2==0 && t/I2<=95)count=count+S2*R*6;
    total=total+((t*count+31)/32)*32;
   end
   ring_bytes=total;
  end
 endfunction
 localparam RING_BYTES=ring_bytes(0);
 integer g,d,sz,a,c0,c1,c2;
 initial begin
  if(MODE<1||MODE>3||S0<0||S1<0||S2<0||S0+S1+S2!=13||
     !legal_i(I0)||!legal_i(I1)||!legal_i(I2)||BASE[4:0]!=0)
   $fatal(1,"invalid fixed T configuration");
  plans[0]=0;
  for(g=1;g<GN;g=g+1)begin
   d=g*STEP;a=0;sz=0;c0=0;c1=0;c2=0;
   if(S0 && I0 && d%I0==0 && d/I0<=95)begin a=a|1;sz=sz+S0*R*6;c0=(77*(95-d/I0))%96;end
   if(S1 && I1 && d%I1==0 && d/I1<=95)begin a=a|2;sz=sz+S1*R*6;c1=(77*(95-d/I1))%96;end
   if(S2 && I2 && d%I2==0 && d/I2<=95)begin a=a|4;sz=sz+S2*R*6;c2=(77*(95-d/I2))%96;end
   plans[g]={7'(c2),7'(c1),7'(c0),3'(a),10'(sz)};
  end
  if({1'b0,BASE}+RING_BYTES>5690880)$fatal(1,"T rings overlap S reservation");
 end
 // Position within a merged delay group -> original segment/carrier/bit slot.
 // 77 is the inverse of 5 modulo 96; repeated carrier blocks share a delay.
 function [AW-1:0] natural_address(input [9:0] index,input[33:0] plan);
  reg[9:0] p;reg[14:0] segment_base;reg[6:0] carrier;
  begin
   p=index;segment_base=0;carrier=plan[19:13];
   if(!(plan[10+0] && p<S0*R*6))begin
    if(plan[10+0])p=p-S0*R*6;
    segment_base=S0;carrier=plan[26:20];
    if(!(plan[10+1] && p<S1*R*6))begin
     if(plan[10+1])p=p-S1*R*6;
     segment_base=S0+S1;carrier=plan[33:27];
    end
   end
   natural_address=segment_base*(96*R*6)+(p/6)*576+carrier*6+p%6;
  end
 endfunction
 wire vi_ready,vo_valid,vo_ready,vdone,vfault,vector_ready;
 wire[15:0] vo_data;wire[20:0] logical_word;
 assign start_ready=state==IDLE;
 assign busy=state!=IDLE;assign fault=vfault;
 assign out_valid=state==SWAP && result_ready && old_valid && !old_sent;
 assign out_data=ram_q;assign out_last=out_valid && position==N-4;
 wire old_taken=out_valid&&out_ready;
 assign in_ready=state==SWAP && !draining && (!result_ready||old_sent||old_taken);
 wire new_taken=in_valid&&in_ready;
 wire advance=state==SWAP && (draining?old_taken:new_taken);
 wire feed_fetch=state==ACTIVE && feed_position<length && (!feed_valid||vi_ready);
 wire swap_fetch=state==PRIME || (advance && result_ready && position!=N-4);
 wire[AW-1:0] read_address=feed_fetch?natural_address(feed_position,meta_q):
  state==PRIME?{AW{1'b0}}:position+3'd4;
 wire[AW-1:0] write_address=new_taken?position:natural_address(return_position,meta_q);
 wire[15:0] write_pair=processed<delay_symbols?16'd0:vo_data;
 assign vo_ready=state==ACTIVE && return_position<feed_position;
 always @(posedge clk)begin
  if(state==PLAN)begin meta_q<=plans[group_id];cursor_q<=cursors[group_id];end
  if(feed_fetch)read_lane<=read_address[1:0];
  if(state==ACTIVE && vdone)cursors[group_id]<=offset+length>=span?23'd0:offset+length;
 end
 // Four byte banks retain the same total capacity and allow full-word capture.
 // Each bank has one synchronous read and one write port.
 genvar lane,block_id;
 generate if(MODE!=3)begin:regular_symbol_ram
 for(lane=0;lane<4;lane=lane+1)begin:bytes
  reg[7:0] ram[0:DEPTH/4-1];reg[7:0] q;
  assign ram_q[lane*8+:8]=q;
  always @(posedge clk)begin
   if(feed_fetch||swap_fetch)q<=ram[read_address[AW-1:2]];
   if(new_taken || (vo_valid&&vo_ready&&write_address[1]==lane/2))
    ram[write_address[AW-1:2]]<=new_taken?in_data[lane*8+:8]:write_pair[(lane%2)*8+:8];
  end
 end
 end else begin:compact_symbol_ram
 // 7488 words: seven full blocks and a 320-word tail per 16-bit pair.
 localparam FULL=(N/4)/1024,TAIL=(N/4)%1024;
 reg[2:0] read_region;
 always @(posedge clk)if(feed_fetch||swap_fetch)read_region<=read_address[14:12];
 for(lane=0;lane<2;lane=lane+1)begin:pairs
  wire[15:0] q[0:FULL];
  wire we=new_taken||(vo_valid&&vo_ready&&write_address[1]==lane);
  wire[15:0] wd=new_taken?in_data[lane*16+:16]:write_pair;
  assign ram_q[lane*16+:16]=q[read_region];
  for(block_id=0;block_id<FULL;block_id=block_id+1)begin:blocks
   (* ram_style="block" *) reg[15:0] ram[0:1023];reg[15:0] value;
   assign q[block_id]=value;
   always @(posedge clk)begin
    if((feed_fetch||swap_fetch)&&read_address[14:12]==block_id)value<=ram[read_address[11:2]];
    if(we&&write_address[14:12]==block_id)ram[write_address[11:2]]<=wd;
   end
  end
  if(TAIL>0)begin:tail
   (* ram_style="distributed" *) reg[15:0] ram[0:TAIL-1];reg[15:0] value;
   assign q[FULL]=value;
   always @(posedge clk)begin
    if((feed_fetch||swap_fetch)&&read_address[14:12]==FULL)value<=ram[read_address[10:2]];
    if(we&&write_address[14:12]==FULL)ram[write_address[10:2]]<=wd;
   end
  end
 end
 end endgenerate
 dual_vector_exchange_pipelined #(.WIDTH(16)) exchange(clk,resetn,state==LAUNCH,vector_ready,base+offset,{6'd0,length},
  feed_valid,vi_ready,ram_q[read_lane*8+:16],vo_valid,vo_ready,vo_data,vdone,vfault,
  req_valid,req_ready,req_write,logical_word,req_data,req_dqm,rsp_valid,rsp_ready,rsp_data);
 // The exchange operates in compact logical byte space, including BL8 cuts at
 // vector/page boundaries. Map each burst separately into banks 1..3.
 wire[12:0] page=logical_word[20:8];
 wire[10:0] row=page/3;wire[1:0] bank=page%3+1;
 assign req_address={row,bank,logical_word[7:0]};
 always @(posedge clk)begin
  if(!resetn)begin
   state<=IDLE;draining<=0;old_sent<=0;old_valid<=0;position<=0;
   processed<=0;group_id<=0;group_base<=BASE;span<=0;feed_position<=0;return_position<=0;feed_valid<=0;
   result_ready<=0;symbol_done<=0;out_settled<=0;
  end else begin
   symbol_done<=0;
   case(state)
    IDLE:if(start_valid)begin
     position<=0;old_sent<=0;old_valid<=0;draining<=drain_only;group_base<=BASE;
     if(drain_only&&!result_ready)symbol_done<=1;
     else state<=result_ready?PRIME:SWAP;
    end
    PRIME:begin old_valid<=1;state<=SWAP;end
    SWAP:begin
     if(old_taken)old_sent<=1;
     if(advance)begin
      old_sent<=0;
      if(position==N-4)begin
       result_ready<=0;old_valid<=0;
       if(draining)begin state<=IDLE;symbol_done<=1;end
       else if(GMAX==0)state<=FINISH;
       else begin group_id<=1;state<=PLAN;end
      end else position<=position+3'd4;
     end
    end
    PLAN:state<=META;
    META:begin
     span<=delay_symbols*length;
     feed_position<=0;return_position<=0;feed_valid<=0;
     if(length!=0)state<=LAUNCH;
     else if(group_id==GMAX)state<=FINISH;
     else begin group_id<=group_id+1'b1;state<=PLAN;end
    end
    LAUNCH:if(vector_ready)state<=ACTIVE;
    ACTIVE:begin
     if(feed_valid&&vi_ready)feed_valid<=0;
     if(feed_fetch)begin feed_valid<=1;feed_position<=feed_position+2'd2;end
     if(vo_valid&&vo_ready)return_position<=return_position+2'd2;
     if(vdone)begin
      group_base<=group_base+aligned_span;
      feed_valid<=0;
      if(group_id==GMAX)state<=FINISH;
      else begin group_id<=group_id+1'b1;state<=PLAN;end
     end
    end
    FINISH:begin
     result_ready<=1;out_settled<=processed>=MAXD;symbol_done<=1;
     if(processed<MAXD)processed<=processed+1'b1;
     state<=IDLE;
    end
   endcase
  end
 end
endmodule
