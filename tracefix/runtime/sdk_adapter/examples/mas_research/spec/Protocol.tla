---- MODULE Protocol ----
EXTENDS Integers, Sequences, TLC

CONSTANTS RESEARCHER_FM, RESEARCHER_RT, RESEARCHER_EVAL, PLOTTER, CHECKER, APPROVER

(* --algorithm Protocol {
variables
  research_to_plotter = <<>>; \* RESEARCHER_FM,RESEARCHER_RT,RESEARCHER_EVAL -> PLOTTER, labels: ['ready']
  research_to_checker = <<>>; \* RESEARCHER_FM,RESEARCHER_RT,RESEARCHER_EVAL -> CHECKER, labels: ['ready']
  plotter_to_approver = <<>>; \* PLOTTER -> APPROVER, labels: ['figures']
  checker_to_approver = <<>>; \* CHECKER -> APPROVER, labels: ['verified']
  DOC = "FREE"; \* Lock

macro send(ch, msg) {
  ch := Append(ch, msg);
}

macro receive(ch, var) {
  await Len(ch) > 0;
  var := Head(ch);
  ch := Tail(ch);
}

macro acquire_lock(lock) {
  await lock = "FREE";
  lock := self;
}

macro release_lock(lock) {
  lock := "FREE";
}

\* Three concurrent researchers. Each composes its section, serializes its write
\* to the shared research.md behind the DOC lock, then signals both downstream
\* consumers on the shared fan-in channels (research_to_plotter / _checker).
fair process (RESEARCHER_FM_proc \in {RESEARCHER_FM})
variables msg = "";
{
  RESEARCHER_FM_draft:
    skip; \* domain: research the formal-methods direction, compose the section
  RESEARCHER_FM_acquire:
    acquire_lock(DOC);
  RESEARCHER_FM_write:
    skip; \* domain: Read research.md then Write the FM section appended (under lock)
  RESEARCHER_FM_release:
    release_lock(DOC);
  RESEARCHER_FM_notify_plotter:
    send(research_to_plotter, "ready");
  RESEARCHER_FM_notify_checker:
    send(research_to_checker, "ready");
  RESEARCHER_FM_done:
    skip;
}

fair process (RESEARCHER_RT_proc \in {RESEARCHER_RT})
variables msg = "";
{
  RESEARCHER_RT_draft:
    skip; \* domain: research the runtime-monitoring direction, compose the section
  RESEARCHER_RT_acquire:
    acquire_lock(DOC);
  RESEARCHER_RT_write:
    skip; \* domain: Read research.md then Write the RT section appended (under lock)
  RESEARCHER_RT_release:
    release_lock(DOC);
  RESEARCHER_RT_notify_plotter:
    send(research_to_plotter, "ready");
  RESEARCHER_RT_notify_checker:
    send(research_to_checker, "ready");
  RESEARCHER_RT_done:
    skip;
}

fair process (RESEARCHER_EVAL_proc \in {RESEARCHER_EVAL})
variables msg = "";
{
  RESEARCHER_EVAL_draft:
    skip; \* domain: research the benchmarks/evaluation direction, compose the section
  RESEARCHER_EVAL_acquire:
    acquire_lock(DOC);
  RESEARCHER_EVAL_write:
    skip; \* domain: Read research.md then Write the EVAL section appended (under lock)
  RESEARCHER_EVAL_release:
    release_lock(DOC);
  RESEARCHER_EVAL_notify_plotter:
    send(research_to_plotter, "ready");
  RESEARCHER_EVAL_notify_checker:
    send(research_to_checker, "ready");
  RESEARCHER_EVAL_done:
    skip;
}

\* PLOTTER drains all three "ready" signals (any arrival order — one fan-in
\* channel), then adds a figure under the DOC lock. By the time it acquires,
\* every researcher has released, so it never contends.
fair process (PLOTTER_proc \in {PLOTTER})
variables msg = "";
{
  PLOTTER_recv1:
    receive(research_to_plotter, msg);
  PLOTTER_recv2:
    receive(research_to_plotter, msg);
  PLOTTER_recv3:
    receive(research_to_plotter, msg);
  PLOTTER_acquire:
    acquire_lock(DOC);
  PLOTTER_write:
    skip; \* domain: add architecture/taxonomy figure into research.md (under lock)
  PLOTTER_release:
    release_lock(DOC);
  PLOTTER_notify:
    send(plotter_to_approver, "figures");
  PLOTTER_done:
    skip;
}

\* CHECKER drains all three "ready" signals, then reads research.md and writes
\* its findings to a SEPARATE file (no lock), then signals the approver.
fair process (CHECKER_proc \in {CHECKER})
variables msg = "";
{
  CHECKER_recv1:
    receive(research_to_checker, msg);
  CHECKER_recv2:
    receive(research_to_checker, msg);
  CHECKER_recv3:
    receive(research_to_checker, msg);
  CHECKER_verify:
    skip; \* domain: Read research.md, verify claims, Write data_check.md (no lock)
  CHECKER_notify:
    send(checker_to_approver, "verified");
  CHECKER_done:
    skip;
}

\* APPROVER waits for BOTH figures and data-check, then reads everything and
\* writes the final acceptance verdict.
fair process (APPROVER_proc \in {APPROVER})
variables msg = "";
{
  APPROVER_recv_figures:
    receive(plotter_to_approver, msg);
  APPROVER_recv_verified:
    receive(checker_to_approver, msg);
  APPROVER_finalize:
    skip; \* domain: Read research.md + data_check.md, Write ACCEPTANCE.md verdict
  APPROVER_done:
    skip;
}

} *)

AllDone == \A p \in {RESEARCHER_FM, RESEARCHER_RT, RESEARCHER_EVAL, PLOTTER, CHECKER, APPROVER}: pc[p] = "Done"

TypeInvariant ==
  /\ \A p \in {RESEARCHER_FM, RESEARCHER_RT, RESEARCHER_EVAL, PLOTTER, CHECKER, APPROVER}: pc[p] \in STRING
  /\ DOC \in {RESEARCHER_FM, RESEARCHER_RT, RESEARCHER_EVAL, PLOTTER, CHECKER, APPROVER, "FREE"}
  /\ research_to_plotter \in Seq(STRING)
  /\ research_to_checker \in Seq(STRING)
  /\ plotter_to_approver \in Seq(STRING)
  /\ checker_to_approver \in Seq(STRING)

NoOrphanLocks ==
  AllDone => (DOC = "FREE")

ChannelsDrained ==
  AllDone => (Len(research_to_plotter) = 0 /\ Len(research_to_checker) = 0 /\ Len(plotter_to_approver) = 0 /\ Len(checker_to_approver) = 0)

ChannelBound ==
  Len(research_to_plotter) <= 3 /\ Len(research_to_checker) <= 3 /\ Len(plotter_to_approver) <= 3 /\ Len(checker_to_approver) <= 3

====