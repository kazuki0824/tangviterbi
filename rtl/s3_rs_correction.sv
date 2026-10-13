// Apply an already validated RS solution to a complete 204-byte codeword.
// Validate sorted roots before accepting any byte. Output includes parity;
// the later TS scheduler must retire/drop/mark the whole block on out_fail.
module s3_rs_correction(
 input wire clk,resetn,
 input wire cfg_valid,output wire cfg_ready,
 input wire [3:0] cfg_count,input wire [63:0] cfg_positions,cfg_magnitudes,
 input wire cfg_failed,output reg cfg_error,
 input wire in_valid,output wire in_ready,input wire [7:0] in_data,
 output reg out_valid,input wire out_ready,output reg [7:0] out_data,
 output reg out_last,output wire out_failed
);
 localparam IDLE=0,CHECK=1,STREAM=2;
 reg [1:0] state;
 reg [63:0] positions,magnitudes;
 reg [3:0] count,left;
 reg [2:0] check_index;
 reg [7:0] previous,offset;
 reg invalid,failed,end_loaded;
 wire current_bad=check_index<count &&
  (positions[7:0]>=204 || (check_index!=0 && positions[7:0]<=previous));
 wire hit=left!=0 && positions[7:0]==offset;
 assign cfg_ready=state==IDLE;
 assign in_ready=state==STREAM && !end_loaded && (!out_valid || out_ready);
 assign out_failed=failed;
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin
   state<=IDLE;positions<=0;magnitudes<=0;count<=0;left<=0;check_index<=0;
   previous<=0;offset<=0;invalid<=0;failed<=0;end_loaded<=0;
   cfg_error<=0;out_valid<=0;out_data<=0;out_last<=0;
  end else begin
   cfg_error<=0;
   if(out_valid&&out_ready)begin
    out_valid<=0;
    if(out_last)state<=IDLE;
   end
   if(cfg_valid&&cfg_ready)begin
    positions<=cfg_positions;magnitudes<=cfg_magnitudes;
    count<=cfg_failed?0:cfg_count;left<=cfg_failed?0:cfg_count;
    invalid<=!cfg_failed && cfg_count>8;failed<=cfg_failed;
    check_index<=0;previous<=0;offset<=0;end_loaded<=0;state<=CHECK;
   end
   if(state==CHECK)begin
    // Eight rotations restore the original low-byte-first order.
    positions<={positions[7:0],positions[63:8]};
    magnitudes<={magnitudes[7:0],magnitudes[63:8]};
    previous<=positions[7:0];invalid<=invalid||current_bad;
    if(check_index==7)begin
     if(invalid||current_bad)begin cfg_error<=1;state<=IDLE;end
     else state<=STREAM;
    end else check_index<=check_index+1'b1;
   end
   if(in_valid&&in_ready)begin
    out_valid<=1;out_data<=in_data^(hit?magnitudes[7:0]:8'd0);out_last<=offset==203;
    if(hit)begin
     left<=left-1'b1;positions<=positions>>8;magnitudes<=magnitudes>>8;
    end
    if(offset==203)end_loaded<=1;else offset<=offset+1'b1;
   end
  end
 end
endmodule
