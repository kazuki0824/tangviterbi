# T finite integration model — fresh reconstruction

This is a fresh reconstruction made on 2026-11-05 from the preserved target
sources and the recorded model requirements. The lost previous executable,
generated files and final runtime report have not been recovered byte for
byte. Previous bank counts are comparisons, not acceptance criteria.

## Final evidence and candidate decision

**Evidence audit: PASS, 28/28 conditions. Candidate: MODEL_NG.** The fresh
strict run used the final linked SDK fee document, the corrected SPI wire
geometry and no provisional-fee override. All 12 runtime unit tests passed.
The exact observations are in [results.json](results.json), the full audit
enumeration is in [audit.log](audit.log), and the semantic test output is in
[unit-tests.log](unit-tests.log).

The current nine-phase owner and conservative admission/postcheck policy do
not reach the requested 100-bank acceptance window. The ideal-clock case
rejects its next producer step after 25 accepted banks; the 240-cycle clock
uncertainty case rejects after 19. These are validated policy rejections
inside the stated model. **They do not prove physical source overwrite, a
model-independent throughput overload, or impossibility of all T designs on
ESP32-S3.** No receiver adoption or hardware WCET is established.

The fee input is [costs.json](costs.json), with 193 passing derivation/input
checks. It binds decompressed target ELF SHA256
`41a01f1a76c3879f0b3757f2bd2b307d0f9977655c3e9ce293562dcf7f5f821c`.
Its compressed linked-path witnesses are retained in
[cost-evidence.json.gz](cost-evidence.json.gz). Provisional development runs
remain outside this report directory and are not final candidate evidence.

```sh
python -m unittest tests.test_t_preprocess_runtime -v
python ci/t_preprocess_runtime_audit.py \
  --costs reports/s3-t-preprocess-integration-v2/runtime/costs.json \
  --output reports/s3-t-preprocess-integration-v2/runtime/results.json
```

CI can supply fresh artifacts under `build/` with the same CLI. The fee
document's `linked_elf_path`, `sdk_audit_path` and `provenance_path` select those
artifacts. Their actual hashes are mandatory, using repository-relative keys
for paths inside the checkout and absolute keys outside it.
The sibling `cost-evidence.json.gz` retains the full path, relocation and IRQ
witness maps. Its selected `evidence_path`, compressed-byte `evidence_sha256`
and source-hash entry are required independently; an empty or unreadable
witness cannot satisfy the strict gate.

### Fresh scenario outcomes

The 21 executed scenarios comprise the 13 rows below and eight intentional
fault injections. The audit checks that each result has valid conservation,
oracle, ownership, stop and fee-accounting evidence; an expected candidate
rejection is separate from an evidence failure. All eight injected faults
were detected as specified. [results.json](results.json)

| Scenario | Accepted banks | Produced 1,024-word blocks | Candidate observation |
|---|---:|---:|---|
| Eight-bank acceptance window, ideal clock | 8 | 83 | Requested window observed; input and DMA remain pending |
| Nominal 100-bank request, ideal clock | 25 | 294 | Whole-step deadline admission rejects |
| Same nominal request without source-bank destruction | 25 | 294 | Same rejection and all 88 compared trace fields agree |
| Clock uncertainty 240 cycles | 19 | 220 | Whole-step deadline admission rejects |
| Clock uncertainty 1,024 cycles | 23 | 269 | Whole-step deadline admission rejects |
| 10% added task-charge stalls | 7 | 72 | Whole-step deadline admission rejects |
| CPU1 PHY 1,000 cycles, first event at 190,000 | 24 | 282 | Whole-step deadline admission rejects |
| CPU1 PHY 10,000 cycles, first event at 190,000 | 25 | 294 | Whole-step deadline admission rejects |
| CPU1 PHY 50,000 cycles, first event at 190,000 | 18 | 209 | Whole-step deadline admission rejects |
| CPU1 PHY 50,000 cycles, first event at 2,400,000 | 13 | 146 | Whole-step deadline admission rejects |
| Diagnostic step bound 10,000 cycles | 1 | 1 | Observed step 10,124 exceeds the postcheck budget |
| Derived model bound 17,791 cycles, ideal clock | 25 | 294 | Same deadline admission rejection as nominal |
| Diagnostic preparation budget 1,024 words per owner iteration | 31 | 371 | Native preparation incomplete at the switch threshold |

All PHY rows use a 1,000 ms period. These finite stopping counts are not a
monotonic tolerance ranking: changing clock uncertainty or service time also
changes native switching, polling and pipeline phase. In the 1,024-word
preparation diagnostic, 12,413 words have arrived when the 12,288-word
threshold is checked; the next bank is still being prepared, only 6,144
preparation words are done, and the current iteration has no preparation
budget left. [results.json](results.json)

### What the primary rejections establish

Both primary cases stop with native fault 0, adapter fault 4, task fault 5
and invariant outcome 0. The exact guard predicate is true: the declared
20,000-cycle whole-step budget is at least the remaining sampled deadline
margin. The completed steps never violate that declared budget in these
cases; their largest observed sampled duration is 14,302 cycles.
[results.json](results.json)

| Observation at rejected admission | Ideal clock | Clock uncertainty 240 |
|---|---:|---:|
| Owner stop, virtual cycles | 4,811,725 | 3,664,167 |
| Accepted words still unconsumed | 12,683 | 12,909 |
| Retained source banks | 2 | 2 |
| Remaining deadline margin from sampled upper clock | 11,084 | 19,618 |
| Actual next path with the guard omitted | Copy, then pipeline busy | Copy, then produce |
| Raw words copied / physical copy chunks | 1,024 / 2 | 1,024 / 2 |
| Counterfactual base whole-step fee | 3,242 | 12,923 |
| Counterfactual base fee until failed bank release | 1,014 | 662 |

The counterfactual intervals start at the pre-step clock sample, including
the wrapper control fee. They are not additional durations starting at the
recorded failure instant. Both omit task stalls and interrupts, and the
failed bank can be released by copy before the full step completes. These
observations identify conservatism in the current guard; they do not validate
a replacement admission algorithm. The separate 17,791-cycle envelope adds
the maximum modeled step 13,537, one SPI service 3,145 and one tick 1,109.
It still exceeds the nominal remaining 11,084-cycle margin and rejects the
same step. A source-lease-aware admission redesign is another candidate.
[results.json](results.json)

### Charged work, polling and pending work

The nominal ledgers below count core0 through owner stop and core1 through
completion of its already-started operation and stop acknowledgment. They
separate useful data processing and completed-transfer work from explicit
empty polling. The control row also contains polling-related work, so it
must not be treated as an intrinsic minimum. [results.json](results.json)

| Charged category, nominal case | Core0 cycles | Core1 cycles |
|---|---:|---:|
| Halfband producer / worker processing | 2,857,974 | 4,168,626 |
| Native sentinel fill and raw copy | 488,474 | 0 |
| Completed pipeline reap | 17,520 | 0 |
| SPI submit, completed reap and ISR services | 199,843 | 0 |
| Empty/busy pipeline checks | 5,369 | 82,324 |
| Empty SPI reap queries | 74,820 | 0 |
| Owner / worker task control | 478,392 | 355,168 |
| Clock, native control/helpers and adapter control | 665,299 | 0 |
| Tick and normal watchdog-feed checks | 24,034 | 219,558 |
| **Total charged** | **4,811,725** | **4,825,676** |

Between first and last bank acceptance, 287 blocks were produced; recorded
charges average 15,767.25/core0 and 15,771.13/core1 cycles per produced block,
against 15,360 input-arrival cycles per 1,024 raw words at 16 Mcomplex/s.
These averages include empty polling, state-dependent control and work
already charged before its publication. The totals and backlog therefore
do **not** establish a model-independent mandatory-work overload bound.
[results.json](results.json)

The short eight-bank diagnostic is deliberately limited: it accepts 99,697
words, produces 84,992 and leaves 14,705 unconsumed. It retains two source
banks and one DMA lease. The nominal 25-bank run independently checks 150,528
completed complex outputs, preserves the released-source destruction trace,
and observes all 35 completed wire intervals at exactly 98,544 virtual
cycles. [results.json](results.json)

### Static completion conditions checked without fail-fast

| Condition group | How it is checked | Result |
|---|---|---|
| Final linked fee prerequisites | Required 27 target inputs, 10 support inputs, four selected artifacts, every supplied hash, same ELF across audit/provenance/witness, nonempty witness maps and exact wire geometry | PASS |
| Fee schema | All 36 named events, owner/owned arrays, dynamic copy table and fill constants; every derivation check PASS | PASS |
| Same-C executable | Generated instrumentation builds with UBSan; recovered owner file is copied verbatim | PASS |
| Owner initialization/fatal contracts | 16 independent C checks, including invalid input and stop handling | PASS |
| Derived discrete-model step envelope | All partitions into up to six physical copy chunks; stated one-SPI/one-tick interval premises | PASS |
| All 21 scenarios | Conservation, independent output oracle, raw/DMA/source ownership, actual wire intervals, expected fault class and accounting identities | PASS |
| Source destruction equivalence | Destroyed and preserved source variants compare all 88 retained trace fields | PASS |
| Model source capture | Every model input hash collected, with missing-file errors enumerated | PASS |

These groups account for the 28 top-level audit conditions: the scenario
group contains 21 separate conditions, and each other row contains one.
The 12 unit tests additionally check malformed evidence, missing bindings,
continued enumeration after failure, instrumentation drift and the targeted
SPI header-lane correction. [audit.log](audit.log)
[unit-tests.log](unit-tests.log)

## Executed control flow

The host compiles the recovered native adapter, retained native capture and
two-slot halfband pipeline. The recovered nine-phase `tpre_runtime.c` is copied
**verbatim** into the host build. Instrumentation is inserted into temporary
copies of the other target C files; it does not change the target sources used
by ESP-IDF. Two coroutines execute the actual C branches and publications.

| Part | Executed behavior and verification |
|---|---|
| RF input | Continuous 16 Mcomplex/s, 15 virtual cycles per raw sample, three 16,384-word rings; actual sentinel preparation, boundary search, handoff and age checks. |
| Owner | Poll, pipeline reap, producer, poll, DMA reap, poll, DMA submit, poll, feed. Shared preparation budget 2,048 words; each poll is capped at 1,024. |
| Adapter | Up to 1,024 raw words per step, full 32-bit metadata retained, bounded carry, and all retained source deadlines checked. |
| Pipeline | Two slots; core0 produces 32 complex outputs and core1 produces 480. READY and DONE publish only after their charged work. |
| Source lease | Every accepted sample is matched to its global sequence. Reused/prepared banks cannot still be owned. Released banks are deliberately destroyed in one run. |
| Output oracle | Every completed block is compared with an independent direct 31-tap convolution, signed 10-bit inputs, explicit floor division and int16 saturation. The oracle does not call the halfband kernel. |
| DMA lease | Eight disjoint 16 KiB frames, two queue entries, ordered completion. Every submitted frame's fingerprint stays unchanged throughout its DMA lease. |
| Stop | RF stops when the owner stops. An already-started worker operation may finish before acknowledgment. Pending source, output and DMA leases remain visible. |

The input pattern varies both I/Q and all metadata bits. A value equal to the
capture sentinel is explicitly excluded. This is an ideal RF ABI assumption,
not physical validation of the undocumented capture interface.

### What a finite pass means

The owner stops when it observes the requested **accepted-bank count**, or on
the first fatal condition. It does not continue processing all newly accepted
input or drain all DMA frames. Consequently an eight-bank diagnostic pass
means an eight-bank **acceptance observation window** completed without a
fault. It does not mean eight banks were completely preprocessed and sent.

Each row states this stop policy, reports unconsumed and unproduced accepted
words, and records `complete_processing_and_dma_drain` separately. Remaining
leases are conserved rather than silently dropped. Task deletion and complete
target shutdown are outside the model.

## Fees, interrupts and publication

Only supplied virtual cycle fees advance time. Host execution time is never
used as target timing. Owner/native/adapter control fees exclude their
separately charged callees; kernel and SPI API fees include their documented
call paths. Feed already includes its clock read. Actual copy lengths use the
linked 1..1,024-word fee table without adding another control allowance. Fill
fees use the linked fixed/span/body constants and split at a ring boundary.

Charges happen before an operation publishes READY/DONE or releases a source.
The worker reads its private workspace after a source bank is destroyed. The
destruction and preservation variants must produce the same complete trace
apart from the case label and destruction counter. Partial carry is checked
at the final observation point, without padding or dropping a tail.

SPI3 is modeled at 80 MHz with quad-lane 16 KiB data, a **single-lane 16-bit
command and single-lane 64-bit address**. The frozen SDK transaction uses
`SPI_TRANS_MODE_QIO` without either multiline-header flag. Its wire duration
is `(16384*8/4 + 16 + 64)*3 = 98,544` CPU cycles at 240 MHz. An earlier
development assumption incorrectly treated the header as quad; that assumption
is excluded from the final run. The regression observes each actual scheduled
launch-to-wire-completion interval; changing descriptive metadata alone cannot
make it pass. The strict fee gate also requires the SDK's checked nine-field
`model.spi_wire` geometry to match this fixed candidate. SDK queue
callbacks are an event model with linked SDK fees; the host does not execute
Xtensa FreeRTOS or SPI hardware. Submission becomes available after the full
API fee. Wire launch and completion publication wait for their full ISR
service. An empty reap is classified at query entry; a completion during that
query is observed on a later owner reap.

Core0 level1 SPI and tick services share a serial service calendar. A tick
already in service delays a newly arriving SPI handler. Simultaneous **new
arrivals** choose tick first. A SPI service already finishing may publish at
its existing completion boundary even when a tick arrives at that boundary.
Extending the owner task's ready time alone would not enforce these rules.

Reception is assumed to occur with cache enabled. This model does not prove
all transitive SPI/tick callees safe with cache disabled. The modeled caller
priorities are owner 23, worker 21 and timer task 22. The generic SDK launcher
accepts caller-supplied priorities; these values are an explicit configuration.

The periodic tick is 100 Hz using the linked no-task-switch paths. PHY
sensitivity runs use the CPU1 timer task, a 1,000 ms period and explicit first
event phases. Their supplied CPU1 service duration includes task dispatch,
context and callback work, and ticks may preempt it. CPU0 timer ISR/IPI and
other interrupts remain unpriced. The physical PHY callback's hardware wait
is not bounded by any supplied sensitivity duration.

## Deadline rejection versus physical source overwrite

The current C declares a 20,000-cycle core0 step bound. This is an upper budget
used by its admission guard, **not a claim that every next path requires
20,000 cycles**. The guard checks all retained banks before entering the step;
the postcheck uses the earliest pre-step deadline for the whole step.

An admission failure records the sampled upper clock, retained deadline,
remaining margin, slot states, pending raw words and the actual next branch.
The counterfactual follows that branch with admission omitted, charging copy
chunks and advance operations in their actual order. It reports copied words,
consumed words, whether publication would occur, the base whole-step fee and,
if applicable, the base fee up to release of the failed bank.

Those counterfactuals omit **both injected task stalls and asynchronous
interrupts**, including in a 10% stall scenario. They are model diagnostics,
not target lower bounds, WCET or permission to bypass admission. Source copy
can release an old bank before the FIR finishes; whole-step rejection alone
does not demonstrate physical overwrite or an impossible source-reuse
deadline. A source-lease-aware admission redesign is a different candidate.

A separate model-only envelope enumerates every partition of up to 1,024
copied words into at most six nonempty physical chunks. It adds one maximum
SPI service and one tick, and checks that the resulting interval is shorter
than the modeled wire and tick periods. The derived-bound sensitivity keeps
the recovered algorithm unchanged. It excludes other ISR/NMI interference,
unpriced memory stalls and silicon effects.

## Evidence gate and failure classification

The strict gate requires every member of the SDK auditor's canonical target
input list, including the actual `halfband31.S` kernel, SDK glue, clock/SPI
support, PIE warmup, SRAM reservations and build recipe. It also requires the
executed fee derivation scripts and reference evidence, plus the specifically
selected linked ELF, SDK audit and provenance. Merely supplying a subset of
source hashes or setting `status` to READY does not satisfy the gate.

Every supplied hash is compared with current bytes. The decompressed target
ELF digest must match the cost document, passing SDK audit and build
provenance. Every cost derivation check must pass, arrays must have their
declared lengths, and all required fees must be present and typed. Only the
separately identified copy-control allowance may be zero; the exact linked
copy table is applied as-is.

The audit enumerates independent conditions without stopping at the first
failure. Non-injected runs are valid performance evidence only when they
reach the requested observation window or a recognized capacity-stop
combination. Adapter deadline/bound and native age/preparation/unavailable
faults are cross-checked with their observed predicates. An argument, ordering
or unexplained task error makes the evidence **FAIL**, rather than being
accepted as a capacity `MODEL_NG`.

Fault tests deliberately inject submit failure, wrong completion sequence,
owner/worker feed failure, clock failure, DMA corruption, raw corruption and
worker sequence corruption. An ambiguous submit error keeps the frame's DMA
lease. Other tests verify exact owner copying, instrumentation-anchor drift,
missing source/evidence bindings, and continued enumeration after the first
independent scenario fails.

`audit_status` describes evidence and semantic validity. `candidate_status`
separately reports `MODEL_NG`, `FINITE_PASS` or `BLOCKED`. A sound audit may
therefore return a negative candidate result. It neither proves original
receiver quality nor that every possible T implementation is impossible on
an S3.

Both cores have full event/fee ledgers and time-accounting identities. Empty
pipeline checks and empty versus completed SPI reaps are distinct categories.
Accepted-bank observations also record input consumption and block progress.
Per-block averages include polling and already-charged pending work; they do
not establish intrinsic utilization or a model-independent overload bound.
