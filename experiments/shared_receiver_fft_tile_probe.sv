// CAD-only scan stimulus and pipelined observation of the integrated block.
module shared_receiver_fft_tile_probe(input wire clk,resetn,scan_enable,scan_in,output wire signature);
 reg[1631:0]stimulus;
 wire[383:0]observed;reg[383:0]observed_capture;
 reg[11:0]digest_chunks;reg digest;
 genvar i;
 generate for(i=0;i<12;i=i+1)begin: chunk
  localparam START=i*32;
  localparam WIDTH=384-START<32 ? 384-START : 32;
  always @(posedge clk)begin
   if(!resetn)digest_chunks[i]<=0;
   else digest_chunks[i]<=^observed_capture[START+:WIDTH];
  end
 end endgenerate
 always @(posedge clk)begin
  if(!resetn)begin stimulus<=0;observed_capture<=0;digest<=0;end
  else begin
   if(scan_enable)stimulus<={stimulus[1630:0],scan_in};
   observed_capture<=observed;digest<=digest^(^digest_chunks);
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
