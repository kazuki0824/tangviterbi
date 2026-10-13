// Core-owned identity/epoch/IQ-ready CSRs, mode-0 SPI3 Quad.
// D71C: epoch=0, nonce32, length=32; D71D: epoch16,45504f43,length=0.
// D71E: epoch16,0/1,length=0. Reset requires all previous owners idle.
// Query snapshot is request/ACK bundled data, held until the next query.
// locked denotes RF/front-end permission to start sampling, not demodulator
// lock that could only be acquired after sampling has already started.
// Prefetch words instead of duplicating the full snapshot in the SPI domain.
module s3_spi_control #(parameter [7:0] IMAGE_ID=0,parameter [31:0] BUILD_TAG=1)(
 input wire clk,resetn,input wire streams_idle,locked,receiver_fault,
 input wire iq_ready,input wire[31:0]iq_offset,
 output reg[15:0]epoch,output reg epoch_reset,stream_enable,control_fault,
 input wire spi_clk,cs_n,input wire[3:0]dq_in,output reg[3:0]dq_out,output wire dq_oe
);
 localparam[31:0]MAGIC=32'h31534353,CHECK=32'h96c39a5f;
 reg query_toggle,command_toggle;reg[15:0]command_epoch,command_kind;reg[31:0]command_arg;
 (* async_reg="true" *) reg query1,query2,cmd1,cmd2;
 reg query_seen,command_seen,query_ack;reg[31:0]snapshot0,snapshot1,snapshot2,snapshot3,snapshot_check;
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin
   query1<=0;query2<=0;cmd1<=0;cmd2<=0;query_seen<=0;command_seen<=0;query_ack<=0;
   snapshot0<=0;snapshot1<=0;snapshot2<=0;snapshot3<=0;snapshot_check<=0;
   epoch<=0;epoch_reset<=0;stream_enable<=0;control_fault<=0;
  end else begin
   query1<=query_toggle;query2<=query1;cmd1<=command_toggle;cmd2<=cmd1;epoch_reset<=0;
   if(receiver_fault)stream_enable<=0;
   if(cmd2!=command_seen)begin
    command_seen<=cmd2;
    if(command_kind==16'hd71d)begin
     if(!streams_idle||stream_enable||command_epoch==0||command_epoch<epoch||command_arg!=32'h45504f43)control_fault<=1;
     else if(command_epoch!=epoch)begin epoch<=command_epoch;epoch_reset<=1;end
    end else if(command_kind==16'hd71e)begin
     if(command_epoch!=epoch||epoch==0||command_arg>1||
      (command_arg==1&&(!locked||receiver_fault||control_fault)))begin control_fault<=1;stream_enable<=0;end
     else stream_enable<=command_arg[0];
    end
   end
   if(query2!=query_seen)begin
    query_seen<=query2;snapshot0<={8'd1,IMAGE_ID,epoch};snapshot1<=iq_offset;
    snapshot2<={27'd0,stream_enable,control_fault,streams_idle,receiver_fault,iq_ready};
    snapshot3<=BUILD_TAG;query_ack<=query2;
    snapshot_check<=MAGIC^{8'd1,IMAGE_ID,epoch}^iq_offset^
     {27'd0,stream_enable,control_fault,streams_idle,receiver_fault,iq_ready}^BUILD_TAG^CHECK;
   end
  end
 end
 (* async_reg="true" *) reg ack1,ack2;
 reg[6:0]beat;reg[79:0]header;reg selected,oe,query_started;
 wire frame_reset=cs_n||!resetn;wire[79:0]next_header={header[75:0],dq_in};
 wire[31:0]nonce=header[47:16],checksum=snapshot_check^nonce;
 wire[255:0]reply={32'd0,checksum,snapshot3,nonce,snapshot2,snapshot1,snapshot0,MAGIC};
 wire[6:0]payload_beat=beat-20;
 wire[2:0]next_word=beat<20?0:(payload_beat+1)/8;
 reg[31:0]word;always @(posedge spi_clk)word<=reply>>(32*next_word);
 wire[7:0]octet=word>>(8*((payload_beat/2)%4));
 always @(posedge spi_clk or negedge resetn)begin
  if(!resetn)begin
   query_toggle<=0;command_toggle<=0;command_epoch<=0;command_arg<=0;command_kind<=0;ack1<=0;ack2<=0;
  end else begin
   ack1<=query_ack;ack2<=ack1;
   if(!cs_n&&beat==3&&next_header[15:0]==16'hd71c&&ack2==query_toggle)query_toggle<=~query_toggle;
   if(!cs_n&&beat==19&&next_header[15:0]==0&&(next_header[79:64]==16'hd71d||next_header[79:64]==16'hd71e))begin
    command_kind<=next_header[79:64];command_epoch<=next_header[63:48];command_arg<=next_header[47:16];command_toggle<=~command_toggle;
   end
  end
 end
 always @(posedge spi_clk or posedge frame_reset)begin
  if(frame_reset)begin beat<=0;header<=0;selected<=0;query_started<=0;end
  else begin
   if(beat!=127)beat<=beat+1'b1;
   if(beat<20)header<=next_header;
   if(beat==3&&next_header[15:0]==16'hd71c&&ack2==query_toggle)query_started<=1;
   if(beat==19)selected<=next_header[79:64]==16'hd71c&&next_header[63:48]==0&&next_header[15:0]==32&&query_started&&ack2==query_toggle;
  end
 end
 always @(negedge spi_clk or posedge frame_reset)begin
  if(frame_reset)begin dq_out<=0;oe<=0;end
  else begin oe<=selected&&beat>=20&&beat<84;dq_out<=payload_beat[0]?octet[3:0]:octet[7:4];end
 end
 assign dq_oe=oe&&!cs_n;
endmodule
