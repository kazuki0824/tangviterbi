# Native adapter reconstruction v2

`native_adapter.c` and the integration owner's `tpre_runtime.c/.h` match the
three preserved source artifacts byte for byte. The missing adapter header is
reconstructed from those implementations. Its layout and this audit are new v2
evidence; they are not presented as recovery of the missing original header.

Run:

```sh
python ci/t_native_adapter_audit.py
python -m unittest tests.test_t_native_adapter -v
```

`results.json` enumerates all 36 completion checks, including build and source
hash availability. The two split groups execute every one of their 1,023
positions and retain failures instead of stopping at the first failed split.
The regression tests also inject an early independent failure and a missing
source to verify that later independent checks still execute.

The audit compiles the recovered adapter and retained two-slot halfband
pipeline with UBSan. A separate direct 31-tap scalar convolution checks output
at shifts 0, 10, 15, and 31. It checks all bank-boundary and ring-wrap split
positions, three banks/six physical segments, full 32-bit metadata copying,
partial and full carry retention, two-slot backpressure, and initialization
while a source, carry, or output is still owned. Source banks are destroyed
after lease release and before the worker reads its private workspace.

Independent fault cases cover malformed and repeated source acceptance,
sequence/clock/overflow errors, the strict deadline inequality, and faults
detected after output publication. Published output remains owned even when a
later bound or clock check stops the adapter.

These are host semantic checks. The scalar host leaf is not the S3 PIE leaf,
and no host execution time is interpreted as target timing. Target ABI sizes,
linked PIE placement and cycle envelopes are separate SDK evidence. A passing
adapter audit does not establish sustained native-capture or receiver quality.
