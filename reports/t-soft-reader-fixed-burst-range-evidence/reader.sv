// Same-clock T soft reader. Two alternating SDRAM symbol banks are committed
// only AFTER their writes complete. Three contiguous, 32-byte-aligned regions (addresses are 32-bit WORD addresses)
// per symbol contain unchanged received soft bytes (not expanded erasures).
// One read in flight; its response is held by the controller during bytewise
// unpacking. 3x64-byte distributed caches plus one output byte are retained.
// No T time-deinterleaver, write producer, rate/epoch switching or PHY here.
module t_soft_reader(
 input wire clk,resetn,
 input wire commit_valid,output wire commit_ready,
 input wire[62:0]commit_addresses,input wire[47:0]commit_lengths,
 output wire[1:0]bank_live,output wire reuse_blocked,
 output wire req_valid,input wire req_ready,output wire[20:0]req_address,
 input wire rsp_valid,output wire rsp_ready,input wire[255:0]rsp_data,
 output reg soft_valid,input wire soft_ready,output reg[1:0]soft_context,
 output reg[7:0]soft_data,output reg fault
);
 reg[1:0]live;
 reg write_bank,read_bank;
 reg[20:0]address[0:5];reg[15:0]remaining[0:5];
 (* ram_style="distributed" *) reg[7:0]cache0[0:63];
 (* ram_style="distributed" *) reg[7:0]cache1[0:63];
 (* ram_style="distributed" *) reg[7:0]cache2[0:63];
 reg[5:0]wp[0:2],rp[0:2];reg[6:0]count[0:2];
 reg[1:0]fetch_rr,output_rr;
 localparam IDLE=0,REQUEST=1,RESPONSE=2;
 reg[1:0]state;
 reg[1:0]fetch_context;
 reg[20:0]held_address;
 reg[5:0]fetch_length,beat;
 wire[20:0]active_address[0:2];
 wire[15:0]active_remaining[0:2];
 wire[5:0]chunk_length[0:2];
 wire[2:0]fetch_eligible,output_eligible,illegal_region;
 genvar context_index;
 generate for(context_index=0;context_index<3;context_index=context_index+1)begin: descriptor_view
  // Check the padded region in BL8 units. start+floor(length/32) can
  // equal the device end only when no partial final burst is required.
  wire[18:0]end_full_bursts={1'b0,commit_addresses[context_index*21+3+:18]}+
   {8'd0,commit_lengths[context_index*16+5+:11]};
  assign illegal_region[context_index]=commit_lengths[context_index*16+:16]!=0 &&
   (commit_addresses[context_index*21+:3]!=0 ||
    (end_full_bursts[18] && ((|end_full_bursts[17:0]) || (|commit_lengths[context_index*16+:5]))));
  // Constant indices keep bank muxes and descriptor write enables explicit.
  assign active_address[context_index]=read_bank ? address[context_index+3]:address[context_index];
  assign active_remaining[context_index]=read_bank ? remaining[context_index+3]:remaining[context_index];
  assign chunk_length[context_index]=active_remaining[context_index]<32 ? active_remaining[context_index][5:0]:6'd32;
  assign fetch_eligible[context_index]=live[read_bank] && active_remaining[context_index]!=0 &&
   ({1'b0,count[context_index]}+{2'b0,chunk_length[context_index]}<=8'd64);
  assign output_eligible[context_index]=count[context_index]!=0;
 end endgenerate
 wire bank_empty=!(|{active_remaining[0],active_remaining[1],active_remaining[2]});
 wire fetch_found=|fetch_eligible,output_found=|output_eligible;
 reg commit_legal;
 reg[1:0]fetch_choice,output_choice;
 reg[2:0]fetch_mask,output_mask,fetch_candidates,output_candidates;
 integer i,j;
 always @* begin
  commit_legal=!(|illegal_region);
  case(fetch_rr)
   1:fetch_mask=3'b110;2:fetch_mask=3'b100;default:fetch_mask=3'b111;
  endcase
  case(output_rr)
   1:output_mask=3'b110;2:output_mask=3'b100;default:output_mask=3'b111;
  endcase
  fetch_candidates=fetch_eligible & fetch_mask;
  if(fetch_candidates==0)fetch_candidates=fetch_eligible;
  output_candidates=output_eligible & output_mask;
  if(output_candidates==0)output_candidates=output_eligible;
  fetch_choice=fetch_candidates[0] ? 0 : fetch_candidates[1] ? 1 : 2;
  output_choice=output_candidates[0] ? 0 : output_candidates[1] ? 1 : 2;
 end
 assign bank_live=live;
 assign commit_ready=resetn && !fault && !live[write_bank] && commit_legal;
 assign reuse_blocked=resetn && commit_valid && live[write_bank];
 assign req_valid=resetn && !fault && state==REQUEST;
 assign req_address=held_address;
 assign rsp_ready=resetn && !fault && state==RESPONSE && beat==fetch_length-1;
 wire put=resetn && !fault && state==RESPONSE && rsp_valid;
 wire pop=resetn && !fault && (!soft_valid || soft_ready) && output_found;
 wire[7:0]received_byte=rsp_data[beat*8+:8];
 always @(posedge clk)begin
  if(put)case(fetch_context)
   0:cache0[wp[0]]<=received_byte;
   1:cache1[wp[1]]<=received_byte;
   2:cache2[wp[2]]<=received_byte;
  endcase
 end
 wire finish_read=put && beat==fetch_length-1;
 wire[15:0]remaining_after_read=active_remaining[fetch_context]-fetch_length;
 wire[20:0]next_address=held_address+21'd8;
 genvar descriptor_index;
 generate for(descriptor_index=0;descriptor_index<6;descriptor_index=descriptor_index+1)begin: descriptor_storage
  always @(posedge clk)begin
   if(!resetn)begin address[descriptor_index]<=0;remaining[descriptor_index]<=0;end
   else if(commit_valid && commit_ready && write_bank==(descriptor_index/3))begin
    address[descriptor_index]<={commit_addresses[(descriptor_index%3)*21+3+:18],3'b000};
    remaining[descriptor_index]<=commit_lengths[(descriptor_index%3)*16+:16];
   end else if(finish_read && read_bank==(descriptor_index/3) && fetch_context==(descriptor_index%3))begin
    address[descriptor_index]<=next_address;
    remaining[descriptor_index]<=remaining_after_read;
   end
  end
 end endgenerate
 always @(posedge clk)begin
  if(!resetn)begin
   live<=0;write_bank<=0;read_bank<=0;state<=IDLE;fault<=0;
   fetch_rr<=0;output_rr<=0;fetch_context<=0;
   held_address<=0;fetch_length<=0;beat<=0;
   soft_valid<=0;soft_context<=0;soft_data<=0;
   for(j=0;j<3;j=j+1)begin wp[j]<=0;rp[j]<=0;count[j]<=0;end
  end else begin
   if(commit_valid && !commit_legal)fault<=1;
   if(commit_valid && commit_ready)begin
    live[write_bank]<=1;write_bank<=!write_bank;
   end
   if(!soft_valid || soft_ready)begin
    soft_valid<=pop;
    if(pop)begin
     soft_context<=output_choice;
     case(output_choice)
      0:soft_data<=cache0[rp[0]];
      1:soft_data<=cache1[rp[1]];
      2:soft_data<=cache2[rp[2]];
     endcase
     output_rr<=output_choice==2?0:output_choice+1'b1;
    end
   end
   for(j=0;j<3;j=j+1)begin
    if(put && fetch_context==j)wp[j]<=wp[j]+1'b1;
    if(pop && output_choice==j)rp[j]<=rp[j]+1'b1;
    case({put && fetch_context==j,pop && output_choice==j})
     2'b10:count[j]<=count[j]+1'b1;
     2'b01:count[j]<=count[j]-1'b1;
    endcase
   end
   case(state)
    IDLE:if(live[read_bank])begin
     if(bank_empty)begin live[read_bank]<=0;read_bank<=!read_bank;end
     else if(fetch_found && !fault)begin
      fetch_context<=fetch_choice;
      held_address<=active_address[fetch_choice];
      fetch_length<=chunk_length[fetch_choice];
      beat<=0;state<=REQUEST;
     end
    end
    REQUEST:if(req_valid && req_ready)state<=RESPONSE;
    RESPONSE:if(put)begin
     if(beat==fetch_length-1)begin
      fetch_rr<=fetch_context==2?0:fetch_context+1'b1;
      beat<=0;state<=IDLE;
     end else beat<=beat+1'b1;
    end
   endcase
  end
 end
endmodule
