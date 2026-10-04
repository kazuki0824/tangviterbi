module hyperram_ctrl #(
    parameter integer DQ_W = 8,
    parameter integer ADDR_W = 22,
    parameter integer LATENCY = 6
) (
    input  wire                 clk,
    input  wire                 resetn,
    input  wire                 req,
    input  wire                 write,
    input  wire [ADDR_W-1:0]    addr,
    input  wire [31:0]          wdata,
    input  wire [DQ_W-1:0]      phy_rdata,
    output reg                  ready,
    output reg                  cs_n,
    output reg                  ck_en,
    output reg                  phy_oe,
    output reg [DQ_W-1:0]       phy_wdata,
    output reg [31:0]           rdata
);
    localparam ST_IDLE = 3'd0;
    localparam ST_CA   = 3'd1;
    localparam ST_WAIT = 3'd2;
    localparam ST_DATA = 3'd3;
    localparam ST_DONE = 3'd4;

    reg [2:0] state;
    reg [47:0] ca_shift;
    reg [31:0] data_shift;
    reg [7:0] count;
    reg op_write;

    // This is the protocol/control datapath only. The board-specific Gowin
    // DDR I/O PHY and calibration macro are deliberately excluded so core
    // controller overhead can be compared reproducibly with open tools.
    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            state      <= ST_IDLE;
            ready      <= 1'b0;
            cs_n       <= 1'b1;
            ck_en      <= 1'b0;
            phy_oe     <= 1'b0;
            phy_wdata  <= {DQ_W{1'b0}};
            rdata      <= 32'd0;
            ca_shift   <= 48'd0;
            data_shift <= 32'd0;
            count      <= 8'd0;
            op_write   <= 1'b0;
        end else begin
            ready <= 1'b0;
            case (state)
                ST_IDLE: begin
                    cs_n   <= 1'b1;
                    ck_en  <= 1'b0;
                    phy_oe <= 1'b0;
                    if (req) begin
                        // HyperBus-like 48-bit command/address packet.
                        ca_shift <= {~write, 2'b00, 13'b0, addr, {(32-ADDR_W){1'b0}}};
                        data_shift <= wdata;
                        op_write <= write;
                        count <= 8'd0;
                        cs_n <= 1'b0;
                        ck_en <= 1'b1;
                        phy_oe <= 1'b1;
                        state <= ST_CA;
                    end
                end
                ST_CA: begin
                    phy_wdata <= ca_shift[47 -: DQ_W];
                    ca_shift <= ca_shift << DQ_W;
                    if (count == (48 / DQ_W) - 1) begin
                        count <= 8'd0;
                        phy_oe <= 1'b0;
                        state <= ST_WAIT;
                    end else begin
                        count <= count + 8'd1;
                    end
                end
                ST_WAIT: begin
                    if (count == LATENCY-1) begin
                        count <= 8'd0;
                        phy_oe <= op_write;
                        state <= ST_DATA;
                    end else begin
                        count <= count + 8'd1;
                    end
                end
                ST_DATA: begin
                    if (op_write) begin
                        phy_wdata <= data_shift[31 -: DQ_W];
                        data_shift <= data_shift << DQ_W;
                    end else begin
                        rdata <= {rdata[31-DQ_W:0], phy_rdata};
                    end

                    if (count == (32 / DQ_W) - 1) begin
                        state <= ST_DONE;
                        count <= 8'd0;
                    end else begin
                        count <= count + 8'd1;
                    end
                end
                default: begin
                    cs_n   <= 1'b1;
                    ck_en  <= 1'b0;
                    phy_oe <= 1'b0;
                    ready  <= 1'b1;
                    state  <= ST_IDLE;
                end
            endcase
        end
    end
endmodule
