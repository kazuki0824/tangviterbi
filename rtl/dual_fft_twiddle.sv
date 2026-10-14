// Synchronous W8192 twiddle, signed Q1.16. Two 18-bit BRAM banks hold
// quarter cosine samples 0..2047; endpoint cos(pi/2)=0 is synthesized.
module dual_fft_twiddle(input wire clk,input wire[12:0] phase,
 output wire signed[17:0] real_part,imag_part);
 (* ram_style="block" *) reg[16:0] rom[0:2047];
 initial $readmemh("rtl/dual_fft_quarter_q16.hex",rom);
 wire[1:0] quadrant=phase[12:11];wire[10:0] offset=phase[10:0];
 wire[11:0] ca=quadrant[0] ? 12'd2048-{1'b0,offset} : {1'b0,offset};
 wire[11:0] sa=quadrant[0] ? {1'b0,offset} : 12'd2048-{1'b0,offset};
 reg[16:0] cr,sr;reg cz,sz,cn,sn;
 always @(posedge clk)begin
  cr<=rom[ca[10:0]];sr<=rom[sa[10:0]];
  cz<=ca[11];sz<=sa[11];cn<=quadrant==1 || quadrant==2;sn<=!quadrant[1];
 end
 wire signed[17:0] c=cz?18'sd0:$signed({1'b0,cr});
 wire signed[17:0] s=sz?18'sd0:$signed({1'b0,sr});
 assign real_part=cn?-c:c;assign imag_part=sn?-s:s;
endmodule
