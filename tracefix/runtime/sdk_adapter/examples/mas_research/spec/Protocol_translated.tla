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
\* BEGIN TRANSLATION (chksum(pcal) = "fc021dca" /\ chksum(tla) = "af02bcdc")
\* Process variable msg of process RESEARCHER_FM_proc at line 37 col 11 changed to msg_
\* Process variable msg of process RESEARCHER_RT_proc at line 56 col 11 changed to msg_R
\* Process variable msg of process RESEARCHER_EVAL_proc at line 75 col 11 changed to msg_RE
\* Process variable msg of process PLOTTER_proc at line 97 col 11 changed to msg_P
\* Process variable msg of process CHECKER_proc at line 120 col 11 changed to msg_C
VARIABLES pc, research_to_plotter, research_to_checker, plotter_to_approver, 
          checker_to_approver, DOC, msg_, msg_R, msg_RE, msg_P, msg_C, msg

vars == << pc, research_to_plotter, research_to_checker, plotter_to_approver, 
           checker_to_approver, DOC, msg_, msg_R, msg_RE, msg_P, msg_C, msg
        >>

ProcSet == ({RESEARCHER_FM}) \cup ({RESEARCHER_RT}) \cup ({RESEARCHER_EVAL}) \cup ({PLOTTER}) \cup ({CHECKER}) \cup ({APPROVER})

Init == (* Global variables *)
        /\ research_to_plotter = <<>>
        /\ research_to_checker = <<>>
        /\ plotter_to_approver = <<>>
        /\ checker_to_approver = <<>>
        /\ DOC = "FREE"
        (* Process RESEARCHER_FM_proc *)
        /\ msg_ = [self \in {RESEARCHER_FM} |-> ""]
        (* Process RESEARCHER_RT_proc *)
        /\ msg_R = [self \in {RESEARCHER_RT} |-> ""]
        (* Process RESEARCHER_EVAL_proc *)
        /\ msg_RE = [self \in {RESEARCHER_EVAL} |-> ""]
        (* Process PLOTTER_proc *)
        /\ msg_P = [self \in {PLOTTER} |-> ""]
        (* Process CHECKER_proc *)
        /\ msg_C = [self \in {CHECKER} |-> ""]
        (* Process APPROVER_proc *)
        /\ msg = [self \in {APPROVER} |-> ""]
        /\ pc = [self \in ProcSet |-> CASE self \in {RESEARCHER_FM} -> "RESEARCHER_FM_draft"
                                        [] self \in {RESEARCHER_RT} -> "RESEARCHER_RT_draft"
                                        [] self \in {RESEARCHER_EVAL} -> "RESEARCHER_EVAL_draft"
                                        [] self \in {PLOTTER} -> "PLOTTER_recv1"
                                        [] self \in {CHECKER} -> "CHECKER_recv1"
                                        [] self \in {APPROVER} -> "APPROVER_recv_figures"]

RESEARCHER_FM_draft(self) == /\ pc[self] = "RESEARCHER_FM_draft"
                             /\ TRUE
                             /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_FM_acquire"]
                             /\ UNCHANGED << research_to_plotter, 
                                             research_to_checker, 
                                             plotter_to_approver, 
                                             checker_to_approver, DOC, msg_, 
                                             msg_R, msg_RE, msg_P, msg_C, msg >>

RESEARCHER_FM_acquire(self) == /\ pc[self] = "RESEARCHER_FM_acquire"
                               /\ DOC = "FREE"
                               /\ DOC' = self
                               /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_FM_write"]
                               /\ UNCHANGED << research_to_plotter, 
                                               research_to_checker, 
                                               plotter_to_approver, 
                                               checker_to_approver, msg_, 
                                               msg_R, msg_RE, msg_P, msg_C, 
                                               msg >>

RESEARCHER_FM_write(self) == /\ pc[self] = "RESEARCHER_FM_write"
                             /\ TRUE
                             /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_FM_release"]
                             /\ UNCHANGED << research_to_plotter, 
                                             research_to_checker, 
                                             plotter_to_approver, 
                                             checker_to_approver, DOC, msg_, 
                                             msg_R, msg_RE, msg_P, msg_C, msg >>

RESEARCHER_FM_release(self) == /\ pc[self] = "RESEARCHER_FM_release"
                               /\ DOC' = "FREE"
                               /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_FM_notify_plotter"]
                               /\ UNCHANGED << research_to_plotter, 
                                               research_to_checker, 
                                               plotter_to_approver, 
                                               checker_to_approver, msg_, 
                                               msg_R, msg_RE, msg_P, msg_C, 
                                               msg >>

RESEARCHER_FM_notify_plotter(self) == /\ pc[self] = "RESEARCHER_FM_notify_plotter"
                                      /\ research_to_plotter' = Append(research_to_plotter, "ready")
                                      /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_FM_notify_checker"]
                                      /\ UNCHANGED << research_to_checker, 
                                                      plotter_to_approver, 
                                                      checker_to_approver, DOC, 
                                                      msg_, msg_R, msg_RE, 
                                                      msg_P, msg_C, msg >>

RESEARCHER_FM_notify_checker(self) == /\ pc[self] = "RESEARCHER_FM_notify_checker"
                                      /\ research_to_checker' = Append(research_to_checker, "ready")
                                      /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_FM_done"]
                                      /\ UNCHANGED << research_to_plotter, 
                                                      plotter_to_approver, 
                                                      checker_to_approver, DOC, 
                                                      msg_, msg_R, msg_RE, 
                                                      msg_P, msg_C, msg >>

RESEARCHER_FM_done(self) == /\ pc[self] = "RESEARCHER_FM_done"
                            /\ TRUE
                            /\ pc' = [pc EXCEPT ![self] = "Done"]
                            /\ UNCHANGED << research_to_plotter, 
                                            research_to_checker, 
                                            plotter_to_approver, 
                                            checker_to_approver, DOC, msg_, 
                                            msg_R, msg_RE, msg_P, msg_C, msg >>

RESEARCHER_FM_proc(self) == RESEARCHER_FM_draft(self)
                               \/ RESEARCHER_FM_acquire(self)
                               \/ RESEARCHER_FM_write(self)
                               \/ RESEARCHER_FM_release(self)
                               \/ RESEARCHER_FM_notify_plotter(self)
                               \/ RESEARCHER_FM_notify_checker(self)
                               \/ RESEARCHER_FM_done(self)

RESEARCHER_RT_draft(self) == /\ pc[self] = "RESEARCHER_RT_draft"
                             /\ TRUE
                             /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_RT_acquire"]
                             /\ UNCHANGED << research_to_plotter, 
                                             research_to_checker, 
                                             plotter_to_approver, 
                                             checker_to_approver, DOC, msg_, 
                                             msg_R, msg_RE, msg_P, msg_C, msg >>

RESEARCHER_RT_acquire(self) == /\ pc[self] = "RESEARCHER_RT_acquire"
                               /\ DOC = "FREE"
                               /\ DOC' = self
                               /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_RT_write"]
                               /\ UNCHANGED << research_to_plotter, 
                                               research_to_checker, 
                                               plotter_to_approver, 
                                               checker_to_approver, msg_, 
                                               msg_R, msg_RE, msg_P, msg_C, 
                                               msg >>

RESEARCHER_RT_write(self) == /\ pc[self] = "RESEARCHER_RT_write"
                             /\ TRUE
                             /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_RT_release"]
                             /\ UNCHANGED << research_to_plotter, 
                                             research_to_checker, 
                                             plotter_to_approver, 
                                             checker_to_approver, DOC, msg_, 
                                             msg_R, msg_RE, msg_P, msg_C, msg >>

RESEARCHER_RT_release(self) == /\ pc[self] = "RESEARCHER_RT_release"
                               /\ DOC' = "FREE"
                               /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_RT_notify_plotter"]
                               /\ UNCHANGED << research_to_plotter, 
                                               research_to_checker, 
                                               plotter_to_approver, 
                                               checker_to_approver, msg_, 
                                               msg_R, msg_RE, msg_P, msg_C, 
                                               msg >>

RESEARCHER_RT_notify_plotter(self) == /\ pc[self] = "RESEARCHER_RT_notify_plotter"
                                      /\ research_to_plotter' = Append(research_to_plotter, "ready")
                                      /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_RT_notify_checker"]
                                      /\ UNCHANGED << research_to_checker, 
                                                      plotter_to_approver, 
                                                      checker_to_approver, DOC, 
                                                      msg_, msg_R, msg_RE, 
                                                      msg_P, msg_C, msg >>

RESEARCHER_RT_notify_checker(self) == /\ pc[self] = "RESEARCHER_RT_notify_checker"
                                      /\ research_to_checker' = Append(research_to_checker, "ready")
                                      /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_RT_done"]
                                      /\ UNCHANGED << research_to_plotter, 
                                                      plotter_to_approver, 
                                                      checker_to_approver, DOC, 
                                                      msg_, msg_R, msg_RE, 
                                                      msg_P, msg_C, msg >>

RESEARCHER_RT_done(self) == /\ pc[self] = "RESEARCHER_RT_done"
                            /\ TRUE
                            /\ pc' = [pc EXCEPT ![self] = "Done"]
                            /\ UNCHANGED << research_to_plotter, 
                                            research_to_checker, 
                                            plotter_to_approver, 
                                            checker_to_approver, DOC, msg_, 
                                            msg_R, msg_RE, msg_P, msg_C, msg >>

RESEARCHER_RT_proc(self) == RESEARCHER_RT_draft(self)
                               \/ RESEARCHER_RT_acquire(self)
                               \/ RESEARCHER_RT_write(self)
                               \/ RESEARCHER_RT_release(self)
                               \/ RESEARCHER_RT_notify_plotter(self)
                               \/ RESEARCHER_RT_notify_checker(self)
                               \/ RESEARCHER_RT_done(self)

RESEARCHER_EVAL_draft(self) == /\ pc[self] = "RESEARCHER_EVAL_draft"
                               /\ TRUE
                               /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_EVAL_acquire"]
                               /\ UNCHANGED << research_to_plotter, 
                                               research_to_checker, 
                                               plotter_to_approver, 
                                               checker_to_approver, DOC, msg_, 
                                               msg_R, msg_RE, msg_P, msg_C, 
                                               msg >>

RESEARCHER_EVAL_acquire(self) == /\ pc[self] = "RESEARCHER_EVAL_acquire"
                                 /\ DOC = "FREE"
                                 /\ DOC' = self
                                 /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_EVAL_write"]
                                 /\ UNCHANGED << research_to_plotter, 
                                                 research_to_checker, 
                                                 plotter_to_approver, 
                                                 checker_to_approver, msg_, 
                                                 msg_R, msg_RE, msg_P, msg_C, 
                                                 msg >>

RESEARCHER_EVAL_write(self) == /\ pc[self] = "RESEARCHER_EVAL_write"
                               /\ TRUE
                               /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_EVAL_release"]
                               /\ UNCHANGED << research_to_plotter, 
                                               research_to_checker, 
                                               plotter_to_approver, 
                                               checker_to_approver, DOC, msg_, 
                                               msg_R, msg_RE, msg_P, msg_C, 
                                               msg >>

RESEARCHER_EVAL_release(self) == /\ pc[self] = "RESEARCHER_EVAL_release"
                                 /\ DOC' = "FREE"
                                 /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_EVAL_notify_plotter"]
                                 /\ UNCHANGED << research_to_plotter, 
                                                 research_to_checker, 
                                                 plotter_to_approver, 
                                                 checker_to_approver, msg_, 
                                                 msg_R, msg_RE, msg_P, msg_C, 
                                                 msg >>

RESEARCHER_EVAL_notify_plotter(self) == /\ pc[self] = "RESEARCHER_EVAL_notify_plotter"
                                        /\ research_to_plotter' = Append(research_to_plotter, "ready")
                                        /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_EVAL_notify_checker"]
                                        /\ UNCHANGED << research_to_checker, 
                                                        plotter_to_approver, 
                                                        checker_to_approver, 
                                                        DOC, msg_, msg_R, 
                                                        msg_RE, msg_P, msg_C, 
                                                        msg >>

RESEARCHER_EVAL_notify_checker(self) == /\ pc[self] = "RESEARCHER_EVAL_notify_checker"
                                        /\ research_to_checker' = Append(research_to_checker, "ready")
                                        /\ pc' = [pc EXCEPT ![self] = "RESEARCHER_EVAL_done"]
                                        /\ UNCHANGED << research_to_plotter, 
                                                        plotter_to_approver, 
                                                        checker_to_approver, 
                                                        DOC, msg_, msg_R, 
                                                        msg_RE, msg_P, msg_C, 
                                                        msg >>

RESEARCHER_EVAL_done(self) == /\ pc[self] = "RESEARCHER_EVAL_done"
                              /\ TRUE
                              /\ pc' = [pc EXCEPT ![self] = "Done"]
                              /\ UNCHANGED << research_to_plotter, 
                                              research_to_checker, 
                                              plotter_to_approver, 
                                              checker_to_approver, DOC, msg_, 
                                              msg_R, msg_RE, msg_P, msg_C, msg >>

RESEARCHER_EVAL_proc(self) == RESEARCHER_EVAL_draft(self)
                                 \/ RESEARCHER_EVAL_acquire(self)
                                 \/ RESEARCHER_EVAL_write(self)
                                 \/ RESEARCHER_EVAL_release(self)
                                 \/ RESEARCHER_EVAL_notify_plotter(self)
                                 \/ RESEARCHER_EVAL_notify_checker(self)
                                 \/ RESEARCHER_EVAL_done(self)

PLOTTER_recv1(self) == /\ pc[self] = "PLOTTER_recv1"
                       /\ Len(research_to_plotter) > 0
                       /\ msg_P' = [msg_P EXCEPT ![self] = Head(research_to_plotter)]
                       /\ research_to_plotter' = Tail(research_to_plotter)
                       /\ pc' = [pc EXCEPT ![self] = "PLOTTER_recv2"]
                       /\ UNCHANGED << research_to_checker, 
                                       plotter_to_approver, 
                                       checker_to_approver, DOC, msg_, msg_R, 
                                       msg_RE, msg_C, msg >>

PLOTTER_recv2(self) == /\ pc[self] = "PLOTTER_recv2"
                       /\ Len(research_to_plotter) > 0
                       /\ msg_P' = [msg_P EXCEPT ![self] = Head(research_to_plotter)]
                       /\ research_to_plotter' = Tail(research_to_plotter)
                       /\ pc' = [pc EXCEPT ![self] = "PLOTTER_recv3"]
                       /\ UNCHANGED << research_to_checker, 
                                       plotter_to_approver, 
                                       checker_to_approver, DOC, msg_, msg_R, 
                                       msg_RE, msg_C, msg >>

PLOTTER_recv3(self) == /\ pc[self] = "PLOTTER_recv3"
                       /\ Len(research_to_plotter) > 0
                       /\ msg_P' = [msg_P EXCEPT ![self] = Head(research_to_plotter)]
                       /\ research_to_plotter' = Tail(research_to_plotter)
                       /\ pc' = [pc EXCEPT ![self] = "PLOTTER_acquire"]
                       /\ UNCHANGED << research_to_checker, 
                                       plotter_to_approver, 
                                       checker_to_approver, DOC, msg_, msg_R, 
                                       msg_RE, msg_C, msg >>

PLOTTER_acquire(self) == /\ pc[self] = "PLOTTER_acquire"
                         /\ DOC = "FREE"
                         /\ DOC' = self
                         /\ pc' = [pc EXCEPT ![self] = "PLOTTER_write"]
                         /\ UNCHANGED << research_to_plotter, 
                                         research_to_checker, 
                                         plotter_to_approver, 
                                         checker_to_approver, msg_, msg_R, 
                                         msg_RE, msg_P, msg_C, msg >>

PLOTTER_write(self) == /\ pc[self] = "PLOTTER_write"
                       /\ TRUE
                       /\ pc' = [pc EXCEPT ![self] = "PLOTTER_release"]
                       /\ UNCHANGED << research_to_plotter, 
                                       research_to_checker, 
                                       plotter_to_approver, 
                                       checker_to_approver, DOC, msg_, msg_R, 
                                       msg_RE, msg_P, msg_C, msg >>

PLOTTER_release(self) == /\ pc[self] = "PLOTTER_release"
                         /\ DOC' = "FREE"
                         /\ pc' = [pc EXCEPT ![self] = "PLOTTER_notify"]
                         /\ UNCHANGED << research_to_plotter, 
                                         research_to_checker, 
                                         plotter_to_approver, 
                                         checker_to_approver, msg_, msg_R, 
                                         msg_RE, msg_P, msg_C, msg >>

PLOTTER_notify(self) == /\ pc[self] = "PLOTTER_notify"
                        /\ plotter_to_approver' = Append(plotter_to_approver, "figures")
                        /\ pc' = [pc EXCEPT ![self] = "PLOTTER_done"]
                        /\ UNCHANGED << research_to_plotter, 
                                        research_to_checker, 
                                        checker_to_approver, DOC, msg_, msg_R, 
                                        msg_RE, msg_P, msg_C, msg >>

PLOTTER_done(self) == /\ pc[self] = "PLOTTER_done"
                      /\ TRUE
                      /\ pc' = [pc EXCEPT ![self] = "Done"]
                      /\ UNCHANGED << research_to_plotter, research_to_checker, 
                                      plotter_to_approver, checker_to_approver, 
                                      DOC, msg_, msg_R, msg_RE, msg_P, msg_C, 
                                      msg >>

PLOTTER_proc(self) == PLOTTER_recv1(self) \/ PLOTTER_recv2(self)
                         \/ PLOTTER_recv3(self) \/ PLOTTER_acquire(self)
                         \/ PLOTTER_write(self) \/ PLOTTER_release(self)
                         \/ PLOTTER_notify(self) \/ PLOTTER_done(self)

CHECKER_recv1(self) == /\ pc[self] = "CHECKER_recv1"
                       /\ Len(research_to_checker) > 0
                       /\ msg_C' = [msg_C EXCEPT ![self] = Head(research_to_checker)]
                       /\ research_to_checker' = Tail(research_to_checker)
                       /\ pc' = [pc EXCEPT ![self] = "CHECKER_recv2"]
                       /\ UNCHANGED << research_to_plotter, 
                                       plotter_to_approver, 
                                       checker_to_approver, DOC, msg_, msg_R, 
                                       msg_RE, msg_P, msg >>

CHECKER_recv2(self) == /\ pc[self] = "CHECKER_recv2"
                       /\ Len(research_to_checker) > 0
                       /\ msg_C' = [msg_C EXCEPT ![self] = Head(research_to_checker)]
                       /\ research_to_checker' = Tail(research_to_checker)
                       /\ pc' = [pc EXCEPT ![self] = "CHECKER_recv3"]
                       /\ UNCHANGED << research_to_plotter, 
                                       plotter_to_approver, 
                                       checker_to_approver, DOC, msg_, msg_R, 
                                       msg_RE, msg_P, msg >>

CHECKER_recv3(self) == /\ pc[self] = "CHECKER_recv3"
                       /\ Len(research_to_checker) > 0
                       /\ msg_C' = [msg_C EXCEPT ![self] = Head(research_to_checker)]
                       /\ research_to_checker' = Tail(research_to_checker)
                       /\ pc' = [pc EXCEPT ![self] = "CHECKER_verify"]
                       /\ UNCHANGED << research_to_plotter, 
                                       plotter_to_approver, 
                                       checker_to_approver, DOC, msg_, msg_R, 
                                       msg_RE, msg_P, msg >>

CHECKER_verify(self) == /\ pc[self] = "CHECKER_verify"
                        /\ TRUE
                        /\ pc' = [pc EXCEPT ![self] = "CHECKER_notify"]
                        /\ UNCHANGED << research_to_plotter, 
                                        research_to_checker, 
                                        plotter_to_approver, 
                                        checker_to_approver, DOC, msg_, msg_R, 
                                        msg_RE, msg_P, msg_C, msg >>

CHECKER_notify(self) == /\ pc[self] = "CHECKER_notify"
                        /\ checker_to_approver' = Append(checker_to_approver, "verified")
                        /\ pc' = [pc EXCEPT ![self] = "CHECKER_done"]
                        /\ UNCHANGED << research_to_plotter, 
                                        research_to_checker, 
                                        plotter_to_approver, DOC, msg_, msg_R, 
                                        msg_RE, msg_P, msg_C, msg >>

CHECKER_done(self) == /\ pc[self] = "CHECKER_done"
                      /\ TRUE
                      /\ pc' = [pc EXCEPT ![self] = "Done"]
                      /\ UNCHANGED << research_to_plotter, research_to_checker, 
                                      plotter_to_approver, checker_to_approver, 
                                      DOC, msg_, msg_R, msg_RE, msg_P, msg_C, 
                                      msg >>

CHECKER_proc(self) == CHECKER_recv1(self) \/ CHECKER_recv2(self)
                         \/ CHECKER_recv3(self) \/ CHECKER_verify(self)
                         \/ CHECKER_notify(self) \/ CHECKER_done(self)

APPROVER_recv_figures(self) == /\ pc[self] = "APPROVER_recv_figures"
                               /\ Len(plotter_to_approver) > 0
                               /\ msg' = [msg EXCEPT ![self] = Head(plotter_to_approver)]
                               /\ plotter_to_approver' = Tail(plotter_to_approver)
                               /\ pc' = [pc EXCEPT ![self] = "APPROVER_recv_verified"]
                               /\ UNCHANGED << research_to_plotter, 
                                               research_to_checker, 
                                               checker_to_approver, DOC, msg_, 
                                               msg_R, msg_RE, msg_P, msg_C >>

APPROVER_recv_verified(self) == /\ pc[self] = "APPROVER_recv_verified"
                                /\ Len(checker_to_approver) > 0
                                /\ msg' = [msg EXCEPT ![self] = Head(checker_to_approver)]
                                /\ checker_to_approver' = Tail(checker_to_approver)
                                /\ pc' = [pc EXCEPT ![self] = "APPROVER_finalize"]
                                /\ UNCHANGED << research_to_plotter, 
                                                research_to_checker, 
                                                plotter_to_approver, DOC, msg_, 
                                                msg_R, msg_RE, msg_P, msg_C >>

APPROVER_finalize(self) == /\ pc[self] = "APPROVER_finalize"
                           /\ TRUE
                           /\ pc' = [pc EXCEPT ![self] = "APPROVER_done"]
                           /\ UNCHANGED << research_to_plotter, 
                                           research_to_checker, 
                                           plotter_to_approver, 
                                           checker_to_approver, DOC, msg_, 
                                           msg_R, msg_RE, msg_P, msg_C, msg >>

APPROVER_done(self) == /\ pc[self] = "APPROVER_done"
                       /\ TRUE
                       /\ pc' = [pc EXCEPT ![self] = "Done"]
                       /\ UNCHANGED << research_to_plotter, 
                                       research_to_checker, 
                                       plotter_to_approver, 
                                       checker_to_approver, DOC, msg_, msg_R, 
                                       msg_RE, msg_P, msg_C, msg >>

APPROVER_proc(self) == APPROVER_recv_figures(self)
                          \/ APPROVER_recv_verified(self)
                          \/ APPROVER_finalize(self) \/ APPROVER_done(self)

(* Allow infinite stuttering to prevent deadlock on termination. *)
Terminating == /\ \A self \in ProcSet: pc[self] = "Done"
               /\ UNCHANGED vars

Next == (\E self \in {RESEARCHER_FM}: RESEARCHER_FM_proc(self))
           \/ (\E self \in {RESEARCHER_RT}: RESEARCHER_RT_proc(self))
           \/ (\E self \in {RESEARCHER_EVAL}: RESEARCHER_EVAL_proc(self))
           \/ (\E self \in {PLOTTER}: PLOTTER_proc(self))
           \/ (\E self \in {CHECKER}: CHECKER_proc(self))
           \/ (\E self \in {APPROVER}: APPROVER_proc(self))
           \/ Terminating

Spec == /\ Init /\ [][Next]_vars
        /\ \A self \in {RESEARCHER_FM} : WF_vars(RESEARCHER_FM_proc(self))
        /\ \A self \in {RESEARCHER_RT} : WF_vars(RESEARCHER_RT_proc(self))
        /\ \A self \in {RESEARCHER_EVAL} : WF_vars(RESEARCHER_EVAL_proc(self))
        /\ \A self \in {PLOTTER} : WF_vars(PLOTTER_proc(self))
        /\ \A self \in {CHECKER} : WF_vars(CHECKER_proc(self))
        /\ \A self \in {APPROVER} : WF_vars(APPROVER_proc(self))

Termination == <>(\A self \in ProcSet: pc[self] = "Done")

\* END TRANSLATION 

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
