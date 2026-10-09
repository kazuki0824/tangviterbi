# Controlled measurements

CI hardware/source commit: e6c05529afcb5a658b396f72e924cc29537c2163.
Workflow run: https://github.com/kazuki0824/tangviterbi/actions/runs/37879016201

Result JSON is transcribed without modification from the published job logs. Full synthesis/P&R logs and netlists are in the run artifacts. All four jobs completed measurement, but every measured 125 MHz timing criterion failed. The isolated module logic sum and the packed harness LUT count are different metrics and must not be interchanged.

The fixed native CI tool is Yosys 0.69+190, not local YoWASP 0.69. Compare within one toolchain. The native dual baseline has RS 2156 logic equivalents; dual4 has 1814. However the packed mem harness rises from 5129 to 5154 LUT4. Resetless reduces packed mem to 4954 but has RS 2085 equivalents. Combination trials are required before choosing a candidate.
