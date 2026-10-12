// Generated balancedGF(256), polynomial0x11d.81-LUT4 Boolean cover.
// No integer products, table RAM, or additional register latency.
// Boolean-cover source from the prior receiver estimate; mapped counts are measured separately.
module gf256_mul(input wire [7:0] a, b, output wire [7:0] y);
  wire [7:0] ax0;
  assign ax0[0] = a[0];
  assign ax0[1] = a[1];
  assign ax0[2] = a[2];
  assign ax0[3] = a[3];
  assign ax0[4] = a[4];
  assign ax0[5] = a[5];
  assign ax0[6] = a[6];
  assign ax0[7] = a[7];
  wire [7:0] ax1;
  assign ax1[0] = a[7];
  assign ax1[1] = a[0];
  assign ax1[2] = a[1] ^ a[7];
  assign ax1[3] = a[2] ^ a[7];
  assign ax1[4] = a[3] ^ a[7];
  assign ax1[5] = a[4];
  assign ax1[6] = a[5];
  assign ax1[7] = a[6];
  wire [7:0] ax2;
  assign ax2[0] = a[6];
  assign ax2[1] = a[7];
  assign ax2[2] = a[0] ^ a[6];
  assign ax2[3] = a[1] ^ a[6] ^ a[7];
  assign ax2[4] = a[2] ^ a[6] ^ a[7];
  assign ax2[5] = a[3] ^ a[7];
  assign ax2[6] = a[4];
  assign ax2[7] = a[5];
  wire [7:0] ax3;
  assign ax3[0] = a[5];
  assign ax3[1] = a[6];
  assign ax3[2] = a[5] ^ a[7];
  assign ax3[3] = a[0] ^ a[5] ^ a[6];
  assign ax3[4] = a[1] ^ a[5] ^ a[6] ^ a[7];
  assign ax3[5] = a[2] ^ a[6] ^ a[7];
  assign ax3[6] = a[3] ^ a[7];
  assign ax3[7] = a[4];
  wire [7:0] ax4;
  assign ax4[0] = a[4];
  assign ax4[1] = a[5];
  assign ax4[2] = a[4] ^ a[6];
  assign ax4[3] = a[4] ^ a[5] ^ a[7];
  assign ax4[4] = a[0] ^ a[4] ^ a[5] ^ a[6];
  assign ax4[5] = a[1] ^ a[5] ^ a[6] ^ a[7];
  assign ax4[6] = a[2] ^ a[6] ^ a[7];
  assign ax4[7] = a[3] ^ a[7];
  wire [7:0] ax5;
  assign ax5[0] = a[3] ^ a[7];
  assign ax5[1] = a[4];
  assign ax5[2] = a[3] ^ a[5] ^ a[7];
  assign ax5[3] = a[3] ^ a[4] ^ a[6] ^ a[7];
  assign ax5[4] = a[3] ^ a[4] ^ a[5];
  assign ax5[5] = a[0] ^ a[4] ^ a[5] ^ a[6];
  assign ax5[6] = a[1] ^ a[5] ^ a[6] ^ a[7];
  assign ax5[7] = a[2] ^ a[6] ^ a[7];
  wire [7:0] ax6;
  assign ax6[0] = a[2] ^ a[6] ^ a[7];
  assign ax6[1] = a[3] ^ a[7];
  assign ax6[2] = a[2] ^ a[4] ^ a[6] ^ a[7];
  assign ax6[3] = a[2] ^ a[3] ^ a[5] ^ a[6];
  assign ax6[4] = a[2] ^ a[3] ^ a[4];
  assign ax6[5] = a[3] ^ a[4] ^ a[5];
  assign ax6[6] = a[0] ^ a[4] ^ a[5] ^ a[6];
  assign ax6[7] = a[1] ^ a[5] ^ a[6] ^ a[7];
  wire [7:0] ax7;
  assign ax7[0] = a[1] ^ a[5] ^ a[6] ^ a[7];
  assign ax7[1] = a[2] ^ a[6] ^ a[7];
  assign ax7[2] = a[1] ^ a[3] ^ a[5] ^ a[6];
  assign ax7[3] = a[1] ^ a[2] ^ a[4] ^ a[5];
  assign ax7[4] = a[1] ^ a[2] ^ a[3] ^ a[7];
  assign ax7[5] = a[2] ^ a[3] ^ a[4];
  assign ax7[6] = a[3] ^ a[4] ^ a[5];
  assign ax7[7] = a[0] ^ a[4] ^ a[5] ^ a[6];
  wire p0_0 = (ax0[0] & b[0]) ^ (ax1[0] & b[1]);
  wire p0_1 = (ax2[0] & b[2]) ^ (ax3[0] & b[3]);
  wire p0_2 = (ax4[0] & b[4]) ^ (ax5[0] & b[5]);
  wire p0_3 = (ax6[0] & b[6]) ^ (ax7[0] & b[7]);
  assign y[0] = p0_0 ^ p0_1 ^ p0_2 ^ p0_3;
  wire p1_0 = (ax0[1] & b[0]) ^ (ax1[1] & b[1]);
  wire p1_1 = (ax2[1] & b[2]) ^ (ax3[1] & b[3]);
  wire p1_2 = (ax4[1] & b[4]) ^ (ax5[1] & b[5]);
  wire p1_3 = (ax6[1] & b[6]) ^ (ax7[1] & b[7]);
  assign y[1] = p1_0 ^ p1_1 ^ p1_2 ^ p1_3;
  wire p2_0 = (ax0[2] & b[0]) ^ (ax1[2] & b[1]);
  wire p2_1 = (ax2[2] & b[2]) ^ (ax3[2] & b[3]);
  wire p2_2 = (ax4[2] & b[4]) ^ (ax5[2] & b[5]);
  wire p2_3 = (ax6[2] & b[6]) ^ (ax7[2] & b[7]);
  assign y[2] = p2_0 ^ p2_1 ^ p2_2 ^ p2_3;
  wire p3_0 = (ax0[3] & b[0]) ^ (ax1[3] & b[1]);
  wire p3_1 = (ax2[3] & b[2]) ^ (ax3[3] & b[3]);
  wire p3_2 = (ax4[3] & b[4]) ^ (ax5[3] & b[5]);
  wire p3_3 = (ax6[3] & b[6]) ^ (ax7[3] & b[7]);
  assign y[3] = p3_0 ^ p3_1 ^ p3_2 ^ p3_3;
  wire p4_0 = (ax0[4] & b[0]) ^ (ax1[4] & b[1]);
  wire p4_1 = (ax2[4] & b[2]) ^ (ax3[4] & b[3]);
  wire p4_2 = (ax4[4] & b[4]) ^ (ax5[4] & b[5]);
  wire p4_3 = (ax6[4] & b[6]) ^ (ax7[4] & b[7]);
  assign y[4] = p4_0 ^ p4_1 ^ p4_2 ^ p4_3;
  wire p5_0 = (ax0[5] & b[0]) ^ (ax1[5] & b[1]);
  wire p5_1 = (ax2[5] & b[2]) ^ (ax3[5] & b[3]);
  wire p5_2 = (ax4[5] & b[4]) ^ (ax5[5] & b[5]);
  wire p5_3 = (ax6[5] & b[6]) ^ (ax7[5] & b[7]);
  assign y[5] = p5_0 ^ p5_1 ^ p5_2 ^ p5_3;
  wire p6_0 = (ax0[6] & b[0]) ^ (ax1[6] & b[1]);
  wire p6_1 = (ax2[6] & b[2]) ^ (ax3[6] & b[3]);
  wire p6_2 = (ax4[6] & b[4]) ^ (ax5[6] & b[5]);
  wire p6_3 = (ax6[6] & b[6]) ^ (ax7[6] & b[7]);
  assign y[6] = p6_0 ^ p6_1 ^ p6_2 ^ p6_3;
  wire p7_0 = (ax0[7] & b[0]) ^ (ax1[7] & b[1]);
  wire p7_1 = (ax2[7] & b[2]) ^ (ax3[7] & b[3]);
  wire p7_2 = (ax4[7] & b[4]) ^ (ax5[7] & b[5]);
  wire p7_3 = (ax6[7] & b[6]) ^ (ax7[7] & b[7]);
  assign y[7] = p7_0 ^ p7_1 ^ p7_2 ^ p7_3;
endmodule


module rs_block_ram (
    input  wire       clk,
    input  wire       we,
    input  wire [7:0] waddr,
    input  wire [7:0] wdata,
    input  wire [7:0] raddr,
    output reg  [7:0] rdata
);
    (* ram_style = "block" *) reg [7:0] mem [0:255];

    always @(posedge clk) begin
        rdata <= mem[raddr];
    end

    always @(posedge clk) begin
        if (we)
            mem[waddr] <= wdata;
    end
endmodule

// Compact, sequential RS(204,188) architecture for resource/timing benchmarking.
//
// Two GF(256) multipliers separate coefficient and feedback operations.
// Sixteen constant-factor XOR networks update all syndromes per accepted byte.
// The serialized later phases retain the budget for the ~25.2 Mbit/s
// post-Viterbi worst-case stream considered by this repository.
//
// The shortened-code position convention and final Forney correction mapping
// still require bit-exact validation against ARIB test vectors before this
// block can be called production decoder RTL. The arithmetic/state/storage
// structure is complete enough for the intended LUT/BSRAM/Fmax comparison.
module rs204_188_compact (
    input  wire       clk,
    input  wire       resetn,
    input  wire       in_valid,
    output wire       in_ready,
    input  wire [7:0] in_byte,
    output reg        out_valid,
    output reg [7:0]  out_byte,
    output reg        block_fail
);
    localparam ST_INPUT          = 6'd0;
    localparam ST_BM_INIT        = 6'd2;
    localparam ST_BM_START       = 6'd3;
    localparam ST_BM_DISC        = 6'd4;
    localparam ST_BM_CHECK       = 6'd5;
    localparam ST_INV_SQUARE     = 6'd6;
    localparam ST_INV_MUL        = 6'd7;
    localparam ST_BM_COEF        = 6'd8;
    localparam ST_BM_UPDATE      = 6'd9;
    localparam ST_BM_POST        = 6'd10;
    localparam ST_OMEGA_INIT     = 6'd11;
    localparam ST_OMEGA_ACC      = 6'd12;
    localparam ST_OMEGA_STORE    = 6'd13;
    localparam ST_CHIEN_INIT     = 6'd14;
    localparam ST_CHIEN_EVAL     = 6'd15;
    localparam ST_CHIEN_CHECK    = 6'd16;
    localparam ST_CHIEN_NEXT     = 6'd17;
    localparam ST_FORNEY_INIT    = 6'd18;
    localparam ST_FORNEY_OMEGA   = 6'd19;
    localparam ST_FORNEY_X2      = 6'd20;
    localparam ST_FORNEY_D0      = 6'd21;
    localparam ST_FORNEY_D1      = 6'd22;
    localparam ST_FORNEY_D2      = 6'd23;
    localparam ST_FORNEY_MAG     = 6'd24;
    localparam ST_FORNEY_READ    = 6'd25;
    localparam ST_FORNEY_WRITE   = 6'd26;
    localparam ST_OUTPUT         = 6'd27;
    localparam ST_BLOCK_RESET    = 6'd28;
    localparam ST_FORNEY_PRIME = 6'd30;
    localparam ST_INV_ADDRESS    = 6'd29;

    reg [5:0] state;

    reg [7:0] synd [0:15];
    reg [7:0] lambda [0:8];
    reg [7:0] bpoly [0:8];
    reg [7:0] temp_poly [0:8];
    (* ram_style="block" *) reg [7:0] omega_mem [0:15];
    reg [7:0] omega_top;

    (* ram_style="block" *) reg [15:0] error_mem [0:7];

    reg [7:0] byte_count;
    reg syndrome_nonzero;

    reg [3:0] bm_n;
    reg [3:0] bm_i;
    reg [3:0] bm_l;
    reg [3:0] bm_m;
    reg [3:0] update_i;
    reg [7:0] discrepancy;
    reg [7:0] bval;
    reg [7:0] coef;

    reg [7:0] inv_acc;
    reg [3:0] inv_bit;
    reg inv_mode; // 0=BM division, 1=Forney derivative inversion

    reg [3:0] omega_j;
    reg [3:0] omega_i;
    reg [7:0] omega_acc;

    reg [7:0] chien_x;
    reg [7:0] chien_acc;
    reg [7:0] chien_top;
    reg [3:0] chien_k;
    reg [7:0] chien_pos;
    reg [3:0] error_count;

    reg [3:0] error_i;
    reg [7:0] forney_acc;
    reg [3:0] forney_k;
    reg [7:0] omega_value;
    reg [7:0] x2;
    reg [7:0] deriv_acc;
    reg [7:0] magnitude;
    reg [7:0] corrected_q;

    reg [7:0] out_index;
    reg       out_primed;

    reg       ram_we;
    reg [7:0] ram_waddr;
    reg [7:0] ram_wdata;
    reg [7:0] ram_raddr;
    wire [7:0] ram_rdata;

    reg [7:0] coefficient_a, coefficient_b, feedback_a, feedback_b;
    wire [7:0] coefficient_y, feedback_y;

    // Prefetch independent coefficients during the preceding FSM cycle. This
    // separates the array selection network from the shared GF arithmetic,
    // without adding cycles to syndrome, BM, Chien or Forney processing.
    reg [7:0] lambda_q, omega_read_q;
    reg omega_empty_q;
    wire [7:0] omega_q=omega_empty_q?8'd0:omega_read_q;
    reg [15:0] error_read_q;
    reg [2:0] error_prefetch_index;
    reg [7:0] error_x_q,error_pos_q;
    function [3:0] onehot_address;
        input [15:0] selection;
        integer address_bit;
        begin
            onehot_address=0;
            for(address_bit=0;address_bit<16;address_bit=address_bit+1)
                onehot_address=onehot_address | ({4{selection[address_bit]}} & address_bit[3:0]);
        end
    endfunction
    reg [15:0] synd_select, omega_select, omega_write;
    reg [8:0] lambda_select, bpoly_select, lambda_write;
    reg [7:0] synd_operand, lambda_operand, bpoly_operand;

    // Registered read, no asynchronous reset: infer one Gowin BSRAM ROM.
    (* ram_style = "block" *) reg [7:0] inverse_rom [0:255];
    reg [7:0] inverse_q;
    wire [7:0] inverse_address = (state == ST_INV_ADDRESS) ?
        coefficient_y : bval;
    initial begin
        inverse_rom[0] = 8'h00;
        inverse_rom[1] = 8'h01;
        inverse_rom[2] = 8'h8e;
        inverse_rom[3] = 8'hf4;
        inverse_rom[4] = 8'h47;
        inverse_rom[5] = 8'ha7;
        inverse_rom[6] = 8'h7a;
        inverse_rom[7] = 8'hba;
        inverse_rom[8] = 8'had;
        inverse_rom[9] = 8'h9d;
        inverse_rom[10] = 8'hdd;
        inverse_rom[11] = 8'h98;
        inverse_rom[12] = 8'h3d;
        inverse_rom[13] = 8'haa;
        inverse_rom[14] = 8'h5d;
        inverse_rom[15] = 8'h96;
        inverse_rom[16] = 8'hd8;
        inverse_rom[17] = 8'h72;
        inverse_rom[18] = 8'hc0;
        inverse_rom[19] = 8'h58;
        inverse_rom[20] = 8'he0;
        inverse_rom[21] = 8'h3e;
        inverse_rom[22] = 8'h4c;
        inverse_rom[23] = 8'h66;
        inverse_rom[24] = 8'h90;
        inverse_rom[25] = 8'hde;
        inverse_rom[26] = 8'h55;
        inverse_rom[27] = 8'h80;
        inverse_rom[28] = 8'ha0;
        inverse_rom[29] = 8'h83;
        inverse_rom[30] = 8'h4b;
        inverse_rom[31] = 8'h2a;
        inverse_rom[32] = 8'h6c;
        inverse_rom[33] = 8'hed;
        inverse_rom[34] = 8'h39;
        inverse_rom[35] = 8'h51;
        inverse_rom[36] = 8'h60;
        inverse_rom[37] = 8'h56;
        inverse_rom[38] = 8'h2c;
        inverse_rom[39] = 8'h8a;
        inverse_rom[40] = 8'h70;
        inverse_rom[41] = 8'hd0;
        inverse_rom[42] = 8'h1f;
        inverse_rom[43] = 8'h4a;
        inverse_rom[44] = 8'h26;
        inverse_rom[45] = 8'h8b;
        inverse_rom[46] = 8'h33;
        inverse_rom[47] = 8'h6e;
        inverse_rom[48] = 8'h48;
        inverse_rom[49] = 8'h89;
        inverse_rom[50] = 8'h6f;
        inverse_rom[51] = 8'h2e;
        inverse_rom[52] = 8'ha4;
        inverse_rom[53] = 8'hc3;
        inverse_rom[54] = 8'h40;
        inverse_rom[55] = 8'h5e;
        inverse_rom[56] = 8'h50;
        inverse_rom[57] = 8'h22;
        inverse_rom[58] = 8'hcf;
        inverse_rom[59] = 8'ha9;
        inverse_rom[60] = 8'hab;
        inverse_rom[61] = 8'h0c;
        inverse_rom[62] = 8'h15;
        inverse_rom[63] = 8'he1;
        inverse_rom[64] = 8'h36;
        inverse_rom[65] = 8'h5f;
        inverse_rom[66] = 8'hf8;
        inverse_rom[67] = 8'hd5;
        inverse_rom[68] = 8'h92;
        inverse_rom[69] = 8'h4e;
        inverse_rom[70] = 8'ha6;
        inverse_rom[71] = 8'h04;
        inverse_rom[72] = 8'h30;
        inverse_rom[73] = 8'h88;
        inverse_rom[74] = 8'h2b;
        inverse_rom[75] = 8'h1e;
        inverse_rom[76] = 8'h16;
        inverse_rom[77] = 8'h67;
        inverse_rom[78] = 8'h45;
        inverse_rom[79] = 8'h93;
        inverse_rom[80] = 8'h38;
        inverse_rom[81] = 8'h23;
        inverse_rom[82] = 8'h68;
        inverse_rom[83] = 8'h8c;
        inverse_rom[84] = 8'h81;
        inverse_rom[85] = 8'h1a;
        inverse_rom[86] = 8'h25;
        inverse_rom[87] = 8'h61;
        inverse_rom[88] = 8'h13;
        inverse_rom[89] = 8'hc1;
        inverse_rom[90] = 8'hcb;
        inverse_rom[91] = 8'h63;
        inverse_rom[92] = 8'h97;
        inverse_rom[93] = 8'h0e;
        inverse_rom[94] = 8'h37;
        inverse_rom[95] = 8'h41;
        inverse_rom[96] = 8'h24;
        inverse_rom[97] = 8'h57;
        inverse_rom[98] = 8'hca;
        inverse_rom[99] = 8'h5b;
        inverse_rom[100] = 8'hb9;
        inverse_rom[101] = 8'hc4;
        inverse_rom[102] = 8'h17;
        inverse_rom[103] = 8'h4d;
        inverse_rom[104] = 8'h52;
        inverse_rom[105] = 8'h8d;
        inverse_rom[106] = 8'hef;
        inverse_rom[107] = 8'hb3;
        inverse_rom[108] = 8'h20;
        inverse_rom[109] = 8'hec;
        inverse_rom[110] = 8'h2f;
        inverse_rom[111] = 8'h32;
        inverse_rom[112] = 8'h28;
        inverse_rom[113] = 8'hd1;
        inverse_rom[114] = 8'h11;
        inverse_rom[115] = 8'hd9;
        inverse_rom[116] = 8'he9;
        inverse_rom[117] = 8'hfb;
        inverse_rom[118] = 8'hda;
        inverse_rom[119] = 8'h79;
        inverse_rom[120] = 8'hdb;
        inverse_rom[121] = 8'h77;
        inverse_rom[122] = 8'h06;
        inverse_rom[123] = 8'hbb;
        inverse_rom[124] = 8'h84;
        inverse_rom[125] = 8'hcd;
        inverse_rom[126] = 8'hfe;
        inverse_rom[127] = 8'hfc;
        inverse_rom[128] = 8'h1b;
        inverse_rom[129] = 8'h54;
        inverse_rom[130] = 8'ha1;
        inverse_rom[131] = 8'h1d;
        inverse_rom[132] = 8'h7c;
        inverse_rom[133] = 8'hcc;
        inverse_rom[134] = 8'he4;
        inverse_rom[135] = 8'hb0;
        inverse_rom[136] = 8'h49;
        inverse_rom[137] = 8'h31;
        inverse_rom[138] = 8'h27;
        inverse_rom[139] = 8'h2d;
        inverse_rom[140] = 8'h53;
        inverse_rom[141] = 8'h69;
        inverse_rom[142] = 8'h02;
        inverse_rom[143] = 8'hf5;
        inverse_rom[144] = 8'h18;
        inverse_rom[145] = 8'hdf;
        inverse_rom[146] = 8'h44;
        inverse_rom[147] = 8'h4f;
        inverse_rom[148] = 8'h9b;
        inverse_rom[149] = 8'hbc;
        inverse_rom[150] = 8'h0f;
        inverse_rom[151] = 8'h5c;
        inverse_rom[152] = 8'h0b;
        inverse_rom[153] = 8'hdc;
        inverse_rom[154] = 8'hbd;
        inverse_rom[155] = 8'h94;
        inverse_rom[156] = 8'hac;
        inverse_rom[157] = 8'h09;
        inverse_rom[158] = 8'hc7;
        inverse_rom[159] = 8'ha2;
        inverse_rom[160] = 8'h1c;
        inverse_rom[161] = 8'h82;
        inverse_rom[162] = 8'h9f;
        inverse_rom[163] = 8'hc6;
        inverse_rom[164] = 8'h34;
        inverse_rom[165] = 8'hc2;
        inverse_rom[166] = 8'h46;
        inverse_rom[167] = 8'h05;
        inverse_rom[168] = 8'hce;
        inverse_rom[169] = 8'h3b;
        inverse_rom[170] = 8'h0d;
        inverse_rom[171] = 8'h3c;
        inverse_rom[172] = 8'h9c;
        inverse_rom[173] = 8'h08;
        inverse_rom[174] = 8'hbe;
        inverse_rom[175] = 8'hb7;
        inverse_rom[176] = 8'h87;
        inverse_rom[177] = 8'he5;
        inverse_rom[178] = 8'hee;
        inverse_rom[179] = 8'h6b;
        inverse_rom[180] = 8'heb;
        inverse_rom[181] = 8'hf2;
        inverse_rom[182] = 8'hbf;
        inverse_rom[183] = 8'haf;
        inverse_rom[184] = 8'hc5;
        inverse_rom[185] = 8'h64;
        inverse_rom[186] = 8'h07;
        inverse_rom[187] = 8'h7b;
        inverse_rom[188] = 8'h95;
        inverse_rom[189] = 8'h9a;
        inverse_rom[190] = 8'hae;
        inverse_rom[191] = 8'hb6;
        inverse_rom[192] = 8'h12;
        inverse_rom[193] = 8'h59;
        inverse_rom[194] = 8'ha5;
        inverse_rom[195] = 8'h35;
        inverse_rom[196] = 8'h65;
        inverse_rom[197] = 8'hb8;
        inverse_rom[198] = 8'ha3;
        inverse_rom[199] = 8'h9e;
        inverse_rom[200] = 8'hd2;
        inverse_rom[201] = 8'hf7;
        inverse_rom[202] = 8'h62;
        inverse_rom[203] = 8'h5a;
        inverse_rom[204] = 8'h85;
        inverse_rom[205] = 8'h7d;
        inverse_rom[206] = 8'ha8;
        inverse_rom[207] = 8'h3a;
        inverse_rom[208] = 8'h29;
        inverse_rom[209] = 8'h71;
        inverse_rom[210] = 8'hc8;
        inverse_rom[211] = 8'hf6;
        inverse_rom[212] = 8'hf9;
        inverse_rom[213] = 8'h43;
        inverse_rom[214] = 8'hd7;
        inverse_rom[215] = 8'hd6;
        inverse_rom[216] = 8'h10;
        inverse_rom[217] = 8'h73;
        inverse_rom[218] = 8'h76;
        inverse_rom[219] = 8'h78;
        inverse_rom[220] = 8'h99;
        inverse_rom[221] = 8'h0a;
        inverse_rom[222] = 8'h19;
        inverse_rom[223] = 8'h91;
        inverse_rom[224] = 8'h14;
        inverse_rom[225] = 8'h3f;
        inverse_rom[226] = 8'he6;
        inverse_rom[227] = 8'hf0;
        inverse_rom[228] = 8'h86;
        inverse_rom[229] = 8'hb1;
        inverse_rom[230] = 8'he2;
        inverse_rom[231] = 8'hf1;
        inverse_rom[232] = 8'hfa;
        inverse_rom[233] = 8'h74;
        inverse_rom[234] = 8'hf3;
        inverse_rom[235] = 8'hb4;
        inverse_rom[236] = 8'h6d;
        inverse_rom[237] = 8'h21;
        inverse_rom[238] = 8'hb2;
        inverse_rom[239] = 8'h6a;
        inverse_rom[240] = 8'he3;
        inverse_rom[241] = 8'he7;
        inverse_rom[242] = 8'hb5;
        inverse_rom[243] = 8'hea;
        inverse_rom[244] = 8'h03;
        inverse_rom[245] = 8'h8f;
        inverse_rom[246] = 8'hd3;
        inverse_rom[247] = 8'hc9;
        inverse_rom[248] = 8'h42;
        inverse_rom[249] = 8'hd4;
        inverse_rom[250] = 8'he8;
        inverse_rom[251] = 8'h75;
        inverse_rom[252] = 8'h7f;
        inverse_rom[253] = 8'hff;
        inverse_rom[254] = 8'h7e;
        inverse_rom[255] = 8'hfd;
    end
    always @(posedge clk) inverse_q <= inverse_rom[inverse_address];


    wire chien_finish = ((state == ST_CHIEN_EVAL) && (chien_k == 0)) ||
                         (state == ST_CHIEN_CHECK);
    wire [7:0] chien_result = (state == ST_CHIEN_CHECK) ?
        chien_acc : (feedback_y ^ lambda_q);
    // Captured before the first position; no extra coefficient-array mux.
    always @(posedge clk)
        if (state == ST_CHIEN_INIT) chien_top <= lambda_q;
    reg bm_promote, bm_degree_overflow;
    reg [4:0] bm_next_degree;
    always @(posedge clk) begin
        if (state == ST_BM_START) begin
            bm_promote <= ({1'b0, bm_l} << 1) <= {1'b0, bm_n};
            bm_next_degree <= {1'b0, bm_n} + 5'd1 - {1'b0, bm_l};
            bm_degree_overflow <= ({1'b0, bm_n} + 5'd1) > ({1'b0, bm_l} + 5'd8);
        end
    end
    reg [8:0] bm_m_mask, degree_mask;
    reg [15:0] bm_n_mask, omega_next_mask;
    always @(posedge clk) begin
        bm_m_mask <= 9'd1 << bm_m;
        bm_n_mask <= 16'd1 << bm_n;
        omega_next_mask <= 16'd1 << (omega_j + 5'd1);
        degree_mask <= 9'd1 << bm_l;
    end
    integer read_slot;
    always @* begin
        synd_operand = 0; lambda_operand = 0;
        bpoly_operand = 0;
        for (read_slot=0; read_slot<16; read_slot=read_slot+1) begin
            synd_operand = synd_operand | (synd[read_slot] & {8{synd_select[read_slot]}});
        end
        for (read_slot=0; read_slot<9; read_slot=read_slot+1) begin
            lambda_operand = lambda_operand | (lambda[read_slot] & {8{lambda_select[read_slot]}});
            bpoly_operand = bpoly_operand | (bpoly[read_slot] & {8{bpoly_select[read_slot]}});
        end
    end

    // Decode the NEXT cycle's prefetch selection ahead of the array read.
    // Recurrences shift a one-hot mask, avoiding subtract/decode/MUX chains.
    // Empty masks are speculative addresses which the FSM does not consume.
    always @(posedge clk) begin
        synd_select <= 16'd1;
        lambda_select <= 9'd1;
        bpoly_select <= 9'd1;
        omega_select <= 16'h4000;
        case (state)
            ST_BM_INIT: begin
                synd_select <= 16'd0;
                lambda_select <= 9'd2;
            end
            ST_BM_START: begin
                synd_select <= synd_select >> 1;
                lambda_select <= 9'd4;
            end
            ST_BM_DISC: begin
                synd_select <= synd_select >> 1;
                lambda_select <= lambda_select << 1;
            end
            ST_BM_CHECK: begin
                synd_select <= (bm_n == 15) ? 16'd1 : (bm_n_mask);
                lambda_select <= (discrepancy != 0) ? (bm_m_mask) : ((bm_n == 15) ? 9'd1 : 9'd2);
            end
            ST_INV_SQUARE, ST_INV_MUL:
                lambda_select <= bm_m_mask;
            ST_BM_COEF: begin
                lambda_select <= lambda_select << 1;
                bpoly_select <= 9'd2;
            end
            ST_BM_UPDATE: begin
                lambda_select <= lambda_select << 1;
                bpoly_select <= bpoly_select << 1;
            end
            ST_BM_POST: begin
                synd_select <= (bm_n == 15) ? 16'd1 : (bm_n_mask);
                lambda_select <= (bm_n == 15) ? 9'd1 : 9'd2;
            end
            ST_OMEGA_INIT: begin
                synd_select <= 16'd0;
                lambda_select <= 9'd2;
            end
            ST_OMEGA_ACC: begin
                if ((omega_i <= bm_l) && (omega_i <= omega_j)) begin
                    synd_select <= synd_select >> 1;
                    lambda_select <= lambda_select << 1;
                end else begin
                    synd_select <= omega_next_mask;
                    lambda_select <= (omega_j == 15) ? (degree_mask) : 9'd1;
                end
            end
            ST_OMEGA_STORE: begin
                synd_select <= synd_select >> 1;
                lambda_select <= (omega_j == 15) ? (lambda_select >> 1) : 9'd2;
            end
            ST_CHIEN_INIT: begin
                lambda_select <= (bm_l <= 1) ? 9'd1 : (lambda_select >> 1);
            end
            ST_CHIEN_EVAL: begin
                // q receives lambda[0] during k=1; simultaneously select
                // the first coefficient of the next position for k=0.
                if (bm_l <= 1) lambda_select <= 9'd1;
                else if (chien_k == 1) lambda_select <= (degree_mask) >> 1;
                else lambda_select <= lambda_select >> 1;
            end
            ST_CHIEN_CHECK: lambda_select <= 9'd1;
            ST_FORNEY_INIT, ST_FORNEY_WRITE: omega_select <= 16'h2000;
            ST_FORNEY_OMEGA: begin
                omega_select <= omega_select >> 1;
                lambda_select <= (forney_k == 0) ? 9'd32 : 9'd128;
            end
            ST_FORNEY_X2: lambda_select <= 9'd8;
            ST_FORNEY_D0: lambda_select <= 9'd2;
            default: begin end
        endcase
        if (state == ST_BM_COEF) lambda_write <= lambda_select;
        else if (state == ST_BM_UPDATE) lambda_write <= lambda_write << 1;
        if (state == ST_OMEGA_INIT) omega_write <= 16'd1;
        else if (state == ST_OMEGA_STORE) omega_write <= omega_write << 1;
    end

    // These registers need no reset: every consumer has a preceding prefetch
    // state. Out-of-range speculative reads are discarded by the FSM.
    always @(posedge clk) begin
        lambda_q <= lambda_operand;
        omega_read_q <= omega_mem[onehot_address(omega_select)];
        omega_empty_q <= omega_select == 0;
        error_read_q <= error_mem[error_prefetch_index];
        if (state == ST_CHIEN_INIT) error_prefetch_index <= 0;
        if (state == ST_FORNEY_INIT) error_prefetch_index <= 1;
        if (state == ST_FORNEY_WRITE) error_prefetch_index <= error_i[2:0]+3'd2;
        if (state == ST_FORNEY_INIT || state == ST_FORNEY_WRITE) begin
            error_x_q <= error_read_q[15:8];error_pos_q <= error_read_q[7:0];
        end
    end

    // Give each coefficient a local write enable. Constant destinations avoid
    // the variable-address write shifters generated for resettable arrays.
    genvar slot;
    generate for (slot=0; slot<16; slot=slot+1) begin : g_synd_omega
        always @(posedge clk or negedge resetn) begin
            if (!resetn) begin
                synd[slot] <= 8'd0;
            end else begin
                if (state == ST_BLOCK_RESET)
                    synd[slot] <= 8'd0;
                else if ((state == ST_INPUT) && in_valid)
                    synd[slot] <= gf_constant(synd[slot], alpha_factor(slot)) ^ in_byte;
            end
        end
    end
    for (slot=0; slot<9; slot=slot+1) begin : g_polynomial
        always @(posedge clk) begin
            if (resetn) begin
                if (state == ST_BM_INIT) begin
                    lambda[slot] <= (slot == 0) ? 8'd1 : 8'd0;
                    bpoly[slot] <= (slot == 0) ? 8'd1 : 8'd0;
                    temp_poly[slot] <= 8'd0;
                end else begin
                    if ((state == ST_BM_UPDATE) && lambda_write[slot])
                        lambda[slot] <= lambda_q ^ coefficient_y;
                    if ((state == ST_BM_CHECK) && (discrepancy != 0))
                        temp_poly[slot] <= lambda[slot];
                    if ((state == ST_BM_POST) && (bm_promote))
                        bpoly[slot] <= temp_poly[slot];
                end
            end
        end
    end
    endgenerate
    always @(posedge clk) begin
        if (resetn && state == ST_OMEGA_STORE)
            omega_mem[omega_j[3:0]] <= omega_acc;
        if (resetn && state == ST_OMEGA_STORE && omega_j == 15)
            omega_top <= omega_acc;
        if (resetn && chien_finish && chien_result == 0 && error_count < 8)
            error_mem[error_count[2:0]] <= {chien_x,chien_pos};
    end


    gf256_mul u_coefficient_mul(.a(coefficient_a), .b(coefficient_b), .y(coefficient_y));
    gf256_mul u_feedback_mul(.a(feedback_a), .b(feedback_b), .y(feedback_y));

    rs_block_ram u_block_ram (
        .clk(clk),
        .we(ram_we),
        .waddr(ram_waddr),
        .wdata(ram_wdata),
        .raddr(ram_raddr),
        .rdata(ram_rdata)
    );

    // Keep the block buffer in a dedicated synchronous RAM process so Gowin
    // BSRAM inference is not destroyed by the asynchronously-reset decoder FSM.
    always @* begin
        ram_we = 1'b0;
        ram_waddr = 8'd0;
        ram_wdata = 8'd0;
        ram_raddr = 8'd0;

        if ((state == ST_INPUT) && in_valid) begin
            ram_we = 1'b1;
            ram_waddr = byte_count;
            ram_wdata = in_byte;
        end

        if ((state == ST_FORNEY_MAG) ||
            (state == ST_FORNEY_READ) ||
            (state == ST_FORNEY_WRITE)) begin
            ram_raddr = error_pos_q;
        end

        if (state == ST_FORNEY_WRITE) begin
            ram_we = 1'b1;
            ram_waddr = error_pos_q;
            ram_wdata = corrected_q ^ magnitude;
        end

        if (state == ST_OUTPUT) begin
            ram_raddr = out_primed ? (out_index + 8'd1) : out_index;
        end
    end

    function automatic [7:0] gf_xtime;
        input [7:0] x;
        begin
            gf_xtime = {x[6:0], 1'b0} ^ (8'h1d & {8{x[7]}});
        end
    endfunction

    function automatic [7:0] alpha_factor;
        input integer power;
        reg [7:0] x;
        integer i;
        begin
            x = 8'd1;
            for (i=0; i<power; i=i+1) x = gf_xtime(x);
            alpha_factor = x;
        end
    endfunction

    function automatic [7:0] gf_constant;
        input [7:0] x, factor;
        reg [7:0] shifted, product;
        integer i;
        begin
            shifted = x; product = 0;
            for (i=0; i<8; i=i+1) begin
                product = product ^ (shifted & {8{factor[i]}});
                shifted = gf_xtime(shifted);
            end
            gf_constant = product;
        end
    endfunction

    function automatic inv_exponent_bit;
        input [3:0] bit_index;
        begin
            // 254 = 8'b11111110
            inv_exponent_bit = (bit_index != 0);
        end
    endfunction

    assign in_ready = (state == ST_INPUT);

    // Separate coefficient products from Horner/inversion feedback. This
    // removes the broad array/feedback operand MUX from each multiplier input.
    // Both inputs are scheduled in existing cycles; operation count is unchanged.
    reg [7:0] coefficient_next_a, coefficient_next_b;
    reg [7:0] feedback_next_a, feedback_next_b;
    always @* begin
        coefficient_next_a = 0; coefficient_next_b = 0;
        feedback_next_a = 0; feedback_next_b = 0;
        case (state)
            ST_BM_START, ST_BM_DISC, ST_OMEGA_INIT, ST_OMEGA_ACC, ST_OMEGA_STORE: begin
                coefficient_next_a = lambda_operand; coefficient_next_b = synd_operand;
            end
            ST_FORNEY_D2: begin
                // For first root b=0, magnitude = Omega(x)/(Lambda'(x)*x).
                coefficient_next_a = feedback_y ^ lambda_q;
                coefficient_next_b = error_x_q;
            end
            ST_BM_COEF: begin
                coefficient_next_a = coefficient_y; coefficient_next_b = bpoly[0];
            end
            ST_BM_UPDATE: begin
                coefficient_next_a = coef; coefficient_next_b = bpoly_operand;
            end
            ST_INV_SQUARE: begin
                if (!inv_mode) begin
                    coefficient_next_a = discrepancy; coefficient_next_b = inverse_q;
                end
            end
            default: begin end
        endcase
        case (state)
            ST_BM_CHECK, ST_FORNEY_D2: begin
                feedback_next_a = 1; feedback_next_b = 1;
            end
            ST_INV_SQUARE: begin
                if (inv_mode) begin
                    feedback_next_a = omega_value; feedback_next_b = inverse_q;
                end
            end
            ST_INV_MUL: begin
                feedback_next_a = feedback_y; feedback_next_b = feedback_y;
            end
            ST_CHIEN_INIT: begin
                feedback_next_a = lambda_q; feedback_next_b = alpha_factor(52);
            end
            ST_CHIEN_EVAL: begin
                if (chien_k == 0) begin
                    feedback_next_a = chien_top;
                    feedback_next_b = gf_xtime(chien_x);
                end else begin
                    feedback_next_a = feedback_y ^ lambda_q;
                    feedback_next_b = chien_x;
                end
            end
            ST_FORNEY_INIT: begin
                feedback_next_a = omega_top; feedback_next_b = error_read_q[15:8];
            end
            ST_FORNEY_OMEGA: begin
                if (forney_k == 0) begin
                    feedback_next_a = error_x_q; feedback_next_b = error_x_q;
                end else begin
                    feedback_next_a = feedback_y ^ omega_q; feedback_next_b = error_x_q;
                end
            end
            ST_FORNEY_X2: begin
                feedback_next_a = lambda_q; feedback_next_b = feedback_y;
            end
            ST_FORNEY_D0, ST_FORNEY_D1: begin
                feedback_next_a = feedback_y ^ lambda_q; feedback_next_b = x2;
            end
            ST_FORNEY_WRITE: begin
                feedback_next_a = omega_top; feedback_next_b = error_read_q[15:8];
            end
            default: begin end
        endcase
    end
    always @(posedge clk) begin
        coefficient_a <= coefficient_next_a; coefficient_b <= coefficient_next_b;
        feedback_a <= feedback_next_a; feedback_b <= feedback_next_b;
    end

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            state <= ST_INPUT;
            byte_count <= 8'd0;
            syndrome_nonzero <= 1'b0;
            out_valid <= 1'b0;
            out_byte <= 8'd0;
            block_fail <= 1'b0;
            bm_n <= 5'd0;
            bm_i <= 4'd0;
            bm_l <= 4'd0;
            bm_m <= 4'd1;
            update_i <= 4'd0;
            discrepancy <= 8'd0;
            bval <= 8'd1;
            coef <= 8'd0;
            inv_acc <= 8'd1;
            inv_bit <= 4'd7;
            inv_mode <= 1'b0;
            omega_j <= 5'd0;
            omega_i <= 4'd0;
            omega_acc <= 8'd0;
            chien_x <= 8'd1;
            chien_acc <= 8'd0;
            chien_k <= 4'd0;
            chien_pos <= 8'd0;
            error_count <= 4'd0;
            error_i <= 4'd0;
            forney_acc <= 8'd0;
            forney_k <= 5'd0;
            omega_value <= 8'd0;
            x2 <= 8'd0;
            deriv_acc <= 8'd0;
            magnitude <= 8'd0;
            corrected_q <= 8'd0;
            out_index <= 8'd0;
            out_primed <= 1'b0;
        end else begin
            out_valid <= 1'b0;

            case (state)
                ST_INPUT: begin
                    if (in_valid) begin
                        // The sticky flag matches the original decoder: the
                        // first nonzero byte makes every running syndrome
                        // nonzero, and the flag stays set until block reset.
                        if (in_byte != 0) syndrome_nonzero <= 1'b1;
                        if (byte_count == 8'd203) begin
                            if (!(syndrome_nonzero || (in_byte != 0))) begin
                                out_index <= 8'd0;
                                out_primed <= 1'b0;
                                block_fail <= 1'b0;
                                state <= ST_OUTPUT;
                            end else begin
                                state <= ST_BM_INIT;
                            end
                        end else begin
                            byte_count <= byte_count + 8'd1;
                        end
                    end
                end

                ST_BM_INIT: begin
                    bm_l <= 4'd0;
                    bm_m <= 4'd1;
                    bval <= 8'd1;
                    bm_n <= 5'd0;
                    state <= ST_BM_START;
                end

                ST_BM_START: begin
                    discrepancy <= synd[bm_n];
                    bm_i <= 4'd1;
                    state <= ST_BM_DISC;
                end

                ST_BM_DISC: begin
                    if ((bm_i <= bm_l) && (bm_i <= bm_n)) begin
                        discrepancy <= discrepancy ^ coefficient_y;
                        bm_i <= bm_i + 4'd1;
                    end else begin
                        state <= ST_BM_CHECK;
                    end
                end

                ST_BM_CHECK: begin
                    if (discrepancy == 8'd0) begin
                        bm_m <= bm_m + 4'd1;
                        if (bm_n == 5'd15)
                            state <= ST_OMEGA_INIT;
                        else begin
                            bm_n <= bm_n + 5'd1;
                            state <= ST_BM_START;
                        end
                    end else begin
                        inv_acc <= 8'd1;
                        inv_bit <= 4'd7;
                        inv_mode <= 1'b0;
                        state <= ST_INV_SQUARE;
                    end
                end

                ST_INV_ADDRESS: state <= ST_INV_SQUARE;
                ST_INV_SQUARE: begin
                    state <= inv_mode ? ST_FORNEY_MAG : ST_BM_COEF;
                end

                ST_BM_COEF: begin
                    coef <= coefficient_y;
                    update_i <= 4'd0;
                    state <= ST_BM_UPDATE;
                end

                ST_BM_UPDATE: begin

                    if (update_i == 4'd8)
                        state <= ST_BM_POST;
                    else
                        update_i <= update_i + 4'd1;
                end

                ST_BM_POST: begin
                    if (bm_promote) begin
                        bm_l <= bm_next_degree[3:0];
                        bval <= discrepancy;
                        bm_m <= 4'd1;
                    end else begin
                        bm_m <= bm_m + 4'd1;
                    end

                    if (bm_promote && bm_degree_overflow) begin
                        // Uncorrectable degree: no correction has touched RAM.
                        block_fail <= 1'b1;
                        out_index <= 8'd0;
                        out_primed <= 1'b0;
                        state <= ST_OUTPUT;
                    end else if (bm_n == 5'd15)
                        state <= ST_OMEGA_INIT;
                    else begin
                        bm_n <= bm_n + 5'd1;
                        state <= ST_BM_START;
                    end
                end

                ST_OMEGA_INIT: begin
                    omega_j <= 5'd0;
                    omega_i <= 4'd0;
                    omega_acc <= 8'd0;
                    state <= ST_OMEGA_ACC;
                end

                ST_OMEGA_ACC: begin
                    if ((omega_i <= bm_l) && (omega_i <= omega_j)) begin
                        omega_acc <= omega_acc ^ coefficient_y;
                        omega_i <= omega_i + 4'd1;
                    end else begin
                        state <= ST_OMEGA_STORE;
                    end
                end

                ST_OMEGA_STORE: begin
                    if (omega_j == 5'd15)
                        state <= ST_CHIEN_INIT;
                    else begin
                        omega_j <= omega_j + 5'd1;
                        omega_i <= 4'd0;
                        omega_acc <= 8'd0;
                        state <= ST_OMEGA_ACC;
                    end
                end

                ST_CHIEN_INIT: begin
                    // Byte j is coefficient x^(203-j), hence locator root
                    // alpha^(j-203) = alpha^(j+52) in the 255-element group.
                    chien_x <= alpha_factor(52);
                    chien_pos <= 8'd0;
                    error_count <= 4'd0;
                    chien_acc <= lambda_q;
                    chien_k <= (bm_l == 0) ? 0 : (bm_l - 1'b1);
                    state <= (bm_l == 0) ? ST_CHIEN_CHECK : ST_CHIEN_EVAL;
                end

                ST_CHIEN_EVAL, ST_CHIEN_CHECK: begin
                    if (chien_finish) begin
                        if ((chien_result == 0) && (error_count < 8))
                            error_count <= error_count + 4'd1;
                        chien_x <= gf_xtime(chien_x);
                        if (chien_pos == 8'd203) state <= ST_FORNEY_PRIME;
                        else begin
                            chien_pos <= chien_pos + 8'd1;
                            chien_acc <= chien_top;
                            chien_k <= (bm_l == 0) ? 0 : (bm_l - 1'b1);
                            state <= (bm_l == 0) ? ST_CHIEN_CHECK : ST_CHIEN_EVAL;
                        end
                    end else begin
                        chien_acc <= feedback_y ^ lambda_q;
                        chien_k <= chien_k - 4'd1;
                    end
                end

                // One extra clock makes even a last-byte-only error's
                // freshly written table entry visible to the first read.
                ST_FORNEY_PRIME: state <= ST_FORNEY_INIT;
                ST_FORNEY_INIT: begin
                    block_fail <= (error_count != bm_l);
                    if (error_count == 0) begin
                        out_index <= 8'd0;
                        out_primed <= 1'b0;
                        state <= ST_OUTPUT;
                    end else begin
                        error_i <= 4'd0;
                        forney_acc <= omega_top;
                        forney_k <= 5'd14;
                        state <= ST_FORNEY_OMEGA;
                    end
                end

                ST_FORNEY_OMEGA: begin
                    forney_acc <= feedback_y ^ omega_q;
                    if (forney_k == 0) begin
                        omega_value <= feedback_y ^ omega_q;
                        state <= ST_FORNEY_X2;
                    end else begin
                        forney_k <= forney_k - 5'd1;
                    end
                end

                ST_FORNEY_X2: begin
                    x2 <= feedback_y;
                    deriv_acc <= lambda_q;
                    state <= ST_FORNEY_D0;
                end

                ST_FORNEY_D0: begin
                    deriv_acc <= feedback_y ^ lambda_q;
                    state <= ST_FORNEY_D1;
                end
                ST_FORNEY_D1: begin
                    deriv_acc <= feedback_y ^ lambda_q;
                    state <= ST_FORNEY_D2;
                end
                ST_FORNEY_D2: begin
                    deriv_acc <= feedback_y ^ lambda_q;
                    bval <= feedback_y ^ lambda_q;
                    inv_acc <= 8'd1;
                    inv_bit <= 4'd7;
                    inv_mode <= 1'b1;
                    state <= ST_INV_ADDRESS;
                end

                ST_FORNEY_MAG: begin
                    magnitude <= feedback_y;
                    state <= ST_FORNEY_READ;
                end

                ST_FORNEY_READ: begin
                    corrected_q <= ram_rdata;
                    state <= ST_FORNEY_WRITE;
                end

                ST_FORNEY_WRITE: begin
                    if (error_i + 1 >= error_count) begin
                        out_index <= 8'd0;
                        state <= ST_OUTPUT;
                    end else begin
                        error_i <= error_i + 4'd1;
                        forney_acc <= omega_top;
                        forney_k <= 5'd14;
                        state <= ST_FORNEY_OMEGA;
                    end
                end

                ST_OUTPUT: begin
                    if (!out_primed) begin
                        // One cycle to prime the synchronous BSRAM read port.
                        out_primed <= 1'b1;
                    end else begin
                        out_byte <= ram_rdata;
                        out_valid <= 1'b1;
                        if (out_index == 8'd187)
                            state <= ST_BLOCK_RESET;
                        else
                            out_index <= out_index + 8'd1;
                    end
                end

                default: begin
                    byte_count <= 8'd0;
                    out_primed <= 1'b0;
                            syndrome_nonzero <= 1'b0;
                    state <= ST_INPUT;
                end
            endcase
        end
    end
endmodule
