// Experimental joint service/reader + S retention + ingress selector + T3/S K7.
// Common clock and reset; external BG producers retain requests until ready.
// No SDRAM PHY, FFT arithmetic, RF endpoint, interleaver or RS/TS included.
module shared_receiver_service_buffered(
 input wire clk,resetn,sample_accept,output wire external_ready,
 input wire read_enable,input wire[11:0]read_address,output wire[31:0]read_data,
 input wire write_enable,input wire[11:0]write_address,input wire[31:0]write_data,
 input wire[3:0]bg_valid,output wire[3:0]bg_ready,input wire[3:0]bg_write,
 input wire[83:0]bg_address,input wire[1023:0]bg_data,input wire[127:0]bg_dqm,
 output wire[3:0]bg_rsp_valid,input wire[3:0]bg_rsp_ready,output wire[255:0]bg_rsp_data,
 input wire commit_valid,output wire commit_ready,
 input wire[62:0]commit_addresses,input wire[47:0]commit_lengths,
 output wire[1:0]bank_live,output wire reuse_blocked,
 input wire[11:0]rates,input wire s_tc8_mode,
 input wire s_valid,output wire s_ready,input wire[31:0]s_data,
 output wire out_valid,out_bit,out_b1,out_tc8,output wire[1:0]out_context,
 output wire initialized,fault,output wire[2:0]sd_cmd,output wire[1:0]sd_bank,
 output wire[10:0]sd_address,output wire sd_cke,output wire[3:0]sd_dqm,
 output wire dq_oe,output wire[31:0]dq_out,input wire[31:0]dq_in
);

 wire tv,tr,mfault;wire[1:0]tc;wire[7:0]td;
 t_soft_sdram_service_buffered memory(
 .clk(clk),.resetn(resetn),.sample_accept(sample_accept),.external_ready(external_ready),
 .read_enable(read_enable),.read_address(read_address),.read_data(read_data),
 .write_enable(write_enable),.write_address(write_address),.write_data(write_data),
 .bg_valid(bg_valid),.bg_ready(bg_ready),.bg_write(bg_write),.bg_address(bg_address),
 .bg_data(bg_data),.bg_dqm(bg_dqm),.bg_rsp_valid(bg_rsp_valid),.bg_rsp_ready(bg_rsp_ready),.bg_rsp_data(bg_rsp_data),
 .commit_valid(commit_valid),.commit_ready(commit_ready),.commit_addresses(commit_addresses),.commit_lengths(commit_lengths),
 .bank_live(bank_live),.reuse_blocked(reuse_blocked),.soft_valid(tv),.soft_ready(tr),.soft_context(tc),.soft_data(td),
 .initialized(initialized),.fault(mfault),.sd_cmd(sd_cmd),.sd_bank(sd_bank),.sd_address(sd_address),.sd_cke(sd_cke),.sd_dqm(sd_dqm),
 .dq_oe(dq_oe),.dq_out(dq_out),.dq_in(dq_in));
 wire sv,sr,space;wire[31:0]sd;
 wire[3:0]kf;wire kr,qi;
 reg[1:0]phase;reg locked,locked_s;
 wire choose_s=locked ? locked_s : sv && (phase!=2 || !tv);
 wire binary_s=!s_tc8_mode && choose_s;
 wire iv=binary_s ? sv : tv;
 assign tr=!binary_s && kr;
 assign sr=s_tc8_mode ? qi : choose_s && kr;
 assign s_ready=space && !fault;
 s_input_fifo s_fifo(clk,resetn,s_valid && !fault,space,s_data,sv,sr,sd);
 shared_tc8_k7_depuncture_stream k7(
 .clk(clk),.resetn(resetn),.rates(rates),.s_tc8_mode(s_tc8_mode),
 .iq_valid(s_tc8_mode && sv),.iq_ready(qi),.in_i(sd[31:16]),.in_q(sd[15:0]),
 .in_valid(iv),.in_ready(kr),.in_context(binary_s ? 2'd3 : tc),.in_soft(binary_s ? sd[7:0] : td),
 .out_valid(out_valid),.out_bit(out_bit),.out_context(out_context),.out_b1(out_b1),.out_tc8(out_tc8),.fault(kf));
 assign fault=mfault || |kf;
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin phase<=0;locked<=0;locked_s<=0;end
  else if(iv)begin
   if(kr)begin locked<=0;phase<=phase==2 ? 0 : phase+1'b1;end
   else begin locked<=1;locked_s<=choose_s;end
  end
 end
endmodule
