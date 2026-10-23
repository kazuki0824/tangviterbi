"""Synthesize the actual coole198669 K=7 64-ACS/traceback RTL against GW1NR-9.

Pin upstream source to 5412b61196a425179def39e030828dac978161da.
This is a single decoder with 64 ACS, NOT a three-context shared decoder.
A small survivor-memory wrapper is used; no physical RF/demapper/TS receiver.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

REF = "5412b61196a425179def39e030828dac978161da"
ROOT = Path(__file__).resolve().parents[1]
NAMES = ("BMU.v", "ACS.v", "pm_normalize.v", "traceback.v", "viterbi_core.v")

WRAPPER = r"""
module coole_probe (
    input wire clk_i, rst_an_i, frame_start_i,
    output wire [7:0] dst_wdata_o,
    output wire dst_wr_o, frame_done_o, busy_o,
    output wire [7:0] diagnostic_o
);
    wire [11:0] src_addr_o, dst_addr_o;
    wire src_rd_o;
    reg [23:0] data_q;
    wire [23:0] src_rdata_i = data_q ^ {12'd0,src_addr_o};
    always @(posedge clk_i or negedge rst_an_i)
      if(!rst_an_i) data_q <= 24'hace135;
      else if(src_rd_o) data_q <= {data_q[22:0],data_q[23]^data_q[22]^data_q[21]^data_q[16]};
    wire tb_wr_o, tb_rd_o;
    wire [5:0] tb_addr_o;
    wire [63:0] tb_wdata_o;
    reg [63:0] tb_rdata_i;
    (* ram_style="block" *) reg [63:0] survivor [0:63];
    always @(posedge clk_i) begin
        tb_rdata_i <= survivor[tb_addr_o];
        if (tb_wr_o) survivor[tb_addr_o] <= tb_wdata_o;
    end
    assign diagnostic_o = core.pm_tmp_s_0[7:0] ^ core.pm_tmp_s_31[7:0] ^
                          core.pm_tmp_s_63[7:0] ^ core.bm_s_0[7:0];
    viterbi_core #(.WIDTH_BM(9),.SRC_ADDR_W(12),.DST_ADDR_W(12),.W_TB_ADDR(6)) core (
        .clk_i(clk_i),.rst_an_i(rst_an_i),.rst_sync_i(1'b0),
        .frame_start_i(frame_start_i),
        .register_num_i({frame_start_i, data_q[3]}),.valid_polynomials_i(data_q[6:4]),
        .tail_biting_en_i(1'b0),
        .polynomial1_i(8'h79),.polynomial2_i(8'h5b),
        .polynomial3_i(8'd0),.polynomial4_i(8'd0),
        .polynomial5_i(8'd0),.polynomial6_i(8'd0),
        .infobit_length_i(12'd1024),.decoding_length_i(13'd1024),
        .src_start_addr_i(12'd0),.dst_start_addr_i(12'd0),
        .frame_done_o(frame_done_o),.busy_o(busy_o),
        .src_rd_o(src_rd_o),.src_addr_o(src_addr_o),
        .src_rdata_i(src_rdata_i),
        .dst_wr_o(dst_wr_o),.dst_addr_o(dst_addr_o),
        .dst_wdata_o(dst_wdata_o),
        .tb_wr_o(tb_wr_o),.tb_rd_o(tb_rd_o),
        .tb_addr_o(tb_addr_o),.tb_wdata_o(tb_wdata_o),.tb_rdata_i(tb_rdata_i)
    );
endmodule
"""

def run(command, *, cwd, logfile, timeout=650):
    try:
        with logfile.open("w") as out:
            p = subprocess.run(command, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, timeout=timeout)
        return p.returncode
    except subprocess.TimeoutExpired:
        with logfile.open("a") as out:
            out.write("\nTIMEOUT\n")
        return 124

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--normalize-multiple-driver", action="store_true")
    args = p.parse_args()
    source = args.source.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    result = {
        "upstream": "coole198669/viterbi_decoder",
        "commit": REF,
        "design": "64-ACS K7 rate-1/2 single context plus survivor SRAM wrapper",
        "three_context": False,
        "same_semantics_as_9k_8bit_soft": False,
        "clock_mhz_target": 108,
        "seed": 1,
        "device": "GW1NR-LV9QN88PC6/I5",
        "external_src_storage": False,
        "external_dst_storage": False,
        "external_io_STA_verified": False,
        "patched_multiple_driver": args.normalize_multiple_driver,
    }
    files = []
    for name in NAMES:
        text = (source / name).read_text()
        result.setdefault("sha256", {})[name] = hashlib.sha256(text.encode()).hexdigest()
        if name == "traceback.v" and args.normalize_multiple_driver:
            # Make the minimum obvious typo correction ONLY for diagnostics.
            # Upstream unmodified must also be tested separately.
            line = "else if(tb_counter_r==0 && rdata_valid_r==1'b1)"
            old = "if(!rst_an_i)              tb_bits_valid_r <= 0;"
            new = "if(!rst_an_i)              last_bit_load_r <= 0;"
            if text.count(line) != 1 or text.count(old) != 2:
                raise ValueError("Upstream traceback multiple driver format changed")
            begin = text.index(line)
            span = text.rfind("always@", 0, begin)
            end = text.index("end", begin) + 3
            chunk = text[span:end]
            # first block must use last_bit_load_r throughout;
            # the second block remains the tb_bits_valid_r register.
            chunk2 = chunk.replace("tb_bits_valid_r", "last_bit_load_r")
            if chunk2 == chunk or "last_bit_load_r" not in chunk2:
                raise ValueError("Did not find multiple-driver typo")
            text = text[:span] + chunk2 + text[end:]
        local = out / name
        local.write_text(text)
        files.append(local)
    wrapper = out / "coole_probe.v"
    wrapper.write_text(WRAPPER)
    ys = out / "synth.ys"
    ys.write_text(
        "read_verilog -sv " + " ".join(str(f) for f in [*files,wrapper]) + "\n"
        "hierarchy -check -top coole_probe\n"
        "synth_gowin -family gw1n -top coole_probe -nowidelut -json " + str(out/"mapped.json") + "\n"
        "check -assert\n"
    )
    result["yosys_version"] = subprocess.check_output(["yosys","-V"],text=True).strip()
    result["synth_exit"] = run(["yosys","-Q","-s",str(ys)],cwd=ROOT,logfile=out/"synth.log")
    if result["synth_exit"] == 0:
        # Pre-P&R structural census; a placer failure cannot hide synthesis area.
        mapped = json.loads((out/"mapped.json").read_text())
        modules = mapped.get("modules", {})
        top_modules = [name for name, info in modules.items() if str(info.get("attributes",{}).get("top","0")).lstrip("0") == "1"]
        # Yosys Gowin flow flattens the design; if not, preserve per-module data
        # rather than pretending a single top-only census includes child instances.
        census = {}
        for mod, info in modules.items():
            cells = info.get("cells",{})
            types = {}
            for cell in cells.values():
                name=cell.get("type","")
                types[name]=types.get(name,0)+1
            census[mod] = dict(cell_count=len(cells), types=types)
        result["mapped_top_modules"] = top_modules
        result["mapped_module_census"] = census
        result["mapped_all_modules_cell_counts"] = {
            mod: row["cell_count"] for mod,row in census.items()
        }
        top = modules.get("coole_probe",{})
        ct=census.get("coole_probe",{}).get("types",{})
        result["mapped_top_cell_types"] = ct
        result["mapped_top_logic_positions"] = ct.get("LUT4",0)+ct.get("ALU",0)
        result["mapped_top_FF_count"] = sum(v for k,v in ct.items() if k.startswith("DFF"))
        result["mapped_top_BSRAM_count"] = sum(v for k,v in ct.items() if k.startswith("DPB") or k.startswith("SP") or k == "BSRAM")
        result["mapped_top_is_flat"] = all(cell.get("type") not in modules for cell in top.get("cells",{}).values())
        result["mapped_logic_over_8640"] = bool(result["mapped_top_is_flat"] and result["mapped_top_logic_positions"] > 8640)
        result["mapped_logic_over_K7_allowance_2096"] = bool(result["mapped_top_is_flat"] and result["mapped_top_logic_positions"] > 2096)
        print("PRE-PLACE NETLIST CENSUS: "+json.dumps({
          "top":top_modules,"flat":result["mapped_top_is_flat"],
          "top_logic_positions":result["mapped_top_logic_positions"],
          "top_FFs":result["mapped_top_FF_count"],
          "top_types":ct,
          "modules":result["mapped_all_modules_cell_counts"]},sort_keys=True),flush=True)
        cst = out / "pins.cst"
        inputs = [("clk_i",52),("rst_an_i",35),("frame_start_i",25)]
        outputs = [("dst_wr_o",10),("frame_done_o",11),("busy_o",13)]
        outputs.extend((f"dst_wdata_o[{i}]",pin) for i,pin in enumerate([14,15,16,26,27,28,29,30]))
        outputs.extend((f"diagnostic_o[{i}]",pin) for i,pin in enumerate([31,32,33,34,36,37,38,40]))
        cst.write_text("".join(f'IO_LOC "{name}" {pin};\nIO_PORT "{name}" IO_TYPE=LVCMOS33;\n' for name,pin in inputs+outputs))
        cmd = ["nextpnr-himbaechel","--json",str(out/"mapped.json"),
               "--device","GW1NR-LV9QN88PC6/I5",
               "--vopt","family=GW1N-9C","--vopt",f"cst={cst}",
               "--freq","108","--seed","1","--report",str(out/"pnr.json")]
        (out/"pnr-command.json").write_text(json.dumps(cmd,indent=2))
        result["pnr_exit"] = run(cmd,cwd=ROOT,logfile=out/"pnr.log")
        log = (out/"pnr.log").read_text()
        result["route_completed"] = "Routing complete." in log
        result["errors"] = [line for line in log.splitlines() if "ERROR:" in line][-20:]
        if (out/"pnr.json").exists():
            data = json.loads((out/"pnr.json").read_text())
            u=data.get("utilization",{})
            result["utilization"] = u
            result["fmax"] = data.get("fmax",{})
            result["logic_positions"] = sum(u.get(k,{}).get("used",0) for k in ("LUT4","ALU"))
            for key in ("LUT4","ALU","DFF","BSRAM","RAM16SDP4","MULT18X18"):
                result[key] = u.get(key,{}).get("used",0)
    result["sizing_qualified"] = bool(result.get("route_completed") and result.get("pnr_exit")==0 and result.get("logic_positions",0)>500 and result.get("mapped_top_is_flat"))
    result["preplace_logic_fit_8640"] = bool(result.get("mapped_top_is_flat") and not result.get("mapped_logic_over_8640") and result.get("mapped_top_logic_positions",0)>500)
    result["instrumented_core_logic_retained"] = result.get("logic_positions",0)>500
    result["full_rate_qualified"] = False  # requires functional and service-rate validation
    (out/"summary.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))
    if not result["sizing_qualified"]:
        print("Unqualified P&R: report the failure; do not treat green workflow as a fit.",file=sys.stderr)

if __name__ == "__main__":
    main()
