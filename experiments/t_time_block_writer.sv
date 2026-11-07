// Write 16 times x six existing soft bytes, packed into three aligned BL8s.
// start_address, base and end are 32-byte aligned; end may equal 8 MiB.
module t_time_block_writer(
 input wire clk,resetn,start_valid,output wire start_ready,
 input wire[22:0] ring_base,input wire[23:0] ring_end,input wire[22:0] start_address,
 input wire in_valid,output wire in_ready,input wire[7:0] in_data,
 output wire req_valid,input wire req_ready,output wire[20:0] req_address,
 output wire[255:0] req_data,input wire rsp_valid,output wire rsp_ready,
 output reg done
);
 localparam IDLE=0,FILL=1,REQUEST=2,RESPONSE=3;
 reg[1:0]state,burst;
 reg[4:0]count;
 reg[22:0]base_q,address;
 reg[23:0]end_q;
 reg[255:0]buffer_data;
 assign start_ready=resetn&&state==IDLE;
 assign in_ready=resetn&&state==FILL;
 assign req_valid=resetn&&state==REQUEST;
 assign req_address=address[22:2];
 assign req_data=buffer_data;
 assign rsp_ready=resetn&&state==RESPONSE;
 always @(posedge clk)begin
  if(!resetn)begin state<=IDLE;burst<=0;count<=0;base_q<=0;address<=0;end_q<=0;done<=0;end
  else begin
   done<=0;
   case(state)
    IDLE:if(start_valid)begin
     base_q<=ring_base;end_q<=ring_end;address<=start_address;burst<=0;count<=0;state<=FILL;
    end
    FILL:if(in_valid)begin
     buffer_data<={in_data,buffer_data[255:8]};
     if(count==31)begin count<=0;state<=REQUEST;end else count<=count+1'b1;
    end
    REQUEST:if(req_ready)state<=RESPONSE;
    RESPONSE:if(rsp_valid)begin
     if(burst==2)begin done<=1;state<=IDLE;end
     else begin
      burst<=burst+1'b1;address<=address+24'd32==end_q?base_q:address+23'd32;state<=FILL;
     end
    end
   endcase
  end
 end
endmodule
