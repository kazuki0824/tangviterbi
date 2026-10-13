// Independent clock-pair protocol oracle, NOT a vendor analog DDR model.
// Decodes CA bytes, enforces fixed-latency wrapped bursts and recovery, and
// returns independently delayed die words. No references to DUT internals.
module w955_pair_model #(
 parameter integer WORDS=65536,
 parameter integer DIE0_DELAY=1,DIE1_DELAY=3
)(
 input wire clk,resetn,
 input wire ram_reset_n,cs_n,ck_enable,dq_drive,rwds_drive,
 input wire [15:0] first_byte,second_byte,
 input wire suppress_reads,bad_configuration,bad_identity,
 output reg [1:0] rx_valid,
 output reg [15:0] rx0,rx1,
 output integer writes,reads,bursts,max_cs_cycles
);
 reg [31:0] memory[0:WORDS-1];
 reg [47:0] ca;reg [15:0] cr0;
 reg previous_cs,previous_reset;
 integer beat,high_cycles,low_cycles,write_words,base,now,i,j,index;
 reg reading,register_space;reg [15:0] value;
 initial begin rx_valid=0;rx0=0;rx1=0;writes=0;reads=0;bursts=0;max_cs_cycles=0;end
 // Returned words cross a modeled PHY boundary; delays are measured in core
 // clocks and may differ between dies. Electrical phase is tested separately.
 always @(negedge clk)begin
  rx_valid=0;
  if(resetn&&ram_reset_n&&!cs_n&&reading&&beat>=3&&!suppress_reads)begin
   for(j=0;j<2;j=j+1)begin
    index=beat-11-(j==0?DIE0_DELAY:DIE1_DELAY);
    if(index>=0&&index<(register_space?1:64))begin
     if(register_space)begin
      case(ca)
       48'he00001000000:value=bad_configuration?(cr0^16'h0010):cr0;
       48'he00000000000:value=bad_identity?16'h005e:16'h0c5f;
       48'he00000000001:value=16'h000f;
       default:$fatal(1,"unsupported register read %h",ca);
      endcase
     end else value=j==0?memory[(base&~63)|((base+index)&63)][15:0]:memory[(base&~63)|((base+index)&63)][31:16];
     rx_valid[j]=1;if(j==0)rx0=value;else rx1=value;
    end
   end
  end
 end
 always @(posedge clk)begin
  if(!resetn||!ram_reset_n)begin
   previous_cs=1;previous_reset=0;beat=0;high_cycles=1000;low_cycles=0;
   ca=0;cr0=16'h8f1f;reading=0;register_space=0;write_words=0;
  end else begin
   if(cs_n)begin
    if(!previous_cs)begin
     if(!reading && !register_space && write_words!=64)$fatal(1,"short/long write %0d",write_words);
     if(low_cycles>max_cs_cycles)max_cs_cycles=low_cycles;
     if(low_cycles>=396)$fatal(1,"tCSM");
     low_cycles=0;high_cycles=0;
    end
    high_cycles=high_cycles+1;beat=0;ca=0;reading=0;register_space=0;write_words=0;
    if(ck_enable)$fatal(1,"clock enabled while CS high");
   end else begin
    if(previous_cs)begin
     if(high_cycles<4)$fatal(1,"tRWR %0d",high_cycles);
     if(ck_enable)$fatal(1,"missing CS setup");
     bursts=bursts+1;
    end
    low_cycles=low_cycles+1;
    if(ck_enable)begin
     if(beat<3)begin
      if(!dq_drive||rwds_drive||first_byte[7:0]!==first_byte[15:8]||second_byte[7:0]!==second_byte[15:8])$fatal(1,"CA bus");
      ca={ca[31:0],first_byte[7:0],second_byte[7:0]};
      if(beat==2)begin
       reading=ca[47];register_space=ca[46];base={ca[33:16],ca[2:0]};
       if(ca[44:34]!=0||ca[15:3]!=0)$fatal(1,"CA reserved bits");
       if(ca[45]!==register_space)$fatal(1,"wrapped/register CA45");
       if(!register_space&&(base%64!=0||base>=WORDS))$fatal(1,"address %d",base);
      end
     end else if(register_space&&!reading)begin
      if(beat!=3||ca!=48'h600001000000||!dq_drive||rwds_drive)$fatal(1,"CR0 write timing");
      if(first_byte[7:0]!==first_byte[15:8]||second_byte[7:0]!==second_byte[15:8])$fatal(1,"die config mismatch");
      cr0={first_byte[7:0],second_byte[7:0]};if(cr0!==16'h8ffc)$fatal(1,"CR0");
     end else if(!reading && beat>=10)begin
      if(!dq_drive||!rwds_drive||beat>=74)$fatal(1,"write data timing %d",beat);
      memory[base+beat-10]={first_byte[15:8],second_byte[15:8],first_byte[7:0],second_byte[7:0]};
      write_words=write_words+1;writes=writes+1;
     end else begin
      if(dq_drive)$fatal(1,"host drives DQ during read/latency");
      if(reading&&rwds_drive)$fatal(1,"host drives read strobe");
     end
     beat=beat+1;
    end
   end
   previous_cs=cs_n;previous_reset=1;
  end
 end
endmodule
