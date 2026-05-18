---- MODULE Protocol ----
EXTENDS Integers, Sequences, TLC

CONSTANTS Architect, DeveloperA, DeveloperB, Reviewer, Tester

(* --algorithm Protocol {
variables
  devA_to_arch = <<>>; \* developerA -> architect, labels: ['design_proposal']
  arch_to_devA = <<>>; \* architect -> developerA, labels: ['approve', 'reject']
  devB_to_arch = <<>>; \* developerB -> architect, labels: ['design_proposal']
  arch_to_devB = <<>>; \* architect -> developerB, labels: ['approve', 'reject']
  devA_to_reviewer = <<>>; \* developerA -> reviewer, labels: ['review_request', 'done']
  reviewer_to_devA = <<>>; \* reviewer -> developerA, labels: ['approved', 'revise']
  devB_to_reviewer = <<>>; \* developerB -> reviewer, labels: ['review_request', 'done']
  reviewer_to_devB = <<>>; \* reviewer -> developerB, labels: ['approved', 'revise']
  devA_to_tester = <<>>; \* developerA -> tester, labels: ['test_request', 'done']
  tester_to_devA = <<>>; \* tester -> developerA, labels: ['pass', 'fail']
  devB_to_tester = <<>>; \* developerB -> tester, labels: ['test_request', 'done']
  tester_to_devB = <<>>; \* tester -> developerB, labels: ['pass', 'fail']
  shared_lib_lock = "FREE"; \* Lock
  merge_lock = "FREE"; \* Lock
  test_lock = "FREE"; \* Lock

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

fair process (architect_proc \in {Architect})
variables msg = "", archDoneA = FALSE, archDoneB = FALSE;
{
  arch_loop:
    while (~archDoneA \/ ~archDoneB) {
      arch_recv:
        either {
          receive(devA_to_arch, msg);
          arch_replyA:
            either {
              send(arch_to_devA, "approve");
              archDoneA := TRUE;
            } or {
              send(arch_to_devA, "reject");
            };
        } or {
          receive(devB_to_arch, msg);
          arch_replyB:
            either {
              send(arch_to_devB, "approve");
              archDoneB := TRUE;
            } or {
              send(arch_to_devB, "reject");
            };
        };
    };
  arch_done:
    skip;
}

fair process (developerA_proc \in {DeveloperA})
variables msg = "";
{
  da_design:
    send(devA_to_arch, "design_proposal");
  da_wait_arch:
    receive(arch_to_devA, msg);
  da_check_arch:
    if (msg = "reject") {
      goto da_design;
    };
  da_impl:
    acquire_lock(shared_lib_lock);
  da_release_lib:
    release_lock(shared_lib_lock);
  da_review:
    send(devA_to_reviewer, "review_request");
  da_wait_review:
    receive(reviewer_to_devA, msg);
  da_check_review:
    if (msg = "revise") {
      goto da_impl;
    };
  da_test:
    send(devA_to_tester, "test_request");
  da_wait_test:
    receive(tester_to_devA, msg);
  da_check_test:
    if (msg = "fail") {
      goto da_impl;
    };
  da_merge:
    acquire_lock(merge_lock);
  da_release_merge:
    release_lock(merge_lock);
  da_notify:
    send(devA_to_reviewer, "done");
    send(devA_to_tester, "done");
  da_done:
    skip;
}

fair process (developerB_proc \in {DeveloperB})
variables msg = "";
{
  db_design:
    send(devB_to_arch, "design_proposal");
  db_wait_arch:
    receive(arch_to_devB, msg);
  db_check_arch:
    if (msg = "reject") {
      goto db_design;
    };
  db_impl:
    acquire_lock(shared_lib_lock);
  db_release_lib:
    release_lock(shared_lib_lock);
  db_review:
    send(devB_to_reviewer, "review_request");
  db_wait_review:
    receive(reviewer_to_devB, msg);
  db_check_review:
    if (msg = "revise") {
      goto db_impl;
    };
  db_test:
    send(devB_to_tester, "test_request");
  db_wait_test:
    receive(tester_to_devB, msg);
  db_check_test:
    if (msg = "fail") {
      goto db_impl;
    };
  db_merge:
    acquire_lock(merge_lock);
  db_release_merge:
    release_lock(merge_lock);
  db_notify:
    send(devB_to_reviewer, "done");
    send(devB_to_tester, "done");
  db_done:
    skip;
}

fair process (reviewer_proc \in {Reviewer})
variables msg = "", rvDoneA = FALSE, rvDoneB = FALSE;
{
  rv_loop:
    while (~rvDoneA \/ ~rvDoneB) {
      rv_recv:
        either {
          receive(devA_to_reviewer, msg);
          rv_handleA:
            if (msg = "done") {
              rvDoneA := TRUE;
            } else {
              rv_decideA:
                either {
                  send(reviewer_to_devA, "approved");
                } or {
                  send(reviewer_to_devA, "revise");
                };
            };
        } or {
          receive(devB_to_reviewer, msg);
          rv_handleB:
            if (msg = "done") {
              rvDoneB := TRUE;
            } else {
              rv_decideB:
                either {
                  send(reviewer_to_devB, "approved");
                } or {
                  send(reviewer_to_devB, "revise");
                };
            };
        };
    };
  rv_done:
    skip;
}

fair process (tester_proc \in {Tester})
variables msg = "", tsDoneA = FALSE, tsDoneB = FALSE;
{
  ts_loop:
    while (~tsDoneA \/ ~tsDoneB) {
      ts_recv:
        either {
          receive(devA_to_tester, msg);
          ts_handleA:
            if (msg = "done") {
              tsDoneA := TRUE;
            } else {
              ts_lockA:
                acquire_lock(test_lock);
              ts_decideA:
                either {
                  send(tester_to_devA, "pass");
                } or {
                  send(tester_to_devA, "fail");
                };
              ts_unlockA:
                release_lock(test_lock);
            };
        } or {
          receive(devB_to_tester, msg);
          ts_handleB:
            if (msg = "done") {
              tsDoneB := TRUE;
            } else {
              ts_lockB:
                acquire_lock(test_lock);
              ts_decideB:
                either {
                  send(tester_to_devB, "pass");
                } or {
                  send(tester_to_devB, "fail");
                };
              ts_unlockB:
                release_lock(test_lock);
            };
        };
    };
  ts_done:
    skip;
}

} *)
\* BEGIN TRANSLATION (chksum(pcal) = "8ff4fe8e" /\ chksum(tla) = "a124b092")
\* Process variable msg of process architect_proc at line 44 col 11 changed to msg_
\* Process variable msg of process developerA_proc at line 74 col 11 changed to msg_d
\* Process variable msg of process developerB_proc at line 116 col 11 changed to msg_de
\* Process variable msg of process reviewer_proc at line 158 col 11 changed to msg_r
VARIABLES pc, devA_to_arch, arch_to_devA, devB_to_arch, arch_to_devB, 
          devA_to_reviewer, reviewer_to_devA, devB_to_reviewer, 
          reviewer_to_devB, devA_to_tester, tester_to_devA, devB_to_tester, 
          tester_to_devB, shared_lib_lock, merge_lock, test_lock, msg_, 
          archDoneA, archDoneB, msg_d, msg_de, msg_r, rvDoneA, rvDoneB, msg, 
          tsDoneA, tsDoneB

vars == << pc, devA_to_arch, arch_to_devA, devB_to_arch, arch_to_devB, 
           devA_to_reviewer, reviewer_to_devA, devB_to_reviewer, 
           reviewer_to_devB, devA_to_tester, tester_to_devA, devB_to_tester, 
           tester_to_devB, shared_lib_lock, merge_lock, test_lock, msg_, 
           archDoneA, archDoneB, msg_d, msg_de, msg_r, rvDoneA, rvDoneB, msg, 
           tsDoneA, tsDoneB >>

ProcSet == ({Architect}) \cup ({DeveloperA}) \cup ({DeveloperB}) \cup ({Reviewer}) \cup ({Tester})

Init == (* Global variables *)
        /\ devA_to_arch = <<>>
        /\ arch_to_devA = <<>>
        /\ devB_to_arch = <<>>
        /\ arch_to_devB = <<>>
        /\ devA_to_reviewer = <<>>
        /\ reviewer_to_devA = <<>>
        /\ devB_to_reviewer = <<>>
        /\ reviewer_to_devB = <<>>
        /\ devA_to_tester = <<>>
        /\ tester_to_devA = <<>>
        /\ devB_to_tester = <<>>
        /\ tester_to_devB = <<>>
        /\ shared_lib_lock = "FREE"
        /\ merge_lock = "FREE"
        /\ test_lock = "FREE"
        (* Process architect_proc *)
        /\ msg_ = [self \in {Architect} |-> ""]
        /\ archDoneA = [self \in {Architect} |-> FALSE]
        /\ archDoneB = [self \in {Architect} |-> FALSE]
        (* Process developerA_proc *)
        /\ msg_d = [self \in {DeveloperA} |-> ""]
        (* Process developerB_proc *)
        /\ msg_de = [self \in {DeveloperB} |-> ""]
        (* Process reviewer_proc *)
        /\ msg_r = [self \in {Reviewer} |-> ""]
        /\ rvDoneA = [self \in {Reviewer} |-> FALSE]
        /\ rvDoneB = [self \in {Reviewer} |-> FALSE]
        (* Process tester_proc *)
        /\ msg = [self \in {Tester} |-> ""]
        /\ tsDoneA = [self \in {Tester} |-> FALSE]
        /\ tsDoneB = [self \in {Tester} |-> FALSE]
        /\ pc = [self \in ProcSet |-> CASE self \in {Architect} -> "arch_loop"
                                        [] self \in {DeveloperA} -> "da_design"
                                        [] self \in {DeveloperB} -> "db_design"
                                        [] self \in {Reviewer} -> "rv_loop"
                                        [] self \in {Tester} -> "ts_loop"]

arch_loop(self) == /\ pc[self] = "arch_loop"
                   /\ IF ~archDoneA[self] \/ ~archDoneB[self]
                         THEN /\ pc' = [pc EXCEPT ![self] = "arch_recv"]
                         ELSE /\ pc' = [pc EXCEPT ![self] = "arch_done"]
                   /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                   arch_to_devB, devA_to_reviewer, 
                                   reviewer_to_devA, devB_to_reviewer, 
                                   reviewer_to_devB, devA_to_tester, 
                                   tester_to_devA, devB_to_tester, 
                                   tester_to_devB, shared_lib_lock, merge_lock, 
                                   test_lock, msg_, archDoneA, archDoneB, 
                                   msg_d, msg_de, msg_r, rvDoneA, rvDoneB, msg, 
                                   tsDoneA, tsDoneB >>

arch_recv(self) == /\ pc[self] = "arch_recv"
                   /\ \/ /\ Len(devA_to_arch) > 0
                         /\ msg_' = [msg_ EXCEPT ![self] = Head(devA_to_arch)]
                         /\ devA_to_arch' = Tail(devA_to_arch)
                         /\ pc' = [pc EXCEPT ![self] = "arch_replyA"]
                         /\ UNCHANGED devB_to_arch
                      \/ /\ Len(devB_to_arch) > 0
                         /\ msg_' = [msg_ EXCEPT ![self] = Head(devB_to_arch)]
                         /\ devB_to_arch' = Tail(devB_to_arch)
                         /\ pc' = [pc EXCEPT ![self] = "arch_replyB"]
                         /\ UNCHANGED devA_to_arch
                   /\ UNCHANGED << arch_to_devA, arch_to_devB, 
                                   devA_to_reviewer, reviewer_to_devA, 
                                   devB_to_reviewer, reviewer_to_devB, 
                                   devA_to_tester, tester_to_devA, 
                                   devB_to_tester, tester_to_devB, 
                                   shared_lib_lock, merge_lock, test_lock, 
                                   archDoneA, archDoneB, msg_d, msg_de, msg_r, 
                                   rvDoneA, rvDoneB, msg, tsDoneA, tsDoneB >>

arch_replyA(self) == /\ pc[self] = "arch_replyA"
                     /\ \/ /\ arch_to_devA' = Append(arch_to_devA, "approve")
                           /\ archDoneA' = [archDoneA EXCEPT ![self] = TRUE]
                        \/ /\ arch_to_devA' = Append(arch_to_devA, "reject")
                           /\ UNCHANGED archDoneA
                     /\ pc' = [pc EXCEPT ![self] = "arch_loop"]
                     /\ UNCHANGED << devA_to_arch, devB_to_arch, arch_to_devB, 
                                     devA_to_reviewer, reviewer_to_devA, 
                                     devB_to_reviewer, reviewer_to_devB, 
                                     devA_to_tester, tester_to_devA, 
                                     devB_to_tester, tester_to_devB, 
                                     shared_lib_lock, merge_lock, test_lock, 
                                     msg_, archDoneB, msg_d, msg_de, msg_r, 
                                     rvDoneA, rvDoneB, msg, tsDoneA, tsDoneB >>

arch_replyB(self) == /\ pc[self] = "arch_replyB"
                     /\ \/ /\ arch_to_devB' = Append(arch_to_devB, "approve")
                           /\ archDoneB' = [archDoneB EXCEPT ![self] = TRUE]
                        \/ /\ arch_to_devB' = Append(arch_to_devB, "reject")
                           /\ UNCHANGED archDoneB
                     /\ pc' = [pc EXCEPT ![self] = "arch_loop"]
                     /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                     devA_to_reviewer, reviewer_to_devA, 
                                     devB_to_reviewer, reviewer_to_devB, 
                                     devA_to_tester, tester_to_devA, 
                                     devB_to_tester, tester_to_devB, 
                                     shared_lib_lock, merge_lock, test_lock, 
                                     msg_, archDoneA, msg_d, msg_de, msg_r, 
                                     rvDoneA, rvDoneB, msg, tsDoneA, tsDoneB >>

arch_done(self) == /\ pc[self] = "arch_done"
                   /\ TRUE
                   /\ pc' = [pc EXCEPT ![self] = "Done"]
                   /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                   arch_to_devB, devA_to_reviewer, 
                                   reviewer_to_devA, devB_to_reviewer, 
                                   reviewer_to_devB, devA_to_tester, 
                                   tester_to_devA, devB_to_tester, 
                                   tester_to_devB, shared_lib_lock, merge_lock, 
                                   test_lock, msg_, archDoneA, archDoneB, 
                                   msg_d, msg_de, msg_r, rvDoneA, rvDoneB, msg, 
                                   tsDoneA, tsDoneB >>

architect_proc(self) == arch_loop(self) \/ arch_recv(self)
                           \/ arch_replyA(self) \/ arch_replyB(self)
                           \/ arch_done(self)

da_design(self) == /\ pc[self] = "da_design"
                   /\ devA_to_arch' = Append(devA_to_arch, "design_proposal")
                   /\ pc' = [pc EXCEPT ![self] = "da_wait_arch"]
                   /\ UNCHANGED << arch_to_devA, devB_to_arch, arch_to_devB, 
                                   devA_to_reviewer, reviewer_to_devA, 
                                   devB_to_reviewer, reviewer_to_devB, 
                                   devA_to_tester, tester_to_devA, 
                                   devB_to_tester, tester_to_devB, 
                                   shared_lib_lock, merge_lock, test_lock, 
                                   msg_, archDoneA, archDoneB, msg_d, msg_de, 
                                   msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                   tsDoneB >>

da_wait_arch(self) == /\ pc[self] = "da_wait_arch"
                      /\ Len(arch_to_devA) > 0
                      /\ msg_d' = [msg_d EXCEPT ![self] = Head(arch_to_devA)]
                      /\ arch_to_devA' = Tail(arch_to_devA)
                      /\ pc' = [pc EXCEPT ![self] = "da_check_arch"]
                      /\ UNCHANGED << devA_to_arch, devB_to_arch, arch_to_devB, 
                                      devA_to_reviewer, reviewer_to_devA, 
                                      devB_to_reviewer, reviewer_to_devB, 
                                      devA_to_tester, tester_to_devA, 
                                      devB_to_tester, tester_to_devB, 
                                      shared_lib_lock, merge_lock, test_lock, 
                                      msg_, archDoneA, archDoneB, msg_de, 
                                      msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                      tsDoneB >>

da_check_arch(self) == /\ pc[self] = "da_check_arch"
                       /\ IF msg_d[self] = "reject"
                             THEN /\ pc' = [pc EXCEPT ![self] = "da_design"]
                             ELSE /\ pc' = [pc EXCEPT ![self] = "da_impl"]
                       /\ UNCHANGED << devA_to_arch, arch_to_devA, 
                                       devB_to_arch, arch_to_devB, 
                                       devA_to_reviewer, reviewer_to_devA, 
                                       devB_to_reviewer, reviewer_to_devB, 
                                       devA_to_tester, tester_to_devA, 
                                       devB_to_tester, tester_to_devB, 
                                       shared_lib_lock, merge_lock, test_lock, 
                                       msg_, archDoneA, archDoneB, msg_d, 
                                       msg_de, msg_r, rvDoneA, rvDoneB, msg, 
                                       tsDoneA, tsDoneB >>

da_impl(self) == /\ pc[self] = "da_impl"
                 /\ shared_lib_lock = "FREE"
                 /\ shared_lib_lock' = self
                 /\ pc' = [pc EXCEPT ![self] = "da_release_lib"]
                 /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                 arch_to_devB, devA_to_reviewer, 
                                 reviewer_to_devA, devB_to_reviewer, 
                                 reviewer_to_devB, devA_to_tester, 
                                 tester_to_devA, devB_to_tester, 
                                 tester_to_devB, merge_lock, test_lock, msg_, 
                                 archDoneA, archDoneB, msg_d, msg_de, msg_r, 
                                 rvDoneA, rvDoneB, msg, tsDoneA, tsDoneB >>

da_release_lib(self) == /\ pc[self] = "da_release_lib"
                        /\ shared_lib_lock' = "FREE"
                        /\ pc' = [pc EXCEPT ![self] = "da_review"]
                        /\ UNCHANGED << devA_to_arch, arch_to_devA, 
                                        devB_to_arch, arch_to_devB, 
                                        devA_to_reviewer, reviewer_to_devA, 
                                        devB_to_reviewer, reviewer_to_devB, 
                                        devA_to_tester, tester_to_devA, 
                                        devB_to_tester, tester_to_devB, 
                                        merge_lock, test_lock, msg_, archDoneA, 
                                        archDoneB, msg_d, msg_de, msg_r, 
                                        rvDoneA, rvDoneB, msg, tsDoneA, 
                                        tsDoneB >>

da_review(self) == /\ pc[self] = "da_review"
                   /\ devA_to_reviewer' = Append(devA_to_reviewer, "review_request")
                   /\ pc' = [pc EXCEPT ![self] = "da_wait_review"]
                   /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                   arch_to_devB, reviewer_to_devA, 
                                   devB_to_reviewer, reviewer_to_devB, 
                                   devA_to_tester, tester_to_devA, 
                                   devB_to_tester, tester_to_devB, 
                                   shared_lib_lock, merge_lock, test_lock, 
                                   msg_, archDoneA, archDoneB, msg_d, msg_de, 
                                   msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                   tsDoneB >>

da_wait_review(self) == /\ pc[self] = "da_wait_review"
                        /\ Len(reviewer_to_devA) > 0
                        /\ msg_d' = [msg_d EXCEPT ![self] = Head(reviewer_to_devA)]
                        /\ reviewer_to_devA' = Tail(reviewer_to_devA)
                        /\ pc' = [pc EXCEPT ![self] = "da_check_review"]
                        /\ UNCHANGED << devA_to_arch, arch_to_devA, 
                                        devB_to_arch, arch_to_devB, 
                                        devA_to_reviewer, devB_to_reviewer, 
                                        reviewer_to_devB, devA_to_tester, 
                                        tester_to_devA, devB_to_tester, 
                                        tester_to_devB, shared_lib_lock, 
                                        merge_lock, test_lock, msg_, archDoneA, 
                                        archDoneB, msg_de, msg_r, rvDoneA, 
                                        rvDoneB, msg, tsDoneA, tsDoneB >>

da_check_review(self) == /\ pc[self] = "da_check_review"
                         /\ IF msg_d[self] = "revise"
                               THEN /\ pc' = [pc EXCEPT ![self] = "da_impl"]
                               ELSE /\ pc' = [pc EXCEPT ![self] = "da_test"]
                         /\ UNCHANGED << devA_to_arch, arch_to_devA, 
                                         devB_to_arch, arch_to_devB, 
                                         devA_to_reviewer, reviewer_to_devA, 
                                         devB_to_reviewer, reviewer_to_devB, 
                                         devA_to_tester, tester_to_devA, 
                                         devB_to_tester, tester_to_devB, 
                                         shared_lib_lock, merge_lock, 
                                         test_lock, msg_, archDoneA, archDoneB, 
                                         msg_d, msg_de, msg_r, rvDoneA, 
                                         rvDoneB, msg, tsDoneA, tsDoneB >>

da_test(self) == /\ pc[self] = "da_test"
                 /\ devA_to_tester' = Append(devA_to_tester, "test_request")
                 /\ pc' = [pc EXCEPT ![self] = "da_wait_test"]
                 /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                 arch_to_devB, devA_to_reviewer, 
                                 reviewer_to_devA, devB_to_reviewer, 
                                 reviewer_to_devB, tester_to_devA, 
                                 devB_to_tester, tester_to_devB, 
                                 shared_lib_lock, merge_lock, test_lock, msg_, 
                                 archDoneA, archDoneB, msg_d, msg_de, msg_r, 
                                 rvDoneA, rvDoneB, msg, tsDoneA, tsDoneB >>

da_wait_test(self) == /\ pc[self] = "da_wait_test"
                      /\ Len(tester_to_devA) > 0
                      /\ msg_d' = [msg_d EXCEPT ![self] = Head(tester_to_devA)]
                      /\ tester_to_devA' = Tail(tester_to_devA)
                      /\ pc' = [pc EXCEPT ![self] = "da_check_test"]
                      /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                      arch_to_devB, devA_to_reviewer, 
                                      reviewer_to_devA, devB_to_reviewer, 
                                      reviewer_to_devB, devA_to_tester, 
                                      devB_to_tester, tester_to_devB, 
                                      shared_lib_lock, merge_lock, test_lock, 
                                      msg_, archDoneA, archDoneB, msg_de, 
                                      msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                      tsDoneB >>

da_check_test(self) == /\ pc[self] = "da_check_test"
                       /\ IF msg_d[self] = "fail"
                             THEN /\ pc' = [pc EXCEPT ![self] = "da_impl"]
                             ELSE /\ pc' = [pc EXCEPT ![self] = "da_merge"]
                       /\ UNCHANGED << devA_to_arch, arch_to_devA, 
                                       devB_to_arch, arch_to_devB, 
                                       devA_to_reviewer, reviewer_to_devA, 
                                       devB_to_reviewer, reviewer_to_devB, 
                                       devA_to_tester, tester_to_devA, 
                                       devB_to_tester, tester_to_devB, 
                                       shared_lib_lock, merge_lock, test_lock, 
                                       msg_, archDoneA, archDoneB, msg_d, 
                                       msg_de, msg_r, rvDoneA, rvDoneB, msg, 
                                       tsDoneA, tsDoneB >>

da_merge(self) == /\ pc[self] = "da_merge"
                  /\ merge_lock = "FREE"
                  /\ merge_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "da_release_merge"]
                  /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                  arch_to_devB, devA_to_reviewer, 
                                  reviewer_to_devA, devB_to_reviewer, 
                                  reviewer_to_devB, devA_to_tester, 
                                  tester_to_devA, devB_to_tester, 
                                  tester_to_devB, shared_lib_lock, test_lock, 
                                  msg_, archDoneA, archDoneB, msg_d, msg_de, 
                                  msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                  tsDoneB >>

da_release_merge(self) == /\ pc[self] = "da_release_merge"
                          /\ merge_lock' = "FREE"
                          /\ pc' = [pc EXCEPT ![self] = "da_notify"]
                          /\ UNCHANGED << devA_to_arch, arch_to_devA, 
                                          devB_to_arch, arch_to_devB, 
                                          devA_to_reviewer, reviewer_to_devA, 
                                          devB_to_reviewer, reviewer_to_devB, 
                                          devA_to_tester, tester_to_devA, 
                                          devB_to_tester, tester_to_devB, 
                                          shared_lib_lock, test_lock, msg_, 
                                          archDoneA, archDoneB, msg_d, msg_de, 
                                          msg_r, rvDoneA, rvDoneB, msg, 
                                          tsDoneA, tsDoneB >>

da_notify(self) == /\ pc[self] = "da_notify"
                   /\ devA_to_reviewer' = Append(devA_to_reviewer, "done")
                   /\ devA_to_tester' = Append(devA_to_tester, "done")
                   /\ pc' = [pc EXCEPT ![self] = "da_done"]
                   /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                   arch_to_devB, reviewer_to_devA, 
                                   devB_to_reviewer, reviewer_to_devB, 
                                   tester_to_devA, devB_to_tester, 
                                   tester_to_devB, shared_lib_lock, merge_lock, 
                                   test_lock, msg_, archDoneA, archDoneB, 
                                   msg_d, msg_de, msg_r, rvDoneA, rvDoneB, msg, 
                                   tsDoneA, tsDoneB >>

da_done(self) == /\ pc[self] = "da_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                 arch_to_devB, devA_to_reviewer, 
                                 reviewer_to_devA, devB_to_reviewer, 
                                 reviewer_to_devB, devA_to_tester, 
                                 tester_to_devA, devB_to_tester, 
                                 tester_to_devB, shared_lib_lock, merge_lock, 
                                 test_lock, msg_, archDoneA, archDoneB, msg_d, 
                                 msg_de, msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                 tsDoneB >>

developerA_proc(self) == da_design(self) \/ da_wait_arch(self)
                            \/ da_check_arch(self) \/ da_impl(self)
                            \/ da_release_lib(self) \/ da_review(self)
                            \/ da_wait_review(self)
                            \/ da_check_review(self) \/ da_test(self)
                            \/ da_wait_test(self) \/ da_check_test(self)
                            \/ da_merge(self) \/ da_release_merge(self)
                            \/ da_notify(self) \/ da_done(self)

db_design(self) == /\ pc[self] = "db_design"
                   /\ devB_to_arch' = Append(devB_to_arch, "design_proposal")
                   /\ pc' = [pc EXCEPT ![self] = "db_wait_arch"]
                   /\ UNCHANGED << devA_to_arch, arch_to_devA, arch_to_devB, 
                                   devA_to_reviewer, reviewer_to_devA, 
                                   devB_to_reviewer, reviewer_to_devB, 
                                   devA_to_tester, tester_to_devA, 
                                   devB_to_tester, tester_to_devB, 
                                   shared_lib_lock, merge_lock, test_lock, 
                                   msg_, archDoneA, archDoneB, msg_d, msg_de, 
                                   msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                   tsDoneB >>

db_wait_arch(self) == /\ pc[self] = "db_wait_arch"
                      /\ Len(arch_to_devB) > 0
                      /\ msg_de' = [msg_de EXCEPT ![self] = Head(arch_to_devB)]
                      /\ arch_to_devB' = Tail(arch_to_devB)
                      /\ pc' = [pc EXCEPT ![self] = "db_check_arch"]
                      /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                      devA_to_reviewer, reviewer_to_devA, 
                                      devB_to_reviewer, reviewer_to_devB, 
                                      devA_to_tester, tester_to_devA, 
                                      devB_to_tester, tester_to_devB, 
                                      shared_lib_lock, merge_lock, test_lock, 
                                      msg_, archDoneA, archDoneB, msg_d, msg_r, 
                                      rvDoneA, rvDoneB, msg, tsDoneA, tsDoneB >>

db_check_arch(self) == /\ pc[self] = "db_check_arch"
                       /\ IF msg_de[self] = "reject"
                             THEN /\ pc' = [pc EXCEPT ![self] = "db_design"]
                             ELSE /\ pc' = [pc EXCEPT ![self] = "db_impl"]
                       /\ UNCHANGED << devA_to_arch, arch_to_devA, 
                                       devB_to_arch, arch_to_devB, 
                                       devA_to_reviewer, reviewer_to_devA, 
                                       devB_to_reviewer, reviewer_to_devB, 
                                       devA_to_tester, tester_to_devA, 
                                       devB_to_tester, tester_to_devB, 
                                       shared_lib_lock, merge_lock, test_lock, 
                                       msg_, archDoneA, archDoneB, msg_d, 
                                       msg_de, msg_r, rvDoneA, rvDoneB, msg, 
                                       tsDoneA, tsDoneB >>

db_impl(self) == /\ pc[self] = "db_impl"
                 /\ shared_lib_lock = "FREE"
                 /\ shared_lib_lock' = self
                 /\ pc' = [pc EXCEPT ![self] = "db_release_lib"]
                 /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                 arch_to_devB, devA_to_reviewer, 
                                 reviewer_to_devA, devB_to_reviewer, 
                                 reviewer_to_devB, devA_to_tester, 
                                 tester_to_devA, devB_to_tester, 
                                 tester_to_devB, merge_lock, test_lock, msg_, 
                                 archDoneA, archDoneB, msg_d, msg_de, msg_r, 
                                 rvDoneA, rvDoneB, msg, tsDoneA, tsDoneB >>

db_release_lib(self) == /\ pc[self] = "db_release_lib"
                        /\ shared_lib_lock' = "FREE"
                        /\ pc' = [pc EXCEPT ![self] = "db_review"]
                        /\ UNCHANGED << devA_to_arch, arch_to_devA, 
                                        devB_to_arch, arch_to_devB, 
                                        devA_to_reviewer, reviewer_to_devA, 
                                        devB_to_reviewer, reviewer_to_devB, 
                                        devA_to_tester, tester_to_devA, 
                                        devB_to_tester, tester_to_devB, 
                                        merge_lock, test_lock, msg_, archDoneA, 
                                        archDoneB, msg_d, msg_de, msg_r, 
                                        rvDoneA, rvDoneB, msg, tsDoneA, 
                                        tsDoneB >>

db_review(self) == /\ pc[self] = "db_review"
                   /\ devB_to_reviewer' = Append(devB_to_reviewer, "review_request")
                   /\ pc' = [pc EXCEPT ![self] = "db_wait_review"]
                   /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                   arch_to_devB, devA_to_reviewer, 
                                   reviewer_to_devA, reviewer_to_devB, 
                                   devA_to_tester, tester_to_devA, 
                                   devB_to_tester, tester_to_devB, 
                                   shared_lib_lock, merge_lock, test_lock, 
                                   msg_, archDoneA, archDoneB, msg_d, msg_de, 
                                   msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                   tsDoneB >>

db_wait_review(self) == /\ pc[self] = "db_wait_review"
                        /\ Len(reviewer_to_devB) > 0
                        /\ msg_de' = [msg_de EXCEPT ![self] = Head(reviewer_to_devB)]
                        /\ reviewer_to_devB' = Tail(reviewer_to_devB)
                        /\ pc' = [pc EXCEPT ![self] = "db_check_review"]
                        /\ UNCHANGED << devA_to_arch, arch_to_devA, 
                                        devB_to_arch, arch_to_devB, 
                                        devA_to_reviewer, reviewer_to_devA, 
                                        devB_to_reviewer, devA_to_tester, 
                                        tester_to_devA, devB_to_tester, 
                                        tester_to_devB, shared_lib_lock, 
                                        merge_lock, test_lock, msg_, archDoneA, 
                                        archDoneB, msg_d, msg_r, rvDoneA, 
                                        rvDoneB, msg, tsDoneA, tsDoneB >>

db_check_review(self) == /\ pc[self] = "db_check_review"
                         /\ IF msg_de[self] = "revise"
                               THEN /\ pc' = [pc EXCEPT ![self] = "db_impl"]
                               ELSE /\ pc' = [pc EXCEPT ![self] = "db_test"]
                         /\ UNCHANGED << devA_to_arch, arch_to_devA, 
                                         devB_to_arch, arch_to_devB, 
                                         devA_to_reviewer, reviewer_to_devA, 
                                         devB_to_reviewer, reviewer_to_devB, 
                                         devA_to_tester, tester_to_devA, 
                                         devB_to_tester, tester_to_devB, 
                                         shared_lib_lock, merge_lock, 
                                         test_lock, msg_, archDoneA, archDoneB, 
                                         msg_d, msg_de, msg_r, rvDoneA, 
                                         rvDoneB, msg, tsDoneA, tsDoneB >>

db_test(self) == /\ pc[self] = "db_test"
                 /\ devB_to_tester' = Append(devB_to_tester, "test_request")
                 /\ pc' = [pc EXCEPT ![self] = "db_wait_test"]
                 /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                 arch_to_devB, devA_to_reviewer, 
                                 reviewer_to_devA, devB_to_reviewer, 
                                 reviewer_to_devB, devA_to_tester, 
                                 tester_to_devA, tester_to_devB, 
                                 shared_lib_lock, merge_lock, test_lock, msg_, 
                                 archDoneA, archDoneB, msg_d, msg_de, msg_r, 
                                 rvDoneA, rvDoneB, msg, tsDoneA, tsDoneB >>

db_wait_test(self) == /\ pc[self] = "db_wait_test"
                      /\ Len(tester_to_devB) > 0
                      /\ msg_de' = [msg_de EXCEPT ![self] = Head(tester_to_devB)]
                      /\ tester_to_devB' = Tail(tester_to_devB)
                      /\ pc' = [pc EXCEPT ![self] = "db_check_test"]
                      /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                      arch_to_devB, devA_to_reviewer, 
                                      reviewer_to_devA, devB_to_reviewer, 
                                      reviewer_to_devB, devA_to_tester, 
                                      tester_to_devA, devB_to_tester, 
                                      shared_lib_lock, merge_lock, test_lock, 
                                      msg_, archDoneA, archDoneB, msg_d, msg_r, 
                                      rvDoneA, rvDoneB, msg, tsDoneA, tsDoneB >>

db_check_test(self) == /\ pc[self] = "db_check_test"
                       /\ IF msg_de[self] = "fail"
                             THEN /\ pc' = [pc EXCEPT ![self] = "db_impl"]
                             ELSE /\ pc' = [pc EXCEPT ![self] = "db_merge"]
                       /\ UNCHANGED << devA_to_arch, arch_to_devA, 
                                       devB_to_arch, arch_to_devB, 
                                       devA_to_reviewer, reviewer_to_devA, 
                                       devB_to_reviewer, reviewer_to_devB, 
                                       devA_to_tester, tester_to_devA, 
                                       devB_to_tester, tester_to_devB, 
                                       shared_lib_lock, merge_lock, test_lock, 
                                       msg_, archDoneA, archDoneB, msg_d, 
                                       msg_de, msg_r, rvDoneA, rvDoneB, msg, 
                                       tsDoneA, tsDoneB >>

db_merge(self) == /\ pc[self] = "db_merge"
                  /\ merge_lock = "FREE"
                  /\ merge_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "db_release_merge"]
                  /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                  arch_to_devB, devA_to_reviewer, 
                                  reviewer_to_devA, devB_to_reviewer, 
                                  reviewer_to_devB, devA_to_tester, 
                                  tester_to_devA, devB_to_tester, 
                                  tester_to_devB, shared_lib_lock, test_lock, 
                                  msg_, archDoneA, archDoneB, msg_d, msg_de, 
                                  msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                  tsDoneB >>

db_release_merge(self) == /\ pc[self] = "db_release_merge"
                          /\ merge_lock' = "FREE"
                          /\ pc' = [pc EXCEPT ![self] = "db_notify"]
                          /\ UNCHANGED << devA_to_arch, arch_to_devA, 
                                          devB_to_arch, arch_to_devB, 
                                          devA_to_reviewer, reviewer_to_devA, 
                                          devB_to_reviewer, reviewer_to_devB, 
                                          devA_to_tester, tester_to_devA, 
                                          devB_to_tester, tester_to_devB, 
                                          shared_lib_lock, test_lock, msg_, 
                                          archDoneA, archDoneB, msg_d, msg_de, 
                                          msg_r, rvDoneA, rvDoneB, msg, 
                                          tsDoneA, tsDoneB >>

db_notify(self) == /\ pc[self] = "db_notify"
                   /\ devB_to_reviewer' = Append(devB_to_reviewer, "done")
                   /\ devB_to_tester' = Append(devB_to_tester, "done")
                   /\ pc' = [pc EXCEPT ![self] = "db_done"]
                   /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                   arch_to_devB, devA_to_reviewer, 
                                   reviewer_to_devA, reviewer_to_devB, 
                                   devA_to_tester, tester_to_devA, 
                                   tester_to_devB, shared_lib_lock, merge_lock, 
                                   test_lock, msg_, archDoneA, archDoneB, 
                                   msg_d, msg_de, msg_r, rvDoneA, rvDoneB, msg, 
                                   tsDoneA, tsDoneB >>

db_done(self) == /\ pc[self] = "db_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                 arch_to_devB, devA_to_reviewer, 
                                 reviewer_to_devA, devB_to_reviewer, 
                                 reviewer_to_devB, devA_to_tester, 
                                 tester_to_devA, devB_to_tester, 
                                 tester_to_devB, shared_lib_lock, merge_lock, 
                                 test_lock, msg_, archDoneA, archDoneB, msg_d, 
                                 msg_de, msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                 tsDoneB >>

developerB_proc(self) == db_design(self) \/ db_wait_arch(self)
                            \/ db_check_arch(self) \/ db_impl(self)
                            \/ db_release_lib(self) \/ db_review(self)
                            \/ db_wait_review(self)
                            \/ db_check_review(self) \/ db_test(self)
                            \/ db_wait_test(self) \/ db_check_test(self)
                            \/ db_merge(self) \/ db_release_merge(self)
                            \/ db_notify(self) \/ db_done(self)

rv_loop(self) == /\ pc[self] = "rv_loop"
                 /\ IF ~rvDoneA[self] \/ ~rvDoneB[self]
                       THEN /\ pc' = [pc EXCEPT ![self] = "rv_recv"]
                       ELSE /\ pc' = [pc EXCEPT ![self] = "rv_done"]
                 /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                 arch_to_devB, devA_to_reviewer, 
                                 reviewer_to_devA, devB_to_reviewer, 
                                 reviewer_to_devB, devA_to_tester, 
                                 tester_to_devA, devB_to_tester, 
                                 tester_to_devB, shared_lib_lock, merge_lock, 
                                 test_lock, msg_, archDoneA, archDoneB, msg_d, 
                                 msg_de, msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                 tsDoneB >>

rv_recv(self) == /\ pc[self] = "rv_recv"
                 /\ \/ /\ Len(devA_to_reviewer) > 0
                       /\ msg_r' = [msg_r EXCEPT ![self] = Head(devA_to_reviewer)]
                       /\ devA_to_reviewer' = Tail(devA_to_reviewer)
                       /\ pc' = [pc EXCEPT ![self] = "rv_handleA"]
                       /\ UNCHANGED devB_to_reviewer
                    \/ /\ Len(devB_to_reviewer) > 0
                       /\ msg_r' = [msg_r EXCEPT ![self] = Head(devB_to_reviewer)]
                       /\ devB_to_reviewer' = Tail(devB_to_reviewer)
                       /\ pc' = [pc EXCEPT ![self] = "rv_handleB"]
                       /\ UNCHANGED devA_to_reviewer
                 /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                 arch_to_devB, reviewer_to_devA, 
                                 reviewer_to_devB, devA_to_tester, 
                                 tester_to_devA, devB_to_tester, 
                                 tester_to_devB, shared_lib_lock, merge_lock, 
                                 test_lock, msg_, archDoneA, archDoneB, msg_d, 
                                 msg_de, rvDoneA, rvDoneB, msg, tsDoneA, 
                                 tsDoneB >>

rv_handleA(self) == /\ pc[self] = "rv_handleA"
                    /\ IF msg_r[self] = "done"
                          THEN /\ rvDoneA' = [rvDoneA EXCEPT ![self] = TRUE]
                               /\ pc' = [pc EXCEPT ![self] = "rv_loop"]
                          ELSE /\ pc' = [pc EXCEPT ![self] = "rv_decideA"]
                               /\ UNCHANGED rvDoneA
                    /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                    arch_to_devB, devA_to_reviewer, 
                                    reviewer_to_devA, devB_to_reviewer, 
                                    reviewer_to_devB, devA_to_tester, 
                                    tester_to_devA, devB_to_tester, 
                                    tester_to_devB, shared_lib_lock, 
                                    merge_lock, test_lock, msg_, archDoneA, 
                                    archDoneB, msg_d, msg_de, msg_r, rvDoneB, 
                                    msg, tsDoneA, tsDoneB >>

rv_decideA(self) == /\ pc[self] = "rv_decideA"
                    /\ \/ /\ reviewer_to_devA' = Append(reviewer_to_devA, "approved")
                       \/ /\ reviewer_to_devA' = Append(reviewer_to_devA, "revise")
                    /\ pc' = [pc EXCEPT ![self] = "rv_loop"]
                    /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                    arch_to_devB, devA_to_reviewer, 
                                    devB_to_reviewer, reviewer_to_devB, 
                                    devA_to_tester, tester_to_devA, 
                                    devB_to_tester, tester_to_devB, 
                                    shared_lib_lock, merge_lock, test_lock, 
                                    msg_, archDoneA, archDoneB, msg_d, msg_de, 
                                    msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                    tsDoneB >>

rv_handleB(self) == /\ pc[self] = "rv_handleB"
                    /\ IF msg_r[self] = "done"
                          THEN /\ rvDoneB' = [rvDoneB EXCEPT ![self] = TRUE]
                               /\ pc' = [pc EXCEPT ![self] = "rv_loop"]
                          ELSE /\ pc' = [pc EXCEPT ![self] = "rv_decideB"]
                               /\ UNCHANGED rvDoneB
                    /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                    arch_to_devB, devA_to_reviewer, 
                                    reviewer_to_devA, devB_to_reviewer, 
                                    reviewer_to_devB, devA_to_tester, 
                                    tester_to_devA, devB_to_tester, 
                                    tester_to_devB, shared_lib_lock, 
                                    merge_lock, test_lock, msg_, archDoneA, 
                                    archDoneB, msg_d, msg_de, msg_r, rvDoneA, 
                                    msg, tsDoneA, tsDoneB >>

rv_decideB(self) == /\ pc[self] = "rv_decideB"
                    /\ \/ /\ reviewer_to_devB' = Append(reviewer_to_devB, "approved")
                       \/ /\ reviewer_to_devB' = Append(reviewer_to_devB, "revise")
                    /\ pc' = [pc EXCEPT ![self] = "rv_loop"]
                    /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                    arch_to_devB, devA_to_reviewer, 
                                    reviewer_to_devA, devB_to_reviewer, 
                                    devA_to_tester, tester_to_devA, 
                                    devB_to_tester, tester_to_devB, 
                                    shared_lib_lock, merge_lock, test_lock, 
                                    msg_, archDoneA, archDoneB, msg_d, msg_de, 
                                    msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                    tsDoneB >>

rv_done(self) == /\ pc[self] = "rv_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                 arch_to_devB, devA_to_reviewer, 
                                 reviewer_to_devA, devB_to_reviewer, 
                                 reviewer_to_devB, devA_to_tester, 
                                 tester_to_devA, devB_to_tester, 
                                 tester_to_devB, shared_lib_lock, merge_lock, 
                                 test_lock, msg_, archDoneA, archDoneB, msg_d, 
                                 msg_de, msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                 tsDoneB >>

reviewer_proc(self) == rv_loop(self) \/ rv_recv(self) \/ rv_handleA(self)
                          \/ rv_decideA(self) \/ rv_handleB(self)
                          \/ rv_decideB(self) \/ rv_done(self)

ts_loop(self) == /\ pc[self] = "ts_loop"
                 /\ IF ~tsDoneA[self] \/ ~tsDoneB[self]
                       THEN /\ pc' = [pc EXCEPT ![self] = "ts_recv"]
                       ELSE /\ pc' = [pc EXCEPT ![self] = "ts_done"]
                 /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                 arch_to_devB, devA_to_reviewer, 
                                 reviewer_to_devA, devB_to_reviewer, 
                                 reviewer_to_devB, devA_to_tester, 
                                 tester_to_devA, devB_to_tester, 
                                 tester_to_devB, shared_lib_lock, merge_lock, 
                                 test_lock, msg_, archDoneA, archDoneB, msg_d, 
                                 msg_de, msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                 tsDoneB >>

ts_recv(self) == /\ pc[self] = "ts_recv"
                 /\ \/ /\ Len(devA_to_tester) > 0
                       /\ msg' = [msg EXCEPT ![self] = Head(devA_to_tester)]
                       /\ devA_to_tester' = Tail(devA_to_tester)
                       /\ pc' = [pc EXCEPT ![self] = "ts_handleA"]
                       /\ UNCHANGED devB_to_tester
                    \/ /\ Len(devB_to_tester) > 0
                       /\ msg' = [msg EXCEPT ![self] = Head(devB_to_tester)]
                       /\ devB_to_tester' = Tail(devB_to_tester)
                       /\ pc' = [pc EXCEPT ![self] = "ts_handleB"]
                       /\ UNCHANGED devA_to_tester
                 /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                 arch_to_devB, devA_to_reviewer, 
                                 reviewer_to_devA, devB_to_reviewer, 
                                 reviewer_to_devB, tester_to_devA, 
                                 tester_to_devB, shared_lib_lock, merge_lock, 
                                 test_lock, msg_, archDoneA, archDoneB, msg_d, 
                                 msg_de, msg_r, rvDoneA, rvDoneB, tsDoneA, 
                                 tsDoneB >>

ts_handleA(self) == /\ pc[self] = "ts_handleA"
                    /\ IF msg[self] = "done"
                          THEN /\ tsDoneA' = [tsDoneA EXCEPT ![self] = TRUE]
                               /\ pc' = [pc EXCEPT ![self] = "ts_loop"]
                          ELSE /\ pc' = [pc EXCEPT ![self] = "ts_lockA"]
                               /\ UNCHANGED tsDoneA
                    /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                    arch_to_devB, devA_to_reviewer, 
                                    reviewer_to_devA, devB_to_reviewer, 
                                    reviewer_to_devB, devA_to_tester, 
                                    tester_to_devA, devB_to_tester, 
                                    tester_to_devB, shared_lib_lock, 
                                    merge_lock, test_lock, msg_, archDoneA, 
                                    archDoneB, msg_d, msg_de, msg_r, rvDoneA, 
                                    rvDoneB, msg, tsDoneB >>

ts_lockA(self) == /\ pc[self] = "ts_lockA"
                  /\ test_lock = "FREE"
                  /\ test_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "ts_decideA"]
                  /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                  arch_to_devB, devA_to_reviewer, 
                                  reviewer_to_devA, devB_to_reviewer, 
                                  reviewer_to_devB, devA_to_tester, 
                                  tester_to_devA, devB_to_tester, 
                                  tester_to_devB, shared_lib_lock, merge_lock, 
                                  msg_, archDoneA, archDoneB, msg_d, msg_de, 
                                  msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                  tsDoneB >>

ts_decideA(self) == /\ pc[self] = "ts_decideA"
                    /\ \/ /\ tester_to_devA' = Append(tester_to_devA, "pass")
                       \/ /\ tester_to_devA' = Append(tester_to_devA, "fail")
                    /\ pc' = [pc EXCEPT ![self] = "ts_unlockA"]
                    /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                    arch_to_devB, devA_to_reviewer, 
                                    reviewer_to_devA, devB_to_reviewer, 
                                    reviewer_to_devB, devA_to_tester, 
                                    devB_to_tester, tester_to_devB, 
                                    shared_lib_lock, merge_lock, test_lock, 
                                    msg_, archDoneA, archDoneB, msg_d, msg_de, 
                                    msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                    tsDoneB >>

ts_unlockA(self) == /\ pc[self] = "ts_unlockA"
                    /\ test_lock' = "FREE"
                    /\ pc' = [pc EXCEPT ![self] = "ts_loop"]
                    /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                    arch_to_devB, devA_to_reviewer, 
                                    reviewer_to_devA, devB_to_reviewer, 
                                    reviewer_to_devB, devA_to_tester, 
                                    tester_to_devA, devB_to_tester, 
                                    tester_to_devB, shared_lib_lock, 
                                    merge_lock, msg_, archDoneA, archDoneB, 
                                    msg_d, msg_de, msg_r, rvDoneA, rvDoneB, 
                                    msg, tsDoneA, tsDoneB >>

ts_handleB(self) == /\ pc[self] = "ts_handleB"
                    /\ IF msg[self] = "done"
                          THEN /\ tsDoneB' = [tsDoneB EXCEPT ![self] = TRUE]
                               /\ pc' = [pc EXCEPT ![self] = "ts_loop"]
                          ELSE /\ pc' = [pc EXCEPT ![self] = "ts_lockB"]
                               /\ UNCHANGED tsDoneB
                    /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                    arch_to_devB, devA_to_reviewer, 
                                    reviewer_to_devA, devB_to_reviewer, 
                                    reviewer_to_devB, devA_to_tester, 
                                    tester_to_devA, devB_to_tester, 
                                    tester_to_devB, shared_lib_lock, 
                                    merge_lock, test_lock, msg_, archDoneA, 
                                    archDoneB, msg_d, msg_de, msg_r, rvDoneA, 
                                    rvDoneB, msg, tsDoneA >>

ts_lockB(self) == /\ pc[self] = "ts_lockB"
                  /\ test_lock = "FREE"
                  /\ test_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "ts_decideB"]
                  /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                  arch_to_devB, devA_to_reviewer, 
                                  reviewer_to_devA, devB_to_reviewer, 
                                  reviewer_to_devB, devA_to_tester, 
                                  tester_to_devA, devB_to_tester, 
                                  tester_to_devB, shared_lib_lock, merge_lock, 
                                  msg_, archDoneA, archDoneB, msg_d, msg_de, 
                                  msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                  tsDoneB >>

ts_decideB(self) == /\ pc[self] = "ts_decideB"
                    /\ \/ /\ tester_to_devB' = Append(tester_to_devB, "pass")
                       \/ /\ tester_to_devB' = Append(tester_to_devB, "fail")
                    /\ pc' = [pc EXCEPT ![self] = "ts_unlockB"]
                    /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                    arch_to_devB, devA_to_reviewer, 
                                    reviewer_to_devA, devB_to_reviewer, 
                                    reviewer_to_devB, devA_to_tester, 
                                    tester_to_devA, devB_to_tester, 
                                    shared_lib_lock, merge_lock, test_lock, 
                                    msg_, archDoneA, archDoneB, msg_d, msg_de, 
                                    msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                    tsDoneB >>

ts_unlockB(self) == /\ pc[self] = "ts_unlockB"
                    /\ test_lock' = "FREE"
                    /\ pc' = [pc EXCEPT ![self] = "ts_loop"]
                    /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                    arch_to_devB, devA_to_reviewer, 
                                    reviewer_to_devA, devB_to_reviewer, 
                                    reviewer_to_devB, devA_to_tester, 
                                    tester_to_devA, devB_to_tester, 
                                    tester_to_devB, shared_lib_lock, 
                                    merge_lock, msg_, archDoneA, archDoneB, 
                                    msg_d, msg_de, msg_r, rvDoneA, rvDoneB, 
                                    msg, tsDoneA, tsDoneB >>

ts_done(self) == /\ pc[self] = "ts_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << devA_to_arch, arch_to_devA, devB_to_arch, 
                                 arch_to_devB, devA_to_reviewer, 
                                 reviewer_to_devA, devB_to_reviewer, 
                                 reviewer_to_devB, devA_to_tester, 
                                 tester_to_devA, devB_to_tester, 
                                 tester_to_devB, shared_lib_lock, merge_lock, 
                                 test_lock, msg_, archDoneA, archDoneB, msg_d, 
                                 msg_de, msg_r, rvDoneA, rvDoneB, msg, tsDoneA, 
                                 tsDoneB >>

tester_proc(self) == ts_loop(self) \/ ts_recv(self) \/ ts_handleA(self)
                        \/ ts_lockA(self) \/ ts_decideA(self)
                        \/ ts_unlockA(self) \/ ts_handleB(self)
                        \/ ts_lockB(self) \/ ts_decideB(self)
                        \/ ts_unlockB(self) \/ ts_done(self)

(* Allow infinite stuttering to prevent deadlock on termination. *)
Terminating == /\ \A self \in ProcSet: pc[self] = "Done"
               /\ UNCHANGED vars

Next == (\E self \in {Architect}: architect_proc(self))
           \/ (\E self \in {DeveloperA}: developerA_proc(self))
           \/ (\E self \in {DeveloperB}: developerB_proc(self))
           \/ (\E self \in {Reviewer}: reviewer_proc(self))
           \/ (\E self \in {Tester}: tester_proc(self))
           \/ Terminating

Spec == /\ Init /\ [][Next]_vars
        /\ \A self \in {Architect} : WF_vars(architect_proc(self))
        /\ \A self \in {DeveloperA} : WF_vars(developerA_proc(self))
        /\ \A self \in {DeveloperB} : WF_vars(developerB_proc(self))
        /\ \A self \in {Reviewer} : WF_vars(reviewer_proc(self))
        /\ \A self \in {Tester} : WF_vars(tester_proc(self))

Termination == <>(\A self \in ProcSet: pc[self] = "Done")

\* END TRANSLATION 

AllDone == \A p \in {Architect, DeveloperA, DeveloperB, Reviewer, Tester}: pc[p] = "Done"

TypeInvariant ==
  /\ \A p \in {Architect, DeveloperA, DeveloperB, Reviewer, Tester}: pc[p] \in STRING
  /\ shared_lib_lock \in {Architect, DeveloperA, DeveloperB, Reviewer, Tester, "FREE"}
  /\ merge_lock \in {Architect, DeveloperA, DeveloperB, Reviewer, Tester, "FREE"}
  /\ test_lock \in {Architect, DeveloperA, DeveloperB, Reviewer, Tester, "FREE"}
  /\ devA_to_arch \in Seq(STRING)
  /\ arch_to_devA \in Seq(STRING)
  /\ devB_to_arch \in Seq(STRING)
  /\ arch_to_devB \in Seq(STRING)
  /\ devA_to_reviewer \in Seq(STRING)
  /\ reviewer_to_devA \in Seq(STRING)
  /\ devB_to_reviewer \in Seq(STRING)
  /\ reviewer_to_devB \in Seq(STRING)
  /\ devA_to_tester \in Seq(STRING)
  /\ tester_to_devA \in Seq(STRING)
  /\ devB_to_tester \in Seq(STRING)
  /\ tester_to_devB \in Seq(STRING)

NoOrphanLocks ==
  AllDone => (shared_lib_lock = "FREE" /\ merge_lock = "FREE" /\ test_lock = "FREE")

ChannelsDrained ==
  AllDone => (Len(devA_to_arch) = 0 /\ Len(arch_to_devA) = 0 /\ Len(devB_to_arch) = 0 /\ Len(arch_to_devB) = 0 /\ Len(devA_to_reviewer) = 0 /\ Len(reviewer_to_devA) = 0 /\ Len(devB_to_reviewer) = 0 /\ Len(reviewer_to_devB) = 0 /\ Len(devA_to_tester) = 0 /\ Len(tester_to_devA) = 0 /\ Len(devB_to_tester) = 0 /\ Len(tester_to_devB) = 0)

ChannelBound ==
  Len(devA_to_arch) <= 3 /\ Len(arch_to_devA) <= 3 /\ Len(devB_to_arch) <= 3 /\ Len(arch_to_devB) <= 3 /\ Len(devA_to_reviewer) <= 3 /\ Len(reviewer_to_devA) <= 3 /\ Len(devB_to_reviewer) <= 3 /\ Len(reviewer_to_devB) <= 3 /\ Len(devA_to_tester) <= 3 /\ Len(tester_to_devA) <= 3 /\ Len(devB_to_tester) <= 3 /\ Len(tester_to_devB) <= 3

====
