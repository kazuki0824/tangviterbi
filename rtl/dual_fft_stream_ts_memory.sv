// Aligned FFT-window streams plus independent T LLR and S byte streams.
// The FFT bins are not yet connected through synchronization/equalization/demap
// to the T input. All three clients own their actual SDRAM requests.
module dual_fft_stream_ts_memory #(parameter INIT_CYCLES=27000,MODE=1,S0=3,I0=4,S1=3,I1=8,S2=7,I2=16)(
 input wire core_clk,mem_clk,resetn,
 input wire in_valid,output wire in_ready,input wire[31:0] in_data,input wire in_last,
 output wire out_valid,input wire out_ready,output wire[31:0] out_data,output wire out_last,
 output wire[8:0] ownership,
 input wire other_valid,output wire other_ready,input wire other_write,
 input wire[20:0] other_address,input wire[255:0] other_data,
 output wire other_rsp_valid,input wire other_rsp_ready,output wire[255:0] other_rsp_data,
 output wire initialized,memory_fault,output wire[2:0] sd_cmd,
 output wire[1:0] sd_bank,output wire[10:0] sd_address,
 output wire sd_cke,output wire[3:0] sd_dqm,output wire dq_oe,
 output wire[31:0] dq_out,input wire[31:0] dq_in,
 input wire[31:0] other_dqm,output wire[15:0] background_level,
 input wire s_byte_valid,output wire s_byte_ready,input wire[7:0] s_byte_data,
 output wire s_out_valid,input wire s_out_ready,output wire[7:0] s_out_data,
 output wire s_cw_last,s_super_last,s_fault,output wire[1:0] s_pending_packets,
 output wire[3:0] s_ownership,
 input wire t_start,output wire t_start_ready,input wire t_drain,
 input wire t_in_valid,output wire t_in_ready,input wire[31:0] t_in_data,
 output wire t_out_valid,input wire t_out_ready,output wire[31:0] t_out_data,
 output wire t_out_last,t_settled,t_result,t_done,t_busy,t_fault);
 wire bad_io=other_valid && other_address[9:8]==0;
 wire io_ready,core_memory_fault;reg partition_fault;
 always @(posedge mem_clk)begin
  if(!resetn)partition_fault<=0;else if(bad_io)partition_fault<=1;
 end
 assign other_ready=io_ready&&!bad_io;
 assign memory_fault=core_memory_fault|partition_fault;
 wire tv,tr,tw,trv,trr;wire[20:0] ta;wire[255:0] td,trd;wire[31:0] tm;
 dual_t_time_dma #(.MODE(MODE),.S0(S0),.I0(I0),.S1(S1),.I1(I1),.S2(S2),.I2(I2)) ttime(
  mem_clk,resetn,t_start,t_start_ready,t_drain,t_in_valid,t_in_ready,t_in_data,
  t_out_valid,t_out_ready,t_out_data,t_out_last,t_settled,t_result,t_done,t_busy,t_fault,
  tv,tr,tw,ta,td,tm,trv,trr,trd);
 wire sv,sr,sw,srv,srr;wire[20:0] sa;wire[255:0] sd,srd;wire[31:0] sm;
 dual_s_frame_dma sframe(mem_clk,resetn,s_byte_valid,s_byte_ready,s_byte_data,
  s_out_valid,s_out_ready,s_out_data,s_cw_last,s_super_last,
  sv,sr,sw,sa,sd,sm,srv,srr,srd,s_pending_packets,s_ownership,s_fault);
 wire bv,br,bw,brv,brr;wire[20:0] ba;wire[255:0] bd,brd;wire[31:0] bm;
 // T has priority over IO to bound its serial symbol processing latency.
 // The T exchange retains old bytes itself; a direct response avoids another
 // register hop. IO must consume its response or backpressure the shared bus.
 dual_burst_arbiter #(.PRIORITY_SECOND(1),.DIRECT_RESPONSE(1)) tio(mem_clk,resetn,{tv,other_valid&&!bad_io},{tr,io_ready},
  {tw,other_write},{ta,other_address},{td,other_data},
  {trv,other_rsp_valid},{trr,other_rsp_ready},{trd,other_rsp_data},
  bv,br,bw,ba,bd,brv,brr,brd,{tm,other_dqm},bm);
 wire v,r,w,rv,rr;wire[20:0] a;wire[255:0] data,rd;wire[31:0] mask;
 dual_burst_arbiter #(.PRIORITY_SECOND(1),.DIRECT_RESPONSE(1)) background(mem_clk,resetn,
  {sv,bv},{sr,br},{sw,bw},{sa,ba},{sd,bd},{srv,brv},{srr,brr},{srd,brd},
  v,r,w,a,data,rv,rr,rd,{sm,bm},mask);
 dual_fft_stream_memory #(.LOGN(MODE+10),.INIT_CYCLES(INIT_CYCLES)) memory(
  core_clk,mem_clk,resetn,in_valid,in_ready,in_data,in_last,out_valid,out_ready,out_data,out_last,
  v,r,w,a,data,mask,rv,rr,rd,initialized,core_memory_fault,ownership,background_level,
  sd_cmd,sd_bank,sd_address,sd_cke,sd_dqm,dq_oe,dq_out,dq_in);
endmodule
