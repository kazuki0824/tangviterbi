// Cross-twiddle multiplier. One complex word per four clocks, 4 DSP products.
// Same Q1.16 coefficient and signed Q15 sample convention as dual_fft_tile.
module dual_fft_cross(input wire clk,resetn,input wire in_valid,output wire in_ready,
 input wire signed[15:0] xr,xi,input wire signed[17:0] wr,wi,
 output wire out_valid,input wire out_ready,output reg[31:0] out_data,output reg overflow);
 reg[1:0] state;
 reg signed[33:0] rr,ii,ri,ir;
 reg signed[34:0] real_sum,imag_sum;
 function signed[34:0] rounded;
  input signed[34:0] x;
  begin rounded=(x+(x<0 ? 35'sd32767 : 35'sd32768))>>>16;end
 endfunction
 function[15:0] clamp;
  input signed[34:0] x;reg signed[34:0] y;
  begin y=rounded(x);clamp=y>32767 ? 16'h7fff : y < -32768 ? 16'h8000 : y[15:0];end
 endfunction
 assign in_ready=state==0;assign out_valid=state==3;
 always @(posedge clk)begin
  if(!resetn)begin state<=0;out_data<=0;overflow<=0;end
  else case(state)
   0:if(in_valid)begin rr<=xr*wr;ii<=xi*wi;ri<=xr*wi;ir<=xi*wr;state<=1;end
   1:begin real_sum<={rr[33],rr}-{ii[33],ii};imag_sum<={ri[33],ri}+{ir[33],ir};state<=2;end
   2:begin
    out_data<={clamp(imag_sum),clamp(real_sum)};
    overflow<=rounded(real_sum)>32767 || rounded(real_sum)<-32768 || rounded(imag_sum)>32767 || rounded(imag_sum)<-32768;
    state<=3;
   end
   3:if(out_ready)state<=0;
  endcase
 end
endmodule
