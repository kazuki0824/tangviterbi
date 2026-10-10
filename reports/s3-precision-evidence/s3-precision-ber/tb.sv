module tb;
reg clk=0;always #5 clk=~clk;reg rst=0,iv=0;reg[31:0]w=0;
wire ir22,mv22,mr22,ov22;wire[35:0]cost22;wire[3:0]choice22;wire[1:0]bits22;
metric22 m22(clk,rst,iv,ir22,w[15:0],w[31:16],mv22,mr22,cost22,choice22);
viterbi22 v22(clk,rst,mv22,mr22,cost22,choice22,ov22,bits22);
wire ir23,mv23,mr23,ov23;wire[35:0]cost23;wire[3:0]choice23;wire[1:0]bits23;
metric23 m23(clk,rst,iv,ir23,w[15:0],w[31:16],mv23,mr23,cost23,choice23);
viterbi23 v23(clk,rst,mv23,mr23,cost23,choice23,ov23,bits23);
wire ir24,mv24,mr24,ov24;wire[35:0]cost24;wire[3:0]choice24;wire[1:0]bits24;
metric24 m24(clk,rst,iv,ir24,w[15:0],w[31:16],mv24,mr24,cost24,choice24);
viterbi24 v24(clk,rst,mv24,mr24,cost24,choice24,ov24,bits24);
wire ir25,mv25,mr25,ov25;wire[35:0]cost25;wire[3:0]choice25;wire[1:0]bits25;
metric25 m25(clk,rst,iv,ir25,w[15:0],w[31:16],mv25,mr25,cost25,choice25);
viterbi25 v25(clk,rst,mv25,mr25,cost25,choice25,ov25,bits25);
reg[31:0]words[0:114687];integer e,s,cycle=0,f,got=0;
initial begin $readmemh("input.hex",words);f=$fopen("output.txt","w");
for(e=0;e<7;e=e+1)begin
 @(negedge clk);rst=0;iv=0;repeat(4)@(negedge clk);rst=1;s=0;
 while(s<16384)begin
  @(negedge clk);iv=cycle%31!=7;w=words[e*16384+s];
  @(posedge clk);if(iv&&ir22)s=s+1;cycle=cycle+1;
 end
 @(negedge clk);iv=0;repeat(500)@(negedge clk);
end $fclose(f);$display("PASS paired_symbols=%0d",got);$finish;end
always @(posedge clk)begin #1;if(rst)begin
 if(ir23!==ir22||ov23!==ov22)$fatal(1,"control mismatch shift23");
if(ir24!==ir22||ov24!==ov22)$fatal(1,"control mismatch shift24");
if(ir25!==ir22||ov25!==ov22)$fatal(1,"control mismatch shift25");
 if(ov22)begin $fwrite(f,"%0d",e);$fwrite(f," %0d",bits22);$fwrite(f," %0d",bits23);$fwrite(f," %0d",bits24);$fwrite(f," %0d",bits25);$fwrite(f,"\n");got=got+1;end
end end
endmodule