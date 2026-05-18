---- MODULE Protocol ----
EXTENDS Integers, Sequences, TLC

CONSTANTS Dev_a, Dev_b, Reviewer

(* --algorithm Protocol {
variables
  deva_to_reviewer = <<>>; \* dev_a -> reviewer, labels: ['code_ready']
  devb_to_reviewer = <<>>; \* dev_b -> reviewer, labels: ['code_ready']
  reviewer_to_deva = <<>>; \* reviewer -> dev_a, labels: ['approved', 'revise']
  reviewer_to_devb = <<>>; \* reviewer -> dev_b, labels: ['approved', 'revise']
  utility_lock = "FREE"; \* Lock
  merge_lock = "FREE"; \* Lock

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

fair process (dev_a_proc \in {Dev_a})
variables msg = "";
{
  \* Dev A: modify shared utility file -> submit for review -> if approved, merge
  da_edit:
    acquire_lock(utility_lock);
  da_edit_rel:
    release_lock(utility_lock);
    send(deva_to_reviewer, "code_ready");
  da_wait_review:
    receive(reviewer_to_deva, msg);
  da_check:
    if (msg = "approved") {
      goto da_merge;
    } else {
      goto da_edit;
    };
  da_merge:
    acquire_lock(merge_lock);
  da_merge_rel:
    release_lock(merge_lock);
}

fair process (dev_b_proc \in {Dev_b})
variables msg = "";
{
  \* Dev B: modify shared utility file -> submit for review -> if approved, merge
  db_edit:
    acquire_lock(utility_lock);
  db_edit_rel:
    release_lock(utility_lock);
    send(devb_to_reviewer, "code_ready");
  db_wait_review:
    receive(reviewer_to_devb, msg);
  db_check:
    if (msg = "approved") {
      goto db_merge;
    } else {
      goto db_edit;
    };
  db_merge:
    acquire_lock(merge_lock);
  db_merge_rel:
    release_lock(merge_lock);
}

fair process (reviewer_proc \in {Reviewer})
variables msg = "", doneA = FALSE, doneB = FALSE;
{
  \* Reviewer: review both developers' code, approve or request revision
  rv_loop:
    while (~doneA \/ ~doneB) {
      rv_recv:
        either {
          await ~doneA;
          receive(deva_to_reviewer, msg);
        rv_decide_a:
          either {
            send(reviewer_to_deva, "approved");
            doneA := TRUE;
            goto rv_loop;
          } or {
            send(reviewer_to_deva, "revise");
            goto rv_loop;
          };
        } or {
          await ~doneB;
          receive(devb_to_reviewer, msg);
        rv_decide_b:
          either {
            send(reviewer_to_devb, "approved");
            doneB := TRUE;
            goto rv_loop;
          } or {
            send(reviewer_to_devb, "revise");
            goto rv_loop;
          };
        };
    };
}

} *)
\* BEGIN TRANSLATION (chksum(pcal) = "8c41647c" /\ chksum(tla) = "27ae4738")
\* Process variable msg of process dev_a_proc at line 35 col 11 changed to msg_
\* Process variable msg of process dev_b_proc at line 58 col 11 changed to msg_d
VARIABLES pc, deva_to_reviewer, devb_to_reviewer, reviewer_to_deva, 
          reviewer_to_devb, utility_lock, merge_lock, msg_, msg_d, msg, doneA, 
          doneB

vars == << pc, deva_to_reviewer, devb_to_reviewer, reviewer_to_deva, 
           reviewer_to_devb, utility_lock, merge_lock, msg_, msg_d, msg, 
           doneA, doneB >>

ProcSet == ({Dev_a}) \cup ({Dev_b}) \cup ({Reviewer})

Init == (* Global variables *)
        /\ deva_to_reviewer = <<>>
        /\ devb_to_reviewer = <<>>
        /\ reviewer_to_deva = <<>>
        /\ reviewer_to_devb = <<>>
        /\ utility_lock = "FREE"
        /\ merge_lock = "FREE"
        (* Process dev_a_proc *)
        /\ msg_ = [self \in {Dev_a} |-> ""]
        (* Process dev_b_proc *)
        /\ msg_d = [self \in {Dev_b} |-> ""]
        (* Process reviewer_proc *)
        /\ msg = [self \in {Reviewer} |-> ""]
        /\ doneA = [self \in {Reviewer} |-> FALSE]
        /\ doneB = [self \in {Reviewer} |-> FALSE]
        /\ pc = [self \in ProcSet |-> CASE self \in {Dev_a} -> "da_edit"
                                        [] self \in {Dev_b} -> "db_edit"
                                        [] self \in {Reviewer} -> "rv_loop"]

da_edit(self) == /\ pc[self] = "da_edit"
                 /\ utility_lock = "FREE"
                 /\ utility_lock' = self
                 /\ pc' = [pc EXCEPT ![self] = "da_edit_rel"]
                 /\ UNCHANGED << deva_to_reviewer, devb_to_reviewer, 
                                 reviewer_to_deva, reviewer_to_devb, 
                                 merge_lock, msg_, msg_d, msg, doneA, doneB >>

da_edit_rel(self) == /\ pc[self] = "da_edit_rel"
                     /\ utility_lock' = "FREE"
                     /\ deva_to_reviewer' = Append(deva_to_reviewer, "code_ready")
                     /\ pc' = [pc EXCEPT ![self] = "da_wait_review"]
                     /\ UNCHANGED << devb_to_reviewer, reviewer_to_deva, 
                                     reviewer_to_devb, merge_lock, msg_, msg_d, 
                                     msg, doneA, doneB >>

da_wait_review(self) == /\ pc[self] = "da_wait_review"
                        /\ Len(reviewer_to_deva) > 0
                        /\ msg_' = [msg_ EXCEPT ![self] = Head(reviewer_to_deva)]
                        /\ reviewer_to_deva' = Tail(reviewer_to_deva)
                        /\ pc' = [pc EXCEPT ![self] = "da_check"]
                        /\ UNCHANGED << deva_to_reviewer, devb_to_reviewer, 
                                        reviewer_to_devb, utility_lock, 
                                        merge_lock, msg_d, msg, doneA, doneB >>

da_check(self) == /\ pc[self] = "da_check"
                  /\ IF msg_[self] = "approved"
                        THEN /\ pc' = [pc EXCEPT ![self] = "da_merge"]
                        ELSE /\ pc' = [pc EXCEPT ![self] = "da_edit"]
                  /\ UNCHANGED << deva_to_reviewer, devb_to_reviewer, 
                                  reviewer_to_deva, reviewer_to_devb, 
                                  utility_lock, merge_lock, msg_, msg_d, msg, 
                                  doneA, doneB >>

da_merge(self) == /\ pc[self] = "da_merge"
                  /\ merge_lock = "FREE"
                  /\ merge_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "da_merge_rel"]
                  /\ UNCHANGED << deva_to_reviewer, devb_to_reviewer, 
                                  reviewer_to_deva, reviewer_to_devb, 
                                  utility_lock, msg_, msg_d, msg, doneA, doneB >>

da_merge_rel(self) == /\ pc[self] = "da_merge_rel"
                      /\ merge_lock' = "FREE"
                      /\ pc' = [pc EXCEPT ![self] = "Done"]
                      /\ UNCHANGED << deva_to_reviewer, devb_to_reviewer, 
                                      reviewer_to_deva, reviewer_to_devb, 
                                      utility_lock, msg_, msg_d, msg, doneA, 
                                      doneB >>

dev_a_proc(self) == da_edit(self) \/ da_edit_rel(self)
                       \/ da_wait_review(self) \/ da_check(self)
                       \/ da_merge(self) \/ da_merge_rel(self)

db_edit(self) == /\ pc[self] = "db_edit"
                 /\ utility_lock = "FREE"
                 /\ utility_lock' = self
                 /\ pc' = [pc EXCEPT ![self] = "db_edit_rel"]
                 /\ UNCHANGED << deva_to_reviewer, devb_to_reviewer, 
                                 reviewer_to_deva, reviewer_to_devb, 
                                 merge_lock, msg_, msg_d, msg, doneA, doneB >>

db_edit_rel(self) == /\ pc[self] = "db_edit_rel"
                     /\ utility_lock' = "FREE"
                     /\ devb_to_reviewer' = Append(devb_to_reviewer, "code_ready")
                     /\ pc' = [pc EXCEPT ![self] = "db_wait_review"]
                     /\ UNCHANGED << deva_to_reviewer, reviewer_to_deva, 
                                     reviewer_to_devb, merge_lock, msg_, msg_d, 
                                     msg, doneA, doneB >>

db_wait_review(self) == /\ pc[self] = "db_wait_review"
                        /\ Len(reviewer_to_devb) > 0
                        /\ msg_d' = [msg_d EXCEPT ![self] = Head(reviewer_to_devb)]
                        /\ reviewer_to_devb' = Tail(reviewer_to_devb)
                        /\ pc' = [pc EXCEPT ![self] = "db_check"]
                        /\ UNCHANGED << deva_to_reviewer, devb_to_reviewer, 
                                        reviewer_to_deva, utility_lock, 
                                        merge_lock, msg_, msg, doneA, doneB >>

db_check(self) == /\ pc[self] = "db_check"
                  /\ IF msg_d[self] = "approved"
                        THEN /\ pc' = [pc EXCEPT ![self] = "db_merge"]
                        ELSE /\ pc' = [pc EXCEPT ![self] = "db_edit"]
                  /\ UNCHANGED << deva_to_reviewer, devb_to_reviewer, 
                                  reviewer_to_deva, reviewer_to_devb, 
                                  utility_lock, merge_lock, msg_, msg_d, msg, 
                                  doneA, doneB >>

db_merge(self) == /\ pc[self] = "db_merge"
                  /\ merge_lock = "FREE"
                  /\ merge_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "db_merge_rel"]
                  /\ UNCHANGED << deva_to_reviewer, devb_to_reviewer, 
                                  reviewer_to_deva, reviewer_to_devb, 
                                  utility_lock, msg_, msg_d, msg, doneA, doneB >>

db_merge_rel(self) == /\ pc[self] = "db_merge_rel"
                      /\ merge_lock' = "FREE"
                      /\ pc' = [pc EXCEPT ![self] = "Done"]
                      /\ UNCHANGED << deva_to_reviewer, devb_to_reviewer, 
                                      reviewer_to_deva, reviewer_to_devb, 
                                      utility_lock, msg_, msg_d, msg, doneA, 
                                      doneB >>

dev_b_proc(self) == db_edit(self) \/ db_edit_rel(self)
                       \/ db_wait_review(self) \/ db_check(self)
                       \/ db_merge(self) \/ db_merge_rel(self)

rv_loop(self) == /\ pc[self] = "rv_loop"
                 /\ IF ~doneA[self] \/ ~doneB[self]
                       THEN /\ pc' = [pc EXCEPT ![self] = "rv_recv"]
                       ELSE /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << deva_to_reviewer, devb_to_reviewer, 
                                 reviewer_to_deva, reviewer_to_devb, 
                                 utility_lock, merge_lock, msg_, msg_d, msg, 
                                 doneA, doneB >>

rv_recv(self) == /\ pc[self] = "rv_recv"
                 /\ \/ /\ ~doneA[self]
                       /\ Len(deva_to_reviewer) > 0
                       /\ msg' = [msg EXCEPT ![self] = Head(deva_to_reviewer)]
                       /\ deva_to_reviewer' = Tail(deva_to_reviewer)
                       /\ pc' = [pc EXCEPT ![self] = "rv_decide_a"]
                       /\ UNCHANGED devb_to_reviewer
                    \/ /\ ~doneB[self]
                       /\ Len(devb_to_reviewer) > 0
                       /\ msg' = [msg EXCEPT ![self] = Head(devb_to_reviewer)]
                       /\ devb_to_reviewer' = Tail(devb_to_reviewer)
                       /\ pc' = [pc EXCEPT ![self] = "rv_decide_b"]
                       /\ UNCHANGED deva_to_reviewer
                 /\ UNCHANGED << reviewer_to_deva, reviewer_to_devb, 
                                 utility_lock, merge_lock, msg_, msg_d, doneA, 
                                 doneB >>

rv_decide_a(self) == /\ pc[self] = "rv_decide_a"
                     /\ \/ /\ reviewer_to_deva' = Append(reviewer_to_deva, "approved")
                           /\ doneA' = [doneA EXCEPT ![self] = TRUE]
                           /\ pc' = [pc EXCEPT ![self] = "rv_loop"]
                        \/ /\ reviewer_to_deva' = Append(reviewer_to_deva, "revise")
                           /\ pc' = [pc EXCEPT ![self] = "rv_loop"]
                           /\ doneA' = doneA
                     /\ UNCHANGED << deva_to_reviewer, devb_to_reviewer, 
                                     reviewer_to_devb, utility_lock, 
                                     merge_lock, msg_, msg_d, msg, doneB >>

rv_decide_b(self) == /\ pc[self] = "rv_decide_b"
                     /\ \/ /\ reviewer_to_devb' = Append(reviewer_to_devb, "approved")
                           /\ doneB' = [doneB EXCEPT ![self] = TRUE]
                           /\ pc' = [pc EXCEPT ![self] = "rv_loop"]
                        \/ /\ reviewer_to_devb' = Append(reviewer_to_devb, "revise")
                           /\ pc' = [pc EXCEPT ![self] = "rv_loop"]
                           /\ doneB' = doneB
                     /\ UNCHANGED << deva_to_reviewer, devb_to_reviewer, 
                                     reviewer_to_deva, utility_lock, 
                                     merge_lock, msg_, msg_d, msg, doneA >>

reviewer_proc(self) == rv_loop(self) \/ rv_recv(self) \/ rv_decide_a(self)
                          \/ rv_decide_b(self)

(* Allow infinite stuttering to prevent deadlock on termination. *)
Terminating == /\ \A self \in ProcSet: pc[self] = "Done"
               /\ UNCHANGED vars

Next == (\E self \in {Dev_a}: dev_a_proc(self))
           \/ (\E self \in {Dev_b}: dev_b_proc(self))
           \/ (\E self \in {Reviewer}: reviewer_proc(self))
           \/ Terminating

Spec == /\ Init /\ [][Next]_vars
        /\ \A self \in {Dev_a} : WF_vars(dev_a_proc(self))
        /\ \A self \in {Dev_b} : WF_vars(dev_b_proc(self))
        /\ \A self \in {Reviewer} : WF_vars(reviewer_proc(self))

Termination == <>(\A self \in ProcSet: pc[self] = "Done")

\* END TRANSLATION 

AllDone == \A p \in {Dev_a, Dev_b, Reviewer}: pc[p] = "Done"

TypeInvariant ==
  /\ \A p \in {Dev_a, Dev_b, Reviewer}: pc[p] \in STRING
  /\ utility_lock \in {Dev_a, Dev_b, Reviewer, "FREE"}
  /\ merge_lock \in {Dev_a, Dev_b, Reviewer, "FREE"}
  /\ deva_to_reviewer \in Seq(STRING)
  /\ devb_to_reviewer \in Seq(STRING)
  /\ reviewer_to_deva \in Seq(STRING)
  /\ reviewer_to_devb \in Seq(STRING)

NoOrphanLocks ==
  AllDone => (utility_lock = "FREE" /\ merge_lock = "FREE")

ChannelsDrained ==
  AllDone => (Len(deva_to_reviewer) = 0 /\ Len(devb_to_reviewer) = 0 /\ Len(reviewer_to_deva) = 0 /\ Len(reviewer_to_devb) = 0)

ChannelBound ==
  Len(deva_to_reviewer) <= 3 /\ Len(devb_to_reviewer) <= 3 /\ Len(reviewer_to_deva) <= 3 /\ Len(reviewer_to_devb) <= 3

====
