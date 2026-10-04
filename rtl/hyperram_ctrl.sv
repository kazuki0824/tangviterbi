module hyperram_ctrl #(
    parameter integer ADDR_W = 22,
    parameter integer LATENCY = 6
) (
    input  wire                 clk,
    input  wire                 resetn,
    input  wire                 req,
    input  wire                 write,
    input  wire [ADDR_W-1:0]    addr,
    input  wire [31:0]          wdata,
    input  wire [7:0]           phy_rdata,
    input  wire                 phy_rwds,
    output reg                  ready,
    output wire                 busy,
    output reg                  cs_n,
    output reg                  ck_en,
    output reg                  phy_oe,
    output reg [7:0]            phy_wdata,
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
    reg extra_latency;
    assign busy = (state != ST_IDLE);

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
            phy_wdata  <= 8'd0;
            rdata      <= 32'd0;
            ca_shift   <= 48'd0;
            data_shift <= 32'd0;
            count      <= 8'd0;
            op_write   <= 1'b0;
            extra_latency <= 1'b0;
        end else begin
            ready <= 1'b0;
            case (state)
                ST_IDLE: begin
                    cs_n   <= 1'b1;
                    ck_en  <= 1'b0;
                    phy_oe <= 1'b0;
                    if (req) begin
                        // addr is a WORD address (two bytes), split into
                        // upper and lower column fields in the 48-bit CA.
                        // 4K: linear burst, 22-bit word address.
                        // The 9K PSRAM has its own controller in psram_ctrl.sv.
                        ca_shift <= {~write, 1'b0, 1'b1,
                                     {(32-ADDR_W){1'b0}}, addr[ADDR_W-1:3],
                                     13'b0, addr[2:0]};
                        data_shift <= wdata;
                        op_write <= write;
                        extra_latency <= phy_rwds;
                        count <= 8'd0;
                        cs_n <= 1'b0;
                        ck_en <= 1'b1;
                        phy_oe <= 1'b1;
                        state <= ST_CA;
                    end
                end
                ST_CA: begin
                    phy_wdata <= ca_shift[47:40];
                    ca_shift <= ca_shift << 8;
                    if (count == 5) begin
                        count <= 8'd0;
                        phy_oe <= 1'b0;
                        state <= ST_WAIT;
                    end else begin
                        count <= count + 8'd1;
                    end
                end
                ST_WAIT: begin
                    if (count == (extra_latency ? 2*LATENCY : LATENCY)-1) begin
                        count <= 8'd0;
                        phy_oe <= op_write;
                        state <= ST_DATA;
                    end else begin
                        count <= count + 8'd1;
                    end
                end
                ST_DATA: begin
                    if (op_write) begin
                        phy_wdata <= data_shift[31:24];
                        data_shift <= data_shift << 8;
                    end else begin
                        rdata <= {rdata[23:0], phy_rdata};
                    end

                    if (count == 3) begin
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
