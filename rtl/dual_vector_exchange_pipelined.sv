// Compact masked-ring exchange with one incoming and one old-data BL8 buffer.
// The old read response is retained before the write can issue. Its byte stream
// drains concurrently with the write and the next block's input capture.
// A following read response waits until the old buffer has drained. Completion waits
// for both the final write acknowledgement and final old-byte consumption.
module dual_vector_exchange_pipelined #(parameter WIDTH=8)(
 input wire clk,resetn,
 input wire vector_valid,output wire vector_ready,
 input wire[22:0] vector_address,input wire[15:0] vector_length,
 input wire in_valid,output wire in_ready,input wire[WIDTH-1:0] in_data,
 output wire out_valid,input wire out_ready,output wire[WIDTH-1:0] out_data,
 output reg done,output reg fault,
 output wire req_valid,input wire req_ready,output wire req_write,
 output wire[20:0] req_address,output wire[255:0] req_data,output wire[31:0] req_dqm,
 input wire rsp_valid,output wire rsp_ready,input wire[255:0] rsp_data);
 localparam STEP=WIDTH/8;
 initial if(WIDTH!=8&&WIDTH!=16)$fatal(1,"unsupported exchange width");
 localparam IDLE=0,SELECT=1,READ=2,RACK=3,WRITE=4,WACK=5,DRAIN=6,WAIT_FILL=7;
 reg[2:0] state;reg[22:0] address;reg[15:0] remaining;
 reg[5:0] first,last,input_cursor,output_cursor,output_end;
 reg[255:0] incoming,old_data;reg[31:0] mask;
 reg filling,filled,final_block,output_valid;
 wire[5:0] room=32-{1'b0,vector_address[4:0]};
 assign vector_ready=state==IDLE;
 assign in_ready=filling;
 assign out_valid=output_valid;assign out_data=old_data[output_cursor*8+:WIDTH];
 wire chain_write=state==RACK&&rsp_valid&&rsp_ready&&filled;
 wire chain_read=state==WACK&&rsp_valid&&!final_block;
 assign req_valid=state==READ||state==WRITE||chain_write||chain_read;
 assign req_write=state==WRITE||chain_write;
 assign req_address={address[22:5],3'b000};assign req_data=req_write?incoming:256'd0;assign req_dqm=req_write?mask:32'hffffffff;
 assign rsp_ready=(state==RACK&&!output_valid)||state==WACK;
 always @(posedge clk)begin
  if(!resetn)begin
   state<=IDLE;address<=0;remaining<=0;first<=0;last<=0;input_cursor<=0;
   output_cursor<=0;output_end<=0;incoming<=0;old_data<=0;mask<=32'hffffffff;
   filling<=0;filled<=0;final_block<=0;output_valid<=0;done<=0;fault<=0;
  end else begin
   done<=0;
   if(output_valid&&out_ready)begin
    if(output_cursor+STEP==output_end)output_valid<=0;
    else output_cursor<=output_cursor+STEP;
   end
   if(in_valid&&in_ready)begin
    incoming[input_cursor*8+:WIDTH]<=in_data;
    for(integer lane=0;lane<STEP;lane=lane+1)mask[input_cursor+lane]<=0;
    if(input_cursor+STEP==last)begin filling<=0;filled<=1;end
    else input_cursor<=input_cursor+STEP;
   end
   case(state)
    IDLE:if(vector_valid)begin
     if(vector_length==0 || (WIDTH==16 && (vector_address[0]||vector_length[0])) || {1'b0,vector_address}+{8'b0,vector_length}>24'h800000)fault<=1;
     else begin
      address<=vector_address;remaining<=vector_length;first<={1'b0,vector_address[4:0]};
      input_cursor<={1'b0,vector_address[4:0]};
      last<=vector_length<room?{1'b0,vector_address[4:0]}+vector_length[5:0]:6'd32;
      mask<=32'hffffffff;incoming<=0;filling<=1;filled<=0;final_block<=0;state<=READ;
     end
    end
    SELECT:if(!output_valid)state<=READ;
    READ:if(req_ready)state<=RACK;
    RACK:if(rsp_valid&&rsp_ready)begin
     old_data<=rsp_data;output_cursor<=first;output_end<=last;output_valid<=1;state<=filled?WRITE:WAIT_FILL;
    end
    WAIT_FILL:if(filled)state<=WRITE;
    WRITE:begin end // Accepted writes are handled below, including RACK bypass.
    WACK:if(rsp_valid)begin
     if(!final_block)state<=READ;
     else if(!output_valid || (out_ready&&output_cursor+STEP==output_end))begin done<=1;state<=IDLE;end
     else state<=DRAIN;
    end
    DRAIN:if(!output_valid)begin done<=1;state<=IDLE;end
    default:begin fault<=1;state<=IDLE;end
   endcase
   if(chain_read&&req_ready)state<=RACK;
   if(req_valid&&req_ready&&req_write)begin
     final_block<=remaining==last-first;filled<=0;state<=WACK;
     if(remaining!=last-first)begin
      remaining<=remaining-(last-first);address<={address[22:5],5'b0}+23'd32;
      first<=0;input_cursor<=0;mask<=32'hffffffff;incoming<=0;filling<=1;
      last<=remaining-(last-first)<32?remaining-(last-first):6'd32;
     end
    end
  end
 end
endmodule
