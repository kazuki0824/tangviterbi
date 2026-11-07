// Experimental GW2AR-18 SDR SDRAM controller: 4 banks, 2048 rows, 256 x32 columns.
// One aligned BL8 request (32 bytes); open-page retention, periodic refresh,
// whole-burst write buffering and read response backpressure. No CDC/IO PHY.
// Timing values are design inputs at 135 MHz, NOT device-qualified measurements.
module dual_sdram_burst #(
 parameter integer INIT_CYCLES=27000,REFRESH_CYCLES=1053,
 parameter integer TRP=3,TRCD=3,TRFC=10,TWR=3,TMRD=3,CL=3,
 parameter integer OPEN_PAGE=1
)(input wire clk,resetn,input wire req_valid,output wire req_ready,
 input wire req_write,input wire[20:0] req_address,input wire[255:0] req_data,
 input wire[31:0] req_dqm,output wire rsp_valid,input wire rsp_ready,
 output wire[255:0] rsp_data,output reg initialized,fault,
 output reg[2:0] sd_cmd,output reg[1:0] sd_bank,output reg[10:0] sd_address,
 output wire sd_cke,output reg[3:0] sd_dqm,output reg dq_oe,
 output reg[31:0] dq_out,input wire[31:0] dq_in);
 localparam BOOT=0,IPRE=1,IREF=2,MODE=3,IDLE=4,PRE=5,ACT=6,
            RCMD=7,WCMD=8,RLAT=9,RDATA=10,WDATA=11,WAIT=12,
            COMPLETE=13,PREALL=14,REFRESH=15,CLOSE=16;
 // Only threshold predicates are observed; saturating at the fault threshold
 // preserves them and avoids keeping unreachable high timer bits.
 localparam REFRESH_WIDTH=$clog2(REFRESH_CYCLES+1);
 reg[4:0] state,after_wait;reg[15:0] wait_count;
 reg[REFRESH_WIDTH-1:0] refresh_age;
 reg[3:0] init_refreshes;reg[2:0] beat;
 reg response_valid;reg[255:0] response_data;
 reg writing;reg[20:0] address;reg[255:0] write_data;reg[31:0] masks;
 reg[3:0] open;reg[10:0] row[0:3];
 wire[1:0] bank=address[9:8];wire[10:0] active_row=address[20:10];
 // Experimental look-ahead predicate. Compare the current age one cycle
 // before the threshold; retain until the same MODE/REFRESH reset edges.
 reg refresh_due;
 always @(posedge clk) begin
  if(!resetn) refresh_due<=0;
  else if(state==MODE || state==REFRESH) refresh_due<=0;
  else if(initialized && refresh_age==REFRESH_CYCLES-33) refresh_due<=1;
 end
 // EXPERIMENT: compare all open rows in parallel before selecting the bank.
 wire [3:0] request_bank_select = 4'b0001 << req_address[9:8];
 wire [3:0] request_row_match;
 genvar rb;
 generate for(rb=0;rb<4;rb=rb+1)begin: request_row_comparators
  assign request_row_match[rb] = row[rb] == req_address[20:10];
 end endgenerate
 wire request_open = |(request_bank_select & open);
 wire request_hit = |(request_bank_select & open & request_row_match);
 // Accept the next descriptor on the completion edge. Its first command is
 // gated until the previous response is consumed; a late consumer stall can
 // never overwrite that response or start a read burst without storage.
 wire completing=OPEN_PAGE && (state==COMPLETE || (state==RDATA && beat==7));
 wire command_allowed=!response_valid || rsp_ready;
 assign rsp_valid=response_valid || completing;
 assign rsp_data=response_valid ? response_data :
                 state==RDATA ? {dq_in,response_data[255:32]} : 256'd0;
 assign req_ready=(state==IDLE || (completing && rsp_ready)) && !fault && !refresh_due && command_allowed;
 assign sd_cke=resetn;
 always @* begin
  sd_cmd=3'b111;sd_bank=bank;sd_address=0;sd_dqm=0;dq_oe=0;dq_out=0;
  case(state)
   IPRE,PREALL:begin sd_cmd=3'b010;sd_address=11'h400;end
   PRE,CLOSE:sd_cmd=3'b010;
   IREF,REFRESH:sd_cmd=3'b001;
   MODE:begin sd_cmd=3'b000;sd_address=(CL<<4)|3;sd_bank=0;end
   ACT:begin sd_cmd=3'b011;sd_address=active_row;end
   RCMD:begin sd_cmd=3'b101;sd_address={3'd0,address[7:0]};end
   WCMD:begin sd_cmd=3'b100;sd_address={3'd0,address[7:0]};dq_oe=1;dq_out=write_data[31:0];sd_dqm=masks[3:0];end
   WDATA:begin dq_oe=1;dq_out=write_data[beat*32+:32];sd_dqm=masks[beat*4+:4];end
  endcase
  if(!command_allowed && (state==PRE || state==ACT || state==RCMD || state==WCMD))begin
   sd_cmd=3'b111;dq_oe=0;dq_out=0;sd_dqm=0;
  end
 end
 // A command is sampled on the edge entering WAIT. Reach its successor
 // after exactly the requested separation, not an accidental extra clock.
 task delay_to;
  input integer clocks;input[4:0] target;
  begin
   after_wait<=target;
   if(clocks==1)state<=target;
   else begin wait_count<=clocks-2;state<=WAIT;end
  end
 endtask
 integer k;
 always @(posedge clk)begin
  if(!resetn)begin
   state<=BOOT;wait_count<=INIT_CYCLES-1;after_wait<=IPRE;refresh_age<=0;init_refreshes<=0;
   beat<=0;writing<=0;address<=0;write_data<=0;masks<=0;open<=0;
   response_valid<=0;response_data<=0;initialized<=0;fault<=0;
   for(k=0;k<4;k=k+1)row[k]<=0;
  end else begin
   if(rsp_valid && rsp_ready)response_valid<=0;
   if(initialized && refresh_age<REFRESH_CYCLES)refresh_age<=refresh_age+1'b1;
   if(initialized && refresh_age>=REFRESH_CYCLES)fault<=1;
   case(state)
    BOOT:if(wait_count==0)state<=IPRE;else wait_count<=wait_count-1'b1;
    IPRE:if(command_allowed)begin open<=0;delay_to(TRP,IREF);end
    IREF:begin
     init_refreshes<=init_refreshes+1'b1;delay_to(TRFC,init_refreshes==7?MODE:IREF);
    end
    MODE:begin delay_to(TMRD,IDLE);initialized<=1;refresh_age<=0;end
    IDLE:begin
     if(refresh_due)state<=PREALL;
    end
    PRE:if(command_allowed)begin open[bank]<=0;delay_to(TRP,ACT);end
    ACT:if(command_allowed)begin row[bank]<=active_row;open[bank]<=1;delay_to(TRCD,writing?WCMD:RCMD);end
    RCMD:if(command_allowed)begin wait_count<=CL-2;state<=RLAT;beat<=0;end
    RLAT:if(wait_count==0)state<=RDATA;else wait_count<=wait_count-1'b1;
    RDATA:begin
     response_data<={dq_in,response_data[255:32]};
     if(beat==7)begin response_valid<=!OPEN_PAGE || !rsp_ready;state<=OPEN_PAGE?IDLE:CLOSE;end
     else beat<=beat+1'b1;
    end
    WCMD:if(command_allowed)begin beat<=1;state<=WDATA;end
    WDATA:if(beat==7)begin delay_to(TWR,COMPLETE);end
          else beat<=beat+1'b1;
    COMPLETE:begin response_data<=0;response_valid<=!OPEN_PAGE || !rsp_ready;state<=OPEN_PAGE?IDLE:CLOSE;end
    CLOSE:begin open[bank]<=0;delay_to(TRP,IDLE);end
    PREALL:begin open<=0;delay_to(TRP,REFRESH);end
    REFRESH:begin refresh_age<=0;delay_to(TRFC,IDLE);end
    WAIT:if(wait_count==0)state<=after_wait;else wait_count<=wait_count-1'b1;
   endcase
   if(req_valid && req_ready)begin
    if(req_address[2:0]!=0)fault<=1;
    else begin
     address<=req_address;writing<=req_write;write_data<=req_data;masks<=req_dqm;
     if(request_hit)state<=req_write?WCMD:RCMD;
     else if(request_open)state<=PRE;
     else state<=ACT;
    end
   end
  end
 end
 initial begin
  if(CL<2 || TRP<1 || TRCD<1 || TWR<1 || TMRD<1 || TRFC<1 || INIT_CYCLES<1 || REFRESH_CYCLES<64 || REFRESH_CYCLES>65535)
   $fatal(1,"invalid SDRAM timing contract");
 end
endmodule
