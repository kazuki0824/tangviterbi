// Independent-clock FIFO. DEPTH is 2**AW. Both sides reset at a stopped epoch.
// Gray pointers cross through two registers; no multibit binary pointer CDC.
// RAM prefetch plus a separate output register break the RAM-to-parser path.
// Both holding stages support backpressure; at most DEPTH+2 words are owned.
module s3_async_fifo #(parameter W=36, AW=5)(
 input wire wclk, rclk, resetn,
 input wire wvalid, output wire wready, input wire [W-1:0] wdata,
 output wire rvalid, input wire rready, output wire [W-1:0] rdata
);
 initial if(AW<2 || W<1) $fatal(1,"unsupported FIFO dimensions");
 (* ram_style="block" *) reg [W-1:0] mem[0:(1<<AW)-1];
 reg [AW:0] wb, wg, rb, rg;
 (* async_reg="true" *) reg [AW:0] rq1,rq2,wq1,wq2;
 reg [W-1:0] rd, output_data;
 reg valid, prefetched;
 wire move_output=!valid || rready;
 wire fetch=!prefetched || move_output;
 wire [AW:0] full_value={~rq2[AW:AW-1],rq2[AW-2:0]};
 assign wready=wg!=full_value;
 always @(posedge wclk) if(resetn && wvalid && wready) mem[wb[AW-1:0]]<=wdata;
 wire [AW:0] wn=wb+1'b1;
 always @(posedge wclk or negedge resetn) begin
  if(!resetn) begin wb<=0;wg<=0;rq1<=0;rq2<=0;end
  else begin
   rq1<=rg;rq2<=rq1;
   if(wvalid&&wready) begin wb<=wn;wg<=wn^(wn>>1);end
  end
 end
 always @(posedge rclk) if(resetn && fetch && rg!=wq2) rd<=mem[rb[AW-1:0]];
 wire [AW:0] rn=rb+1'b1;
 always @(posedge rclk or negedge resetn) begin
  if(!resetn) begin rb<=0;rg<=0;wq1<=0;wq2<=0;valid<=0;prefetched<=0;end
  else begin
   wq1<=wg;wq2<=wq1;
   if(move_output) begin valid<=prefetched;if(prefetched)output_data<=rd;end
   if(fetch) begin
    prefetched<=rg!=wq2;
    if(rg!=wq2) begin rb<=rn;rg<=rn^(rn>>1);end
   end
  end
 end
 assign rvalid=valid;
 assign rdata=output_data;
endmodule
