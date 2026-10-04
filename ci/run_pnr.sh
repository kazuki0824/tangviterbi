#!/usr/bin/env bash
set -euo pipefail

board="${1:?board: 9k}"
variant="${2:?variant: core-only, mem, viterbi-only or rs-only}"
with_viterbi=1
with_rs=1
diagnostic=0

case "${board}" in
  9k)
    device="GW1NR-LV9QN88PC6/I5"
    family_args=(--vopt family=GW1N-9C)
    cst="constraints/tangnano9k.cst"
    ;;
  *)
    echo "unsupported board: ${board}" >&2
    exit 2
    ;;
esac

case "${variant}" in
  core-only)
    with_mem=0
    ;;
  mem)
    with_mem=1
    ;;
  viterbi-only)
    with_mem=0
    with_rs=0
    diagnostic=1
    ;;
  rs-only)
    with_mem=0
    with_viterbi=0
    diagnostic=1
    ;;
  *)
    echo "unsupported variant: ${variant}" >&2
    exit 2
    ;;
esac

mkdir -p build
rm -f build/design.json build/packed.json build/routed.json build/report.json build/synth.log build/pnr.log

sv_sources=(
  rtl/viterbi_k7_16acs.sv
  rtl/rs204_188_compact.sv
  rtl/psram_ctrl.sv
  rtl/benchmark_top.sv
)

{
  printf 'read_verilog -sv'
  printf ' %q' "${sv_sources[@]}"
  printf '\n'
  printf 'chparam -set WITH_MEM %d -set WITH_VITERBI %d -set WITH_RS %d benchmark_top\n' \
    "${with_mem}" "${with_viterbi}" "${with_rs}"
  printf 'hierarchy -check -top benchmark_top\n'
  printf 'synth_gowin -top benchmark_top -json build/design.json\n'
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
  --exit-code "${rc}" --seed "${pnr_seed}" "${report_mode[@]}" > build/summary.md

cat build/summary.md
exit "${rc}"
