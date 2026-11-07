// Optional one-entry producer holding register, not a burst-rate smoothing FIFO.
// Upstream may release a descriptor after in_valid && in_ready. The downstream
// descriptor remains stable until out_valid && out_ready, including replacement
// on the same edge. Response storage/ownership is handled outside this module.
module sdram_request_slot #(parameter READ_ONLY=0)(
 input wire clk,resetn,input wire in_valid,output wire in_ready,
 input wire in_write,input wire[20:0]in_address,
 input wire[255:0]in_data,input wire[31:0]in_dqm,
 output wire out_valid,input wire out_ready,output wire out_write,
 output wire[20:0]out_address,output wire[255:0]out_data,
 output wire[31:0]out_dqm,output reg fault
);
 reg occupied;
 reg[20:0] address;
 wire legal_request=!READ_ONLY || !in_write;
 assign in_ready=resetn && (!occupied || out_ready) && legal_request;
 assign out_valid=resetn && occupied;
 assign out_address=address;
 always @(posedge clk)begin
  if(!resetn)begin occupied<=0;fault<=0;end
  else begin
   if(in_valid && !legal_request)fault<=1;
   if(in_ready)begin
    occupied<=in_valid;
    if(in_valid)address<=in_address;
   end else if(out_ready)occupied<=0;
  end
 end
 generate if(READ_ONLY)begin: read_only
  assign out_write=0;assign out_data=0;assign out_dqm=0;
 end else begin: read_write
  reg write_request;
  reg[255:0] data;
  reg[31:0] dqm;
  assign out_write=write_request;assign out_data=data;assign out_dqm=dqm;
  always @(posedge clk)if(in_valid && in_ready)begin
   write_request<=in_write;data<=in_data;dqm<=in_dqm;
  end
 end endgenerate
endmodule
