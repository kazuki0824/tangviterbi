// Connected memory clients: bounded T/IO request FIFO, urgent S CW port.
// S priority is local to the background port; FFT/background remain round-robin.
// The S producer must hold its current complete CW until all bursts are accepted.
// Physical bank 0 belongs to FFT; background addresses must use banks 1..3.
module dual_fft_memory_clients #(parameter INIT_CYCLES=27000)(
 input wire core_clk,mem_clk,resetn,start,input wire[3:0] mode_log,
 input wire[20:0] input_base,middle_base,output_base,
 output wire busy,done,fft_fault,overflow,
 input wire other_valid,output wire other_ready,input wire other_write,
 input wire[20:0] other_address,input wire[255:0] other_data,
 output wire other_rsp_valid,input wire other_rsp_ready,output wire[255:0] other_rsp_data,
 output wire initialized,memory_fault,output wire[2:0] sd_cmd,
 output wire[1:0] sd_bank,output wire[10:0] sd_address,
 output wire sd_cke,output wire[3:0] sd_dqm,output wire dq_oe,
 output wire[31:0] dq_out,input wire[31:0] dq_in,
 input wire[31:0] other_dqm,output wire[15:0] background_level,
 input wire s_valid,output wire s_ready,input wire s_write,
 input wire[20:0] s_address,input wire[255:0] s_data,input wire[31:0] s_dqm,
 output wire s_rsp_valid,input wire s_rsp_ready,output wire[255:0] s_rsp_data);
 wire bad_t=other_valid&&other_address[9:8]==0;
 wire bad_s=s_valid&&s_address[9:8]==0;
 reg partition_fault;wire core_memory_fault,t_ready,s_accept;
 always @(posedge mem_clk)begin
  if(!resetn)partition_fault<=0;
  else if(bad_t||bad_s)partition_fault<=1;
 end
 assign memory_fault=core_memory_fault|partition_fault;
 assign other_ready=t_ready&&!bad_t;assign s_ready=s_accept&&!bad_s;
 wire tv,tr,tw;wire[20:0] ta;wire[255:0] td;wire[31:0] tm;
 dual_burst_fifo #(.DEPTH(256)) tq(mem_clk,resetn,
  other_valid&&!bad_t,t_ready,other_write,other_address,other_data,other_dqm,
  tv,tr,tw,ta,td,tm,background_level);
 wire v,r,w,rv,rr;wire[20:0] a;wire[255:0] d,rd;wire[31:0] mask;
 dual_burst_arbiter #(.PRIORITY_SECOND(1),.DIRECT_RESPONSE(1)) background(mem_clk,resetn,
  {s_valid&&!bad_s,tv},{s_accept,tr},{s_write,tw},{s_address,ta},{s_data,td},
  {s_rsp_valid,other_rsp_valid},{s_rsp_ready,other_rsp_ready},{s_rsp_data,other_rsp_data},
  v,r,w,a,d,rv,rr,rd,{s_dqm,tm},mask);
 dual_fft_memory #(.INIT_CYCLES(INIT_CYCLES),.FFT_BANK_ISOLATION(1)) memory(
  core_clk,mem_clk,resetn,start,mode_log,input_base,middle_base,output_base,
  busy,done,fft_fault,overflow,v,r,w,a,d,rv,rr,rd,
  initialized,core_memory_fault,sd_cmd,sd_bank,sd_address,sd_cke,sd_dqm,dq_oe,dq_out,dq_in,mask,);
endmodule
