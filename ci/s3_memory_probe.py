#!/usr/bin/env python3
"""Build an actual ESP-IDF ELF/map and preserve failed link evidence as data."""
import json
import os
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[1]
os.environ.setdefault("PROBE_TRANSPORT", "0")
os.environ.setdefault("PROBE_LATE_RF", "0")
app = root / "experiments/s3_memory_probe"
name = os.environ["PROBE_NAME"]
out = root / "build/s3-memory" / name
out.mkdir(parents=True, exist_ok=True)
command = ["idf.py", "-B", str(out / "idf"), "-DIDF_TARGET=esp32s3", "build"]
if os.environ["PROBE_TRANSPORT"] == "1":
    command.insert(-1, "-DSDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.transport.defaults")
with (out / "build.log").open("w") as log:
    rc = subprocess.run(command, cwd=app, stdout=log, stderr=subprocess.STDOUT).returncode
log = (out / "build.log").read_text(errors="replace")
map_file = out / "idf/s3_memory_probe.map"
result = {"profile": name, "IDF_version": subprocess.check_output(
    ["idf.py", "--version"], text=True).strip(),
    "IDF_commit": subprocess.check_output(
        ["git", "-C", os.environ["IDF_PATH"], "rev-parse", "HEAD"], text=True).strip(),
    "build_exit_code": rc, "link_succeeded": rc == 0,
    "RF_reserved_range": ["0x3fcb0000", "0x3fce0000"],
    "zero_copy_reservation": os.environ.get("PROBE_ZEROCOPY") == "1",
    "real_SPI_transport_linked": os.environ["PROBE_TRANSPORT"] == "1",
    "late_RF_queue_reserved_range": (["0x3fce4000", "0x3fcec000"]
                                    if os.environ["PROBE_LATE_RF"] == "1" else None),
    "late_twiddle_reserved_range": (["0x3fce0000", "0x3fce4000"]
                                    if os.environ.get("PROBE_ZEROCOPY") == "1" and os.environ["PROBE_TERRESTRIAL"] == "1" else None),
    "scope": "Link-only probe. Optional real SPI/SCT adapter and scalar FFT hot IRAM; no RF/PHY acquisition, SIMD or complete runtime heap/stacks. No silicon execution. Success is not a receiver memory fit.",
    "symbols": {}, "guard_errors": [line.strip() for line in log.splitlines()
                                      if "S3 RF ring overlaps" in line]}
if map_file.exists():
    text = map_file.read_text(errors="replace")
    symbols = ("_iram_start", "_iram_end", "_data_start", "_data_end", "_bss_start", "_bss_end",
               "rf_packed_queue", "link_staging", "fft_transfer_slots", "fft_twiddle_reservation",
               "link_headers", "link_descriptor_reserve", "transport_object_sizes",
               "transport_ports", "octal_segments", "quad_segments", "transport_ring")
    for symbol in symbols:
        matches = re.findall(r"^\s*(0x[0-9a-fA-F]+)\s+" + symbol + r"\b", text, re.M)
        if matches:
            result["symbols"][symbol] = matches[-1]
    if "_bss_end" in result["symbols"]:
        result["static_gap_to_RF_bytes"] = 0x3fcb0000 - int(result["symbols"]["_bss_end"], 16)
elf_file = out / "idf/s3_memory_probe.elf"
if elf_file.exists() and os.environ["PROBE_TRANSPORT"] == "1":
    import struct
    from elftools.elf.elffile import ELFFile
    with elf_file.open("rb") as f:
        elf = ELFFile(f)
        table = elf.get_section_by_name(".symtab")
        sym = table.get_symbol_by_name("transport_object_sizes")[0]
        section = elf.get_section(sym["st_shndx"])
        offset = sym["st_value"] - section["sh_addr"]
        values = struct.unpack("<7I", section.data()[offset:offset+28])
        result["transport_sizes_bytes"] = dict(zip(("port", "segment", "ring_control", "DMA_descriptor",
            "SPI2_DMA_pool", "SPI3_DMA_pool", "peak_SCT_configuration"), values))
        result["hot_functions"] = {name: hex(table.get_symbol_by_name(name)[0]["st_value"])
            for name in ("s3_fft_stage_tile", "s3_fft_reverse_tile", "spi_device_queue_trans")}
(out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
print("\n".join(log.splitlines()[-35:]))
# A known placement rejection is a completed measurement; unrelated build
# failures are infrastructure/source errors and must fail the workflow.
if rc and not result["guard_errors"]:
    raise SystemExit(rc)
