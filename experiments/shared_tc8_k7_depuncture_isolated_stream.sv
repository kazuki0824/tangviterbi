// Experimental integrated TC8 metric / binary depuncture / queues / scheduler / core.
// Global reset is the mode and rate epoch boundary; no output backpressure.
// Four independent puncture phases feeding the queued shared K7 engine.
// rates: three bits per context, 0=1/2, 1=2/3, 2=3/4, 3=5/6, 4=7/8.
// Hold rates stable through the first rising edge after global reset release.
// Rate changes require global reset; no independent retune is implemented.
module shared_tc8_k7_depuncture_isolated_stream (
 input wire clk, resetn,
 input wire [11:0] rates,
 input wire s_tc8_mode,
 input wire iq_valid, output wire iq_ready, input wire signed [15:0] in_i, in_q,
 output wire out_b1, out_tc8,
 input wire in_valid, output wire in_ready,
 input wire [1:0] in_context, input wire [7:0] in_soft,
 output wire out_valid, out_bit, output wire [1:0] out_context,
 output wire [3:0] fault
);
 reg configuring;
 reg tc8_mode, mode_fault;
 wire active = resetn && !configuring && !mode_fault;
 always @(posedge clk or negedge resetn)
  if (!resetn) begin tc8_mode<=0; mode_fault<=0; end
  else if (configuring) tc8_mode<=s_tc8_mode;
  else if (s_tc8_mode!=tc8_mode) mode_fault<=1;
 wire metric_valid, metric_ready, metric_input_ready;
 wire [35:0] costs; wire [3:0] choice;
 assign iq_ready=active && tc8_mode && metric_input_ready;
 assign out_tc8=out_valid && out_context==3 && tc8_mode;
 s3_tc8psk_metric_folded metric (
  .clk(clk), .resetn(resetn), .in_valid(iq_valid && active && tc8_mode),
  .in_ready(metric_input_ready), .in_i(in_i), .in_q(in_q),
  .out_valid(metric_valid), .out_ready(metric_ready), .costs(costs), .b1_choice(choice)
 );
 always @(posedge clk or negedge resetn)
  if (!resetn) configuring<=1; else configuring<=0;
 wire [3:0] soft_ready, pair_valid, pair_ready;
 wire [7:0] xs[0:3], ys[0:3];
 wire [1:0] erased[0:3];
 reg [1:0] rr, selected;
 reg found;
 integer offset;
 reg [1:0] candidate;
 wire queue_ready;
 wire [3:0] context_ready;
 assign in_ready=active && !(tc8_mode && in_context==3) && soft_ready[in_context];
 generate for(genvar c=0;c<4;c=c+1)begin : g_depuncture
  wire sr,pv,pr,err;
  wire accept_context=in_valid && active && !(tc8_mode && c==3) && in_context==c;
  wire [2:0] context_rate=rates[3*c+:3];
  assign pair_ready[c]=active && !(tc8_mode && c==3) && found && selected==c && queue_ready;
  wire [7:0] sx,sy;
  wire [1:0] er;
  assign soft_ready[c]=sr;
  assign pair_valid[c]=pv;
  assign xs[c]=sx;
  assign ys[c]=sy;
  assign erased[c]=er;
  assign fault[c]=err | (c==3 && mode_fault);
  assign pr=pair_ready[c];
  s3_depuncture_isolated dp (
   .clk(clk), .resetn(resetn), .frame_start(configuring), .rate(context_rate),
   .in_valid(accept_context),
   .in_ready(sr), .in_soft(in_soft),
   .out_valid(pv), .out_ready(pr),
   .soft_x(sx), .soft_y(sy), .erasure(er), .fault(err)
  );
 end endgenerate
 always @* begin
  selected=rr;found=0;candidate=0;
  for(offset=0;offset<4;offset=offset+1)begin
   candidate=rr+offset;
   if(!found && (candidate==3 && tc8_mode ? metric_valid : pair_valid[candidate]) && context_ready[candidate])begin selected=candidate;found=1;end
  end
 end
 always @(posedge clk or negedge resetn)
  if(!resetn)rr<=0;
  else if(found && queue_ready && !configuring)rr<=selected+1'b1;
 assign metric_ready=active && tc8_mode && found && selected==3 && queue_ready;
 shared_tc8_k7_stream stream (
  .clk(clk), .resetn(resetn), .in_valid(found && active), .in_ready(queue_ready),
  .in_context(selected), .soft0(xs[selected]), .soft1(ys[selected]), .erasure(erased[selected]),
  .out_valid(out_valid), .out_bit(out_bit), .out_context(out_context), .context_ready(context_ready),
  .tc8_mode(tc8_mode), .costs(costs), .b1_choice(choice), .out_b1(out_b1)
 );
endmodule
