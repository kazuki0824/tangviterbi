// Validate an S3 -> FPGA RS response before the external staging page commits.
// The caller stores accepted bytes in an UNCOMMITTED page, and publishes it
// only after result_valid && result_errors==0. This block stores no payload.
// It checks v1 lambda (kind 2) and magnitude (kind 4) pages, including CRC,
// exact length, expected epoch/batch, ordered IDs, record invariants and pad.
// A bad result stops the caller's epoch; it is NOT permission to retry/reuse.
// Expected batch ownership, root-count-dependent magnitude checks, SPI CDC,
// staging memory and the whole-batch scheduler are separate components.
module s3_rs_rpc_guard #(
 parameter integer GAP_CYCLES=16384
)(
 input wire clk,resetn,
 input wire cfg_valid,output wire cfg_ready,
 input wire [7:0] cfg_kind,input wire [15:0] cfg_epoch,input wire [31:0] cfg_batch,
 input wire in_valid,output wire in_ready,input wire [7:0] in_data,input wire in_last,
 output wire result_valid,input wire result_ready,output reg [5:0] result_errors
);
 // Error bits: 0 header/identity, 1 CRC, 2 length, 3 record, 4 padding, 5 gap.
 localparam IDLE=0,BUSY=1,DONE=2;
 localparam integer GAP_W=GAP_CYCLES<2?1:$clog2(GAP_CYCLES);
 reg [1:0] state;
 reg [11:0] offset;
 reg [7:0] kind,record_id;
 reg [3:0] record_pos,degree;
 reg record_failed;
 reg [15:0] epoch;
 reg [31:0] batch,crc,wire_crc;
 reg [5:0] errors;
 reg [GAP_W-1:0] gap;
 wire payload=offset>=16 && (kind==2 ? offset<2668 : offset<2464);
 wire [7:0] crc_byte=(offset>=12&&offset<16)?8'd0:in_data;
 function [31:0] advance_crc;
  input [31:0] previous;input [7:0] value;
  reg [31:0] x;integer b;
  begin
   x=previous^{24'd0,value};
   for(b=0;b<8;b=b+1)x=(x>>1)^(x[0]?32'hedb88320:32'd0);
   advance_crc=x;
  end
 endfunction
 wire [31:0] next_crc=advance_crc(crc,crc_byte);
 reg [5:0] byte_errors;
 reg [7:0] header_expected;
 always @* begin
  byte_errors=0;header_expected=0;
  case(offset)
   0:header_expected=8'h52;1:header_expected=8'h53;
   2:header_expected=1;3:header_expected=kind;
   4:header_expected=epoch[7:0];5:header_expected=epoch[15:8];
   6:header_expected=204;7:header_expected=0;
   8:header_expected=batch[7:0];9:header_expected=batch[15:8];
   10:header_expected=batch[23:16];11:header_expected=batch[31:24];
   default:header_expected=0;
  endcase
  if(offset<12 && in_data!=header_expected)byte_errors[0]=1;
  if(payload)begin
   if(record_pos==0 && in_data!=record_id)byte_errors[3]=1;
   if(record_pos==1 && in_data!=0)byte_errors[3]=1;
   if(record_pos==2 && in_data>1)byte_errors[3]=1;
   if(kind==2)begin
    if(record_pos==3 && (in_data>8 || (record_failed && in_data!=0)))byte_errors[3]=1;
    if(record_pos>=4)begin
     if(record_failed && in_data!=0)byte_errors[3]=1;
     if(!record_failed)begin
      if(record_pos==4 && in_data!=1)byte_errors[3]=1;
      if(record_pos>4+degree && in_data!=0)byte_errors[3]=1;
      if(record_pos==4+degree && in_data==0)byte_errors[3]=1;
     end
    end
   end else begin
    if(record_pos>=3 && record_pos<=10 && record_failed && in_data!=0)byte_errors[3]=1;
    if(record_pos==11 && in_data!=0)byte_errors[3]=1;
   end
  end else if(offset>=16 && in_data!=0)byte_errors[4]=1;
 end
 assign cfg_ready=state==IDLE;
 assign in_ready=state==BUSY;
 assign result_valid=state==DONE;
 initial if(GAP_CYCLES<1)$fatal(1,"GAP_CYCLES must be positive");
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin
   state<=IDLE;offset<=0;kind<=0;epoch<=0;batch<=0;crc<=32'hffffffff;
   wire_crc<=0;errors<=0;result_errors<=0;record_id<=0;record_pos<=0;
   record_failed<=0;degree<=0;gap<=0;
  end else begin
   if(state==IDLE && cfg_valid)begin
    state<=BUSY;offset<=0;kind<=cfg_kind;epoch<=cfg_epoch;batch<=cfg_batch;
    crc<=32'hffffffff;wire_crc<=0;errors<=cfg_kind==2||cfg_kind==4?0:1;
    record_id<=0;record_pos<=0;record_failed<=0;degree<=0;gap<=0;
   end
   if(state==BUSY)begin
    if(in_valid)begin
     gap<=0;crc<=next_crc;errors<=errors|byte_errors;
     case(offset)
      12:wire_crc[7:0]<=in_data;13:wire_crc[15:8]<=in_data;
      14:wire_crc[23:16]<=in_data;15:wire_crc[31:24]<=in_data;
      default:begin end
     endcase
     if(payload)begin
      if(record_pos==2)record_failed<=in_data!=0;
      if(record_pos==3)degree<=in_data[3:0];
      if(record_pos==(kind==2?12:11))begin record_pos<=0;record_id<=record_id+1'b1;end
      else record_pos<=record_pos+1'b1;
     end
     if(in_last || offset==4095)begin
      state<=DONE;
      result_errors<=errors|byte_errors|
       ((next_crc^32'hffffffff)!=wire_crc?6'b000010:6'd0)|
       ((offset!=4095||!in_last)?6'b000100:6'd0);
     end else offset<=offset+1'b1;
    end else if(gap==GAP_CYCLES-1)begin
     state<=DONE;result_errors<=errors|6'b100000;
    end else gap<=gap+1'b1;
   end
   if(state==DONE && result_ready)state<=IDLE;
  end
 end
endmodule
