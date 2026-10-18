module folded_probe(input clk,resetn,valid,input[7:0] soft0,soft1,
 input[1:0] erasure, output ready,ov,ob);
 folded_t_viterbi dut(clk,resetn,valid,ready,soft0,soft1,erasure,ov,ob);
 endmodule
