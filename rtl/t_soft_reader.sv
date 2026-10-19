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
 reg[2:0]fetch_index;
 reg[20:0]held_address;
 reg[5:0]fetch_length,beat;
 reg fetch_found,output_found,bank_empty,commit_legal;
 reg[1:0]fetch_choice,output_choice;
 integer i,j,candidate,index;
 always @* begin
  commit_legal=1;
  for(i=0;i<3;i=i+1)
   if(commit_lengths[i*16+:16]!=0 &&
    (commit_addresses[i*21+:3]!=0 ||
     ({1'b0,commit_addresses[i*21+:21]} +
      (({6'd0,commit_lengths[i*16+:16]}+22'd31)>>5)*8)>22'h200000))commit_legal=0;
  fetch_found=0;fetch_choice=0;output_found=0;output_choice=0;
  bank_empty=1;candidate=0;index=0;
  for(i=0;i<3;i=i+1)begin
   if(remaining[read_bank*3+i]!=0)bank_empty=0;
   candidate=fetch_rr+i;if(candidate>=3)candidate=candidate-3;
   index=read_bank*3+candidate;
   if(!fetch_found && live[read_bank] && remaining[index]!=0 &&
    count[candidate]+((remaining[index]<32)?remaining[index]:16'd32)<=64)begin
    fetch_found=1;fetch_choice=candidate;
   end
   candidate=output_rr+i;if(candidate>=3)candidate=candidate-3;
   if(!output_found && count[candidate]!=0)begin output_found=1;output_choice=candidate;end
  end
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
 always @(posedge clk)begin
  if(!resetn)begin
   live<=0;write_bank<=0;read_bank<=0;state<=IDLE;fault<=0;
   fetch_rr<=0;output_rr<=0;fetch_context<=0;fetch_index<=0;
   held_address<=0;fetch_length<=0;beat<=0;
   soft_valid<=0;soft_context<=0;soft_data<=0;
   for(j=0;j<6;j=j+1)begin address[j]<=0;remaining[j]<=0;end
   for(j=0;j<3;j=j+1)begin wp[j]<=0;rp[j]<=0;count[j]<=0;end
  end else begin
   if(commit_valid && !commit_legal)fault<=1;
   if(commit_valid && commit_ready)begin
    live[write_bank]<=1;write_bank<=!write_bank;
    for(j=0;j<3;j=j+1)begin
     address[write_bank*3+j]<=commit_addresses[j*21+:21];
     remaining[write_bank*3+j]<=commit_lengths[j*16+:16];
    end
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
      fetch_context<=fetch_choice;fetch_index<=read_bank*3+fetch_choice;
      held_address<=address[read_bank*3+fetch_choice];
      fetch_length<=remaining[read_bank*3+fetch_choice]<32 ? remaining[read_bank*3+fetch_choice]:16'd32;
      beat<=0;state<=REQUEST;
     end
    end
    REQUEST:if(req_valid && req_ready)state<=RESPONSE;
    RESPONSE:if(put)begin
     if(beat==fetch_length-1)begin
      remaining[fetch_index]<=remaining[fetch_index]-fetch_length;
      address[fetch_index]<=address[fetch_index]+21'd8;
      fetch_rr<=fetch_context==2?0:fetch_context+1'b1;
      beat<=0;state<=IDLE;
     end else beat<=beat+1'b1;
    end
   endcase
  end
 end
endmodule
