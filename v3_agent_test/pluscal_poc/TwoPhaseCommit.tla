--------------------------- MODULE TwoPhaseCommit ---------------------------
EXTENDS Integers, Sequences, TLC

CONSTANTS Coord, WorkerA, WorkerB

\* === Variables ===
\* Channels: unbounded FIFO queues (modeled as sequences)
\* Resources: Locks (FREE or holder agent id)

(* --algorithm TwoPhaseCommit

variables
  \* Channels (from IR declarations)
  to_A = <<>>,      \* coordinator -> workerA: prepare, commit, abort
  to_B = <<>>,      \* coordinator -> workerB: prepare, commit, abort
  from_A = <<>>,    \* workerA -> coordinator: yes, no
  from_B = <<>>,    \* workerB -> coordinator: yes, no
  \* Resources (from IR declarations)
  res_A = "FREE",   \* Lock
  res_B = "FREE";   \* Lock

\* --- Macros generated from IR channel/resource declarations ---

macro send(ch, msg) begin
  ch := Append(ch, msg);
end macro;

macro receive(ch, var) begin
  await Len(ch) > 0;
  var := Head(ch);
  ch := Tail(ch);
end macro;

macro acquire(lock, who) begin
  await lock = "FREE";
  lock := who;
end macro;

macro release(lock) begin
  lock := "FREE";
end macro;

\* === Process bodies (this is what the LLM writes) ===

fair process coordinator = Coord
variables msg = "";
begin
  c_send:
    send(to_A, "prepare");
    send(to_B, "prepare");

  c_wait:
    \* Either-order: receive from A or B first
    either
      receive(from_A, msg);
      c_gotA:
        if msg = "yes" then
          c_waitB_afterAyes:
            receive(from_B, msg);
            if msg = "yes" then
              c_commit:
                send(to_A, "commit");
                send(to_B, "commit");
            else
              c_abort1:
                send(to_A, "abort");
                send(to_B, "abort");
            end if;
        else
          c_waitB_afterAno:
            receive(from_B, msg);
            c_abort2:
              send(to_A, "abort");
              send(to_B, "abort");
        end if;
    or
      receive(from_B, msg);
      c_gotB:
        if msg = "yes" then
          c_waitA_afterByes:
            receive(from_A, msg);
            if msg = "yes" then
              c_commit2:
                send(to_A, "commit");
                send(to_B, "commit");
            else
              c_abort3:
                send(to_A, "abort");
                send(to_B, "abort");
            end if;
        else
          c_waitA_afterBno:
            receive(from_A, msg);
            c_abort4:
              send(to_A, "abort");
              send(to_B, "abort");
        end if;
    end either;

  c_done: skip;
end process;

fair process workerA = WorkerA
variables wmsg = "";
begin
  a_idle:
    receive(to_A, wmsg);

  a_vote:
    either
      \* Vote yes: acquire lock
      acquire(res_A, WorkerA);
      send(from_A, "yes");
      a_wait_decision:
        receive(to_A, wmsg);
        a_release:
          release(res_A);
    or
      \* Vote no
      send(from_A, "no");
      a_wait_decision_no:
        receive(to_A, wmsg);
    end either;

  a_done: skip;
end process;

fair process workerB = WorkerB
variables wmsg = "";
begin
  b_idle:
    receive(to_B, wmsg);

  b_vote:
    either
      acquire(res_B, WorkerB);
      send(from_B, "yes");
      b_wait_decision:
        receive(to_B, wmsg);
        b_release:
          release(res_B);
    or
      send(from_B, "no");
      b_wait_decision_no:
        receive(to_B, wmsg);
    end either;

  b_done: skip;
end process;

end algorithm; *)
\* BEGIN TRANSLATION (chksum(pcal) = "38480ff8" /\ chksum(tla) = "5c97c210")
\* Process variable wmsg of process workerA at line 104 col 11 changed to wmsg_
VARIABLES pc, to_A, to_B, from_A, from_B, res_A, res_B, msg, wmsg_, wmsg

vars == << pc, to_A, to_B, from_A, from_B, res_A, res_B, msg, wmsg_, wmsg >>

ProcSet == {Coord} \cup {WorkerA} \cup {WorkerB}

Init == (* Global variables *)
        /\ to_A = <<>>
        /\ to_B = <<>>
        /\ from_A = <<>>
        /\ from_B = <<>>
        /\ res_A = "FREE"
        /\ res_B = "FREE"
        (* Process coordinator *)
        /\ msg = ""
        (* Process workerA *)
        /\ wmsg_ = ""
        (* Process workerB *)
        /\ wmsg = ""
        /\ pc = [self \in ProcSet |-> CASE self = Coord -> "c_send"
                                        [] self = WorkerA -> "a_idle"
                                        [] self = WorkerB -> "b_idle"]

c_send == /\ pc[Coord] = "c_send"
          /\ to_A' = Append(to_A, "prepare")
          /\ to_B' = Append(to_B, "prepare")
          /\ pc' = [pc EXCEPT ![Coord] = "c_wait"]
          /\ UNCHANGED << from_A, from_B, res_A, res_B, msg, wmsg_, wmsg >>

c_wait == /\ pc[Coord] = "c_wait"
          /\ \/ /\ Len(from_A) > 0
                /\ msg' = Head(from_A)
                /\ from_A' = Tail(from_A)
                /\ pc' = [pc EXCEPT ![Coord] = "c_gotA"]
                /\ UNCHANGED from_B
             \/ /\ Len(from_B) > 0
                /\ msg' = Head(from_B)
                /\ from_B' = Tail(from_B)
                /\ pc' = [pc EXCEPT ![Coord] = "c_gotB"]
                /\ UNCHANGED from_A
          /\ UNCHANGED << to_A, to_B, res_A, res_B, wmsg_, wmsg >>

c_gotA == /\ pc[Coord] = "c_gotA"
          /\ IF msg = "yes"
                THEN /\ pc' = [pc EXCEPT ![Coord] = "c_waitB_afterAyes"]
                ELSE /\ pc' = [pc EXCEPT ![Coord] = "c_waitB_afterAno"]
          /\ UNCHANGED << to_A, to_B, from_A, from_B, res_A, res_B, msg, wmsg_, 
                          wmsg >>

c_waitB_afterAyes == /\ pc[Coord] = "c_waitB_afterAyes"
                     /\ Len(from_B) > 0
                     /\ msg' = Head(from_B)
                     /\ from_B' = Tail(from_B)
                     /\ IF msg' = "yes"
                           THEN /\ pc' = [pc EXCEPT ![Coord] = "c_commit"]
                           ELSE /\ pc' = [pc EXCEPT ![Coord] = "c_abort1"]
                     /\ UNCHANGED << to_A, to_B, from_A, res_A, res_B, wmsg_, 
                                     wmsg >>

c_commit == /\ pc[Coord] = "c_commit"
            /\ to_A' = Append(to_A, "commit")
            /\ to_B' = Append(to_B, "commit")
            /\ pc' = [pc EXCEPT ![Coord] = "c_done"]
            /\ UNCHANGED << from_A, from_B, res_A, res_B, msg, wmsg_, wmsg >>

c_abort1 == /\ pc[Coord] = "c_abort1"
            /\ to_A' = Append(to_A, "abort")
            /\ to_B' = Append(to_B, "abort")
            /\ pc' = [pc EXCEPT ![Coord] = "c_done"]
            /\ UNCHANGED << from_A, from_B, res_A, res_B, msg, wmsg_, wmsg >>

c_waitB_afterAno == /\ pc[Coord] = "c_waitB_afterAno"
                    /\ Len(from_B) > 0
                    /\ msg' = Head(from_B)
                    /\ from_B' = Tail(from_B)
                    /\ pc' = [pc EXCEPT ![Coord] = "c_abort2"]
                    /\ UNCHANGED << to_A, to_B, from_A, res_A, res_B, wmsg_, 
                                    wmsg >>

c_abort2 == /\ pc[Coord] = "c_abort2"
            /\ to_A' = Append(to_A, "abort")
            /\ to_B' = Append(to_B, "abort")
            /\ pc' = [pc EXCEPT ![Coord] = "c_done"]
            /\ UNCHANGED << from_A, from_B, res_A, res_B, msg, wmsg_, wmsg >>

c_gotB == /\ pc[Coord] = "c_gotB"
          /\ IF msg = "yes"
                THEN /\ pc' = [pc EXCEPT ![Coord] = "c_waitA_afterByes"]
                ELSE /\ pc' = [pc EXCEPT ![Coord] = "c_waitA_afterBno"]
          /\ UNCHANGED << to_A, to_B, from_A, from_B, res_A, res_B, msg, wmsg_, 
                          wmsg >>

c_waitA_afterByes == /\ pc[Coord] = "c_waitA_afterByes"
                     /\ Len(from_A) > 0
                     /\ msg' = Head(from_A)
                     /\ from_A' = Tail(from_A)
                     /\ IF msg' = "yes"
                           THEN /\ pc' = [pc EXCEPT ![Coord] = "c_commit2"]
                           ELSE /\ pc' = [pc EXCEPT ![Coord] = "c_abort3"]
                     /\ UNCHANGED << to_A, to_B, from_B, res_A, res_B, wmsg_, 
                                     wmsg >>

c_commit2 == /\ pc[Coord] = "c_commit2"
             /\ to_A' = Append(to_A, "commit")
             /\ to_B' = Append(to_B, "commit")
             /\ pc' = [pc EXCEPT ![Coord] = "c_done"]
             /\ UNCHANGED << from_A, from_B, res_A, res_B, msg, wmsg_, wmsg >>

c_abort3 == /\ pc[Coord] = "c_abort3"
            /\ to_A' = Append(to_A, "abort")
            /\ to_B' = Append(to_B, "abort")
            /\ pc' = [pc EXCEPT ![Coord] = "c_done"]
            /\ UNCHANGED << from_A, from_B, res_A, res_B, msg, wmsg_, wmsg >>

c_waitA_afterBno == /\ pc[Coord] = "c_waitA_afterBno"
                    /\ Len(from_A) > 0
                    /\ msg' = Head(from_A)
                    /\ from_A' = Tail(from_A)
                    /\ pc' = [pc EXCEPT ![Coord] = "c_abort4"]
                    /\ UNCHANGED << to_A, to_B, from_B, res_A, res_B, wmsg_, 
                                    wmsg >>

c_abort4 == /\ pc[Coord] = "c_abort4"
            /\ to_A' = Append(to_A, "abort")
            /\ to_B' = Append(to_B, "abort")
            /\ pc' = [pc EXCEPT ![Coord] = "c_done"]
            /\ UNCHANGED << from_A, from_B, res_A, res_B, msg, wmsg_, wmsg >>

c_done == /\ pc[Coord] = "c_done"
          /\ TRUE
          /\ pc' = [pc EXCEPT ![Coord] = "Done"]
          /\ UNCHANGED << to_A, to_B, from_A, from_B, res_A, res_B, msg, wmsg_, 
                          wmsg >>

coordinator == c_send \/ c_wait \/ c_gotA \/ c_waitB_afterAyes \/ c_commit
                  \/ c_abort1 \/ c_waitB_afterAno \/ c_abort2 \/ c_gotB
                  \/ c_waitA_afterByes \/ c_commit2 \/ c_abort3
                  \/ c_waitA_afterBno \/ c_abort4 \/ c_done

a_idle == /\ pc[WorkerA] = "a_idle"
          /\ Len(to_A) > 0
          /\ wmsg_' = Head(to_A)
          /\ to_A' = Tail(to_A)
          /\ pc' = [pc EXCEPT ![WorkerA] = "a_vote"]
          /\ UNCHANGED << to_B, from_A, from_B, res_A, res_B, msg, wmsg >>

a_vote == /\ pc[WorkerA] = "a_vote"
          /\ \/ /\ res_A = "FREE"
                /\ res_A' = WorkerA
                /\ from_A' = Append(from_A, "yes")
                /\ pc' = [pc EXCEPT ![WorkerA] = "a_wait_decision"]
             \/ /\ from_A' = Append(from_A, "no")
                /\ pc' = [pc EXCEPT ![WorkerA] = "a_wait_decision_no"]
                /\ res_A' = res_A
          /\ UNCHANGED << to_A, to_B, from_B, res_B, msg, wmsg_, wmsg >>

a_wait_decision == /\ pc[WorkerA] = "a_wait_decision"
                   /\ Len(to_A) > 0
                   /\ wmsg_' = Head(to_A)
                   /\ to_A' = Tail(to_A)
                   /\ pc' = [pc EXCEPT ![WorkerA] = "a_release"]
                   /\ UNCHANGED << to_B, from_A, from_B, res_A, res_B, msg, 
                                   wmsg >>

a_release == /\ pc[WorkerA] = "a_release"
             /\ res_A' = "FREE"
             /\ pc' = [pc EXCEPT ![WorkerA] = "a_done"]
             /\ UNCHANGED << to_A, to_B, from_A, from_B, res_B, msg, wmsg_, 
                             wmsg >>

a_wait_decision_no == /\ pc[WorkerA] = "a_wait_decision_no"
                      /\ Len(to_A) > 0
                      /\ wmsg_' = Head(to_A)
                      /\ to_A' = Tail(to_A)
                      /\ pc' = [pc EXCEPT ![WorkerA] = "a_done"]
                      /\ UNCHANGED << to_B, from_A, from_B, res_A, res_B, msg, 
                                      wmsg >>

a_done == /\ pc[WorkerA] = "a_done"
          /\ TRUE
          /\ pc' = [pc EXCEPT ![WorkerA] = "Done"]
          /\ UNCHANGED << to_A, to_B, from_A, from_B, res_A, res_B, msg, wmsg_, 
                          wmsg >>

workerA == a_idle \/ a_vote \/ a_wait_decision \/ a_release
              \/ a_wait_decision_no \/ a_done

b_idle == /\ pc[WorkerB] = "b_idle"
          /\ Len(to_B) > 0
          /\ wmsg' = Head(to_B)
          /\ to_B' = Tail(to_B)
          /\ pc' = [pc EXCEPT ![WorkerB] = "b_vote"]
          /\ UNCHANGED << to_A, from_A, from_B, res_A, res_B, msg, wmsg_ >>

b_vote == /\ pc[WorkerB] = "b_vote"
          /\ \/ /\ res_B = "FREE"
                /\ res_B' = WorkerB
                /\ from_B' = Append(from_B, "yes")
                /\ pc' = [pc EXCEPT ![WorkerB] = "b_wait_decision"]
             \/ /\ from_B' = Append(from_B, "no")
                /\ pc' = [pc EXCEPT ![WorkerB] = "b_wait_decision_no"]
                /\ res_B' = res_B
          /\ UNCHANGED << to_A, to_B, from_A, res_A, msg, wmsg_, wmsg >>

b_wait_decision == /\ pc[WorkerB] = "b_wait_decision"
                   /\ Len(to_B) > 0
                   /\ wmsg' = Head(to_B)
                   /\ to_B' = Tail(to_B)
                   /\ pc' = [pc EXCEPT ![WorkerB] = "b_release"]
                   /\ UNCHANGED << to_A, from_A, from_B, res_A, res_B, msg, 
                                   wmsg_ >>

b_release == /\ pc[WorkerB] = "b_release"
             /\ res_B' = "FREE"
             /\ pc' = [pc EXCEPT ![WorkerB] = "b_done"]
             /\ UNCHANGED << to_A, to_B, from_A, from_B, res_A, msg, wmsg_, 
                             wmsg >>

b_wait_decision_no == /\ pc[WorkerB] = "b_wait_decision_no"
                      /\ Len(to_B) > 0
                      /\ wmsg' = Head(to_B)
                      /\ to_B' = Tail(to_B)
                      /\ pc' = [pc EXCEPT ![WorkerB] = "b_done"]
                      /\ UNCHANGED << to_A, from_A, from_B, res_A, res_B, msg, 
                                      wmsg_ >>

b_done == /\ pc[WorkerB] = "b_done"
          /\ TRUE
          /\ pc' = [pc EXCEPT ![WorkerB] = "Done"]
          /\ UNCHANGED << to_A, to_B, from_A, from_B, res_A, res_B, msg, wmsg_, 
                          wmsg >>

workerB == b_idle \/ b_vote \/ b_wait_decision \/ b_release
              \/ b_wait_decision_no \/ b_done

(* Allow infinite stuttering to prevent deadlock on termination. *)
Terminating == /\ \A self \in ProcSet: pc[self] = "Done"
               /\ UNCHANGED vars

Next == coordinator \/ workerA \/ workerB
           \/ Terminating

Spec == /\ Init /\ [][Next]_vars
        /\ WF_vars(coordinator)
        /\ WF_vars(workerA)
        /\ WF_vars(workerB)

Termination == <>(\A self \in ProcSet: pc[self] = "Done")

\* END TRANSLATION 

\* === Invariants (generated from IR resource declarations) ===

MutualExclusion_res_A ==
  \/ res_A = "FREE"
  \/ \A p \in {WorkerA, WorkerB} : res_A = p =>
       \A q \in {WorkerA, WorkerB} : q # p => res_A # q

MutualExclusion_res_B ==
  \/ res_B = "FREE"
  \/ \A p \in {WorkerA, WorkerB} : res_B = p =>
       \A q \in {WorkerA, WorkerB} : q # p => res_B # q

TypeInvariant ==
  /\ res_A \in {"FREE", WorkerA, WorkerB}
  /\ res_B \in {"FREE", WorkerA, WorkerB}

NoOrphanLocks ==
  (\A p \in {Coord, WorkerA, WorkerB} : pc[p] = "Done") =>
    /\ res_A = "FREE"
    /\ res_B = "FREE"

ChannelsDrained ==
  (\A p \in {Coord, WorkerA, WorkerB} : pc[p] = "Done") =>
    /\ to_A = <<>>
    /\ to_B = <<>>
    /\ from_A = <<>>
    /\ from_B = <<>>

\* Channel bound constraint for finite state space
ChannelBound ==
  /\ Len(to_A) <= 3
  /\ Len(to_B) <= 3
  /\ Len(from_A) <= 3
  /\ Len(from_B) <= 3

=============================================================================
