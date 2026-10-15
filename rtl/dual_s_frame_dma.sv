// Conventional ISDB-S, ITU-R BO.1408-1 Annex 1 section 5 / Figure 6.
// Input: decoded main-signal bytes ONLY, transmission frame/slot/byte order;
// TMCC, bursts, sync symbols and dummy slots are handled upstream. This profile
// has 48 active TC8PSK slots, 8 frames, 203 transmitted bytes per slot.
// Output: restored 204-byte codewords in original frame/slot/byte order.
// Energy dispersal is NOT removed here: output feeds a descrambler before RS.
// Reset establishes the super-frame boundary; do not reset mid-stream without
// reacquiring that boundary. All interfaces are in mem_clk domain.
// Two 203-byte packet slots decouple ingress from masked scatter writes.
// Two SDRAM super-frame regions are FREE/FILLING/FULL/READING, not overwritten
// until the last output byte is accepted. Input backpressure is explicit.
module dual_s_frame_dma #(parameter [22:0] BASE=23'd5690880, parameter LINEAR_BANKS=0, parameter SLOT_MAJOR=1)(
 input wire clk,resetn,
 input wire in_valid,output wire in_ready,input wire[7:0] in_data,
 output wire out_valid,input wire out_ready,output wire[7:0] out_data,
 output wire out_cw_last,output wire out_super_last,
 output wire req_valid,input wire req_ready,output wire req_write,
 output wire[20:0] req_address,output wire[255:0] req_data,output wire[31:0] req_dqm,
 input wire rsp_valid,output wire rsp_ready,input wire[255:0] rsp_data,
 output wire[1:0] pending_packets,output wire[3:0] ownership,
 output reg fault
);
 localparam FREE=0,FILLING=1,FULL=2,READING=3;
 localparam IDLE=0,PREP=1,BUILD=2,FLUSH=3,WREQ=5,WACK=6,RREQ=7,RACK=8,STORE=9;
 reg[3:0] state;
 reg[1:0] owner[0:1];
 reg[7:0] packets[0:511];
 reg[1:0] packet_full;
 reg packet_bank[0:1];reg[2:0] packet_frame[0:1];reg[5:0] packet_slot[0:1];
 reg fill_packet,write_packet,fill_bank;
 reg[7:0] fill_byte;reg[2:0] fill_frame;reg[5:0] fill_slot;
 reg[2:0] target_frame;reg[7:0] block_byte;
 reg[5:0] build_byte;reg[255:0] write_data;reg[31:0] write_mask;
 wire[8:0] ram_address={write_packet,source_byte[7:0]};reg[7:0] ram_data;
 reg pipe_valid,pipe_sync;reg[4:0] pipe_byte;
 reg read_active,read_bank;reg[8:0] read_cw;reg[2:0] read_burst;
 reg[2:0] store_word;reg[255:0] read_data;
 reg[34:0] output_fifo[0:511];reg[8:0] fifo_write,fifo_read;
 reg[9:0] fifo_count;reg refill;
 reg[34:0] fifo_ram_data,output_word;reg word_valid,word_pending;reg[1:0] output_byte;
 wire enqueue=state==STORE;
 wire dequeue=!word_valid&&!word_pending&&fifo_count!=0;
 wire last_store=store_word==(read_burst==6?2:7);
 wire store_cw_last=last_store&&read_burst==6;
 wire store_super_last=store_cw_last&&read_cw==383;
 wire can_read=refill&&fifo_count<=504;
 always @(posedge clk)begin
  if(enqueue)output_fifo[fifo_write]<={read_bank,store_super_last,store_cw_last,read_data[store_word*32+:32]};
  if(dequeue)fifo_ram_data<=output_fifo[fifo_read];
 end

 wire[10:0] transmitted_start=packet_frame[write_packet]*11'd203;
 wire[8:0] first_byte=packet_frame[write_packet]==0?9'd0:
                      9'd1+((transmitted_start+11'd7-{8'd0,target_frame})>>3);
 wire[8:0] end_byte=9'd1+((transmitted_start+11'd210-{8'd0,target_frame})>>3);
 wire[8:0] position={1'b0,block_byte}+{3'd0,build_byte};
 wire[10:0] source_byte=((position-9'd1)<<3)+target_frame-transmitted_start;
 wire[8:0] write_index=SLOT_MAJOR ? {packet_slot[write_packet],target_frame} : target_frame*9'd48+packet_slot[write_packet];
 wire[8:0] read_index=SLOT_MAJOR ? (read_cw%48)*8+read_cw/48 : read_cw;
 wire[22:0] write_logical=BASE+(packet_bank[write_packet]?23'd86016:23'd0)
       +write_index*23'd224+block_byte;
 wire[22:0] read_logical=BASE+(read_bank?23'd86016:23'd0)+read_index*23'd224+read_burst*23'd32;
 wire[22:0] logical_address=req_write?write_logical:read_logical;
 // Dense logical background space -> physical SDRAM banks 1..3 (bank 0 FFT).
 wire[12:0] page=logical_address[22:10];
 wire[10:0] row=LINEAR_BANKS ? page[10:0] : page/3;
 wire[1:0] bank=LINEAR_BANKS ? page[12:11]+2'd1 : page%3+1;
 assign req_address={row,bank,logical_address[9:2]};
 assign req_valid=state==WREQ||state==RREQ;
 assign req_write=state==WREQ;
 assign req_data=write_data;assign req_dqm=write_mask;
 assign rsp_ready=state==WACK||state==RACK;
 assign in_ready=!packet_full[fill_packet]&&(owner[fill_bank]==FREE||owner[fill_bank]==FILLING)&&!fault;
 assign out_valid=word_valid;
 assign out_data=output_word[output_byte*8+:8];
 assign out_cw_last=out_valid&&output_word[32]&&output_byte==3;
 assign out_super_last=out_cw_last&&output_word[33];
 assign pending_packets={1'b0,packet_full[0]}+{1'b0,packet_full[1]};
 assign ownership={owner[1],owner[0]};
 always @(posedge clk)begin
  ram_data<=packets[ram_address];
  if(in_valid&&in_ready)packets[{fill_packet,fill_byte}]<=in_data;
 end
 always @(posedge clk)begin
  if(!resetn)begin
   state<=IDLE;owner[0]<=FREE;owner[1]<=FREE;packet_full<=0;
   fill_packet<=0;write_packet<=0;fill_bank<=0;fill_byte<=0;fill_frame<=0;fill_slot<=0;
   target_frame<=0;block_byte<=0;build_byte<=0;write_data<=0;write_mask<=32'hffffffff;
   pipe_valid<=0;pipe_sync<=0;pipe_byte<=0;read_active<=0;read_bank<=0;read_cw<=0;read_burst<=0;store_word<=0;read_data<=0;
   fifo_write<=0;fifo_read<=0;fifo_count<=0;refill<=1;
   word_valid<=0;word_pending<=0;output_byte<=0;output_word<=0;
   packet_bank[0]<=0;packet_bank[1]<=0;packet_frame[0]<=0;packet_frame[1]<=0;packet_slot[0]<=0;packet_slot[1]<=0;
   fault<={1'b0,BASE}+24'd172032>24'd6291456 || BASE[4:0]!=0;
  end else begin
   // The BRAM read and burst assembly pipeline accepts one byte each cycle.
   // FLUSH retires the last byte before asserting the memory request.
   pipe_valid<=state==BUILD && position>=first_byte && position<end_byte;
   pipe_sync<=position==0;pipe_byte<=build_byte[4:0];
   if(pipe_valid)begin
    write_data[pipe_byte*8+:8]<=pipe_sync ? 8'h47 : ram_data;
    write_mask[pipe_byte]<=0;
   end
   if(in_valid&&in_ready)begin
    if(owner[fill_bank]==FREE)owner[fill_bank]<=FILLING;
    if(fill_byte==202)begin
     packet_full[fill_packet]<=1;packet_bank[fill_packet]<=fill_bank;
     packet_frame[fill_packet]<=fill_frame;packet_slot[fill_packet]<=fill_slot;
     fill_packet<=!fill_packet;fill_byte<=0;
     if(fill_slot==47)begin
      fill_slot<=0;
      if(fill_frame==7)begin fill_frame<=0;fill_bank<=!fill_bank;end
      else fill_frame<=fill_frame+1;
     end else fill_slot<=fill_slot+1;
    end else fill_byte<=fill_byte+1;
   end
   case({enqueue,dequeue})
    2'b10:fifo_count<=fifo_count+1;
    2'b01:fifo_count<=fifo_count-1;
   endcase
   if(enqueue)fifo_write<=fifo_write+1;
   if(dequeue)begin fifo_read<=fifo_read+1;word_pending<=1;end
   if(word_pending)begin output_word<=fifo_ram_data;word_valid<=1;word_pending<=0;output_byte<=0;end
   if(word_valid&&out_ready)begin
    if(output_byte==3)begin
     word_valid<=0;
     if(output_word[33])owner[output_word[34]]<=FREE;
    end else output_byte<=output_byte+1;
   end
   if(fifo_count<=256)refill<=1;
   else if(fifo_count>504)refill<=0;
   case(state)
    IDLE:begin
     if(packet_full[write_packet])begin target_frame<=0;state<=PREP;end
     else if(read_active&&can_read)state<=RREQ;
     else if(!read_active&&can_read&&(owner[0]==FULL||owner[1]==FULL))begin
      read_bank<=owner[0]==FULL?0:1;owner[owner[0]==FULL?0:1]<=READING;
      read_active<=1;read_cw<=0;read_burst<=0;state<=RREQ;
     end
    end
    PREP:begin block_byte<={first_byte[7:5],5'b0};build_byte<=0;write_data<=0;write_mask<=32'hffffffff;state<=BUILD;end
    BUILD:begin
     if(build_byte==31)state<=FLUSH;
     else build_byte<=build_byte+1;
    end
    FLUSH:state<=WREQ;
    WREQ:if(req_ready)state<=WACK;
    WACK:if(rsp_valid)begin
     if({1'b0,block_byte}+9'd32<end_byte)begin
      block_byte<=block_byte+32;build_byte<=0;write_data<=0;write_mask<=32'hffffffff;state<=BUILD;
     end else if(target_frame!=7)begin target_frame<=target_frame+1;state<=PREP;end
     else begin
      packet_full[write_packet]<=0;write_packet<=!write_packet;state<=IDLE;
      if(packet_frame[write_packet]==7&&packet_slot[write_packet]==47)owner[packet_bank[write_packet]]<=FULL;
     end
    end
    RREQ:if(req_ready)state<=RACK;
    RACK:if(rsp_valid)begin read_data<=rsp_data;store_word<=0;state<=STORE;end
    STORE:begin
     if(last_store)begin
      if(read_burst==6)begin
       read_burst<=0;
       if(read_cw==383)read_active<=0;else read_cw<=read_cw+1;
      end else read_burst<=read_burst+1;
      state<=IDLE;
     end else store_word<=store_word+1;
    end
    default:begin fault<=1;state<=IDLE;end
   endcase
  end
 end
endmodule
