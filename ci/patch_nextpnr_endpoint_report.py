"""Add opt-in endpoint reports to the pinned nextpnr, without changing P&R."""
from pathlib import Path
import argparse
import subprocess

PIN = "e2fe86b3ce6feaa3f09d8db5c0971c1cda3fc641"
ANCHOR = "            clock_reports[launch.clock] = build_critical_path_report(i, worst_endpoint.at(0), true);\n"
EXTRA = r'''
            // Diagnostic only: retain tied endpoints and expose the engine's
            // setup slack plus a complete path. Normal Fmax and P&R are unchanged.
            if (ctx->settings.count(ctx->id("diagnostics/final_report"))) {
                std::vector<CellPortKey> diagnostic_endpoints;
                for (const auto &ep : domains.at(dp.key.capture).endpoints) {
                    const auto &pd = ports.at(ep.first);
                    if (pd.domain_pairs.count(i))
                        diagnostic_endpoints.push_back(ep.first);
                }
                std::sort(diagnostic_endpoints.begin(), diagnostic_endpoints.end(),
                          [&](const CellPortKey &a, const CellPortKey &b) {
                    auto sa = ports.at(a).domain_pairs.at(i).setup_slack;
                    auto sb = ports.at(b).domain_pairs.at(i).setup_slack;
                    if (sa != sb)
                        return sa < sb;
                    return std::make_pair(a.cell.str(ctx), a.port.str(ctx)) <
                           std::make_pair(b.cell.str(ctx), b.port.str(ctx));
                });
                int rank = 0;
                for (const auto &ep : diagnostic_endpoints) {
                    if (rank == 32)
                        break;
                    auto slack = ports.at(ep).domain_pairs.at(i).setup_slack;
                    log_info("Endpoint diagnostic rank=%d cell=%s port=%s setup_slack_ns=%.6f\n",
                             ++rank, ep.cell.c_str(ctx), ep.port.c_str(ctx), ctx->getDelayNS(slack));
                    xclock_reports.emplace_back(build_critical_path_report(i, ep, true));
                }
            }
'''
ROUTER_ANCHOR = '''        log_info("Checksum: 0x%08x\\n", ctx->checksum());
        timing_analysis(ctx, true /* slack_histogram */, true /* print_fmax */, true /* print_path */,
                        true /* warn_on_failure */, true /* update_results */);
'''
ROUTER_REPLACEMENT = ROUTER_ANCHOR.replace(
    '        timing_analysis(ctx,',
    '        // Report additional endpoints only in the existing final timing pass.\n'
    '        ctx->settings[ctx->id("diagnostics/final_report")] = std::to_string(1);\n'
    '        timing_analysis(ctx,',
)


def patch_timing(source):
    if source.count(ANCHOR) != 1 or "diagnostics/final_report" in source:
        raise ValueError("Unexpected or already patched timing source")
    return source.replace(ANCHOR, ANCHOR + EXTRA)


def patch_chipdb_build(source):
    # Use the suite's matching binary database, rather than regenerate it.
    first = "if (NOT IMPORT_BBA_FILES)"
    loop = "foreach (device ${HIMBAECHEL_GOWIN_DEVICES})"
    if source.count(first) != 1 or source.count(loop) != 1:
        raise ValueError("Unexpected Gowin CMake source")
    source = source.replace(first, "if (NOT IMPORT_BBA_FILES AND NOT EXTERNAL_CHIPDB)")
    return source.replace(loop, "if (NOT EXTERNAL_CHIPDB)\n" + loop) + "\nendif()\n"


def patch_router(source):
    if source.count(ROUTER_ANCHOR) != 1 or "diagnostics/final_report" in source:
        raise ValueError("Unexpected or already patched router")
    return source.replace(ROUTER_ANCHOR, ROUTER_REPLACEMENT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=args.checkout, text=True
    ).strip()
    if actual != PIN:
        raise ValueError(f"Expected nextpnr {PIN}, got {actual}")
    timing = args.checkout / "common/kernel/timing.cc"
    router = args.checkout / "common/route/router1.cc"
    cmake = args.checkout / "himbaechel/uarch/gowin/CMakeLists.txt"
    timing.write_text(patch_timing(timing.read_text()))
    router.write_text(patch_router(router.read_text()))
    cmake.write_text(patch_chipdb_build(cmake.read_text()))
    print("Applied report-only endpoint diagnostics and external-chipdb build patch.")


if __name__ == "__main__":
    main()
