// Dual-channel ISDB raw-sample complex FIR multiply-accumulate kernel.
// Unquantized signed I10/Q10 x signed 16-bit runtime coefficients;
// exact signed32 accumulator output. 33 taps, PAR concurrent taps per
// axis, no SoC downsampling or precision degradation. One completed output
// per ceil(33/PAR) fabric clocks when sink is always ready.
// This is FIR arithmetic only: coefficient design, polyphase rate selection,
// resampler, symbol timing and RF lock are NOT included.
// CAD candidate: bank coefficient/sample addressing per multiply lane.
// Keeps exact signed arithmetic and the original handshake/latency.
module isdb_complex_fir33 #(
 parameter integer PAR=11
)(
 input wire clk,resetn,
 input wire in_valid,output wire in_ready,
 input wire signed[9:0]in_i,in_q,
 output reg out_valid,input wire out_ready,
 output reg signed[31:0]out_i,out_q,
 input wire coeff_valid,output wire coeff_ready,
 input wire[5:0]coeff_addr,input wire signed[15:0]coeff_value
);
 localparam integer PHASES=(33+PAR-1)/PAR;
 initial if(PAR<1 || PAR>33) $fatal(1,"PAR must be in [1,33]");
 reg signed[15:0]coeff[0:32];
 reg[32:0]coeff_written;
 reg signed[9:0]hist_i[0:32],hist_q[0:32];
 reg[5:0]phase;
 reg signed[31:0]acc_i,acc_q;
 wire coeff_fire=coeff_valid&&coeff_ready;
 assign coeff_ready=resetn&&phase==0&&!out_valid&&!in_valid;
 assign in_ready=resetn&&(&coeff_written)&&phase==0&&(!out_valid||out_ready)&&!coeff_valid;
 wire take=in_valid&&in_ready;
 genvar lane;
 wire signed [31:0]mult_i[0:PAR-1],mult_q[0:PAR-1];
 generate for(lane=0;lane<PAR;lane=lane+1)begin:bank
  wire signed[15:0]phase_coeff[0:PHASES-1];
  wire signed[9:0]phase_i[0:PHASES-1];
  wire signed[9:0]phase_q[0:PHASES-1];
  for(genvar p=0;p<PHASES;p=p+1)begin:part
   if(p*PAR+lane<33)begin:used
    assign phase_coeff[p]=coeff[p*PAR+lane];
    if(p==0)begin:first
     if(lane==0)begin:first_sample
      assign phase_i[p]=in_i;
      assign phase_q[p]=in_q;
     end else begin:history
      assign phase_i[p]=hist_i[lane-1];
      assign phase_q[p]=hist_q[lane-1];
     end
    end else begin:later
     assign phase_i[p]=hist_i[p*PAR+lane];
     assign phase_q[p]=hist_q[p*PAR+lane];
    end
   end else begin:unused
    assign phase_coeff[p]=16'sd0;
    assign phase_i[p]=10'sd0;
    assign phase_q[p]=10'sd0;
   end
  end
  reg signed[15:0]selected_coeff;
  reg signed[9:0]selected_i,selected_q;
  integer t;
  always @* begin
   selected_coeff=0; selected_i=0;selected_q=0;
   for(t=0;t<PHASES;t=t+1)begin
    if(phase==t)begin
     selected_coeff=phase_coeff[t];
     selected_i=phase_i[t];
     selected_q=phase_q[t];
    end
   end
  end
  wire signed[25:0]product_i=selected_i*selected_coeff;
  wire signed[25:0]product_q=selected_q*selected_coeff;
  assign mult_i[lane]={{6{product_i[25]}},product_i};
  assign mult_q[lane]={{6{product_q[25]}},product_q};
 end endgenerate
 integer k;
 reg signed[31:0]partial_i,partial_q;
 always @*begin
  partial_i=0;partial_q=0;
  for(k=0;k<PAR;k=k+1)begin
   partial_i=partial_i+mult_i[k];
   partial_q=partial_q+mult_q[k];
  end
 end
 integer j;
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin
   phase<=0;out_valid<=0;out_i<=0;out_q<=0;
   acc_i<=0;acc_q<=0;coeff_written<=0;
   for(j=0;j<33;j=j+1)begin hist_i[j]<=0;hist_q[j]<=0;end
  end else begin
   if(coeff_fire && coeff_addr<33)begin
    coeff[coeff_addr]<=coeff_value;
    coeff_written[coeff_addr]<=1'b1;
   end
   if(out_valid&&out_ready)out_valid<=0;
   if(phase==0)begin
    if(take)begin
     for(j=32;j>0;j=j-1)begin
      hist_i[j]<=hist_i[j-1];hist_q[j]<=hist_q[j-1];
     end
     hist_i[0]<=in_i;hist_q[0]<=in_q;
     acc_i<=partial_i;acc_q<=partial_q;
     if(PHASES==1)begin
      out_i<=partial_i;out_q<=partial_q;out_valid<=1;phase<=0;
     end else phase<=1;
    end
   end else if(phase==PHASES-1)begin
    out_i<=acc_i+partial_i;out_q<=acc_q+partial_q;
    out_valid<=1;phase<=0;
   end else begin
    acc_i<=acc_i+partial_i;acc_q<=acc_q+partial_q;
    phase<=phase+1'b1;
   end
  end
 end
endmodule

// Native 16-MS/s T and 40-MS/s S candidates, common 154.285714-MHz
// compute clock. T: 9 clocks/sample, 8 complex MAC multipliers.
// S: 3 clocks/sample, 22 complex MAC multipliers.
// These are nominal initiation intervals, not routed WCET/PHY proof.
module dual_isdb_complex_fir33(
 input wire clk,resetn,
 input wire[1:0]in_valid,output wire[1:0]in_ready,
 input wire signed[19:0]in_i,in_q,
 output wire[1:0]out_valid,input wire[1:0]out_ready,
 output wire signed[63:0]out_i,out_q,
 input wire[1:0]coeff_valid,output wire[1:0]coeff_ready,
 input wire[11:0]coeff_addr,input wire signed[31:0]coeff_value
);
 isdb_complex_fir33 #(.PAR(4)) t (
  .clk(clk),.resetn(resetn),.in_valid(in_valid[0]),.in_ready(in_ready[0]),
  .in_i(in_i[9:0]),.in_q(in_q[9:0]),
  .out_valid(out_valid[0]),.out_ready(out_ready[0]),
  .out_i(out_i[31:0]),.out_q(out_q[31:0]),
  .coeff_valid(coeff_valid[0]),.coeff_ready(coeff_ready[0]),
  .coeff_addr(coeff_addr[5:0]),.coeff_value(coeff_value[15:0])
 );
 isdb_complex_fir33 #(.PAR(11)) s (
  .clk(clk),.resetn(resetn),.in_valid(in_valid[1]),.in_ready(in_ready[1]),
  .in_i(in_i[19:10]),.in_q(in_q[19:10]),
  .out_valid(out_valid[1]),.out_ready(out_ready[1]),
  .out_i(out_i[63:32]),.out_q(out_q[63:32]),
  .coeff_valid(coeff_valid[1]),.coeff_ready(coeff_ready[1]),
  .coeff_addr(coeff_addr[11:6]),.coeff_value(coeff_value[31:16])
 );
endmodule
