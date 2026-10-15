// Actual window capture -> FFT -> bin stream through SDRAM. Framing/sync,
// equalization and demapping are upstream/downstream, not supplied here.
module dual_fft_stream_memory #(parameter LOGN=11,INIT_CYCLES=27000)(
 input wire core_clk,mem_clk,resetn,
 input wire in_valid,output wire in_ready,input wire[31:0] in_data,input wire in_last,
 output wire out_valid,input wire out_ready,output wire[31:0] out_data,output wire out_last,
 input wire other_valid,output wire other_ready,input wire other_write,input wire[20:0] other_address,
 input wire[255:0] other_data,input wire[31:0] other_dqm,
 output wire other_rsp_valid,input wire other_rsp_ready,output wire[255:0] other_rsp_data,
 output wire initialized,fault,output wire[8:0] ownership,output wire[15:0] queued_bursts,
 output wire[2:0] sd_cmd,output wire[1:0] sd_bank,output wire[10:0] sd_address,
 output wire sd_cke,output wire[3:0] sd_dqm,output wire dq_oe,output wire[31:0] dq_out,input wire[31:0] dq_in);
 wire[1:0] js;wire jv,jr,jdone,jfault,io_fault,input_ready_raw;
 assign in_ready=initialized&&input_ready_raw;
 wire iv,ir,iw,irv,irr;wire[20:0] ia;wire[255:0] id,ird;wire[31:0] im;
 dual_frame_io #(.LOGN(LOGN)) io(mem_clk,resetn,in_valid&&initialized,input_ready_raw,in_data,in_last,
  out_valid,out_ready,out_data,out_last,jv,jr,js,jdone,jfault,iv,ir,iw,ia,id,im,irv,irr,ird,ownership,queued_bursts,io_fault);
 // Single outstanding bundled-data mailbox. Slot stays fixed until completion.
 // Both clocks reset only at a stopped epoch. Physical CDC constraints still required.
 reg command,return_seen;reg[1:0] held_slot;reg[1:0] return_sync;
 reg seen,running,completion,completed_fault;reg[1:0] command_sync;reg launch;reg[1:0] core_slot;
 wire busy,done,fft_fault,overflow,memory_fault;
 assign jr=command==return_sync[1];assign jdone=return_sync[1]!=return_seen;
 assign jfault=completed_fault;
 always @(posedge mem_clk)begin
  if(!resetn)begin command<=0;held_slot<=0;return_seen<=0;return_sync<=0;end
  else begin
   return_sync<={return_sync[0],completion};
   if(jv&&jr)begin held_slot<=js;command<=!command;end
   if(jdone)return_seen<=return_sync[1];
  end
 end
 always @(posedge core_clk)begin
  if(!resetn)begin seen<=0;running<=0;completion<=0;completed_fault<=0;command_sync<=0;launch<=0;core_slot<=0;end
  else begin
   command_sync<={command_sync[0],command};launch<=0;
   if(command_sync[1]!=seen&&!running)begin core_slot<=held_slot;launch<=1;seen<=command_sync[1];running<=1;end
   if(running&&!launch&&(done||fft_fault))begin completion<=seen;completed_fault<=fft_fault||overflow;running<=0;end
  end
 end
 wire v,r,w,rv,rr;wire[20:0] a;wire[255:0] data,rd;wire[31:0] mask;
 wire bad=other_valid&&other_address[9:8]==0;reg partition_fault;
 always @(posedge mem_clk)if(!resetn)partition_fault<=0;else if(bad)partition_fault<=1;
 wire other_ready_raw;assign other_ready=other_ready_raw&&!bad;
 dual_burst_arbiter #(.DIRECT_RESPONSE(1)) arb(mem_clk,resetn,{other_valid&&!bad,iv},{other_ready_raw,ir},
  {other_write,iw},{other_address,ia},{other_data,id},{other_rsp_valid,irv},{other_rsp_ready,irr},{other_rsp_data,ird},
  v,r,w,a,data,rv,rr,rd,{other_dqm,im},mask);
 dual_fft_memory #(.INIT_CYCLES(INIT_CYCLES),.FFT_BANK_ISOLATION(1),.DIRECT_RESPONSE(1)) memory(core_clk,mem_clk,resetn,launch,4'(LOGN),
  {6'd0,core_slot,13'd0},21'd24576,21'd32768+{6'd0,core_slot,13'd0},
  busy,done,fft_fault,overflow,v,r,w,a,data,rv,rr,rd,initialized,memory_fault,
  sd_cmd,sd_bank,sd_address,sd_cke,sd_dqm,dq_oe,dq_out,dq_in,mask,);
 assign fault=io_fault||partition_fault||memory_fault;
endmodule
