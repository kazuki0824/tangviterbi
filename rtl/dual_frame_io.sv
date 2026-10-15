// Aligned FFT-window capture and natural-bin output; not RF synchronization.
// Three slots own input AND output until the last output word is consumed.
// Logical bank-0 words: inputs 0/8192/16384, middle 24576, outputs 32768/40960/49152.
// Ingress is full-precision Q15 complex, one 32-bit word; upstream honors ready.
module dual_frame_io #(parameter LOGN=11,QUEUE_DEPTH=16)(
 input wire clk,resetn,
 input wire in_valid,output wire in_ready,input wire[31:0] in_data,input wire in_last,
 output wire out_valid,input wire out_ready,output wire[31:0] out_data,output wire out_last,
 output reg job_valid,input wire job_ready,output reg[1:0] job_slot,input wire job_done,input wire job_fault,
 output wire req_valid,input wire req_ready,output wire req_write,output wire[20:0] req_address,
 output wire[255:0] req_data,output wire[31:0] req_dqm,
 input wire rsp_valid,output wire rsp_ready,input wire[255:0] rsp_data,
 output wire[8:0] ownership,output wire[15:0] queued_bursts,output reg fault);
 localparam N=1<<LOGN,FREE=0,CAPTURE=1,READY=2,FFT=3,OUTPUT=4;
 initial if(LOGN<11||LOGN>13||QUEUE_DEPTH<2||(QUEUE_DEPTH&(QUEUE_DEPTH-1))!=0)$fatal(1,"invalid FFT mode");
 reg[2:0] owner[0:2];reg[1:0] capture_next,fft_next,output_next;
 reg[13:0] captured;reg[10:0] acknowledged[0:2];
 reg[255:0] pack_data;reg[3:0] packed_words;
 reg[20:0] pack_address;reg active_job;
 wire enqueue=packed_words==8;
 wire fq_ready,fq_valid,fq_take;wire[20:0] fq_address;wire[255:0] fq_data;
 wire fq_write;wire[31:0] fq_mask;
 assign in_ready=!fault && !enqueue && (owner[capture_next]==FREE||owner[capture_next]==CAPTURE);
 wire take=in_valid&&in_ready;
 dual_burst_fifo #(.DEPTH(QUEUE_DEPTH)) queue(clk,resetn,enqueue,fq_ready,1'b1,pack_address,pack_data,32'd0,
  fq_valid,fq_take,fq_write,fq_address,fq_data,fq_mask,queued_bursts);
 // Read/response stream retains the complete burst throughout downstream stalls.
 localparam R_IDLE=0,R_REQ=1,R_WAIT=2,R_DRAIN=3;
 reg[1:0] read_state;reg[13:0] emitted;reg[2:0] beat;reg[255:0] read_data;
 wire read_valid=read_state==R_REQ;wire read_ready,read_rsp_valid;
 wire[255:0] read_rsp_data;wire write_rsp_valid;wire[255:0] unused_write_data;
 reg[1:0] write_slot;wire[20:0] read_address=21'd32768+{6'd0,output_next,13'd0}+{emitted[13:3],3'b000};
 wire[20:0] logical_address;
 dual_burst_arbiter #(.DIRECT_RESPONSE(1)) arb(clk,resetn,{read_valid,fq_valid},{read_ready,fq_take},
  {1'b0,fq_write},{read_address,fq_address},{256'd0,fq_data},
  {read_rsp_valid,write_rsp_valid},{read_state==R_WAIT,1'b1},{read_rsp_data,unused_write_data},
  req_valid,req_ready,req_write,logical_address,req_data,rsp_valid,rsp_ready,rsp_data,{32'd0,fq_mask},req_dqm);
 assign req_address={logical_address[18:8],2'b00,logical_address[7:0]};
 assign out_valid=read_state==R_DRAIN&&!fault;
 assign out_data=read_data[beat*32+:32];assign out_last=out_valid&&emitted==N-1;
 assign ownership={owner[2],owner[1],owner[0]};
 always @(posedge clk)begin
  if(!resetn)begin
   owner[0]<=FREE;owner[1]<=FREE;owner[2]<=FREE;capture_next<=0;fft_next<=0;output_next<=0;
   captured<=0;acknowledged[0]<=0;acknowledged[1]<=0;acknowledged[2]<=0;packed_words<=0;pack_data<=0;pack_address<=0;
   job_valid<=0;job_slot<=0;active_job<=0;fault<=0;write_slot<=0;
   read_state<=R_IDLE;emitted<=0;beat<=0;read_data<=0;
  end else begin
   if(enqueue&&fq_ready)packed_words<=0;
   if(take)begin
    if(in_last!=(captured==N-1))fault<=1;
    if(captured==0)owner[capture_next]<=CAPTURE;
    if(packed_words==0)pack_address<={6'd0,capture_next,13'd0}+captured;
    pack_data[packed_words*32+:32]<=in_data;packed_words<=packed_words+1'b1;
    if(captured==N-1)begin captured<=0;capture_next<=capture_next==2?0:capture_next+1'b1;end
    else captured<=captured+1'b1;
   end
   // Last ACK commits a frame, never the last input word or queued request.
   if(fq_valid&&fq_take)write_slot<=fq_address[14:13];
   if(write_rsp_valid)begin
    if(owner[write_slot]!=CAPTURE)fault<=1;
    if(acknowledged[write_slot]==N/8-1)begin
     acknowledged[write_slot]<=0;owner[write_slot]<=READY;
    end else acknowledged[write_slot]<=acknowledged[write_slot]+1'b1;
   end
   if(!active_job&&!job_valid&&owner[fft_next]==READY&&!fault)begin job_valid<=1;job_slot<=fft_next;end
   if(job_valid&&job_ready)begin
    job_valid<=0;active_job<=1;owner[job_slot]<=FFT;fft_next<=fft_next==2?0:fft_next+1'b1;
   end
   if(job_done)begin
    if(!active_job||owner[job_slot]!=FFT)fault<=1;
    owner[job_slot]<=OUTPUT;active_job<=0;
    if(job_fault)fault<=1;
   end
   case(read_state)
    R_IDLE:if(owner[output_next]==OUTPUT&&!fault)begin emitted<=0;beat<=0;read_state<=R_REQ;end
    R_REQ:if(read_ready)read_state<=R_WAIT;
    R_WAIT:if(read_rsp_valid)begin read_data<=read_rsp_data;beat<=0;read_state<=R_DRAIN;end
    R_DRAIN:if(out_valid&&out_ready)begin
     if(emitted==N-1)begin owner[output_next]<=FREE;output_next<=output_next==2?0:output_next+1'b1;read_state<=R_IDLE;end
     else if(beat==7)begin emitted<=emitted+1'b1;read_state<=R_REQ;end
     else begin emitted<=emitted+1'b1;beat<=beat+1'b1;end
    end
   endcase
  end
 end
endmodule
