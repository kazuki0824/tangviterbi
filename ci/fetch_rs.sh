#!/usr/bin/env bash
set -euo pipefail

commit="2d581673ad7d3a97bca63c674b867ec80db0e2c6"
base="https://raw.githubusercontent.com/freecores/reed_solomon_decoder/${commit}/rtl"
out="third_party/rs"
mkdir -p "${out}"

files=(
  BM_lamda.v
  DP_RAM.v
  GF_matrix_ascending_binary.v
  GF_matrix_dec.v
  GF_mult_add_syndromes.v
  Omega_Phy.v
  RS_dec.v
  error_correction.v
  input_syndromes.v
  lamda_roots.v
  out_stage.v
  transport_in2out.v
)

for f in "${files[@]}"; do
  curl --fail --location --silent --show-error "${base}/${f}" -o "${out}/${f}"
done

cat > "${out}/SOURCE.txt" <<EOF
Source: https://github.com/freecores/reed_solomon_decoder
Commit: ${commit}
License: GPLv3 notices are present in the upstream RTL files.
Purpose: fetched transiently for synthesis benchmarking; not vendored in this repository.
EOF
