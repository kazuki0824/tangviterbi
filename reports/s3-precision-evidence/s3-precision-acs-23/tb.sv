module tb;
reg clk=0;always #5 clk=~clk;reg rst=0,iv=0;reg[39:0]word=0;wire ready,ov,rr,rv;wire[1:0]bits,rbits;
s3_tc8psk dut(clk,rst,iv,ready,word[35:0],word[39:36],ov,bits);
reference13 reference(clk,rst,iv,rr,word[35:0],word[39:36],rv,rbits);
reg[39:0]inputs[0:6143];reg[831:0]expected[0:6143];
integer e,s,j,index=0,checks=0,pairs=0;
initial begin $readmemh("input.hex",inputs);$readmemh("oracle.hex",expected);
 for(e=0;e<3;e=e+1)begin
  @(negedge clk);rst=0;iv=0;repeat(3)@(negedge clk);rst=1;
  for(s=0;s<2048;s=s+1)begin
   @(negedge clk);iv=0;while(!ready)@(negedge clk);
   if(s%29<3)repeat(1+s%5)@(negedge clk);
   word=inputs[index];iv=1;@(posedge clk);#1;@(negedge clk);iv=0;
   @(posedge clk);#1;@(posedge clk);#1;
   for(j=0;j<64;j=j+1)begin
    if(dut.metrics[j]!==expected[index][13*j+:11])$fatal(1,"oracle e=%0d s=%0d state=%0d",e,s,j);
    checks=checks+1;
   end index=index+1;
  end
 end
 if(pairs<5000)$fatal(1,"insufficient output pairs");
 $display("PASS symbols=%0d state_checks=%0d output_pairs=%0d",index,checks,pairs);$finish;
end
always @(posedge clk)begin #2;if(rst)begin
 if(ready!==rr||ov!==rv||(ov&&bits!==rbits))$fatal(1,"reference mismatch");
 if(ov)pairs=pairs+1;
end end
endmodule