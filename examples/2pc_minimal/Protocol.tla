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