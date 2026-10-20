// Read one 16-carrier-time block (96 existing soft bytes) from a circular ring.
// base/end are 32-byte aligned byte addresses, start is within [base,end).
// One outstanding BL8; response buffered before byte-wise downstream delivery.
module t_time_block_reader(
 input wire clk,resetn,start_valid,output wire start_ready,
 input wire[22:0] ring_base,input wire[23:0] ring_end,input wire[22:0] start_address,
 output wire req_valid,input wire req_ready,output wire[20:0] req_address,
 input wire rsp_valid,output wire rsp_ready,input wire[255:0] rsp_data,
 output wire out_valid,input wire out_ready,output wire[7:0] out_data,
 output reg done
);
 localparam IDLE=0,REQUEST=1,RESPONSE=2,DRAIN=3;
 reg[1:0]state;
 reg[22:0]base_q,address;
 reg[23:0]end_q;
 reg[4:0]skip;
 reg[5:0]available;
 reg[6:0]remaining;
 reg[255:0]buffer_data;
 assign start_ready=resetn&&state==IDLE;
 assign req_valid=resetn&&state==REQUEST;
 assign req_address=address[22:2];
 assign rsp_ready=resetn&&state==RESPONSE;
 assign out_valid=resetn&&state==DRAIN&&skip==0;
 assign out_data=buffer_data[7:0];
 always @(posedge clk)begin
  if(!resetn)begin state<=IDLE;done<=0;base_q<=0;end_q<=0;address<=0;skip<=0;available<=0;remaining<=0;end
  else begin
   done<=0;
   case(state)
    IDLE:if(start_valid)begin
     base_q<=ring_base;end_q<=ring_end;address<={start_address[22:5],5'd0};
     skip<=start_address[4:0];remaining<=96;state<=REQUEST;
    end
    REQUEST:if(req_ready)state<=RESPONSE;
    RESPONSE:if(rsp_valid)begin
     buffer_data<=rsp_data;available<=32;state<=DRAIN;
    end
    DRAIN:if(skip!=0)begin
     buffer_data<=buffer_data>>8;skip<=skip-1'b1;available<=available-1'b1;
    end else if(out_ready)begin
     buffer_data<=buffer_data>>8;remaining<=remaining-1'b1;available<=available-1'b1;
     if(remaining==1)begin state<=IDLE;done<=1;end
     else if(available==1)begin
      address<=address+23'd32==end_q?base_q:address+23'd32;
      state<=REQUEST;
     end
    end
   endcase
  end
 end
endmodule
