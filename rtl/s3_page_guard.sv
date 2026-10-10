// Validate RX tokens before exposing a page to the two-port reorder store.
// Writes are tentative; consumers MUST wait for commit before reading a page.
// A fault poisons the epoch until reset. No page overwrite or automatic retry.
// Absolute frame bound includes downstream backpressure. Default 331 us at
// 99 MHz exceeds a 102.65 us Quad page; store arbitration must fit this bound.
module s3_page_guard #(parameter MAX_FRAME_CYCLES=32768)(
 input wire clk, resetn, input wire [15:0] epoch,
 input wire valid, output wire ready, input wire [35:0] token,
 input wire page_ready, output reg page_start,
 output reg [1:0] stream, output reg [31:0] offset,
 output wire data_valid,input wire data_ready,output wire [31:0] data,
 output reg commit,output reg fault,output wire page_request
);
 localparam IDLE=0,OFFSET=1,LENGTH=2,RESERVE=3,BODY=4;
 reg [2:0] state;
 reg [9:0] words;
 localparam TIMER_W=$clog2(MAX_FRAME_CYCLES+1);
 initial if(MAX_FRAME_CYCLES<2) $fatal(1,"frame watchdog too small");
 reg [TIMER_W-1:0] age;
 wire [3:0] tag=token[35:32];
 wire good_data=state==BODY && ((words==1023 && tag==8) || (words!=1023 && tag==0));
 // Validate/consume length first; reserve on a separate registered state.
 // This keeps wide header checks out of the cross-port credit/ownership path.
 // A following payload token remains buffered until the grant is accepted.
 assign page_request=!fault && state==RESERVE;
 assign ready=!fault && state!=RESERVE && (good_data ? data_ready : 1'b1);
 assign data_valid=valid && !fault && good_data;
 assign data=token[31:0];
 always @(posedge clk or negedge resetn) begin
  if(!resetn) begin state<=IDLE;words<=0;stream<=0;offset<=0;page_start<=0;commit<=0;fault<=0;age<=0;end
  else begin
   page_start<=0;commit<=0;
   if(state==IDLE) age<=0;
   else if(!fault) age<=age+1'b1;
   if(state!=IDLE && age==MAX_FRAME_CYCLES-1) fault<=1;
   else if(!fault && state==RESERVE && page_ready)begin
    page_start<=1;words<=0;state<=BODY;
   end
   else if(valid&&ready) case(state)
    IDLE: if(tag!=1 || epoch==0 || token[15:0]!=epoch ||
              (token[31:16]!=16'hd711 && token[31:16]!=16'hd712)) fault<=1;
          else begin stream<=token[17:16];state<=OFFSET;end
    OFFSET: if(tag!=2 || token[11:0]!=0) fault<=1;
            else begin offset<=token[31:0];state<=LENGTH;end
    LENGTH: if(tag!=3 || token[31:0]!=4096) fault<=1;
            else state<=RESERVE;
    BODY: if(!good_data) fault<=1;
          else if(words==1023) begin commit<=1;state<=IDLE;end
          else words<=words+1'b1;
   endcase
  end
 end
endmodule
