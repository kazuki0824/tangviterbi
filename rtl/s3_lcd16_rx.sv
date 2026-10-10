// 40-MHz I80 write strobes -> existing 36-bit page-token protocol.
// Header is eight big-endian 16-bit beats: command, epoch, offset high/low,
// length, three zero reserved beats. DC=0 for header, DC=1 for payload.
// Payload beats are little-endian byte pairs, two beats per FIFO word.
// CS resets parsing only. Fault/overflow is sticky until epoch reset;
// the consumer must mute output and never commit an incomplete page.
module s3_lcd16_rx #(parameter FIFO_AW=7)(
 input wire wr_clk,cs_n,dc,clk,resetn,input wire [15:0] dq,
 output wire valid,input wire ready,output wire [35:0] token,
 output wire fault
);
 reg [11:0] count;
 reg [15:0] command,half;
 wire frame_reset=!resetn||cs_n;
 wire body=count>=8&&count<2056;
 wire write_command=command==16'hd711||command==16'hd712;
 wire wvalid=!cs_n&&(count==1||count==3||count==4||
                    (body&&count[0]&&write_command));
 wire [3:0] tag=count==1?1:count==3?2:count==4?3:count==2055?8:0;
 wire [31:0] value=count==1?{command,dq}:count==3?{half,dq}:
                      count==4?{16'd0,dq}:{dq,half};
 wire wready;
 reg sticky;
 (* async_reg="true" *) reg fault1,fault2;
 always @(posedge wr_clk or negedge resetn)begin
  if(!resetn)sticky<=0;
  else if(!cs_n&&((wvalid&&!wready)||count>=2056||
              (dc!=(count>=8))||(count>=5&&count<8&&dq!=0)))sticky<=1;
 end
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin fault1<=0;fault2<=0;end
  else begin fault1<=sticky;fault2<=fault1;end
 end
 assign fault=fault2;
 always @(posedge wr_clk or posedge frame_reset)begin
  if(frame_reset)begin count<=0;command<=0;half<=0;end
  else begin
   if(count!=4095)count<=count+1'b1;
   half<=dq;
   if(count==0)command<=dq;
  end
 end
 s3_async_fifo #(.W(36),.AW(FIFO_AW)) fifo(
  wr_clk,clk,resetn,wvalid,wready,{tag,value},valid,ready,token);
endmodule
