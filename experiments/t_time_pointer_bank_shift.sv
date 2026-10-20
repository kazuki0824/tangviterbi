// Experimental time-deinterleaver pointer state only, NOT a memory controller.
// ARIB B31 Fig.3-23 complementary receive delay: I * (95 - m), m=(5*i)%96.
// Carriers of one layer and delay class share a symbol position; do not store
// one pointer per carrier. Configuration is stable between resets.
// All 288 entries advance once per next_symbol. Queries are invalid while busy.
module t_time_pointer_bank(
 input wire clk,resetn,next_symbol,
 input wire [14:0] lengths,
 input wire [1:0] query_layer,
 input wire [6:0] query_class,
 output wire query_valid,
 output wire [10:0] query_position,
 output reg busy
);
 (* ram_style="distributed" *) reg [10:0] positions[0:287];
 reg initializing;
 reg [1:0] layer;
 reg [6:0] delay_class;
 wire [4:0] length=lengths[layer*5+:5];
 wire [10:0] complement=11'd95-delay_class;
 reg [10:0] depth;
 // Valid B31 lengths are powers of two or zero; no multiplier is needed.
 always @* case(length)
  1:depth=complement;2:depth=complement<<1;4:depth=complement<<2;
  8:depth=complement<<3;16:depth=complement<<4;default:depth=0;
 endcase
 wire [8:0] update_address=layer*9'd96+delay_class;
 wire [8:0] query_address=query_layer*9'd96+query_class;
 assign query_valid=resetn && !busy && query_layer<3 && query_class<96;
 assign query_position=query_valid ? positions[query_address] : 11'd0;
 always @(posedge clk) begin
  if(!resetn)begin busy<=1;initializing<=1;layer<=0;delay_class<=0;end
  else if(busy)begin
   if(initializing || depth==0 || positions[update_address]>=depth-1'b1)
    positions[update_address]<=0;
   else positions[update_address]<=positions[update_address]+1'b1;
   if(delay_class==95)begin
    delay_class<=0;
    if(layer==2)begin layer<=0;busy<=0;initializing<=0;end
    else layer<=layer+1'b1;
   end else delay_class<=delay_class+1'b1;
  end else if(next_symbol)begin busy<=1;layer<=0;delay_class<=0;end
 end
endmodule
