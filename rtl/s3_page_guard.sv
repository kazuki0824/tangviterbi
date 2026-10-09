// Validate RX tokens before exposing a page to the two-port reorder store.
// Writes are tentative; consumers MUST wait for commit before reading a page.
// A fault poisons the epoch until reset. No page overwrite or automatic retry.
module s3_page_guard(
 input wire clk, resetn, input wire [15:0] epoch,
 input wire valid, output wire ready, input wire [35:0] token,
 input wire page_ready, output reg page_start,
 output reg [1:0] stream, output reg [31:0] offset,
 output wire data_valid,input wire data_ready,output wire [31:0] data,
 output reg commit,output reg fault
);
 localparam IDLE=0,OFFSET=1,LENGTH=2,BODY=3;
 reg [1:0] state;
 reg [9:0] words;
 wire [3:0] tag=token[35:32];
 wire good_data=state==BODY && ((words==1023 && tag==8) || (words!=1023 && tag==0));
 assign ready=!fault && (state==LENGTH ? page_ready : good_data ? data_ready : 1'b1);
 assign data_valid=valid && !fault && good_data;
 assign data=token[31:0];
 always @(posedge clk or negedge resetn) begin
  if(!resetn) begin state<=IDLE;words<=0;stream<=0;offset<=0;page_start<=0;commit<=0;fault<=0;end
  else begin
   page_start<=0;commit<=0;
   if(valid&&ready) case(state)
    IDLE: if(tag!=1 || epoch==0 || token[15:0]!=epoch ||
              (token[31:16]!=16'hd711 && token[31:16]!=16'hd712)) fault<=1;
          else begin stream<=token[17:16];state<=OFFSET;end
    OFFSET: if(tag!=2 || token[11:0]!=0) fault<=1;
            else begin offset<=token[31:0];state<=LENGTH;end
    LENGTH: if(tag!=3 || token[31:0]!=4096) fault<=1;
            else begin page_start<=1;words<=0;state<=BODY;end
    BODY: if(!good_data) fault<=1;
          else if(words==1023) begin commit<=1;state<=IDLE;end
          else words<=words+1'b1;
   endcase
  end
 end
endmodule
