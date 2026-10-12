#!/usr/bin/env python3
"""Measure direct BSRAM RF transport plus existing FEC partial workloads.

This is not a connected RF-to-TS receiver. FIR/sync/interleavers, FFT return,
Offload RPC where required, receiver TS integration and external IO STA remain absent. Preserve every failure.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from s3_logic_site_audit import audit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
from s3_tc8psk import source as tc_source
from s3_viterbi_traceback import generate
from s3_rs_isdb import source as rs_source
from s3_rs_syndrome_registered import source as syndrome_source


def top(mode):
    common = '''module top(input wire clk27,resetn,
 input wire spi2_sclk,spi2_cs_n,input wire[7:0] spi2_d,
 input wire spi3_sclk,spi3_cs_n,input wire[3:0] spi3_d,output wire activity);
 wire clk,unused,rst; s3_psram_clock clocks(clk27,resetn,clk,unused,rst);
 wire spi2_clock,spi3_clock;
 BUFG global2(.I(spi2_sclk),.O(spi2_clock));BUFG global3(.I(spi3_sclk),.O(spi3_clock));
 wire v,last,fault;wire[31:0] data,offset;
 s3_spi_direct_bridge bridge(clk,rst,16'd1,spi2_clock,spi2_cs_n,spi2_d,
 spi3_clock,spi3_cs_n,spi3_d,v,1'b1,data,last,offset,fault);
 reg[31:0] checksum;reg[63:0] lfsr;
 always @(posedge clk or negedge rst)
  if(!rst)begin checksum<=0;lfsr<=64'hc14fb4391aceb00c;end
  else begin
   if(v)checksum<={checksum[30:0],checksum[31]}^data;
   lfsr<={lfsr[62:0],lfsr[63]^lfsr[62]^lfsr[60]^lfsr[59]};
  end
'''
    if mode == "T":
        fec = '''wire vr,vv,bit_out,rr,rv,rf;wire[7:0] rd;
 s3_viterbi_traceback vit(clk,rst,1'b1,vr,lfsr[7:0],lfsr[15:8],vv,bit_out);
 rs204_188_compact rs(clk,rst,1'b1,rr,lfsr[23:16],rv,rd,rf);
 assign activity=^{checksum,offset,last,fault,vr,vv,bit_out,rr,rv,rd,rf};
'''
    elif mode == "S-all-RS":
        fec = '''wire mr,mv,vr,vv,rr,rv,rf;wire[35:0] costs;wire[3:0] b1;
 wire[1:0] bits_out;wire[7:0] rd;
 s3_tc8psk_metric_folded metric(clk,rst,1'b1,mr,lfsr[15:0],lfsr[31:16],mv,vr,costs,b1);
 s3_tc8psk vit(clk,rst,mv,vr,costs,b1,vv,bits_out);
 rs204_188_compact rs(clk,rst,1'b1,rr,lfsr[23:16],rv,rd,rf);
 assign activity=^{checksum,offset,last,fault,mr,mv,vv,bits_out,rr,rv,rd,rf};
'''
    else:
        fec = '''wire mr,mv,vr,vv,syready,syvalid,cr,rv,done,failed,fr,fv,ff;
 wire[35:0] costs;wire[3:0] b1,roots;wire[1:0] bits_out;wire[7:0] position;
 wire[127:0] syndromes;wire[63:0] magnitudes;
 s3_tc8psk_metric_folded metric(clk,rst,1'b1,mr,lfsr[15:0],lfsr[31:16],mv,vr,costs,b1);
 s3_tc8psk vit(clk,rst,mv,vr,costs,b1,vv,bits_out);
 s3_rs_syndrome syndrome(clk,rst,1'b1,syready,lfsr[23:16],syvalid,cr,syndromes);
 s3_rs_chien chien(clk,rst,syvalid,cr,{syndromes[71:8],8'd1},4'd8,
 rv,1'b1,position,done,1'b1,failed,roots);
 s3_rs_forney forney(clk,rst,syvalid,fr,{syndromes[71:8],8'd1},syndromes,
 roots,roots,lfsr,fv,1'b1,ff,magnitudes);
 assign activity=^{checksum,offset,last,fault,mr,mv,vv,bits_out,syready,syvalid,cr,rv,
 position,done,failed,roots,fr,fv,ff,magnitudes};
'''
    return common + fec + "endmodule\n"


def measure(mode, output, timeout, seed=1):
    b = ROOT / "build" / ("s3-direct-" + mode + (f"-seed{seed}" if seed != 1 else ""))
    b.mkdir(parents=True, exist_ok=True)
    (b / "top.sv").write_text(top(mode))
    target_mhz = 99 if mode == "S-all-RS" else 90
    clock = (ROOT / "rtl/s3_psram_clock.sv").read_text().replace(".FBDIV_SEL(10)", f".FBDIV_SEL({10 if target_mhz == 99 else 9})")
    (b / "clock.sv").write_text(clock)
    (b / "vit.sv").write_text(generate("modulo13-pipe") if mode == "T" else tc_source(True, True, 32, True))
    (b / "fec.sv").write_text(rs_source(True, True) if mode in ("T", "S-all-RS") else syndrome_source())
    sources = [ROOT / "rtl" / n for n in ("s3_async_fifo.sv", "s3_spi_rx.sv", "s3_page_guard.sv",
              "s3_page_reorder.sv", "s3_rx_page_store.sv", "s3_spi_direct_bridge.sv")]
    sources += [b / n for n in ("top.sv", "clock.sv", "vit.sv", "fec.sv")]
    if mode != "T":
        sources += [ROOT / "rtl/s3_tc8psk_metric_folded.sv"]
    if mode == "S":
        sources += [ROOT / "rtl" / n for n in ("s3_rs_chien.sv", "s3_rs_forney.sv")]
    (b / "synth.ys").write_text("read_verilog -sv " + " ".join(map(str, sources)) + "\n"
        + "synth_gowin -top top -family gw1n -nowidelut -json " + str(b / "design.json") + "\ncheck -assert\n")
    with (b / "synth.log").open("w") as log:
        subprocess.run(["yosys", "-Q", "-T", "-s", str(b / "synth.ys")], stdout=log, stderr=subprocess.STDOUT, check=True)
    module = json.loads((b / "design.json").read_text())["modules"]["top"]
    def alias(bits):
        return min((n for n, v in module["netnames"].items() if v["bits"] == bits and not n.startswith("$")), key=len)
    clocks = []
    for cell in module["cells"].values():
        if cell["type"] == "rPLL": clocks.append((alias(cell["connections"]["CLKOUT"]), target_mhz))
        if cell["type"] == "IBUF" and cell["connections"]["I"] == module["ports"]["clk27"]["bits"]:
            clocks.append((alias(cell["connections"]["O"]), 27))
        if cell["type"] == "BUFG":
            if any(cell["connections"]["I"] == other["connections"]["O"]
                   for other in module["cells"].values() if other["type"] == "IBUF"
                   and any(other["connections"]["I"] == module["ports"][p]["bits"] for p in ("spi2_sclk", "spi3_sclk"))):
                clocks.append((alias(cell["connections"]["O"]), 80))
    (b / "clocks.py").write_text("".join(f"ctx.addClock({n!r},{freq})\n" for n, freq in clocks))
    (b / "pins.cst").write_text((ROOT / "experiments/s3_spi_rx_benchmark.cst").read_text().replace('"clk"', '"clk27"'))
    base = ["nextpnr-himbaechel", "--json", str(b / "design.json"), "--device", "GW1NR-LV9QN88PC6/I5",
            "--vopt", "family=GW1N-9C", "--vopt", "cst=" + str(b / "pins.cst"), "--pre-pack", str(b / "clocks.py")]
    with (b / "pack.log").open("w") as log:
        subprocess.run(base + ["--pack-only", "--write", str(b / "packed.json")], stdout=log, stderr=subprocess.STDOUT, check=True)
    sites = audit(b / "packed.json")
    if sites["mapped_netlist_ruled_out"]:
        rc = 126
        (b / "pnr.log").write_text("Mapped netlist exceeds capacity; no placement attempted.\n")
    else:
        with (b / "pnr.log").open("w") as log:
            try:
                rc = subprocess.run(base + ["--freq", str(target_mhz), "--seed", str(seed), "--report", str(b / "pnr.json")],
                                    stdout=log, stderr=subprocess.STDOUT, timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                rc = 124
                log.write("\nP&R wall-time limit reached; timing/fit remain unknown.\n")
    pnr = json.loads((b / "pnr.json").read_text()) if (b / "pnr.json").exists() else {}
    result = {"mode": mode, "seed": seed, "tool_versions": {name: subprocess.check_output([name, "--version"], text=True, stderr=subprocess.STDOUT).strip() for name in ("yosys", "nextpnr-himbaechel")}, "logic_site_audit": sites, "CAD_exit_code": rc,
              "target_core_MHz": target_mhz, "clock_constraints": clocks, "fmax": pnr.get("fmax"), "utilization": pnr.get("utilization"),
              "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
              "scope": __doc__, "receiver_adopted": False, "whole_receiver_resources_verified": False,
              "external_IO_STA_verified": False,
              "absent": ["FIR/sync/all interleavers", "real FEC coupling", "FFT return endpoint",
                         "RS offload RPC/retention/correction integration" if mode == "S" else "receiver TS framing/output integration", "actual host credit sender", "physical IO STA"]}
    dest = output / mode
    if seed != 1: dest = dest / f"seed{seed}"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("top.sv", "clock.sv", "vit.sv", "fec.sv", "synth.ys", "pins.cst", "clocks.py"):
        (dest / name).write_bytes((b / name).read_bytes())
    for name in ("synth.log", "pack.log", "pnr.log"):
        (dest / (name + ".gz")).write_bytes(gzip.compress((b / name).read_bytes(), mtime=0))
    (dest / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"mode": mode, "sites": sites["minimum_required_logic_sites"], "exit_code": rc, "fmax": result["fmax"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("T", "S", "S-all-RS"), required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/s3-direct-stream-evidence")
    parser.add_argument("--pnr-timeout", type=int, default=180)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    measure(args.mode, args.output, args.pnr_timeout, args.seed)
