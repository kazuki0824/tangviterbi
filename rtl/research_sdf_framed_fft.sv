// Research-only framed wrapper around the proven ideal-RAM SDF FFT.
// Accepts exactly N unmodified Q15 complex samples per frame and injects
// N-1 zero-tail samples to drain the SDF pipeline; does not silently drop input.
// It resets every stage between frames. Thus it is *not* a gapless receiver
// pipeline, a variable-latency SDRAM PHY, nor an accepted timing solution.
// LOGN=11/12/13 is selected at elaboration, not runtime.
// The source must honor in_ready during the finite drain/reset interval.
module research_sdf_framed_fft #(parameter integer LOGN=13) (
 input wire clk,resetn,
 input wire in_valid,output wire in_ready,input wire [31:0] in_data,
 output wire out_valid,input wire out_ready,output wire [31:0] out_data,
 output wire [LOGN-1:0] out_bin,output wire out_frame_end,
 input wire external_ready,
 output wire external_read_enable,
 output wire [LOGN-2:0] external_read_addr,
 input wire [31:0] external_read_data,
 output wire external_write_enable,
 output wire [LOGN-2:0] external_write_addr,
 output wire [31:0] external_write_data,
 output wire overflow
);
 localparam integer N=(1<<LOGN);
 localparam [1:0] CLEAR=0,FEED=1,FLUSH=2,DRAIN=3;
 reg [1:0] state;
 reg [LOGN:0] accepted,flushed,emitted;
 wire core_resetn=resetn&&(state!=CLEAR);
 wire core_in_valid=(state==FEED && in_valid)||(state==FLUSH);
 wire [31:0] core_in_data=(state==FEED)?in_data:32'b0;
 wire core_in_ready, core_out_valid, core_out_frame_end;
 wire [31:0] core_out_data;
 wire [LOGN-1:0] core_out_bin;
 assign in_ready=(state==FEED)&&core_in_ready;
 wire src_take=in_valid&&in_ready;
 wire tail_take=(state==FLUSH)&&core_in_ready;
 assign out_valid=(state!=CLEAR)&&core_out_valid;
 assign out_data=core_out_data;
 assign out_bin=core_out_bin;
 assign out_frame_end=out_valid && emitted==(N-1);
 wire sink_take=out_valid&&out_ready;
 research_sdf_fft #(.LOGN(LOGN)) core(
    .clk(clk),.resetn(core_resetn),
    .in_valid(core_in_valid),.in_ready(core_in_ready),
    .in_data(core_in_data),.out_valid(core_out_valid),
    .out_ready(out_ready),.out_data(core_out_data),
    .out_bin(core_out_bin),.out_frame_end(core_out_frame_end),
    .external_ready(external_ready),
    .external_read_enable(external_read_enable),
    .external_read_addr(external_read_addr),
    .external_read_data(external_read_data),
    .external_write_enable(external_write_enable),
    .external_write_addr(external_write_addr),
    .external_write_data(external_write_data),
    .overflow(overflow)
 );
 always @(posedge clk) begin
    if(!resetn) begin
      state<=CLEAR;accepted<=0;flushed<=0;emitted<=0;
    end else begin
      if(sink_take) emitted<=emitted+1'b1;
      case(state)
       CLEAR:begin
         accepted<=0;flushed<=0;emitted<=0;
         state<=FEED;
       end
       FEED:if(src_take)begin
         accepted<=accepted+1'b1;
         if(accepted==N-1) state<=FLUSH;
       end
       FLUSH:if(tail_take)begin
         flushed<=flushed+1'b1;
         if(flushed==N-2)state<=DRAIN;
       end
       DRAIN:if(sink_take && emitted==N-1)state<=CLEAR;
       default:state<=CLEAR;
      endcase
    end
 end
endmodule
