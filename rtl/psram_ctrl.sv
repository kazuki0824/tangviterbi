// Tang Nano 9K PSRAM protocol-only sizing model, with two x8 channels.
// Word-address bit 21 selects a 4 MiB die. One outstanding aligned 32-bit
// transfer shares control/serialization logic across the independent pins.
// The abstract PHY consumes one byte per clock; DDR I/O, initialization and
// calibration are excluded. No HyperRAM controller is instantiated here.
module psram_ctrl #(
    parameter integer LATENCY = 6
) (
    input wire clk,
    input wire resetn,
    input wire req,
    input wire write,
    input wire [21:0] addr,
    input wire [31:0] wdata,
    input wire [15:0] phy_rdata,
    input wire [1:0] phy_rwds,
    output reg ready,
    output wire busy,
    output reg [1:0] cs_n,
    output reg [1:0] ck_en,
    output reg [1:0] phy_oe,
    output reg [15:0] phy_wdata,
    output reg [31:0] rdata
);
    localparam IDLE = 3'd0, CA = 3'd1, WAIT_DATA = 3'd2,
               DATA = 3'd3, DONE = 3'd4;
    reg [2:0] state;
    reg selected_die, op_write, extra_latency;
    reg [47:0] ca_shift;
    reg [31:0] data_shift;
    reg [7:0] count;
    wire [1:0] selected_channel = selected_die ? 2'b10 : 2'b01;
    wire [7:0] read_byte = selected_die ? phy_rdata[15:8] : phy_rdata[7:0];
    assign busy = (state != IDLE);

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            state <= IDLE;
            selected_die <= 0;
            op_write <= 0;
            extra_latency <= 0;
            ca_shift <= 0;
            data_shift <= 0;
            count <= 0;
            ready <= 0;
            cs_n <= 2'b11;
            ck_en <= 0;
            phy_oe <= 0;
            phy_wdata <= 0;
            rdata <= 0;
        end else begin
            ready <= 0;
            case (state)
                IDLE: begin
                    if (req) begin
                        selected_die <= addr[21];
                        op_write <= write;
                        extra_latency <= phy_rwds[addr[21]];
                        // W955D8MBYA: CA[45]=0 (wrapped memory burst),
                        // CA[33:16]=local word A[20:3], CA[2:0]=A[2:0].
                        ca_shift <= {~write, 2'b00, 11'b0,
                                     addr[20:3], 13'b0, addr[2:0]};
                        data_shift <= wdata;
                        count <= 0;
                        cs_n <= addr[21] ? 2'b01 : 2'b10;
                        ck_en <= addr[21] ? 2'b10 : 2'b01;
                        phy_oe <= addr[21] ? 2'b10 : 2'b01;
                        state <= CA;
                    end
                end
                CA: begin
                    phy_wdata <= selected_die ? {ca_shift[47:40], 8'b0}
                                              : {8'b0, ca_shift[47:40]};
                    ca_shift <= ca_shift << 8;
                    if (count == 5) begin
                        count <= 0;
                        phy_oe <= 0;
                        state <= WAIT_DATA;
                    end else count <= count + 1'b1;
                end
                WAIT_DATA: begin
                    if (count == (extra_latency ? 2*LATENCY : LATENCY)-1) begin
                        count <= 0;
                        phy_oe <= op_write ? selected_channel : 2'b00;
                        state <= DATA;
                    end else count <= count + 1'b1;
                end
                DATA: begin
                    if (op_write) begin
                        phy_wdata <= selected_die ? {data_shift[31:24], 8'b0}
                                                  : {8'b0, data_shift[31:24]};
                        data_shift <= data_shift << 8;
                    end else rdata <= {rdata[23:0], read_byte};
                    if (count == 3) begin
                        count <= 0;
                        state <= DONE;
                    end else count <= count + 1'b1;
                end
                default: begin
                    cs_n <= 2'b11;
                    ck_en <= 0;
                    phy_oe <= 0;
                    ready <= 1;
                    state <= IDLE;
                end
            endcase
        end
    end
endmodule
