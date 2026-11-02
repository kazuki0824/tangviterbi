"""Compare the experimentally instantiated SPI endpoint pins against the board
routing budget. Check all conditions, never confuse synthesized logic with
physically routable pin-legal receiving hardware.
"""
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
top=(ROOT/"experiments/dual_s3_spi_ingress_only_area_top.sv").read_text()
document=(ROOT/"reports/20k-dual-s3.md").read_text()
checks=[]
def check(name,passed,detail):
    checks.append(dict(name=name,ok=bool(passed),detail=detail))
check("two SPI2 physical clocks and chip selects",bool(re.search(r"input wire \[1:0\].*spi2_clk.*spi2_cs_n",top)),"2 × (SCLK+CS) = 4 pins")
check("two 8-bit Octal SPI2 buses",bool(re.search(r"input wire \[15:0\] spi2_d",top)),"2 × 8 = 16 pins")
check("two SPI3 physical clocks and chip selects",bool(re.search(r"input wire \[1:0\].*spi3_clk.*spi3_cs_n",top)),"2 × (SCLK+CS) = 4 pins")
check("two 4-bit Quad SPI3 buses",bool(re.search(r"inout wire \[7:0\] spi3_d",top)),"2 × 4 = 8 pins")
check("documented board connector limit",bool("合計34" in document and "J6=18" in document and "J5=16" in document),"J5 16 + J6 18 = 34 header signal upper bound")
check("documented planned 34-pin allocation",bool("T10＋S16＋TS6＋event2＝34" in document),"Planned T: Octal10, S: Octal+Quad16, 2×TS3, event2")
pin_count=4+16+4+8
credit_pins=6 # actual 3-bit RF_credit_gray for each of 2 S3s
check("two explicit 3-bit RF credit outputs",bool(re.search(r"output wire \[5:0\] RF_credit_gray",top)),"2 × 3 = 6 additional physical bits in actual connected IQ probe")
ts_outputs=6
events=2
full_pins=pin_count+ts_outputs+events+credit_pins
planned=10+16+6+2
check("synthesized area top fits with two TS outputs and event pins",full_pins<=34,f"actual area top SPI {pin_count} + TS {ts_outputs} + events {events} + credit {credit_pins} = {full_pins} > 34")
check("proposed alternative fits by pin count only",planned<=34,f"proposed T Octal10+S Octal/Quad16+TS6+event2 = {planned}; NOT implemented in this top")
candidate=(ROOT/"rtl/dual_s3_26pin_transport_candidate.sv").read_text()
candidate_checks={
 "T one Octal10": bool(re.search(r"s3_spi_t_octal_control_endpoint\\s*(?:#\\s*\\([^;]*?\\)\\s*)?t\\s*\\(", candidate, re.S)),
 "S Octal10 and Quad6": ".IMAGE_ID(1)" in candidate and "s_spi3_clk,s_spi3_cs_n" in candidate,
 "no credit GPIO": "output wire [5:0] RF_credit_gray" not in candidate
}
for name,ok in candidate_checks.items():
    check("candidate: "+name,ok,"26-pin transport only; board-pin mapping remains unverified")
check("candidate connector necessary count",10+16+6+2<=34,"T Octal10+S OctalQuad16+TS6+events2=34")
report=dict(stage=2,scope="physical board pin budget for connected IQ partial area top",checks=checks,all_checks_executed=len(checks),ng=sum(not c["ok"] for c in checks),present_area_top_pin_fit=False,planned_pin_count_only_fit=planned<=34,candidate_count_only_fit=all(candidate_checks.values()),receiver_verified=False)
print(json.dumps(report,indent=2))
# A diagnosed violation is retained as a hard negative, not a CI crash.
