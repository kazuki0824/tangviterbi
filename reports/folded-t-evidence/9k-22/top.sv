module folded_probe(input clk,resetn,valid,input[7:0] soft0,soft1,
 output ready,ov,ob);
 folded_t_viterbi dut(clk,resetn,valid,ready,soft0,soft1,ov,ob);
 endmodule
