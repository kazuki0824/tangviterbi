// Bounded request FIFO. Pack each 310-bit descriptor into two 160-bit words
// so a 256-entry FIFO maps to five 512x36 BSRAMs, not nine half-empty blocks.
// One ingress holding slot and one output slot are additional to memory.
// The response path stays outside the FIFO; all requests remain in order.
module dual_burst_fifo #(parameter DEPTH=256)(
 input wire clk,resetn,iv,output wire ir,
 input wire iw,input wire[20:0] ia,input wire[255:0] id,input wire[31:0] im,
 output reg ov,input wire orr,output wire ow,output wire[20:0] oa,
 output wire[255:0] od,output wire[31:0] om,output wire[15:0] level);
 localparam AW=$clog2(DEPTH);
 reg[159:0] ram[0:2*DEPTH-1];
 reg[AW-1:0] wp,rp;reg[AW:0] count;
 reg[1:0] ws,rs;
 wire[309:0] input_payload={iw,ia,id,im};
 reg[149:0] incoming;reg[309:0] outgoing;reg[159:0] read_data;
 wire enqueue=ws==1,dequeue=rs==2;
 assign ir=ws==0&&count<DEPTH;
 assign {ow,oa,od,om}=outgoing;
 assign level=count+(ws!=0)+ov;
 // One physical write port and one physical read port. Expressing lo/hi
 // as separate memory reads would cause synthesis to replicate the RAM.
 always @(posedge clk)begin
  if((iv&&ir)||ws==1)ram[{wp,ws==1}]<=ws==0?input_payload[159:0]:{10'd0,incoming};
  if((rs==0&&count!=0&&!ov)||rs==1)read_data<=ram[{rp,rs==1}];
 end
 always @(posedge clk)begin
  if(!resetn)begin wp<=0;rp<=0;count<=0;ws<=0;rs<=0;ov<=0;incoming<=0;outgoing<=0;end
  else begin
   if(ov&&orr)ov<=0;
   case({enqueue,dequeue})
    2'b10:count<=count+1'b1;
    2'b01:count<=count-1'b1;
   endcase
   case(ws)
    0:if(iv&&ir)begin incoming<=input_payload[309:160];ws<=1;end
    1:begin wp<=wp+1'b1;ws<=0;end
   endcase
   case(rs)
    0:if(count!=0&&!ov)rs<=1;
    1:begin outgoing[159:0]<=read_data;rs<=2;end
    2:begin outgoing[309:160]<=read_data[149:0];ov<=1;rp<=rp+1'b1;rs<=0;end
   endcase
  end
 end
 initial if(DEPTH<2 || (DEPTH&(DEPTH-1))!=0 || DEPTH>32768)$fatal(1,"FIFO depth must be a power of two");
endmodule
