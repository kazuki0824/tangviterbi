// Backpressured staging-reader stream -> slower RPC validator.
// All cfg/result signals belong to check_clk. Data/last use write_clk.
// This is NOT a wire-SPI input: the producer must obey in_ready. The caller
// retains the entire uncommitted staging page until validation succeeds.
// On any validation error stop the epoch, drain IO, and reset BOTH domains;
// queued data must never be reused under a different descriptor.
module s3_rs_rpc_guard_cdc #(parameter GAP_CYCLES=16384, FIFO_AW=7)(
 input wire write_clk,check_clk,resetn,
 input wire cfg_valid,output wire cfg_ready,
 input wire [7:0] cfg_kind,input wire [15:0] cfg_epoch,input wire [31:0] cfg_batch,
 input wire in_valid,output wire in_ready,input wire [7:0] in_data,input wire in_last,
 output wire result_valid,input wire result_ready,output wire [5:0] result_errors
);
 wire v,r;wire[8:0] word;
 s3_async_fifo #(.W(9),.AW(FIFO_AW)) queue(write_clk,check_clk,resetn,
  in_valid,in_ready,{in_last,in_data},v,r,word);
 s3_rs_rpc_guard #(.GAP_CYCLES(GAP_CYCLES)) guard(check_clk,resetn,
  cfg_valid,cfg_ready,cfg_kind,cfg_epoch,cfg_batch,v,r,word[7:0],word[8],
  result_valid,result_ready,result_errors);
endmodule
