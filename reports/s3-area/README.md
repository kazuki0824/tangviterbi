# Controlled measurements

CI hardware/source commit: e6c05529afcb5a658b396f72e924cc29537c2163.
Workflow run: https://github.com/kazuki0824/tangviterbi/actions/runs/37879016201

Result JSON is transcribed without modification from the published job logs. Full synthesis/P&R logs and netlists are in the run artifacts. All four jobs completed measurement, but every measured 125 MHz timing criterion failed. The isolated module logic sum and the packed harness LUT count are different metrics and must not be interchanged.

The fixed native CI tool is Yosys 0.69+190, not local YoWASP 0.69. Compare within one toolchain. The native dual baseline has RS 2156 logic equivalents; dual4 has 1814. However the packed mem harness rises from 5129 to 5154 LUT4. Resetless reduces packed mem to 4954 but has RS 2085 equivalents.

Combination source commit: 05c8aef5cdd0c20466c14c1e7a2d801a42f711a0.
Follow-up run: https://github.com/kazuki0824/tangviterbi/actions/runs/37879826128

The proposal selects `resetless4`: RS 1679 equivalents; packed core/mem
4832/4978 LUT4; routed core/mem 90.34/104.68 MHz; isolated RS 106.92 MHz.
This is a 151-LUT4 reduction for the measured mem harness. It is not a full
receiver area result. `shared-resetless4` uses fewer LUTs but its mem Fmax
97.77 MHz misses the proposed 99 MHz domain. All 18 measured 125 MHz
criteria fail. The S receiver still requires an additional, unimplemented
cycle-count reduction. See [the complete proposal](../s3-internal-sram-proposal.md).
