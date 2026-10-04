#!/usr/bin/env bash
set -euo pipefail

board="${1:?board: 4k or 9k}"
variant="${2:?variant: core-only or mem}"

case "${board}" in
  4k)
    device="GW1NSR-LV4CQN48PC7/I6"
    family_args=()
    cst="constraints/tangnano4k.cst"
    psram=0
    ;;
  9k)
    device="GW1NR-LV9QN88PC6/I5"
    family_args=(--vopt family=GW1N-9C)
    cst="constraints/tangnano9k.cst"
    psram=1
    ;;
  *)
    echo "unsupported board: ${board}" >&2
    exit 2
    ;;
esac

case "${variant}" in
  core-only)
    with_mem=0
    psram=0
    ;;
  mem)
    with_mem=1
    ;;
  *)
    echo "unsupported variant: ${variant}" >&2
    exit 2
    ;;
esac

mkdir -p build
rm -f build/design.json build/routed.json build/report.json build/synth.log build/pnr.log

sv_sources=(
  rtl/viterbi_k7_16acs.sv
  rtl/rs204_188_compact.sv
  rtl/hyperram_ctrl.sv
  rtl/psram_ctrl.sv
  rtl/benchmark_top.sv
)

{
  printf 'read_verilog -sv'
  printf ' %q' "${sv_sources[@]}"
  printf '\n'
  printf 'chparam -set WITH_MEM %d -set PSRAM %d benchmark_top\n' \
    "${with_mem}" "${psram}"
  printf 'hierarchy -check -top benchmark_top\n'
  printf 'synth_gowin -top benchmark_top -json build/design.json\n'
  printf 'stat -top benchmark_top\n'
} > build/synth.ys

yosys -l build/synth.log build/synth.ys

set +e
nextpnr-himbaechel   --json build/design.json   --write build/routed.json   --device "${device}"   "${family_args[@]}"   --vopt "cst=${cst}"   --freq 110   --report build/report.json   2>&1 | tee build/pnr.log
rc=${PIPESTATUS[0]}
set -e

python3 ci/report.py   --board "${board}"   --variant "${variant}"   --report build/report.json   --synth-log build/synth.log   --pnr-log build/pnr.log   --exit-code "${rc}"   > build/summary.md

cat build/summary.md
exit "${rc}"
