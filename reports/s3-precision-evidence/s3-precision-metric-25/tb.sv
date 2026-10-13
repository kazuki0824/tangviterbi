module tb;
reg clk=0;always #5 clk=~clk;reg rst=0,iv=0,ready=0;wire ir,ov;wire[35:0]costs;wire[3:0]choice;
reg[31:0]words[0:4144];reg[31:0]w=0;integer sent=0,got=0,cycle=0,f;
s3_tc8psk_metric_folded dut(clk,rst,iv,ir,w[15:0],w[31:16],ov,ready,costs,choice);
initial begin $readmemh("input.hex",words);f=$fopen("output.hex","w");repeat(3)@(negedge clk);rst=1;
while(got<4145)begin
 @(negedge clk);ready=cycle%17<12;iv=sent<4145&&cycle%11!=3;if(sent<4145)w=words[sent];
 @(posedge clk);if(iv&&ir)sent=sent+1;if(ov&&ready)begin $fdisplay(f,"%010x",{choice,costs});got=got+1;end
 cycle=cycle+1;if(cycle>40000)$fatal(1,"stalled");
end $fclose(f);$finish;end
endmodule