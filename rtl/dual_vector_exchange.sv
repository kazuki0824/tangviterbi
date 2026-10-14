// Byte-exact compact-ring exchange. One vector descriptor, not one descriptor
// per burst. The producer supplies all bytes with valid/ready; old bytes leave
// with valid/ready before their storage is overwritten. No speculative writes.
// Addresses are physical SDRAM byte addresses; caller owns the region and must
// serialize overlapping vectors. The response source must hold rsp_data stable
// until rsp_ready; this retains the old burst without a duplicate data buffer. Clock domain is the SDRAM request domain.
module dual_vector_exchange(
 input wire clk,resetn,
 input wire vector_valid,output wire vector_ready,
 input wire [22:0] vector_address,input wire [15:0] vector_length,
 input wire in_valid,output wire in_ready,input wire [7:0] in_data,
 output wire out_valid,input wire out_ready,output wire [7:0] out_data,
 output reg done,output reg fault,
 output wire req_valid,input wire req_ready,output wire req_write,
 output wire [20:0] req_address,output wire [255:0] req_data,
 output wire [31:0] req_dqm,
 input wire rsp_valid,output wire rsp_ready,input wire [255:0] rsp_data
);
 localparam IDLE=0,FILL=1,READ=2,READ_WAIT=3,WRITE=5,WRITE_WAIT=6;
 reg [2:0] state;
 reg [22:0] address;
 reg [15:0] remaining;
 reg [5:0] first,last,cursor;
 reg [255:0] incoming;
 reg [31:0] mask;
 wire [5:0] room=6'd32-{1'b0,vector_address[4:0]};
 assign vector_ready=state==IDLE;
 assign in_ready=state==FILL;
 assign out_valid=state==READ_WAIT && rsp_valid;
 assign out_data=rsp_data[cursor*8+:8];
 assign req_valid=state==READ||state==WRITE;
 assign req_write=state==WRITE;
 assign req_address={address[22:5],3'b000};
 assign req_data=incoming;
 assign req_dqm=mask;
 assign rsp_ready=(state==READ_WAIT && out_ready && cursor+1==last)||state==WRITE_WAIT;
 always @(posedge clk)begin
  if(!resetn)begin
   state<=IDLE;done<=0;fault<=0;address<=0;remaining<=0;
   first<=0;last<=0;cursor<=0;incoming<=0;mask<=32'hffffffff;
  end else begin
   done<=0;
   case(state)
    IDLE:if(vector_valid)begin
     if(vector_length==0||({1'b0,vector_address}+{8'b0,vector_length})>24'h800000)
      fault<=1;
     else begin
      address<=vector_address;remaining<=vector_length;
      first<={1'b0,vector_address[4:0]};cursor<={1'b0,vector_address[4:0]};
      last<=vector_length<room?{1'b0,vector_address[4:0]}+vector_length[5:0]:6'd32;
      mask<=32'hffffffff;incoming<=0;state<=FILL;
     end
    end
    FILL:if(in_valid)begin
     incoming[cursor*8+:8]<=in_data;mask[cursor]<=0;
     if(cursor+1==last)begin cursor<=first;state<=READ;end
     else cursor<=cursor+1;
    end
    READ:if(req_ready)state<=READ_WAIT;
    READ_WAIT:if(rsp_valid&&out_ready)begin
     if(cursor+1==last)state<=WRITE;
     else cursor<=cursor+1;
    end
    WRITE:if(req_ready)state<=WRITE_WAIT;
    WRITE_WAIT:if(rsp_valid)begin
     if(remaining==last-first)begin state<=IDLE;done<=1;end
     else begin
      remaining<=remaining-(last-first);address<={address[22:5],5'b0}+23'd32;
      first<=0;cursor<=0;mask<=32'hffffffff;incoming<=0;
      last<=remaining-(last-first)<32?remaining-(last-first):6'd32;
      state<=FILL;
     end
    end
    default:begin state<=IDLE;fault<=1;end
   endcase
  end
 end
endmodule
