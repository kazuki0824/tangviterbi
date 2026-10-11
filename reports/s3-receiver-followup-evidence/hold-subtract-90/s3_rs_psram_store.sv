// FIFO codeword retention in 512 external 256-byte PSRAM slots (128 KiB).
// Receive all 204 bytes and zero-pad the burst; commit only after 64 physical
// write acknowledgements. Never reuse a slot at RPC/DMA completion. Reading
// retires the slot after the consumer takes all bytes AND padding is drained.
// One producer and one in-order corrected-codeword consumer. No RPC here.
module s3_rs_psram_store(
 input wire clk,resetn,upstream_fault,
 input wire in_valid,output wire in_ready,input wire [7:0] in_data,
 output reg codeword_committed,
 input wire read_request,output wire read_request_ready,
 output wire out_valid,input wire out_ready,output wire [7:0] out_data,
 output wire out_last,output reg codeword_retired,
 output wire mem_write_valid,input wire mem_write_ready,
 output wire [20:0] mem_write_address,output wire [31:0] mem_write_data,
 input wire mem_write_ack,
 output wire mem_read_request,input wire mem_read_ready,
 output wire [20:0] mem_read_address,
 input wire mem_read_valid,output wire mem_read_take,
 input wire [31:0] mem_read_data,input wire mem_read_last,
 output wire [9:0] held_codewords,output wire fault
);
 reg [9:0] committed,retired;
 reg [7:0] input_offset;
 reg [5:0] write_word;
 reg [31:0] packed_word,pending_data;
 reg pending,padding,write_wait;
 reg [6:0] acknowledgements;
 reg [1:0] read_state,byte_index;
 reg [5:0] read_word;
 reg local_fault;
 localparam READ_IDLE=0,READ_COMMAND=1,READ_STREAM=2;
 assign held_codewords=committed-retired;
 assign fault=local_fault||upstream_fault;
 // The pending word owns pending_data, so the next three input bytes can
 // already fill packed_word. Accept byte four only when that word can leave.
 assign in_ready=!fault&&!padding&&!write_wait&&held_codewords<512&&
                 (!pending||input_offset[1:0]!=3||mem_write_ready);
 assign mem_write_valid=pending&&!fault;
 assign mem_write_address={6'd0,committed[8:0],write_word};
 assign mem_write_data=pending_data;
 assign read_request_ready=read_state==READ_IDLE&&held_codewords!=0&&!fault;
 assign mem_read_request=read_state==READ_COMMAND&&!fault;
 assign mem_read_address={6'd0,retired[8:0],6'd0};
 assign out_valid=read_state==READ_STREAM&&read_word<51&&mem_read_valid&&!fault;
 assign out_data=mem_read_data[byte_index*8+:8];
 assign out_last=read_word==50&&byte_index==3;
 assign mem_read_take=read_state==READ_STREAM&&mem_read_valid&&!fault&&
                      (read_word>=51 || (out_ready&&byte_index==3));
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin
   committed<=0;retired<=0;input_offset<=0;write_word<=0;
   packed_word<=0;pending_data<=0;pending<=0;padding<=0;write_wait<=0;
   acknowledgements<=0;read_state<=READ_IDLE;byte_index<=0;read_word<=0;
   local_fault<=0;codeword_committed<=0;codeword_retired<=0;
  end else begin
   codeword_committed<=0;codeword_retired<=0;
   if(!fault)begin
    if(in_valid&&in_ready)begin
     packed_word[input_offset[1:0]*8+:8]<=in_data;
     if(input_offset[1:0]==3)begin
      pending_data<={in_data,packed_word[23:0]};pending<=1;
     end
     if(input_offset==203)begin padding<=1;input_offset<=0;end
     else input_offset<=input_offset+1'b1;
    end
    if(mem_write_valid&&mem_write_ready)begin
     if(!(in_valid&&in_ready&&input_offset[1:0]==3))pending<=0;
     if(write_word==63)begin write_wait<=1;padding<=0;end
     else begin
      write_word<=write_word+1'b1;
      if(padding)begin pending<=1;pending_data<=0;end
     end
    end
    if(mem_write_ack)begin
     if(!write_wait) local_fault<=1;
     else if(acknowledgements==63)begin
      committed<=committed+1'b1;codeword_committed<=1;
      write_wait<=0;write_word<=0;acknowledgements<=0;
     end else acknowledgements<=acknowledgements+1'b1;
    end
    if(read_request&&read_request_ready)read_state<=READ_COMMAND;
    if(mem_read_request&&mem_read_ready)begin
     read_state<=READ_STREAM;read_word<=0;byte_index<=0;
    end
    if(out_valid&&out_ready)byte_index<=byte_index+1'b1;
    if(mem_read_take)begin
     if(mem_read_last!=(read_word==63))local_fault<=1;
     if(read_word==63)begin
      retired<=retired+1'b1;codeword_retired<=1;read_state<=READ_IDLE;
     end else read_word<=read_word+1'b1;
    end
   end
  end
 end
endmodule
