// FFT/SDRAM plus autonomous conventional-S super-frame DMA.
// T/IO remain explicit background clients; this is not a complete receiver.
module dual_fft_s_memory #(parameter INIT_CYCLES=27000,LINEAR_BANKS=0,SLOT_MAJOR=1)(
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
 input wire s_byte_valid,output wire s_byte_ready,input wire[7:0] s_byte_data,
 output wire s_out_valid,input wire s_out_ready,output wire[7:0] s_out_data,
 output wire s_cw_last,s_super_last,s_fault,output wire[1:0] s_pending_packets,
 output wire[3:0] s_ownership);
 wire sv,sr,sw,srv,srr;wire[20:0] sa;wire[255:0] sd,srd;wire[31:0] sm;
 dual_s_frame_dma #(.LINEAR_BANKS(LINEAR_BANKS),.SLOT_MAJOR(SLOT_MAJOR)) sframe(mem_clk,resetn,s_byte_valid,s_byte_ready,s_byte_data,
  s_out_valid,s_out_ready,s_out_data,s_cw_last,s_super_last,
  sv,sr,sw,sa,sd,sm,srv,srr,srd,s_pending_packets,s_ownership,s_fault);
 dual_fft_memory_clients #(.INIT_CYCLES(INIT_CYCLES)) memory(
  core_clk,mem_clk,resetn,start,mode_log,input_base,middle_base,output_base,
  busy,done,fft_fault,overflow,other_valid,other_ready,other_write,other_address,other_data,
  other_rsp_valid,other_rsp_ready,other_rsp_data,initialized,memory_fault,
  sd_cmd,sd_bank,sd_address,sd_cke,sd_dqm,dq_oe,dq_out,dq_in,other_dqm,background_level,
  sv,sr,sw,sa,sd,sm,srv,srr,srd);
endmodule
