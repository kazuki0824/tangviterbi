// Experimental joint service/reader + S retention + ingress selector + T3/S K7.
// Common clock and reset; external BG producers retain requests until ready.
// Actual FFT arithmetic connected. No RF endpoint, equalizer, interleaver, RS/TS or PHY.
module shared_receiver_fft_metadata(
 input wire clk,resetn,
 input wire[1:0]fft_mode,input wire fft_in_valid,output wire fft_in_ready,
 input wire[31:0]fft_in_data,output wire fft_out_valid,input wire fft_out_ready,
 output wire[31:0]fft_out_data,output wire[12:0]fft_out_bin,
 output wire fft_frame_end,output wire fft_overflow,
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

 wire external_ready,read_enable,write_enable;
 wire[11:0]read_address,write_address;wire[31:0]read_data,write_data;
 // Only Mode 3 uses the external first stage. Mode is stable during an epoch.
 wire sample_accept=fft_mode==2 && fft_in_valid && fft_in_ready;
 shared_sdf_fft fft(.clk(clk),.resetn(resetn),.mode(fft_mode),
 .in_valid(fft_in_valid),.in_ready(fft_in_ready),.in_data(fft_in_data),
 .out_valid(fft_out_valid),.out_ready(fft_out_ready),.out_data(fft_out_data),
 .out_bin(fft_out_bin),.out_frame_end(fft_frame_end),.overflow(fft_overflow),
 .external_ready(external_ready),.external_read_enable(read_enable),
 .external_read_addr(read_address),.external_read_data(read_data),
 .external_write_enable(write_enable),.external_write_addr(write_address),
 .external_write_data(write_data));
 wire tv,tr,mfault;wire[1:0]tc;wire[7:0]td;
 t_soft_sdram_service_metadata memory(
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
 shared_tc8_k7_depuncture_isolated_stream k7(
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
