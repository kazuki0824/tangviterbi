// Measurement fixture: all 1632 scan bits remain independently loadable.
// Twenty-one ALU54D output registers replace 1134 fabric scan registers.
// Output checksum has one less pipeline stage than the older fixture.
// CAD-only scan stimulus and pipelined observation of the integrated block.
module shared_receiver_fft_tile_probe(input wire clk,resetn,scan_enable,scan_in,output wire signature);
 wire[1631:0]stimulus;
 reg[497:0]scan_low;
 wire[1631:0]scan_next={stimulus[1630:0],scan_in};
 assign stimulus[497:0]=scan_low;
 genvar bank;
 generate for(bank=0;bank<21;bank=bank+1)begin: scan_dsp
  ALU54D #(.AREG(0),.BREG(0),.ASIGN_REG(0),.BSIGN_REG(0),
   .ACCLOAD_REG(0),.OUT_REG(1),.B_ADD_SUB(0),.C_ADD_SUB(0),
   .ALUD_MODE(2),.ALU_RESET_MODE("SYNC")) storage(
   .A(scan_next[498+bank*54+:54]),.B(54'd0),.CASI(55'd0),
   .ASIGN(1'b0),.BSIGN(1'b0),.ACCLOAD(1'b0),
   .CLK(clk),.CE(scan_enable||!resetn),.RESET(!resetn),
   .DOUT(stimulus[498+bank*54+:54]),.CASO());
 end endgenerate
 wire[383:0]observed;
 reg[11:0]digest_chunks;reg digest;
 genvar i;
 generate for(i=0;i<12;i=i+1)begin: chunk
  localparam START=i*32;
  localparam WIDTH=384-START<32 ? 384-START : 32;
  always @(posedge clk)begin
   if(!resetn)digest_chunks[i]<=0;
   else digest_chunks[i]<=^observed[START+:WIDTH];
  end
 end endgenerate
 always @(posedge clk)begin
  if(!resetn)begin scan_low<=0;digest<=0;end
  else begin
   if(scan_enable)scan_low<=scan_next[497:0];
digest<=digest^(^digest_chunks);
  end
 end
 assign signature=digest;
 shared_receiver_fft_tile dut(.clk(clk),.resetn(resetn),
.tile_start(stimulus[1497:1497]),
.tile_scratch(stimulus[1520:1498]),
.tile_stride(stimulus[1536:1521]),
.tile_cfg_valid(stimulus[1537:1537]),
.tile_bypass(stimulus[1538:1538]),
.tile_base(stimulus[1561:1539]),
.tile_end(stimulus[1585:1562]),
.tile_write_start(stimulus[1608:1586]),
.tile_read_start(stimulus[1631:1609]),
.tile_ready(observed[380]),
.tile_cfg_ready(observed[381]),
.tile_done(observed[382]),
.tile_collision(observed[383]),
 .fft_mode(stimulus[1:0]),.fft_in_valid(stimulus[2]),
 .fft_in_data(stimulus[34:3]),.fft_out_ready(stimulus[35]),
 .fft_in_ready(observed[0]),.fft_out_data(observed[32:1]),
 .fft_out_bin(observed[376:364]),.fft_out_valid(observed[377]),
 .fft_frame_end(observed[378]),.fft_overflow(observed[379]),
 .bg_valid(stimulus[62:59]),
 .bg_write(stimulus[66:63]),
 .bg_address(stimulus[150:67]),
 .bg_data(stimulus[1174:151]),
 .bg_dqm(stimulus[1302:1175]),
 .bg_rsp_ready(stimulus[1306:1303]),
 .dq_in(stimulus[1338:1307]),
 .commit_valid(stimulus[1339]),
 .commit_addresses(stimulus[1402:1340]),
 .commit_lengths(stimulus[1450:1403]),
 .rates(stimulus[1462:1451]),.s_tc8_mode(stimulus[1463]),
 .s_valid(stimulus[1464]),.s_data(stimulus[1496:1465]),.s_ready(observed[357]),
 .bg_ready(observed[36:33]),
 .bg_rsp_valid(observed[40:37]),
 .bg_rsp_data(observed[296:41]),
 .initialized(observed[297]),
 .fault(observed[298]),
 .sd_cmd(observed[301:299]),
 .sd_bank(observed[303:302]),
 .sd_address(observed[314:304]),
 .sd_cke(observed[315]),
 .sd_dqm(observed[319:316]),
 .dq_oe(observed[320]),
 .dq_out(observed[352:321]),
 .commit_ready(observed[353]),
 .bank_live(observed[355:354]),
 .reuse_blocked(observed[356]),
 .out_valid(observed[358]),.out_bit(observed[359]),.out_b1(observed[360]),
 .out_tc8(observed[361]),.out_context(observed[363:362]));
endmodule
