// Shared ISDB RS(204,188) input ownership and dual 3-wire MPEG-TS sinks.
// A whole codeword is owned by one receiver until all 188 output bytes
// have left the single RS engine. No bitstream reconstruction or RS bypass.
// The decoder is generated from independent-vector-tested s3_rs_isdb.source.
// Error codewords mute the affected TS output. No overall timing proof.
module shared_rs2_dual_ts(
 input wire clk,resetn,
 input wire [1:0] input_valid,output wire [1:0] input_ready,
 input wire [15:0] input_byte,
 output wire [1:0] ts_clk,ts_data,ts_valid,ts_fault
);
 localparam IDLE=2'd0,INGEST=2'd1,EMIT=2'd2;
 reg[1:0]phase;
 reg owner,rr_next;
 reg[7:0]accepted,emitted;
 reg[1:0]hard_fault;
 wire rs_input_ready,rs_output_valid,rs_block_fail;
 wire[7:0]rs_output_byte;
 wire[1:0]ts_byte_ready,ts_sink_fault;
 wire[1:0]ts_raw_valid;
 wire pick= (input_valid[rr_next] || !input_valid[!rr_next]) ? rr_next : !rr_next;
 wire chosen=phase==IDLE?pick:owner;
 wire feed=(phase==IDLE || phase==INGEST) && !hard_fault[chosen];
 wire fire=feed && input_valid[chosen] && rs_input_ready;
 wire accept_t=feed && rs_input_ready && chosen==0;
 wire accept_s=feed && rs_input_ready && chosen==1;
 assign input_ready={accept_s,accept_t};
 wire [7:0]rs_in_byte=input_byte[chosen*8+:8];
 wire out_fire=phase==EMIT && rs_output_valid;
 wire [1:0]ts_byte_valid={
    out_fire && owner==1 && !rs_block_fail && !hard_fault[1],
    out_fire && owner==0 && !rs_block_fail && !hard_fault[0]
 };
 wire [1:0]total_fault=hard_fault | ts_sink_fault;
 assign ts_fault=total_fault;
 assign ts_valid=ts_raw_valid & ~total_fault;

 rs204_188_compact decoder(
  .clk(clk),.resetn(resetn),
  .in_valid(feed&&input_valid[chosen]),.in_ready(rs_input_ready),
  .in_byte(rs_in_byte),.out_valid(rs_output_valid),
  .out_byte(rs_output_byte),.block_fail(rs_block_fail)
 );
 dual_isdb_serial_ts_sinks ts(
  .clk(clk),.resetn(resetn),
  .byte_valid(ts_byte_valid),.byte_ready(ts_byte_ready),
  .byte_data({rs_output_byte,rs_output_byte}),
  .ts_clk(ts_clk),.ts_data(ts_data),.ts_valid(ts_raw_valid),
  .fault(ts_sink_fault)
 );

 always @(posedge clk or negedge resetn) begin
  if(!resetn)begin
   phase<=IDLE;owner<=0;rr_next<=0;accepted<=0;emitted<=0;
   hard_fault<=0;
  end else begin
   if(out_fire && (rs_block_fail || !ts_byte_ready[owner]))
    hard_fault[owner]<=1;
   if(phase==IDLE)begin
    if(fire)begin
     owner<=chosen;accepted<=1;emitted<=0;phase<=INGEST;
    end
   end else if(phase==INGEST)begin
    if(fire)begin
     if(accepted==203)begin phase<=EMIT;accepted<=0;end
     else accepted<=accepted+1'b1;
    end
   end else if(out_fire)begin
    if(emitted==187)begin
     phase<=IDLE;emitted<=0;rr_next<=!owner;
    end else emitted<=emitted+1'b1;
   end
  end
 end
endmodule
