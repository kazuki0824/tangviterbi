// Integration boundary: FFT at core_clk, SDRAM and second client at mem_clk.
// External producer must commit the input frame before start, and reserve all
// three frame regions until done. No concurrent writes to those regions allowed.
module dual_fft_memory #(parameter INIT_CYCLES=27000)(
 input wire core_clk,mem_clk,resetn,start,input wire[3:0] mode_log,
 input wire[20:0] input_base,middle_base,output_base,
 output wire busy,done,fft_fault,overflow,
 input wire other_valid,output wire other_ready,input wire other_write,
 input wire[20:0] other_address,input wire[255:0] other_data,
 output wire other_rsp_valid,input wire other_rsp_ready,output wire[255:0] other_rsp_data,
 output wire initialized,memory_fault,output wire[2:0] sd_cmd,
 output wire[1:0] sd_bank,output wire[10:0] sd_address,
 output wire sd_cke,output wire[3:0] sd_dqm,output wire dq_oe,
 output wire[31:0] dq_out,input wire[31:0] dq_in);
 wire av,ar,aw,arv,arr;wire[20:0] aa;wire[255:0] ad,ard;
 wire bv,br,bw,brv,brr;wire[20:0] ba;wire[255:0] bd,brd;
 dual_fft_dma fft(core_clk,resetn,start,mode_log,input_base,middle_base,output_base,
  busy,done,fft_fault,overflow,av,ar,aw,aa,ad,arv,arr,ard);
 dual_burst_cdc bridge(core_clk,mem_clk,resetn,av,ar,aw,aa,ad,arv,arr,ard,bv,br,bw,ba,bd,brv,brr,brd);
 wire mv,mr,mw,rv,rr;wire[20:0] ma;wire[255:0] md,rd;
 dual_burst_arbiter arb(mem_clk,resetn,{other_valid,bv},{other_ready,br},
  {other_write,bw},{other_address,ba},{other_data,bd},
  {other_rsp_valid,brv},{other_rsp_ready,brr},{other_rsp_data,brd},mv,mr,mw,ma,md,rv,rr,rd);
 dual_sdram_burst #(.INIT_CYCLES(INIT_CYCLES)) memory(mem_clk,resetn,mv,mr,mw,ma,md,32'd0,
  rv,rr,rd,initialized,memory_fault,sd_cmd,sd_bank,sd_address,sd_cke,sd_dqm,dq_oe,dq_out,dq_in);
endmodule
