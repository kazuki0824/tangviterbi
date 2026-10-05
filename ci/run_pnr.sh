#!/usr/bin/env bash
set -euo pipefail

board="${1:?board: 9k or 20k}"
variant="${2:?variant: core-only, mem, viterbi-only, rs-only, or 20K 32-ACS variants}"
with_viterbi=1
with_rs=1
with_mem=0
diagnostic=0
viterbi_acs=16
rs_syndrome_cycles=16
rs_rtl="rtl/rs204_188_compact.sv"
rs_label="current"

case "${board}" in
  9k)
    device="GW1NR-LV9QN88PC6/I5"
    family_args=(--vopt family=GW1N-9C)
    synth_family=()
    cst="constraints/tangnano9k.cst"
    ;;
  20k)
    device="GW2AR-LV18QN88C8/I7"
    family_args=(--vopt family=GW2A-18C)
    synth_family=(-family gw2a)
    cst="constraints/tangnano20k.cst"
    ;;
  *)
    echo "unsupported board: ${board}" >&2
    exit 2
    ;;
esac

case "${variant}" in
  core-only)
    ;;
  mem)
    with_mem=1
    ;;
  viterbi-only)
    with_rs=0
    diagnostic=1
    ;;
  rs-only)
    with_viterbi=0
    diagnostic=1
    ;;
  core-32acs)
    viterbi_acs=32
    ;;
  mem-32acs)
    with_mem=1
    viterbi_acs=32
    ;;
  viterbi-32acs)
    with_rs=0
    diagnostic=1
    viterbi_acs=32
    ;;
  core-32acs-rsconst)
    viterbi_acs=32
    rs_syndrome_cycles=0
    rs_rtl="experiments/rs_syndrome_constants.sv"
    rs_label="constant-16way"
    ;;
  mem-32acs-rsconst)
    with_mem=1
    viterbi_acs=32
    rs_syndrome_cycles=0
    rs_rtl="experiments/rs_syndrome_constants.sv"
    rs_label="constant-16way"
    ;;
  *)
    echo "unsupported variant: ${variant}" >&2
    exit 2
    ;;
esac

if (( viterbi_acs == 32 )) && [[ "${board}" != "20k" ]]; then
  echo "32-ACS variants are intentionally scoped to Tang Nano 20K" >&2
  exit 2
fi

mkdir -p build
rm -f build/design.json build/packed.json build/routed.json build/report.json build/synth.log build/pnr.log

sv_sources=(
  rtl/viterbi_k7_16acs.sv
  rtl/viterbi_k7_32acs.sv
  "${rs_rtl}"
  rtl/psram_ctrl.sv
  rtl/benchmark_top.sv
)

{
  printf 'read_verilog -sv'
  printf ' %q' "${sv_sources[@]}"
  printf '\n'
  printf 'chparam -set WITH_MEM %d -set WITH_VITERBI %d -set WITH_RS %d -set VITERBI_ACS %d benchmark_top\n' \
    "${with_mem}" "${with_viterbi}" "${with_rs}" "${viterbi_acs}"
  printf 'hierarchy -check -top benchmark_top\n'
  printf 'synth_gowin'
  printf ' %q' "${synth_family[@]}"
  printf ' -top benchmark_top -json build/design.json\n'
  printf 'stat -top benchmark_top\n'
} > build/synth.ys

yosys -l build/synth.log build/synth.ys
freq=$(python3 -c 'import json; print(json.load(open("ci/performance.json"))["target_clock_mhz"])')
pnr_seed=$(python3 -c 'import json; print(json.load(open("ci/performance.json"))["pnr_seed"])')

set +e
pnr_mode=()
report_mode=()
output=build/routed.json
if (( diagnostic )); then
  pnr_mode=(--pack-only)
  report_mode=(--pack-only)
  output=build/packed.json
fi
nextpnr-himbaechel --json build/design.json --write "${output}" \
  --device "${device}" "${family_args[@]}" --vopt "cst=${cst}" \
  --freq "${freq}" --seed "${pnr_seed}" --report build/report.json "${pnr_mode[@]}" 2>&1 | tee build/pnr.log
rc=${PIPESTATUS[0]}
set -e

python3 ci/report.py --board "${board}" --variant "${variant}" \
  --report build/report.json --synth-log build/synth.log --pnr-log build/pnr.log \
  --exit-code "${rc}" --seed "${pnr_seed}" --acs-lanes "${viterbi_acs}" \
  --rs-syndrome-cycles "${rs_syndrome_cycles}" --rs-label "${rs_label}" \
  --with-viterbi "${with_viterbi}" --with-rs "${with_rs}" --with-mem "${with_mem}" \
  "${report_mode[@]}" > build/summary.md

cat build/summary.md
exit "${rc}"
