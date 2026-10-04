// Tang Nano 9K protocol-only sizing model: two independent x8 PSRAM dies.
// Each die covers 4 MiB; word-address bit 21 selects the die. Transactions
// are aligned 32-bit accesses, so the wrapped burst does not cross a boundary.
// This is not a DDR PHY or a calibrated/initialized hardware interface.
module psram_ctrl (
    input wire clk,
    input wire resetn,
    input wire req,
    input wire write,
    input wire [21:0] addr,
    input wire [31:0] wdata,
    input wire [15:0] phy_rdata,
    input wire [1:0] phy_rwds,
    output wire ready,
    output wire busy,
    output wire [1:0] cs_n,
    output wire [1:0] ck_en,
    output wire [1:0] phy_oe,
    output wire [15:0] phy_wdata,
    output wire [31:0] rdata
);
    wire [1:0] die_ready;
    wire [1:0] die_busy;
    wire [31:0] die_rdata [0:1];
    reg selected_die;

    always @(posedge clk or negedge resetn) begin
        if (!resetn)
            selected_die <= 1'b0;
        else if (req && !busy)
            selected_die <= addr[21];
    end

    genvar die;
    generate
        for (die = 0; die < 2; die = die + 1) begin : g_die
            hyperram_ctrl #(
                .ADDR_W(21), .LATENCY(6), .LINEAR_BURST(0)
            ) u_protocol (
                .clk(clk), .resetn(resetn),
                .req(req && !busy && (addr[21] == die)), .write(write),
                .addr(addr[20:0]), .wdata(wdata),
                .phy_rdata(phy_rdata[die*8 +: 8]),
                .phy_rwds(phy_rwds[die]), .ready(die_ready[die]),
                .busy(die_busy[die]),
                .cs_n(cs_n[die]), .ck_en(ck_en[die]),
                .phy_oe(phy_oe[die]), .phy_wdata(phy_wdata[die*8 +: 8]),
                .rdata(die_rdata[die])
            );
        end
    endgenerate

    assign ready = |die_ready;
    assign busy = |die_busy;
    assign rdata = die_rdata[selected_die];
endmodule
