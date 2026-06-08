---- MODULE Protocol ----
EXTENDS Integers, Sequences, TLC

CONSTANTS Coordinator, WorkerA, WorkerB

(* --algorithm Protocol {
variables
  to_A = <<>>; \* coordinator -> workerA, labels: ['prepare', 'commit', 'abort']
  to_B = <<>>; \* coordinator -> workerB, labels: ['prepare', 'commit', 'abort']
  from_A = <<>>; \* workerA -> coordinator, labels: ['yes', 'no']
  from_B = <<>>; \* workerB -> coordinator, labels: ['yes', 'no']
  res_A = "FREE"; \* Lock
  res_B = "FREE"; \* Lock

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

fair process (coordinator_proc \in {Coordinator})
variables msg = "", voteA = "", voteB = "";
{
  c_send:
    send(to_A, "prepare");
    send(to_B, "prepare");
  c_wait_votes:
    either {
      c_rcv_A:  receive(from_A, voteA);
      c_rcv_B1: receive(from_B, voteB);
    } or {
      c_rcv_B:  receive(from_B, voteB);
      c_rcv_A1: receive(from_A, voteA);
    };
  c_decide:
    if (voteA = "yes" /\ voteB = "yes") {
      goto c_commit;
    } else {
      goto c_abort;
    };
  c_commit:
    send(to_A, "commit");
    send(to_B, "commit");
    goto c_done;
  c_abort:
    send(to_A, "abort");
    send(to_B, "abort");
  c_done:
    skip;
}

fair process (workerA_proc \in {WorkerA})
variables msg = "";
{
  a_idle:
    receive(to_A, msg); \* domain: receive the prepare request
  a_vote:
    either {
      acquire_lock(res_A); \* domain: tentatively reserve the resource and vote yes
      send(from_A, "yes");
    a_locked:
      receive(to_A, msg);
    a_handle:
      if (msg = "commit") {
      a_release_ok:
        release_lock(res_A); \* domain: commit and free the resource
      } else {
      a_release_abort:
        release_lock(res_A); \* domain: abort and free the resource
      };
    } or {
      send(from_A, "no"); \* domain: vote no
    a_voted_no:
      receive(to_A, msg); \* drain the commit/abort broadcast
    };
}

fair process (workerB_proc \in {WorkerB})
variables msg = "";
{
  b_idle:
    receive(to_B, msg); \* domain: receive the prepare request
  b_vote:
    either {
      acquire_lock(res_B); \* domain: tentatively reserve the resource and vote yes
      send(from_B, "yes");
    b_locked:
      receive(to_B, msg);
    b_handle:
      if (msg = "commit") {
      b_release_ok:
        release_lock(res_B); \* domain: commit and free the resource
      } else {
      b_release_abort:
        release_lock(res_B); \* domain: abort and free the resource
      };
    } or {
      send(from_B, "no"); \* domain: vote no
    b_voted_no:
      receive(to_B, msg); \* drain the commit/abort broadcast
    };
}

} *)
\* BEGIN TRANSLATION (chksum(pcal) = "3b362e12" /\ chksum(tla) = "f4d247cb")
\* Process variable msg of process coordinator_proc at line 35 col 11 changed to msg_
\* Process variable msg of process workerA_proc at line 66 col 11 changed to msg_w
VARIABLES pc, to_A, to_B, from_A, from_B, res_A, res_B, msg_, voteA, voteB, 
          msg_w, msg

vars == << pc, to_A, to_B, from_A, from_B, res_A, res_B, msg_, voteA, voteB, 
           msg_w, msg >>

ProcSet == ({Coordinator}) \cup ({WorkerA}) \cup ({WorkerB})

Init == (* Global variables *)
        /\ to_A = <<>>
        /\ to_B = <<>>
        /\ from_A = <<>>
        /\ from_B = <<>>
        /\ res_A = "FREE"
        /\ res_B = "FREE"
        (* Process coordinator_proc *)
        /\ msg_ = [self \in {Coordinator} |-> ""]
        /\ voteA = [self \in {Coordinator} |-> ""]
        /\ voteB = [self \in {Coordinator} |-> ""]
        (* Process workerA_proc *)
        /\ msg_w = [self \in {WorkerA} |-> ""]
        (* Process workerB_proc *)
        /\ msg = [self \in {WorkerB} |-> ""]
        /\ pc = [self \in ProcSet |-> CASE self \in {Coordinator} -> "c_send"
                                        [] self \in {WorkerA} -> "a_idle"
                                        [] self \in {WorkerB} -> "b_idle"]

c_send(self) == /\ pc[self] = "c_send"
                /\ to_A' = Append(to_A, "prepare")
                /\ to_B' = Append(to_B, "prepare")
                /\ pc' = [pc EXCEPT ![self] = "c_wait_votes"]
                /\ UNCHANGED << from_A, from_B, res_A, res_B, msg_, voteA, 
                                voteB, msg_w, msg >>

c_wait_votes(self) == /\ pc[self] = "c_wait_votes"
                      /\ \/ /\ pc' = [pc EXCEPT ![self] = "c_rcv_A"]
                         \/ /\ pc' = [pc EXCEPT ![self] = "c_rcv_B"]
                      /\ UNCHANGED << to_A, to_B, from_A, from_B, res_A, res_B, 
                                      msg_, voteA, voteB, msg_w, msg >>

c_rcv_A(self) == /\ pc[self] = "c_rcv_A"
                 /\ Len(from_A) > 0
                 /\ voteA' = [voteA EXCEPT ![self] = Head(from_A)]
                 /\ from_A' = Tail(from_A)
                 /\ pc' = [pc EXCEPT ![self] = "c_rcv_B1"]
                 /\ UNCHANGED << to_A, to_B, from_B, res_A, res_B, msg_, voteB, 
                                 msg_w, msg >>

c_rcv_B1(self) == /\ pc[self] = "c_rcv_B1"
                  /\ Len(from_B) > 0
                  /\ voteB' = [voteB EXCEPT ![self] = Head(from_B)]
                  /\ from_B' = Tail(from_B)
                  /\ pc' = [pc EXCEPT ![self] = "c_decide"]
                  /\ UNCHANGED << to_A, to_B, from_A, res_A, res_B, msg_, 
                                  voteA, msg_w, msg >>

c_rcv_B(self) == /\ pc[self] = "c_rcv_B"
                 /\ Len(from_B) > 0
                 /\ voteB' = [voteB EXCEPT ![self] = Head(from_B)]
                 /\ from_B' = Tail(from_B)
                 /\ pc' = [pc EXCEPT ![self] = "c_rcv_A1"]
                 /\ UNCHANGED << to_A, to_B, from_A, res_A, res_B, msg_, voteA, 
                                 msg_w, msg >>

c_rcv_A1(self) == /\ pc[self] = "c_rcv_A1"
                  /\ Len(from_A) > 0
                  /\ voteA' = [voteA EXCEPT ![self] = Head(from_A)]
                  /\ from_A' = Tail(from_A)
                  /\ pc' = [pc EXCEPT ![self] = "c_decide"]
                  /\ UNCHANGED << to_A, to_B, from_B, res_A, res_B, msg_, 
                                  voteB, msg_w, msg >>

c_decide(self) == /\ pc[self] = "c_decide"
                  /\ IF voteA[self] = "yes" /\ voteB[self] = "yes"
                        THEN /\ pc' = [pc EXCEPT ![self] = "c_commit"]
                        ELSE /\ pc' = [pc EXCEPT ![self] = "c_abort"]
                  /\ UNCHANGED << to_A, to_B, from_A, from_B, res_A, res_B, 
                                  msg_, voteA, voteB, msg_w, msg >>

c_commit(self) == /\ pc[self] = "c_commit"
                  /\ to_A' = Append(to_A, "commit")
                  /\ to_B' = Append(to_B, "commit")
                  /\ pc' = [pc EXCEPT ![self] = "c_done"]
                  /\ UNCHANGED << from_A, from_B, res_A, res_B, msg_, voteA, 
                                  voteB, msg_w, msg >>

c_abort(self) == /\ pc[self] = "c_abort"
                 /\ to_A' = Append(to_A, "abort")
                 /\ to_B' = Append(to_B, "abort")
                 /\ pc' = [pc EXCEPT ![self] = "c_done"]
                 /\ UNCHANGED << from_A, from_B, res_A, res_B, msg_, voteA, 
                                 voteB, msg_w, msg >>

c_done(self) == /\ pc[self] = "c_done"
                /\ TRUE
                /\ pc' = [pc EXCEPT ![self] = "Done"]
                /\ UNCHANGED << to_A, to_B, from_A, from_B, res_A, res_B, msg_, 
                                voteA, voteB, msg_w, msg >>

coordinator_proc(self) == c_send(self) \/ c_wait_votes(self)
                             \/ c_rcv_A(self) \/ c_rcv_B1(self)
                             \/ c_rcv_B(self) \/ c_rcv_A1(self)
                             \/ c_decide(self) \/ c_commit(self)
                             \/ c_abort(self) \/ c_done(self)

a_idle(self) == /\ pc[self] = "a_idle"
                /\ Len(to_A) > 0
                /\ msg_w' = [msg_w EXCEPT ![self] = Head(to_A)]
                /\ to_A' = Tail(to_A)
                /\ pc' = [pc EXCEPT ![self] = "a_vote"]
                /\ UNCHANGED << to_B, from_A, from_B, res_A, res_B, msg_, 
                                voteA, voteB, msg >>

a_vote(self) == /\ pc[self] = "a_vote"
                /\ \/ /\ res_A = "FREE"
                      /\ res_A' = self
                      /\ from_A' = Append(from_A, "yes")
                      /\ pc' = [pc EXCEPT ![self] = "a_locked"]
                   \/ /\ from_A' = Append(from_A, "no")
                      /\ pc' = [pc EXCEPT ![self] = "a_voted_no"]
                      /\ res_A' = res_A
                /\ UNCHANGED << to_A, to_B, from_B, res_B, msg_, voteA, voteB, 
                                msg_w, msg >>

a_locked(self) == /\ pc[self] = "a_locked"
                  /\ Len(to_A) > 0
                  /\ msg_w' = [msg_w EXCEPT ![self] = Head(to_A)]
                  /\ to_A' = Tail(to_A)
                  /\ pc' = [pc EXCEPT ![self] = "a_handle"]
                  /\ UNCHANGED << to_B, from_A, from_B, res_A, res_B, msg_, 
                                  voteA, voteB, msg >>

a_handle(self) == /\ pc[self] = "a_handle"
                  /\ IF msg_w[self] = "commit"
                        THEN /\ pc' = [pc EXCEPT ![self] = "a_release_ok"]
                        ELSE /\ pc' = [pc EXCEPT ![self] = "a_release_abort"]
                  /\ UNCHANGED << to_A, to_B, from_A, from_B, res_A, res_B, 
                                  msg_, voteA, voteB, msg_w, msg >>

a_release_ok(self) == /\ pc[self] = "a_release_ok"
                      /\ res_A' = "FREE"
                      /\ pc' = [pc EXCEPT ![self] = "Done"]
                      /\ UNCHANGED << to_A, to_B, from_A, from_B, res_B, msg_, 
                                      voteA, voteB, msg_w, msg >>

a_release_abort(self) == /\ pc[self] = "a_release_abort"
                         /\ res_A' = "FREE"
                         /\ pc' = [pc EXCEPT ![self] = "Done"]
                         /\ UNCHANGED << to_A, to_B, from_A, from_B, res_B, 
                                         msg_, voteA, voteB, msg_w, msg >>

a_voted_no(self) == /\ pc[self] = "a_voted_no"
                    /\ Len(to_A) > 0
                    /\ msg_w' = [msg_w EXCEPT ![self] = Head(to_A)]
                    /\ to_A' = Tail(to_A)
                    /\ pc' = [pc EXCEPT ![self] = "Done"]
                    /\ UNCHANGED << to_B, from_A, from_B, res_A, res_B, msg_, 
                                    voteA, voteB, msg >>

workerA_proc(self) == a_idle(self) \/ a_vote(self) \/ a_locked(self)
                         \/ a_handle(self) \/ a_release_ok(self)
                         \/ a_release_abort(self) \/ a_voted_no(self)

b_idle(self) == /\ pc[self] = "b_idle"
                /\ Len(to_B) > 0
                /\ msg' = [msg EXCEPT ![self] = Head(to_B)]
                /\ to_B' = Tail(to_B)
                /\ pc' = [pc EXCEPT ![self] = "b_vote"]
                /\ UNCHANGED << to_A, from_A, from_B, res_A, res_B, msg_, 
                                voteA, voteB, msg_w >>

b_vote(self) == /\ pc[self] = "b_vote"
                /\ \/ /\ res_B = "FREE"
                      /\ res_B' = self
                      /\ from_B' = Append(from_B, "yes")
                      /\ pc' = [pc EXCEPT ![self] = "b_locked"]
                   \/ /\ from_B' = Append(from_B, "no")
                      /\ pc' = [pc EXCEPT ![self] = "b_voted_no"]
                      /\ res_B' = res_B
                /\ UNCHANGED << to_A, to_B, from_A, res_A, msg_, voteA, voteB, 
                                msg_w, msg >>

b_locked(self) == /\ pc[self] = "b_locked"
                  /\ Len(to_B) > 0
                  /\ msg' = [msg EXCEPT ![self] = Head(to_B)]
                  /\ to_B' = Tail(to_B)
                  /\ pc' = [pc EXCEPT ![self] = "b_handle"]
                  /\ UNCHANGED << to_A, from_A, from_B, res_A, res_B, msg_, 
                                  voteA, voteB, msg_w >>

b_handle(self) == /\ pc[self] = "b_handle"
                  /\ IF msg[self] = "commit"
                        THEN /\ pc' = [pc EXCEPT ![self] = "b_release_ok"]
                        ELSE /\ pc' = [pc EXCEPT ![self] = "b_release_abort"]
                  /\ UNCHANGED << to_A, to_B, from_A, from_B, res_A, res_B, 
                                  msg_, voteA, voteB, msg_w, msg >>

b_release_ok(self) == /\ pc[self] = "b_release_ok"
                      /\ res_B' = "FREE"
                      /\ pc' = [pc EXCEPT ![self] = "Done"]
                      /\ UNCHANGED << to_A, to_B, from_A, from_B, res_A, msg_, 
                                      voteA, voteB, msg_w, msg >>

b_release_abort(self) == /\ pc[self] = "b_release_abort"
                         /\ res_B' = "FREE"
                         /\ pc' = [pc EXCEPT ![self] = "Done"]
                         /\ UNCHANGED << to_A, to_B, from_A, from_B, res_A, 
                                         msg_, voteA, voteB, msg_w, msg >>

b_voted_no(self) == /\ pc[self] = "b_voted_no"
                    /\ Len(to_B) > 0
                    /\ msg' = [msg EXCEPT ![self] = Head(to_B)]
                    /\ to_B' = Tail(to_B)
                    /\ pc' = [pc EXCEPT ![self] = "Done"]
                    /\ UNCHANGED << to_A, from_A, from_B, res_A, res_B, msg_, 
                                    voteA, voteB, msg_w >>

workerB_proc(self) == b_idle(self) \/ b_vote(self) \/ b_locked(self)
                         \/ b_handle(self) \/ b_release_ok(self)
                         \/ b_release_abort(self) \/ b_voted_no(self)

(* Allow infinite stuttering to prevent deadlock on termination. *)
Terminating == /\ \A self \in ProcSet: pc[self] = "Done"
               /\ UNCHANGED vars

Next == (\E self \in {Coordinator}: coordinator_proc(self))
           \/ (\E self \in {WorkerA}: workerA_proc(self))
           \/ (\E self \in {WorkerB}: workerB_proc(self))
           \/ Terminating

Spec == /\ Init /\ [][Next]_vars
        /\ \A self \in {Coordinator} : WF_vars(coordinator_proc(self))
        /\ \A self \in {WorkerA} : WF_vars(workerA_proc(self))
        /\ \A self \in {WorkerB} : WF_vars(workerB_proc(self))

Termination == <>(\A self \in ProcSet: pc[self] = "Done")

\* END TRANSLATION 

AllDone == \A p \in {Coordinator, WorkerA, WorkerB}: pc[p] = "Done"

TypeInvariant ==
  /\ \A p \in {Coordinator, WorkerA, WorkerB}: pc[p] \in STRING
  /\ res_A \in {Coordinator, WorkerA, WorkerB, "FREE"}
  /\ res_B \in {Coordinator, WorkerA, WorkerB, "FREE"}
  /\ to_A \in Seq(STRING)
  /\ to_B \in Seq(STRING)
  /\ from_A \in Seq(STRING)
  /\ from_B \in Seq(STRING)

NoOrphanLocks ==
  AllDone => (res_A = "FREE" /\ res_B = "FREE")

ChannelsDrained ==
  AllDone => (Len(to_A) = 0 /\ Len(to_B) = 0 /\ Len(from_A) = 0 /\ Len(from_B) = 0)

ChannelBound ==
  Len(to_A) <= 3 /\ Len(to_B) <= 3 /\ Len(from_A) <= 3 /\ Len(from_B) <= 3

====
