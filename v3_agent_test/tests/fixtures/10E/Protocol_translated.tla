---- MODULE Protocol ----
EXTENDS Integers, Sequences, TLC

CONSTANTS Builder_a, Builder_b, Integrator

(* --algorithm Protocol {
variables
  a_to_b = <<>>; \* builder_a -> builder_b, labels: ['types_updated', 'types_stable']
  a_to_integrator = <<>>; \* builder_a -> integrator, labels: ['done']
  b_to_integrator = <<>>; \* builder_b -> integrator, labels: ['done']
  core_lib = "FREE"; \* Lock
  shared_types = "FREE"; \* Lock

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

\* Builder A: compile with core_lib, update shared_types, notify B, signal done
fair process (builder_a_proc \in {Builder_a})
variables msg = "";
{
  ba_acq_core:
    acquire_lock(core_lib);  \* exclusive access to core_lib for compilation
  ba_rel_core:
    release_lock(core_lib);
  ba_acq_types:
    acquire_lock(shared_types); \* exclusive access to write type defs
  ba_rel_types:
    release_lock(shared_types);
  ba_notify:
    \* Nondeterministic: either types were updated or stable
    either {
      send(a_to_b, "types_updated");
    } or {
      send(a_to_b, "types_stable");
    };
  ba_done:
    send(a_to_integrator, "done");
}

\* Builder B: compile with core_lib+shared_types, check if rebuild needed
fair process (builder_b_proc \in {Builder_b})
variables msg = "";
{
  bb_acq_core:
    acquire_lock(core_lib);  \* exclusive access to core_lib for compilation
  bb_rel_core:
    release_lock(core_lib);
  bb_acq_types:
    acquire_lock(shared_types); \* read shared types during compilation
  bb_rel_types:
    release_lock(shared_types);
  bb_wait_notify:
    receive(a_to_b, msg);  \* wait for A's notification
  bb_check:
    if (msg = "types_updated") {
      \* Must recompile with updated types
      goto bb_rebuild;
    } else {
      \* Types stable, compilation is valid
      goto bb_done;
    };
  bb_rebuild:
    acquire_lock(core_lib);  \* recompile: need core_lib again
  bb_rebuild_rel_core:
    release_lock(core_lib);
  bb_rebuild_types:
    acquire_lock(shared_types); \* re-read updated types
  bb_rebuild_rel_types:
    release_lock(shared_types);
  bb_done:
    send(b_to_integrator, "done");
}

\* Integrator: wait for both builders to finish, then link
fair process (integrator_proc \in {Integrator})
variables msg = "", gotA = FALSE, gotB = FALSE;
{
  int_collect:
    while (~gotA \/ ~gotB) {
      int_recv:
        either {
          receive(a_to_integrator, msg);
          gotA := TRUE;
        } or {
          receive(b_to_integrator, msg);
          gotB := TRUE;
        };
    };
  int_link:
    skip; \* link both modules into final artifact
}

} *)
\* BEGIN TRANSLATION (chksum(pcal) = "d177d0d7" /\ chksum(tla) = "636ed66")
\* Process variable msg of process builder_a_proc at line 35 col 11 changed to msg_
\* Process variable msg of process builder_b_proc at line 58 col 11 changed to msg_b
VARIABLES pc, a_to_b, a_to_integrator, b_to_integrator, core_lib, 
          shared_types, msg_, msg_b, msg, gotA, gotB

vars == << pc, a_to_b, a_to_integrator, b_to_integrator, core_lib, 
           shared_types, msg_, msg_b, msg, gotA, gotB >>

ProcSet == ({Builder_a}) \cup ({Builder_b}) \cup ({Integrator})

Init == (* Global variables *)
        /\ a_to_b = <<>>
        /\ a_to_integrator = <<>>
        /\ b_to_integrator = <<>>
        /\ core_lib = "FREE"
        /\ shared_types = "FREE"
        (* Process builder_a_proc *)
        /\ msg_ = [self \in {Builder_a} |-> ""]
        (* Process builder_b_proc *)
        /\ msg_b = [self \in {Builder_b} |-> ""]
        (* Process integrator_proc *)
        /\ msg = [self \in {Integrator} |-> ""]
        /\ gotA = [self \in {Integrator} |-> FALSE]
        /\ gotB = [self \in {Integrator} |-> FALSE]
        /\ pc = [self \in ProcSet |-> CASE self \in {Builder_a} -> "ba_acq_core"
                                        [] self \in {Builder_b} -> "bb_acq_core"
                                        [] self \in {Integrator} -> "int_collect"]

ba_acq_core(self) == /\ pc[self] = "ba_acq_core"
                     /\ core_lib = "FREE"
                     /\ core_lib' = self
                     /\ pc' = [pc EXCEPT ![self] = "ba_rel_core"]
                     /\ UNCHANGED << a_to_b, a_to_integrator, b_to_integrator, 
                                     shared_types, msg_, msg_b, msg, gotA, 
                                     gotB >>

ba_rel_core(self) == /\ pc[self] = "ba_rel_core"
                     /\ core_lib' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "ba_acq_types"]
                     /\ UNCHANGED << a_to_b, a_to_integrator, b_to_integrator, 
                                     shared_types, msg_, msg_b, msg, gotA, 
                                     gotB >>

ba_acq_types(self) == /\ pc[self] = "ba_acq_types"
                      /\ shared_types = "FREE"
                      /\ shared_types' = self
                      /\ pc' = [pc EXCEPT ![self] = "ba_rel_types"]
                      /\ UNCHANGED << a_to_b, a_to_integrator, b_to_integrator, 
                                      core_lib, msg_, msg_b, msg, gotA, gotB >>

ba_rel_types(self) == /\ pc[self] = "ba_rel_types"
                      /\ shared_types' = "FREE"
                      /\ pc' = [pc EXCEPT ![self] = "ba_notify"]
                      /\ UNCHANGED << a_to_b, a_to_integrator, b_to_integrator, 
                                      core_lib, msg_, msg_b, msg, gotA, gotB >>

ba_notify(self) == /\ pc[self] = "ba_notify"
                   /\ \/ /\ a_to_b' = Append(a_to_b, "types_updated")
                      \/ /\ a_to_b' = Append(a_to_b, "types_stable")
                   /\ pc' = [pc EXCEPT ![self] = "ba_done"]
                   /\ UNCHANGED << a_to_integrator, b_to_integrator, core_lib, 
                                   shared_types, msg_, msg_b, msg, gotA, gotB >>

ba_done(self) == /\ pc[self] = "ba_done"
                 /\ a_to_integrator' = Append(a_to_integrator, "done")
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << a_to_b, b_to_integrator, core_lib, 
                                 shared_types, msg_, msg_b, msg, gotA, gotB >>

builder_a_proc(self) == ba_acq_core(self) \/ ba_rel_core(self)
                           \/ ba_acq_types(self) \/ ba_rel_types(self)
                           \/ ba_notify(self) \/ ba_done(self)

bb_acq_core(self) == /\ pc[self] = "bb_acq_core"
                     /\ core_lib = "FREE"
                     /\ core_lib' = self
                     /\ pc' = [pc EXCEPT ![self] = "bb_rel_core"]
                     /\ UNCHANGED << a_to_b, a_to_integrator, b_to_integrator, 
                                     shared_types, msg_, msg_b, msg, gotA, 
                                     gotB >>

bb_rel_core(self) == /\ pc[self] = "bb_rel_core"
                     /\ core_lib' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "bb_acq_types"]
                     /\ UNCHANGED << a_to_b, a_to_integrator, b_to_integrator, 
                                     shared_types, msg_, msg_b, msg, gotA, 
                                     gotB >>

bb_acq_types(self) == /\ pc[self] = "bb_acq_types"
                      /\ shared_types = "FREE"
                      /\ shared_types' = self
                      /\ pc' = [pc EXCEPT ![self] = "bb_rel_types"]
                      /\ UNCHANGED << a_to_b, a_to_integrator, b_to_integrator, 
                                      core_lib, msg_, msg_b, msg, gotA, gotB >>

bb_rel_types(self) == /\ pc[self] = "bb_rel_types"
                      /\ shared_types' = "FREE"
                      /\ pc' = [pc EXCEPT ![self] = "bb_wait_notify"]
                      /\ UNCHANGED << a_to_b, a_to_integrator, b_to_integrator, 
                                      core_lib, msg_, msg_b, msg, gotA, gotB >>

bb_wait_notify(self) == /\ pc[self] = "bb_wait_notify"
                        /\ Len(a_to_b) > 0
                        /\ msg_b' = [msg_b EXCEPT ![self] = Head(a_to_b)]
                        /\ a_to_b' = Tail(a_to_b)
                        /\ pc' = [pc EXCEPT ![self] = "bb_check"]
                        /\ UNCHANGED << a_to_integrator, b_to_integrator, 
                                        core_lib, shared_types, msg_, msg, 
                                        gotA, gotB >>

bb_check(self) == /\ pc[self] = "bb_check"
                  /\ IF msg_b[self] = "types_updated"
                        THEN /\ pc' = [pc EXCEPT ![self] = "bb_rebuild"]
                        ELSE /\ pc' = [pc EXCEPT ![self] = "bb_done"]
                  /\ UNCHANGED << a_to_b, a_to_integrator, b_to_integrator, 
                                  core_lib, shared_types, msg_, msg_b, msg, 
                                  gotA, gotB >>

bb_rebuild(self) == /\ pc[self] = "bb_rebuild"
                    /\ core_lib = "FREE"
                    /\ core_lib' = self
                    /\ pc' = [pc EXCEPT ![self] = "bb_rebuild_rel_core"]
                    /\ UNCHANGED << a_to_b, a_to_integrator, b_to_integrator, 
                                    shared_types, msg_, msg_b, msg, gotA, gotB >>

bb_rebuild_rel_core(self) == /\ pc[self] = "bb_rebuild_rel_core"
                             /\ core_lib' = "FREE"
                             /\ pc' = [pc EXCEPT ![self] = "bb_rebuild_types"]
                             /\ UNCHANGED << a_to_b, a_to_integrator, 
                                             b_to_integrator, shared_types, 
                                             msg_, msg_b, msg, gotA, gotB >>

bb_rebuild_types(self) == /\ pc[self] = "bb_rebuild_types"
                          /\ shared_types = "FREE"
                          /\ shared_types' = self
                          /\ pc' = [pc EXCEPT ![self] = "bb_rebuild_rel_types"]
                          /\ UNCHANGED << a_to_b, a_to_integrator, 
                                          b_to_integrator, core_lib, msg_, 
                                          msg_b, msg, gotA, gotB >>

bb_rebuild_rel_types(self) == /\ pc[self] = "bb_rebuild_rel_types"
                              /\ shared_types' = "FREE"
                              /\ pc' = [pc EXCEPT ![self] = "bb_done"]
                              /\ UNCHANGED << a_to_b, a_to_integrator, 
                                              b_to_integrator, core_lib, msg_, 
                                              msg_b, msg, gotA, gotB >>

bb_done(self) == /\ pc[self] = "bb_done"
                 /\ b_to_integrator' = Append(b_to_integrator, "done")
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << a_to_b, a_to_integrator, core_lib, 
                                 shared_types, msg_, msg_b, msg, gotA, gotB >>

builder_b_proc(self) == bb_acq_core(self) \/ bb_rel_core(self)
                           \/ bb_acq_types(self) \/ bb_rel_types(self)
                           \/ bb_wait_notify(self) \/ bb_check(self)
                           \/ bb_rebuild(self) \/ bb_rebuild_rel_core(self)
                           \/ bb_rebuild_types(self)
                           \/ bb_rebuild_rel_types(self) \/ bb_done(self)

int_collect(self) == /\ pc[self] = "int_collect"
                     /\ IF ~gotA[self] \/ ~gotB[self]
                           THEN /\ pc' = [pc EXCEPT ![self] = "int_recv"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "int_link"]
                     /\ UNCHANGED << a_to_b, a_to_integrator, b_to_integrator, 
                                     core_lib, shared_types, msg_, msg_b, msg, 
                                     gotA, gotB >>

int_recv(self) == /\ pc[self] = "int_recv"
                  /\ \/ /\ Len(a_to_integrator) > 0
                        /\ msg' = [msg EXCEPT ![self] = Head(a_to_integrator)]
                        /\ a_to_integrator' = Tail(a_to_integrator)
                        /\ gotA' = [gotA EXCEPT ![self] = TRUE]
                        /\ UNCHANGED <<b_to_integrator, gotB>>
                     \/ /\ Len(b_to_integrator) > 0
                        /\ msg' = [msg EXCEPT ![self] = Head(b_to_integrator)]
                        /\ b_to_integrator' = Tail(b_to_integrator)
                        /\ gotB' = [gotB EXCEPT ![self] = TRUE]
                        /\ UNCHANGED <<a_to_integrator, gotA>>
                  /\ pc' = [pc EXCEPT ![self] = "int_collect"]
                  /\ UNCHANGED << a_to_b, core_lib, shared_types, msg_, msg_b >>

int_link(self) == /\ pc[self] = "int_link"
                  /\ TRUE
                  /\ pc' = [pc EXCEPT ![self] = "Done"]
                  /\ UNCHANGED << a_to_b, a_to_integrator, b_to_integrator, 
                                  core_lib, shared_types, msg_, msg_b, msg, 
                                  gotA, gotB >>

integrator_proc(self) == int_collect(self) \/ int_recv(self)
                            \/ int_link(self)

(* Allow infinite stuttering to prevent deadlock on termination. *)
Terminating == /\ \A self \in ProcSet: pc[self] = "Done"
               /\ UNCHANGED vars

Next == (\E self \in {Builder_a}: builder_a_proc(self))
           \/ (\E self \in {Builder_b}: builder_b_proc(self))
           \/ (\E self \in {Integrator}: integrator_proc(self))
           \/ Terminating

Spec == /\ Init /\ [][Next]_vars
        /\ \A self \in {Builder_a} : WF_vars(builder_a_proc(self))
        /\ \A self \in {Builder_b} : WF_vars(builder_b_proc(self))
        /\ \A self \in {Integrator} : WF_vars(integrator_proc(self))

Termination == <>(\A self \in ProcSet: pc[self] = "Done")

\* END TRANSLATION 

AllDone == \A p \in {Builder_a, Builder_b, Integrator}: pc[p] = "Done"

TypeInvariant ==
  /\ \A p \in {Builder_a, Builder_b, Integrator}: pc[p] \in STRING
  /\ core_lib \in {Builder_a, Builder_b, Integrator, "FREE"}
  /\ shared_types \in {Builder_a, Builder_b, Integrator, "FREE"}
  /\ a_to_b \in Seq(STRING)
  /\ a_to_integrator \in Seq(STRING)
  /\ b_to_integrator \in Seq(STRING)

NoOrphanLocks ==
  AllDone => (core_lib = "FREE" /\ shared_types = "FREE")

ChannelsDrained ==
  AllDone => (Len(a_to_b) = 0 /\ Len(a_to_integrator) = 0 /\ Len(b_to_integrator) = 0)

ChannelBound ==
  Len(a_to_b) <= 3 /\ Len(a_to_integrator) <= 3 /\ Len(b_to_integrator) <= 3

====
