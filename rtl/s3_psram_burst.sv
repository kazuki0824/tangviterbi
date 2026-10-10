// W955D8MBYA-compatible pair of x8 DDR dies, striped as 32-bit core words.
// 64 words = one aligned 128-byte wrapped burst per die = 256 bytes total.
// Datasheet contract: fixed latency 2*4 at <=104 MHz, CR0=8ffc, tRWR>=36 ns.
// PHY interface is two chronological bytes/die/core clock, NOT SDR pin data.
// A write source must provide all 64 words without gaps; a read sink must accept
// all 64 words. Buffer/reservation adapters enforce those contracts upstream.
// Both die reads may arrive independently. There is no assumption of equal
// CK->RWDS delays. Fault is sticky; recovering requires a complete RAM reset.
module s3_psram_burst #(
 parameter integer FREQ_HZ=99000000,
 parameter integer POWERUP_CYCLES=(FREQ_HZ/1000000)*160,
 parameter integer RESET_CYCLES=(FREQ_HZ/1000000)+1,
 parameter integer RECOVERY_CYCLES=4,
 parameter integer MAX_ACTIVE_CYCLES=160
)(
 input wire clk,resetn,abort,
 input wire cmd_valid,cmd_write,input wire [20:0] cmd_address,
 output wire cmd_ready,
 input wire w_valid,input wire [31:0] w_data,output wire w_ready,
 output wire r_valid,output wire [31:0] r_data,
 output reg done,initialized,fault,
 // Registered I/O PHY samples outputs on clk rising edge. It launches a
 // quarter-cycle-delayed CK and returns only qualified RWDS-delimited words.
 output wire ram_reset_n,ram_cs_n,ram_ck_enable,
 output reg dq_drive,rwds_drive,
 output reg [15:0] tx_first,tx_second,
 output wire rx_enable,
 input wire [1:0] rx_valid,input wire [15:0] rx_word0,rx_word1,
 input wire phy_fault
);
 localparam [3:0] RESET=0,POWERUP=1,PREPARE=2,RUN=3,TAIL=4,RECOVER=5,IDLE=6,STOP=7,VERIFY=8;
 localparam integer TIMER_BITS=$clog2(POWERUP_CYCLES+1);
 (* fsm_encoding="one-hot" *) reg [3:0] state;
 reg [TIMER_BITS-1:0] timer;
 reg [7:0] cycle;
 reg [2:0] init_step;
 reg write_op,register_op;
 reg write_window,mask_window;
 reg [47:0] ca;
 reg [31:0] configuration_read;
 reg [6:0] output_count;
 reg [6:0] received[0:1];
 (* keep *) reg [2:0] head[0:1],tail[0:1];
 reg [15:0] fifo0[0:3],fifo1[0:3];
 wire [2:0] used0=tail[0]-head[0],used1=tail[1]-head[1];
 wire pair_valid=used0!=0 && used1!=0;
 wire read_mode=state==RUN && !write_op;
 wire pop=read_mode && pair_valid;
 wire [31:0] pair_data={fifo1[head[1][1:0]],fifo0[head[0][1:0]]};
 wire [6:0] expected_words=register_op ? 7'd1 : 7'd64;
 wire [1:0] push={read_mode&&rx_valid[1]&&received[1]<expected_words,
                  read_mode&&rx_valid[0]&&received[0]<expected_words};
 assign cmd_ready=state==IDLE && initialized && !fault && !abort;
 assign w_ready=state==RUN && write_op && !register_op && write_window && !fault;
 assign r_valid=pop && !register_op && !fault;
 assign r_data=pair_data;
 assign ram_reset_n=state!=RESET && state!=STOP && resetn;
 assign ram_cs_n=!(state==PREPARE || state==RUN || state==TAIL || state==VERIFY);
 assign ram_ck_enable=state==RUN;
 // Start qualification only after the CA/latency region. The physical PHY
 // compensates its IDDR pipeline delay and arms from a *low* RWDS preamble.
 assign rx_enable=read_mode && cycle>=9;
 initial begin
  if(FREQ_HZ>104000000 || FREQ_HZ<1000000)$fatal(1,"fixed latency frequency");
  if(RECOVERY_CYCLES*1000000000.0/FREQ_HZ<36.0)$fatal(1,"tRWR");
  if(MAX_ACTIVE_CYCLES*1000000000.0/FREQ_HZ>=4000.0)$fatal(1,"tCSM");
 end
 reg [15:0] ca_pair;
 always @* begin
  dq_drive=0;rwds_drive=0;tx_first=0;tx_second=0;ca_pair=0;
  if(state==RUN)begin
   if(cycle<3)begin
    case(cycle)0:ca_pair=ca[47:32];1:ca_pair=ca[31:16];default:ca_pair=ca[15:0];endcase
    dq_drive=1;tx_first={2{ca_pair[15:8]}};tx_second={2{ca_pair[7:0]}};
   end else if(register_op && write_op && cycle==3)begin
    // Configuration writes have no latency and RWDS must stay high-Z.
    dq_drive=1;tx_first=16'h8f8f;tx_second=16'hfcfc;
   end else if(write_op && !register_op)begin
    if(mask_window)rwds_drive=1; // low write-mask preamble before first data
    if(write_window)begin
     dq_drive=1;tx_first={w_data[31:24],w_data[15:8]};
     tx_second={w_data[23:16],w_data[7:0]};
    end
   end
  end
 end
 integer p;
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin
   state<=RESET;timer<=0;cycle<=0;init_step<=0;ca<=0;
   write_op<=0;register_op<=0;write_window<=0;mask_window<=0;done<=0;initialized<=0;fault<=0;output_count<=0;configuration_read<=0;
   for(p=0;p<2;p=p+1)begin head[p]<=0;tail[p]<=0;received[p]<=0;end
  end else begin
   done<=0;
   if(abort || phy_fault)begin fault<=1;initialized<=0;state<=STOP;end
   else if(!fault)begin
    case(state)
     RESET:if(timer==RESET_CYCLES-1)begin timer<=0;state<=POWERUP;end else timer<=timer+1'b1;
     POWERUP:if(timer==POWERUP_CYCLES-1)begin
      timer<=0;init_step<=0;write_op<=1;register_op<=1;
      ca<=48'h600001000000;state<=PREPARE;
     end else timer<=timer+1'b1;
     PREPARE:begin
      cycle<=0;output_count<=0;state<=RUN;write_window<=0;mask_window<=0;
      for(p=0;p<2;p=p+1)begin head[p]<=0;tail[p]<=0;received[p]<=0;end
     end
     RUN:begin
      cycle<=cycle+1'b1;
      if(cycle==8)mask_window<=1;
      if(cycle==9)write_window<=1;
      if(cycle==MAX_ACTIVE_CYCLES-1)begin fault<=1;initialized<=0;state<=STOP;end
      else if(write_op)begin
       if(register_op && cycle==3)begin state<=TAIL;timer<=0;end
       if(w_ready && !w_valid)begin fault<=1;initialized<=0;state<=STOP;end
       else if(!register_op && cycle==73)begin state<=TAIL;timer<=0;end
      end else begin
       if(push[0])begin fifo0[tail[0][1:0]]<=rx_word0;tail[0]<=tail[0]+1'b1;received[0]<=received[0]+1'b1;end
       if(push[1])begin fifo1[tail[1][1:0]]<=rx_word1;tail[1]<=tail[1]+1'b1;received[1]<=received[1]+1'b1;end
       if((push[0]&&used0==4&&!pop)||(push[1]&&used1==4&&!pop))begin
        fault<=1;initialized<=0;state<=STOP;
       end else if(pop)begin
        head[0]<=head[0]+1'b1;head[1]<=head[1]+1'b1;output_count<=output_count+1'b1;
        if(register_op)begin configuration_read<=pair_data;state<=VERIFY;end
        else if(output_count==expected_words-1)begin state<=TAIL;timer<=0;end
       end
      end
     end
     VERIFY:begin
      // Configuration comparisons have their own cycle. They must not form
      // a FIFO pointer -> data mux -> 32-bit compare -> state/fault path.
      if((init_step==1 && configuration_read!=32'h8ffc8ffc) ||
         (init_step==2 && (configuration_read&32'h007f007f)!=32'h005f005f) ||
         (init_step==3 && (configuration_read&32'h000f000f)!=32'h000f000f))begin
       fault<=1;initialized<=0;state<=STOP;
      end else begin state<=TAIL;timer<=0;end
     end
     // Two CK-low cycles hold CS until all ODDR/IDDR pipeline data has left.
     TAIL:if(timer==1)begin timer<=0;state<=RECOVER;end else timer<=timer+1'b1;
     RECOVER:if(timer==RECOVERY_CYCLES-1)begin
      timer<=0;
      if(register_op && init_step<3)begin
       init_step<=init_step+1'b1;write_op<=0;state<=PREPARE;
       case(init_step)
        0:ca<=48'he00001000000;
        1:ca<=48'he00000000000;
        2:ca<=48'he00000000001;
       endcase
      end else begin
       state<=IDLE;initialized<=1;if(!register_op)done<=1;
      end
     end else timer<=timer+1'b1;
     IDLE:if(cmd_valid)begin
      if(cmd_address[5:0]!=0)begin fault<=1;initialized<=0;state<=STOP;end
      else begin
       ca<={~cmd_write,2'b00,11'd0,cmd_address[20:3],13'd0,cmd_address[2:0]};
       write_op<=cmd_write;register_op<=0;state<=PREPARE;
      end
     end
     default:begin fault<=1;initialized<=0;state<=STOP;end
    endcase
   end
  end
 end
endmodule
