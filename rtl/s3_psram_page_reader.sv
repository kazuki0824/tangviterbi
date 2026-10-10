// Ordered, committed page descriptor -> sixteen 256-byte memory reads.
// Holds the page slot until all 1024 words are consumed, including downstream
// stalls. BASE_WORD keeps RF/FFT rings distinct in the striped 8 MiB space.
module s3_psram_page_reader #(
 parameter integer SLOT_BITS=4,
 parameter [20:0] BASE_WORD=0
)(
 input wire clk,resetn,upstream_fault,
 input wire page_valid,input wire [SLOT_BITS-1:0] page_slot,
 input wire [31:0] page_offset,output wire page_retire,
 output wire request,input wire request_ready,output wire [20:0] address,
 input wire read_valid,output wire read_take,input wire [31:0] read_data,input wire read_last,
 output wire out_valid,input wire out_ready,output wire [31:0] out_data,
 output wire out_last,output wire [31:0] out_offset,
 output wire fault
);
 reg active,pending,local_fault;
 reg [SLOT_BITS-1:0] slot;
 reg [31:0] offset;
 reg [9:0] index;
 assign fault=upstream_fault||local_fault;
 assign request=active&&!pending&&!fault;
 assign address=BASE_WORD+{slot,index[9:6],6'd0};
 assign out_valid=active&&pending&&read_valid&&!fault;
 assign out_data=read_data;
 assign out_last=index==1023;
 assign out_offset=offset;
 assign read_take=out_valid&&out_ready;
 assign page_retire=read_take&&out_last&&!fault;
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin active<=0;pending<=0;local_fault<=0;slot<=0;offset<=0;index<=0;end
  else if(!fault)begin
   if(!active&&page_valid)begin active<=1;slot<=page_slot;offset<=page_offset;index<=0;end
   if(request&&request_ready)pending<=1;
   if(read_valid&&(!active||!pending))local_fault<=1;
   if(read_take)begin
    if(read_last!=(index[5:0]==63))local_fault<=1;
    index<=index+1'b1;
    if(read_last)pending<=0;
    if(out_last)active<=0;
   end
   if(active&&(!page_valid||page_slot!=slot||page_offset!=offset))local_fault<=1;
  end else local_fault<=1;
 end
endmodule
