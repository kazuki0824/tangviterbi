// Integration boundary: FFT at core_clk, SDRAM and second client at mem_clk.
// External producer must commit the input frame before start, and reserve all
// three frame regions until done. No concurrent writes to those regions allowed.
module dual_fft_memory #(parameter INIT_CYCLES=27000, FFT_BANK_ISOLATION=0, BACKGROUND_FIFO_DEPTH=0)(
 input wire core_clk,mem_clk,resetn,start,input wire[3:0] mode_log,
 input wire[20:0] input_base,middle_base,output_base,
 output wire busy,done,fft_fault,overflow,
 input wire other_valid,output wire other_ready,input wire other_write,
 input wire[20:0] other_address,input wire[255:0] other_data,
 output wire other_rsp_valid,input wire other_rsp_ready,output wire[255:0] other_rsp_data,
 output wire initialized,memory_fault,output wire[2:0] sd_cmd,
 output wire[1:0] sd_bank,output wire[10:0] sd_address,
 output wire sd_cke,output wire[3:0] sd_dqm,output wire dq_oe,
 output wire[31:0] dq_out,input wire[31:0] dq_in, input wire[31:0] other_dqm,output wire[15:0] background_level);
 // Optional fixed bank partition: FFT uses bank 0, background clients must
 // use banks 1..3. FFT frame pointers then address a logical 2 MiB space.
 // The remap is wiring, not division; clients supply physical background addresses.
 wire bank_bad=FFT_BANK_ISOLATION &&
  (({1'b0,input_base}+(22'd1<<mode_log)>22'd524288) ||
   ({1'b0,middle_base}+(22'd1<<mode_log)>22'd524288) ||
   ({1'b0,output_base}+(22'd1<<mode_log)>22'd524288));
 reg bank_fault;wire core_fault;
 always @(posedge core_clk)begin
  if(!resetn)bank_fault<=0;
  else if(start&&!busy)bank_fault<=bank_bad;
 end
 assign fft_fault=core_fault|bank_fault;
 wire av,ar,aw,arv,arr;wire[20:0] aa;wire[255:0] ad,ard;
 wire[31:0] bmask;wire bv,br,bw,brv,brr;wire[20:0] ba;wire[255:0] bd,brd;
 dual_fft_dma fft(core_clk,resetn,start&&!bank_bad,mode_log,input_base,middle_base,output_base,
  busy,done,core_fault,overflow,av,ar,aw,aa,ad,arv,arr,ard);
 dual_burst_cdc bridge(core_clk,mem_clk,resetn,av,ar,aw,aa,ad,arv,arr,ard,bv,br,bw,ba,bd,brv,brr,brd,32'd0,bmask);
 wire qv,qr,qw;wire[20:0] qa;wire[255:0] qd;wire[31:0] qm;
 generate if(BACKGROUND_FIFO_DEPTH>0)begin:queue
  dual_burst_fifo #(.DEPTH(BACKGROUND_FIFO_DEPTH)) fifo(mem_clk,resetn,
   other_valid,other_ready,other_write,other_address,other_data,other_dqm,
   qv,qr,qw,qa,qd,qm,background_level);
 end else begin:no_queue
  assign qv=other_valid;assign other_ready=qr;assign qw=other_write;
  assign qa=other_address;assign qd=other_data;assign qm=other_dqm;assign background_level=0;
 end endgenerate
 wire[20:0] fft_address=FFT_BANK_ISOLATION?{ba[18:8],2'b00,ba[7:0]}:ba;
 wire[31:0] mask;wire mv,mr,mw,rv,rr;wire[20:0] ma;wire[255:0] md,rd;
 dual_burst_arbiter arb(mem_clk,resetn,{qv,bv},{qr,br},
  {qw,bw},{qa,fft_address},{qd,bd},
  {other_rsp_valid,brv},{other_rsp_ready,brr},{other_rsp_data,brd},mv,mr,mw,ma,md,rv,rr,rd,{qm,bmask},mask);
 dual_sdram_burst #(.INIT_CYCLES(INIT_CYCLES)) memory(mem_clk,resetn,mv,mr,mw,ma,md,mask,
  rv,rr,rd,initialized,memory_fault,sd_cmd,sd_bank,sd_address,sd_cke,sd_dqm,dq_oe,dq_out,dq_in);
endmodule
