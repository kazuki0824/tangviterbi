module tb;
reg clk=0;always #5 clk=~clk;reg rst=0,cv=0,iv=0,il=0,rr=0;
reg[7:0]kind=2,data=0;reg[31:0]batch=0;wire cr,ir,rv;wire[5:0]errors;
s3_rs_rpc_guard #(.GAP_CYCLES(32)) dut(clk,rst,cv,cr,kind,16'd17,batch,iv,ir,data,il,rv,rr,errors);
reg[7:0]pages[0:389119],kinds[0:94];reg[31:0]batches[0:94];
reg[5:0]masks[0:94];integer lengths[0:94];reg lasts[0:94];
integer t,j,checks=0,commits=0,cycle=0;reg[5:0]held;
task reset_guard;begin @(negedge clk);rst=0;iv=0;cv=0;rr=0;repeat(3)@(negedge clk);rst=1;end endtask
task configure;begin
 @(negedge clk);if(!cr)$fatal(1,"config blocked");cv=1;
 @(negedge clk);cv=0;if(!ir)$fatal(1,"not receiving");
end endtask
initial begin
 $readmemh("pages.hex",pages);kinds[0]=8'd2;batches[0]=32'h00000000;masks[0]=6'd0;lengths[0]=4096;lasts[0]=1;
kinds[1]=8'd4;batches[1]=32'h00000000;masks[1]=6'd0;lengths[1]=4096;lasts[1]=1;
kinds[2]=8'd2;batches[2]=32'h00000001;masks[2]=6'd0;lengths[2]=4096;lasts[2]=1;
kinds[3]=8'd4;batches[3]=32'h00000001;masks[3]=6'd0;lengths[3]=4096;lasts[3]=1;
kinds[4]=8'd2;batches[4]=32'h00000002;masks[4]=6'd0;lengths[4]=4096;lasts[4]=1;
kinds[5]=8'd4;batches[5]=32'h00000002;masks[5]=6'd0;lengths[5]=4096;lasts[5]=1;
kinds[6]=8'd2;batches[6]=32'h00000003;masks[6]=6'd0;lengths[6]=4096;lasts[6]=1;
kinds[7]=8'd4;batches[7]=32'h00000003;masks[7]=6'd0;lengths[7]=4096;lasts[7]=1;
kinds[8]=8'd2;batches[8]=32'hffffffff;masks[8]=6'd0;lengths[8]=4096;lasts[8]=1;
kinds[9]=8'd4;batches[9]=32'hffffffff;masks[9]=6'd0;lengths[9]=4096;lasts[9]=1;
kinds[10]=8'd2;batches[10]=32'h00000000;masks[10]=6'd0;lengths[10]=4096;lasts[10]=1;
kinds[11]=8'd4;batches[11]=32'h00000000;masks[11]=6'd0;lengths[11]=4096;lasts[11]=1;
kinds[12]=8'd2;batches[12]=32'h00000000;masks[12]=6'd2;lengths[12]=4096;lasts[12]=1;
kinds[13]=8'd2;batches[13]=32'h00000000;masks[13]=6'd2;lengths[13]=4096;lasts[13]=1;
kinds[14]=8'd2;batches[14]=32'h00000000;masks[14]=6'd2;lengths[14]=4096;lasts[14]=1;
kinds[15]=8'd2;batches[15]=32'h00000000;masks[15]=6'd2;lengths[15]=4096;lasts[15]=1;
kinds[16]=8'd2;batches[16]=32'h00000000;masks[16]=6'd2;lengths[16]=4096;lasts[16]=1;
kinds[17]=8'd2;batches[17]=32'h00000000;masks[17]=6'd2;lengths[17]=4096;lasts[17]=1;
kinds[18]=8'd2;batches[18]=32'h00000000;masks[18]=6'd2;lengths[18]=4096;lasts[18]=1;
kinds[19]=8'd2;batches[19]=32'h00000000;masks[19]=6'd2;lengths[19]=4096;lasts[19]=1;
kinds[20]=8'd2;batches[20]=32'h00000000;masks[20]=6'd2;lengths[20]=4096;lasts[20]=1;
kinds[21]=8'd2;batches[21]=32'h00000000;masks[21]=6'd2;lengths[21]=4096;lasts[21]=1;
kinds[22]=8'd2;batches[22]=32'h00000000;masks[22]=6'd2;lengths[22]=4096;lasts[22]=1;
kinds[23]=8'd2;batches[23]=32'h00000000;masks[23]=6'd2;lengths[23]=4096;lasts[23]=1;
kinds[24]=8'd2;batches[24]=32'h00000000;masks[24]=6'd2;lengths[24]=4096;lasts[24]=1;
kinds[25]=8'd2;batches[25]=32'h00000000;masks[25]=6'd2;lengths[25]=4096;lasts[25]=1;
kinds[26]=8'd2;batches[26]=32'h00000000;masks[26]=6'd2;lengths[26]=4096;lasts[26]=1;
kinds[27]=8'd2;batches[27]=32'h00000000;masks[27]=6'd2;lengths[27]=4096;lasts[27]=1;
kinds[28]=8'd2;batches[28]=32'h00000000;masks[28]=6'd2;lengths[28]=4096;lasts[28]=1;
kinds[29]=8'd2;batches[29]=32'h00000000;masks[29]=6'd2;lengths[29]=4096;lasts[29]=1;
kinds[30]=8'd2;batches[30]=32'h00000000;masks[30]=6'd2;lengths[30]=4096;lasts[30]=1;
kinds[31]=8'd2;batches[31]=32'h00000000;masks[31]=6'd2;lengths[31]=4096;lasts[31]=1;
kinds[32]=8'd2;batches[32]=32'h00000000;masks[32]=6'd2;lengths[32]=4096;lasts[32]=1;
kinds[33]=8'd2;batches[33]=32'h00000000;masks[33]=6'd2;lengths[33]=4096;lasts[33]=1;
kinds[34]=8'd2;batches[34]=32'h00000000;masks[34]=6'd2;lengths[34]=4096;lasts[34]=1;
kinds[35]=8'd2;batches[35]=32'h00000000;masks[35]=6'd2;lengths[35]=4096;lasts[35]=1;
kinds[36]=8'd4;batches[36]=32'h00000000;masks[36]=6'd2;lengths[36]=4096;lasts[36]=1;
kinds[37]=8'd4;batches[37]=32'h00000000;masks[37]=6'd2;lengths[37]=4096;lasts[37]=1;
kinds[38]=8'd4;batches[38]=32'h00000000;masks[38]=6'd2;lengths[38]=4096;lasts[38]=1;
kinds[39]=8'd4;batches[39]=32'h00000000;masks[39]=6'd2;lengths[39]=4096;lasts[39]=1;
kinds[40]=8'd4;batches[40]=32'h00000000;masks[40]=6'd2;lengths[40]=4096;lasts[40]=1;
kinds[41]=8'd4;batches[41]=32'h00000000;masks[41]=6'd2;lengths[41]=4096;lasts[41]=1;
kinds[42]=8'd4;batches[42]=32'h00000000;masks[42]=6'd2;lengths[42]=4096;lasts[42]=1;
kinds[43]=8'd4;batches[43]=32'h00000000;masks[43]=6'd2;lengths[43]=4096;lasts[43]=1;
kinds[44]=8'd4;batches[44]=32'h00000000;masks[44]=6'd2;lengths[44]=4096;lasts[44]=1;
kinds[45]=8'd4;batches[45]=32'h00000000;masks[45]=6'd2;lengths[45]=4096;lasts[45]=1;
kinds[46]=8'd4;batches[46]=32'h00000000;masks[46]=6'd2;lengths[46]=4096;lasts[46]=1;
kinds[47]=8'd4;batches[47]=32'h00000000;masks[47]=6'd2;lengths[47]=4096;lasts[47]=1;
kinds[48]=8'd4;batches[48]=32'h00000000;masks[48]=6'd2;lengths[48]=4096;lasts[48]=1;
kinds[49]=8'd4;batches[49]=32'h00000000;masks[49]=6'd2;lengths[49]=4096;lasts[49]=1;
kinds[50]=8'd4;batches[50]=32'h00000000;masks[50]=6'd2;lengths[50]=4096;lasts[50]=1;
kinds[51]=8'd4;batches[51]=32'h00000000;masks[51]=6'd2;lengths[51]=4096;lasts[51]=1;
kinds[52]=8'd4;batches[52]=32'h00000000;masks[52]=6'd2;lengths[52]=4096;lasts[52]=1;
kinds[53]=8'd4;batches[53]=32'h00000000;masks[53]=6'd2;lengths[53]=4096;lasts[53]=1;
kinds[54]=8'd4;batches[54]=32'h00000000;masks[54]=6'd2;lengths[54]=4096;lasts[54]=1;
kinds[55]=8'd4;batches[55]=32'h00000000;masks[55]=6'd2;lengths[55]=4096;lasts[55]=1;
kinds[56]=8'd4;batches[56]=32'h00000000;masks[56]=6'd2;lengths[56]=4096;lasts[56]=1;
kinds[57]=8'd4;batches[57]=32'h00000000;masks[57]=6'd2;lengths[57]=4096;lasts[57]=1;
kinds[58]=8'd4;batches[58]=32'h00000000;masks[58]=6'd2;lengths[58]=4096;lasts[58]=1;
kinds[59]=8'd4;batches[59]=32'h00000000;masks[59]=6'd2;lengths[59]=4096;lasts[59]=1;
kinds[60]=8'd2;batches[60]=32'h00000000;masks[60]=6'd1;lengths[60]=4096;lasts[60]=1;
kinds[61]=8'd2;batches[61]=32'h00000000;masks[61]=6'd1;lengths[61]=4096;lasts[61]=1;
kinds[62]=8'd2;batches[62]=32'h00000000;masks[62]=6'd1;lengths[62]=4096;lasts[62]=1;
kinds[63]=8'd2;batches[63]=32'h00000000;masks[63]=6'd1;lengths[63]=4096;lasts[63]=1;
kinds[64]=8'd2;batches[64]=32'h00000000;masks[64]=6'd1;lengths[64]=4096;lasts[64]=1;
kinds[65]=8'd2;batches[65]=32'h00000000;masks[65]=6'd1;lengths[65]=4096;lasts[65]=1;
kinds[66]=8'd2;batches[66]=32'h00000000;masks[66]=6'd8;lengths[66]=4096;lasts[66]=1;
kinds[67]=8'd2;batches[67]=32'h00000000;masks[67]=6'd8;lengths[67]=4096;lasts[67]=1;
kinds[68]=8'd2;batches[68]=32'h00000000;masks[68]=6'd8;lengths[68]=4096;lasts[68]=1;
kinds[69]=8'd2;batches[69]=32'h00000000;masks[69]=6'd16;lengths[69]=4096;lasts[69]=1;
kinds[70]=8'd4;batches[70]=32'h00000000;masks[70]=6'd1;lengths[70]=4096;lasts[70]=1;
kinds[71]=8'd4;batches[71]=32'h00000000;masks[71]=6'd1;lengths[71]=4096;lasts[71]=1;
kinds[72]=8'd4;batches[72]=32'h00000000;masks[72]=6'd1;lengths[72]=4096;lasts[72]=1;
kinds[73]=8'd4;batches[73]=32'h00000000;masks[73]=6'd1;lengths[73]=4096;lasts[73]=1;
kinds[74]=8'd4;batches[74]=32'h00000000;masks[74]=6'd1;lengths[74]=4096;lasts[74]=1;
kinds[75]=8'd4;batches[75]=32'h00000000;masks[75]=6'd1;lengths[75]=4096;lasts[75]=1;
kinds[76]=8'd4;batches[76]=32'h00000000;masks[76]=6'd8;lengths[76]=4096;lasts[76]=1;
kinds[77]=8'd4;batches[77]=32'h00000000;masks[77]=6'd8;lengths[77]=4096;lasts[77]=1;
kinds[78]=8'd4;batches[78]=32'h00000000;masks[78]=6'd8;lengths[78]=4096;lasts[78]=1;
kinds[79]=8'd4;batches[79]=32'h00000000;masks[79]=6'd16;lengths[79]=4096;lasts[79]=1;
kinds[80]=8'd2;batches[80]=32'h00000000;masks[80]=6'd8;lengths[80]=4096;lasts[80]=1;
kinds[81]=8'd2;batches[81]=32'h00000000;masks[81]=6'd8;lengths[81]=4096;lasts[81]=1;
kinds[82]=8'd2;batches[82]=32'h00000000;masks[82]=6'd8;lengths[82]=4096;lasts[82]=1;
kinds[83]=8'd2;batches[83]=32'h00000000;masks[83]=6'd8;lengths[83]=4096;lasts[83]=1;
kinds[84]=8'd2;batches[84]=32'h00000000;masks[84]=6'd8;lengths[84]=4096;lasts[84]=1;
kinds[85]=8'd4;batches[85]=32'h00000000;masks[85]=6'd8;lengths[85]=4096;lasts[85]=1;
kinds[86]=8'd4;batches[86]=32'h00000000;masks[86]=6'd8;lengths[86]=4096;lasts[86]=1;
kinds[87]=8'd4;batches[87]=32'h00000000;masks[87]=6'd8;lengths[87]=4096;lasts[87]=1;
kinds[88]=8'd2;batches[88]=32'h00000000;masks[88]=6'd4;lengths[88]=1;lasts[88]=1;
kinds[89]=8'd2;batches[89]=32'h00000000;masks[89]=6'd4;lengths[89]=15;lasts[89]=1;
kinds[90]=8'd2;batches[90]=32'h00000000;masks[90]=6'd4;lengths[90]=16;lasts[90]=1;
kinds[91]=8'd2;batches[91]=32'h00000000;masks[91]=6'd4;lengths[91]=101;lasts[91]=1;
kinds[92]=8'd2;batches[92]=32'h00000000;masks[92]=6'd4;lengths[92]=4095;lasts[92]=1;
kinds[93]=8'd2;batches[93]=32'h00000000;masks[93]=6'd4;lengths[93]=4096;lasts[93]=0;
kinds[94]=8'd2;batches[94]=32'h00000000;masks[94]=6'd0;lengths[94]=4096;lasts[94]=1;
 reset_guard();
 for(t=0;t<95;t=t+1)begin
  kind=kinds[t];batch=batches[t];configure();
  for(j=0;j<lengths[t];j=j+1)begin
   @(negedge clk);iv=0;
   if(j%137==0)repeat(3)@(negedge clk);
   if(rv)$fatal(1,"early page publication");
   data=pages[t*4096+j];il=(j==lengths[t]-1)&&lasts[t];iv=1;
   @(posedge clk);if(!ir)$fatal(1,"lost byte");checks=checks+1;
  end
  @(negedge clk);iv=0;il=0;
  if(!rv)$fatal(1,"no result case=%0d",t);
  if(masks[t]==0 && errors!=0)$fatal(1,"good page rejected case=%0d errors=%0h",t,errors);
  if(masks[t]!=0 && (errors&masks[t])!=masks[t])$fatal(1,"bad page accepted case=%0d errors=%0h mask=%0h",t,errors,masks[t]);
  if(errors==0)commits=commits+1;
  held=errors;
  // Held completion rejects new bytes/config until acknowledged.
  iv=1;cv=1;repeat(7)begin @(negedge clk);if(!rv||errors!==held||ir||cr)$fatal(1,"unstable result");end
  iv=0;cv=0;rr=1;@(negedge clk);rr=0;
 end
 // Partial input then silence expires; no fake complete page is published.
 kind=2;batch=0;configure();@(negedge clk);iv=1;data=8'h52;
 @(negedge clk);iv=0;repeat(35)@(negedge clk);
 if(!rv||!errors[5])$fatal(1,"missing timeout");
 reset_guard();configure();@(negedge clk);iv=1;data=8'h52;
 @(negedge clk);iv=0;reset_guard();
 if(rv||ir||!cr)$fatal(1,"dirty reset");
 $display("PASS pages=%0d bytes=%0d committed=%0d timeout=1 dirty_reset=1",95,checks,commits);$finish;
end
endmodule