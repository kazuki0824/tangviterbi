// CAD-only scan inputs and registered observation. Not a receiver top.
module t_time_tile_dma_probe(input wire clk,resetn,scan_enable,scan_in,output wire signature);
 reg[392:0]stimulus;wire[282:0]observed;reg[282:0]observed_capture;
 reg[8:0]digest_chunks;reg digest;
 genvar i;
 generate for(i=0;i<9;i=i+1)begin: chunk
  localparam START=i*32;
  localparam WIDTH=283-START<32 ? 283-START : 32;
  always @(posedge clk)begin
   if(!resetn)digest_chunks[i]<=0;
   else digest_chunks[i]<=^observed_capture[START+:WIDTH];
  end
 end endgenerate
 always @(posedge clk)begin
  if(!resetn)begin stimulus<=0;observed_capture<=0;digest<=0;end
  else begin
   if(scan_enable)stimulus<={stimulus[391:0],scan_in};
   observed_capture<=observed;digest<=digest^(^digest_chunks);
  end
 end
 assign signature=digest;
 t_time_tile_dma dut(.clk(clk),.resetn(resetn),
.start_valid(stimulus[0:0]),
.scratch_base(stimulus[23:1]),
.scratch_stride(stimulus[39:24]),
.cfg_valid(stimulus[40:40]),
.cfg_bypass(stimulus[41:41]),
.cfg_base(stimulus[64:42]),
.cfg_end(stimulus[88:65]),
.cfg_write_start(stimulus[111:89]),
.cfg_read_start(stimulus[134:112]),
.req_ready(stimulus[135:135]),
.rsp_valid(stimulus[136:136]),
.rsp_data(stimulus[392:137]),
.start_ready(observed[0:0]),
.cfg_ready(observed[1:1]),
.req_valid(observed[2:2]),
.req_write(observed[3:3]),
.req_address(observed[24:4]),
.req_data(observed[280:25]),
.done(observed[281:281]),
.collision(observed[282:282]));
endmodule
