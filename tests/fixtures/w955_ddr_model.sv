`timescale 1ns/1ps
// Independent pin-level W955 functional oracle. Both edges of the RAM CK,
// not the FPGA core clock, decode commands and move bytes. Programmable tCKD
// shifts RWDS and DQ together. This does not simulate an analog sampling eye.
module w955_ddr_model #(
 parameter real OUTPUT_DELAY=1.0,
 parameter integer WORDS=2048
)(input wire reset_n,cs_n,ck,ck_n,inout wire [7:0] dq,inout wire rwds);
 reg [15:0] memory[0:WORDS-1];reg[15:0] cr0=16'h8f1f;
 reg[47:0] ca=0;reg[7:0] dout=0,high_byte=0;
 reg dq_oe=0,rwds_oe=0,rwds_value=0;
 integer edge_count=0,base=0,address=0,word_count=0;
 reg reading=0,register_space=0;reg[15:0] value;
 realtime last_end=-10000,start=0;
 assign dq=!cs_n&&dq_oe?dout:8'bz;
 assign rwds=!cs_n&&rwds_oe?rwds_value:1'bz;
 always @(negedge reset_n)begin cr0=16'h8f1f;dq_oe=0;rwds_oe=0;end
 always @(negedge cs_n)begin
  if(reset_n)begin
   if($realtime-last_end<36)$fatal(1,"DDR tRWR");
   if(ck!==0)$fatal(1,"CK must idle low at CS assertion");
  end
  start=$realtime;edge_count=0;word_count=0;ca=0;reading=0;register_space=0;
  dq_oe=0;rwds_oe=1;rwds_value=1;
 end
 always @(posedge cs_n)begin
  if(reset_n&&start>0)begin
   if($realtime-start>=4000)$fatal(1,"DDR tCSM");
   if(ck!==0)$fatal(1,"CK not stopped before CS release");
   if(!reading&&!register_space&&word_count!=64)$fatal(1,"DDR burst word count %d",word_count);
  end
  last_end=$realtime;dq_oe=0;rwds_oe=0;
 end
 always @(posedge ck or negedge ck)begin
  if(reset_n&&cs_n===0)begin
   if(edge_count==0&&$realtime-start<2)$fatal(1,"DDR tCSS");
   if(edge_count<6)begin
    if(^dq===1'bx)$fatal(1,"invalid CA DQ");
    ca={ca[39:0],dq};
    if(edge_count==5)begin
     reading=ca[47];register_space=ca[46];base={ca[33:16],ca[2:0]};
     if(ca[45]!==register_space||ca[44:34]!=0||ca[15:3]!=0)$fatal(1,"DDR CA mapping");
     if(!register_space&&(base%64!=0||base>=WORDS))$fatal(1,"DDR address");
     // Read data has a low RWDS preamble. Writes release RWDS after CA.
     rwds_oe<=#OUTPUT_DELAY reading;rwds_value<=#OUTPUT_DELAY 0;
    end
   end else if(!reading&&register_space)begin
    // The RAM's own tHZ after the last CA edge can exceed half a clock.
    // Check release at the second data edge, not while this model still
    // legally drives RWDS itself. The host PHY always floats register RWDS.
    if(ca!=48'h600001000000||edge_count>7||(edge_count==7&&rwds!==1'bz))$fatal(1,"DDR register timing/RWDS");
    if(edge_count==6)high_byte=dq;
    else begin cr0={high_byte,dq};if(cr0!==16'h8ffc)$fatal(1,"DDR config");end
   end else if(edge_count>=20)begin
    address=(base&~63)|((base+(edge_count-20)/2)&63);
    if(reading)begin
     if(register_space)begin
      case(ca)
       48'he00001000000:value=cr0;
       48'he00000000000:value=16'h0c5f;
       48'he00000000001:value=16'h000f;
       default:$fatal(1,"DDR register address");
      endcase
     end else value=memory[address];
     dq_oe<=#OUTPUT_DELAY 1;dout<=#OUTPUT_DELAY (edge_count%2==0?value[15:8]:value[7:0]);
     rwds_oe<=#OUTPUT_DELAY 1;rwds_value<=#OUTPUT_DELAY (edge_count%2==0);
    end else begin
     if(edge_count>=148||rwds!==0||^dq===1'bx)$fatal(1,"DDR write data/mask");
     if(edge_count%2==0)high_byte=dq;
     else begin memory[address]={high_byte,dq};word_count=word_count+1;end
    end
   end
   edge_count=edge_count+1;
  end
 end
endmodule
