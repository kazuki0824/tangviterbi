// Raw-only 16/32-KiB token frame -> four/eight existing 4-KiB page frames.
// Place after s3_spi_rx with matching WRITE_BYTES, before page_guard/store.
// No payload buffer/copy; upstream CDC FIFO must cover synthetic-header stalls.
// Downstream may commit earlier pages before a later frame fault: fault MUST
// mute the whole epoch. This is framing validation, not CRC/integrity proof.
module s3_bulk_page_split #(parameter MAX_FRAME_CYCLES=262144, WRITE_BYTES=32768)(
 input wire clk, resetn, input wire [15:0] epoch,
 input wire valid, output wire ready, input wire [35:0] token,
 output wire out_valid, input wire out_ready, output wire [35:0] out_token,
 output reg fault
);
 localparam HEADER=0, OFFSET=1, LENGTH=2, EMIT_H=3, EMIT_O=4, EMIT_L=5, BODY=6;
 reg [2:0] state;
 reg [31:0] header, offset;
 reg [$clog2(WRITE_BYTES/4)-1:0] word_index;
 initial if(WRITE_BYTES!=16384 && WRITE_BYTES!=32768) $fatal(1,"unsupported bulk length");
 localparam TIMER_W=$clog2(MAX_FRAME_CYCLES+1);
 reg [TIMER_W-1:0] age;
 initial if(MAX_FRAME_CYCLES<2) $fatal(1,"frame watchdog too small");
 wire [3:0] tag=token[35:32];
 wire good_body=tag==(word_index==WRITE_BYTES/4-1 ? 4'd8 : 4'd0);
 wire emitting=state==EMIT_H || state==EMIT_O || state==EMIT_L;
 assign ready=!fault && !emitting && (state!=BODY || !good_body || out_ready);
 assign out_valid=!fault && (emitting || (state==BODY && valid && good_body));
 assign out_token=state==EMIT_H ? {4'd1,header} :
                  state==EMIT_O ? {4'd2,offset} :
                  state==EMIT_L ? {4'd3,32'd4096} :
                  {word_index[9:0]==1023 ? 4'd8 : 4'd0,token[31:0]};
 always @(posedge clk or negedge resetn) begin
  if(!resetn) begin
   state<=HEADER;header<=0;offset<=0;word_index<=0;age<=0;fault<=0;
  end else if(!fault) begin
   if(state==HEADER) age<=0; else age<=age+1'b1;
   if(state!=HEADER && age==MAX_FRAME_CYCLES-1) fault<=1;
   else if(emitting && out_ready) begin
    case(state)
     EMIT_H: state<=EMIT_O;
     EMIT_O: state<=EMIT_L;
     EMIT_L: state<=BODY;
    endcase
   end else if(valid && ready) begin
    case(state)
     HEADER: if(tag!=1 || token[31:16]!=16'hd711 || epoch==0 || token[15:0]!=epoch)
              fault<=1;
             else begin header<=token[31:0];state<=OFFSET;end
     OFFSET: if(tag!=2 || token[11:0]!=0) fault<=1;
             else begin offset<=token[31:0];state<=LENGTH;end
     LENGTH: if(tag!=3 || token[31:0]!=WRITE_BYTES) fault<=1;
             else begin word_index<=0;state<=EMIT_H;end
     BODY: if(!good_body) fault<=1;
           else if(word_index==WRITE_BYTES/4-1) state<=HEADER;
           else begin
            word_index<=word_index+1'b1;
            if(word_index[9:0]==1023) begin offset<=offset+4096;state<=EMIT_H;end
           end
     default: fault<=1;
    endcase
   end
  end
 end
endmodule
