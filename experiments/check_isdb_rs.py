#!/usr/bin/env python3
"""Independent systematic encoder and 0..8-byte error tests against an RTL file.

No RTL/reference-decoder reuse: encode by polynomial long division, validate
all generator roots, inject errors, and require the original 188 payload bytes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def gf(a, b):
    value = 0
    for bit in range(8):
        if (b >> bit) & 1:
            value ^= a << bit
    for bit in range(14, 7, -1):
        if (value >> bit) & 1:
            value ^= 0x11d << (bit - 8)
    return value


def encode(data):
    generator = [1]
    alpha = 1
    roots = []
    for _ in range(16):
        roots.append(alpha)
        new = [0] * (len(generator) + 1)
        for j, coefficient in enumerate(generator):
            new[j] ^= coefficient
            new[j+1] ^= gf(coefficient, alpha)
        generator = new
        alpha = gf(alpha, 2)
    remainder = list(data) + [0] * 16
    for i in range(len(data)):
        factor = remainder[i]
        for j, coefficient in enumerate(generator):
            remainder[i+j] ^= gf(factor, coefficient)
    codeword = list(data) + remainder[-16:]
    for root in roots:
        value = 0
        for symbol in codeword:
            value = gf(value, root) ^ symbol
        assert value == 0
    return codeword


def vectors(quick=False):
    rng = random.Random(0x204188)
    payload = [0x47] + [rng.randrange(256) for _ in range(187)]
    encoded = encode(payload)
    result = [("clean-random", encoded, payload), ("clean-zero", encode([0]*188), [0]*188)]
    positions = [0, 1, 51, 52, 187, 188, 202, 203] if quick else range(204)
    for pos in positions:
        noisy = encoded.copy(); noisy[pos] ^= 0xa7
        result.append((f"single-{pos}", noisy, payload))
    for count in range(2, 9):
        for trial in range(1 if quick else 8):
            noisy = encoded.copy()
            for pos in rng.sample(range(204), count):
                noisy[pos] ^= rng.randrange(1, 256)
            result.append((f"random-{count}-errors-{trial}", noisy, payload))
    return result


TB = r'''`timescale 1ns/1ps
module isdb_rs_tb;
parameter integer BLOCKS=1;
reg clk=0; always #5 clk=~clk;
reg resetn=0,in_valid=0; reg [7:0] in_byte=0;
wire ready,valid,fail; wire [7:0] data_out;
reg [7:0] received[0:BLOCKS*204-1], original[0:BLOCKS*188-1];
integer blockno,cycle,accepted,emitted,mismatch,maximum=0,warm;
rs204_188_compact dut(clk,resetn,in_valid,ready,in_byte,valid,data_out,fail);
initial begin
 $readmemh("received.hex",received); $readmemh("original.hex",original);
 for(blockno=0;blockno<BLOCKS;blockno=blockno+1) begin
  if(blockno%16==0)begin
   @(negedge clk);resetn=0;in_valid=0;
   repeat(3) @(negedge clk);resetn=1;
   // Abort dirty processing in different phases, then test a fresh codeword.
   for(warm=0;warm<204+(blockno/16)*151;warm=warm+1)begin
    in_valid=ready;in_byte=(warm*17+53)&255;
    @(posedge clk);@(negedge clk);
   end
   resetn=0;in_valid=0;
   repeat(3) @(negedge clk);resetn=1;
  end
  accepted=0;emitted=0;mismatch=0;
  for(cycle=0;cycle<4000 && (emitted<188 || !ready);cycle=cycle+1) begin
   in_valid=accepted<204;
   in_byte=accepted<204?received[blockno*204+accepted]:0;
   @(posedge clk);
   if(in_valid&&ready)accepted=accepted+1;
   #1;
   if(valid)begin
    if(emitted>=188 || data_out !== original[blockno*188+emitted])mismatch=mismatch+1;
    emitted=emitted+1;
   end
   @(negedge clk);
  end
  $display("RESULT %0d %0d %0d %0d %0d",blockno,cycle,emitted,mismatch,fail);
 end
 $finish;
end
endmodule
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rtl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--diagnostic", action="store_true")
    args = parser.parse_args()
    cases = vectors(args.quick)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        (folder/"bench.sv").write_text(TB)
        for name, part in (("received",1),("original",2)):
            (folder/f"{name}.hex").write_text("\n".join(f"{b:02x}" for row in cases for b in row[part])+"\n")
        subprocess.run(["iverilog","-g2012","-s","isdb_rs_tb",f"-Pisdb_rs_tb.BLOCKS={len(cases)}",
                        "-o",str(folder/"bench"),str(args.rtl.resolve()),str(folder/"bench.sv")],check=True)
        log = subprocess.check_output(["vvp",str(folder/"bench")],cwd=folder,text=True,timeout=300)
    rows=[]
    for line in log.splitlines():
        if line.startswith("RESULT "):
            _,i,cycles,emitted,mismatch,fail=line.split()
            row={"case":cases[int(i)][0],"cycles":int(cycles),"emitted":int(emitted),
                 "mismatched_bytes":int(mismatch),"block_fail":int(fail)}
            row["pass"]=row["emitted"]==188 and row["mismatched_bytes"]==0 and row["block_fail"]==0 and row["cycles"]<=2666
            rows.append(row)
    result={"profile":"RS(204,188), GF 0x11d, alpha 2, roots 0..15, high-order byte first",
            "sources":["https://www.arib.or.jp/english/html/overview/doc/6-STD-B31v2_2-E1.pdf#page=32",
                       "https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-0-199910-S!!PDF-E.pdf#page=3"],
            "rtl_sha256":hashlib.sha256(args.rtl.read_bytes()).hexdigest(),
            "tests":rows,"passed":sum(r["pass"] for r in rows),"total":len(cases),
            "reset_abort_trials":(len(cases)+15)//16,
            "non_reset_block_boundaries":len(cases)-(len(cases)+15)//16,
            "maximum_observed_cycles":max((r["cycles"] for r in rows),default=None),
            "all_pass":len(rows)==len(cases) and all(r["pass"] for r in rows)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="tests"},indent=2))
    for row in rows:
        if not row["pass"]:print(row)
    if not result["all_pass"] and not args.diagnostic:raise SystemExit(1)


if __name__=="__main__":main()
