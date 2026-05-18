---- MODULE Protocol ----
EXTENDS Integers, Sequences, TLC

CONSTANTS Phil0, Phil1, Phil2

(* --algorithm Protocol {
variables
  fork0 = "FREE"; \* Lock
  fork1 = "FREE"; \* Lock
  fork2 = "FREE"; \* Lock

macro acquire_lock(lock) {
  await lock = "FREE";
  lock := self;
}

macro release_lock(lock) {
  lock := "FREE";
}

fair process (phil0_proc \in {Phil0})
variables msg = "";
{
  \* Phil0: left=fork0, right=fork2. Order: fork0 then fork2
  p0_think:
    skip; \* thinking
  p0_get_first:
    acquire_lock(fork0);
  p0_get_second:
    acquire_lock(fork2);
  p0_eat:
    skip; \* eating
  p0_release:
    release_lock(fork2);
    release_lock(fork0);
}

fair process (phil1_proc \in {Phil1})
variables msg = "";
{
  \* Phil1: left=fork1, right=fork0. Order: fork0 then fork1
  p1_think:
    skip; \* thinking
  p1_get_first:
    acquire_lock(fork0);
  p1_get_second:
    acquire_lock(fork1);
  p1_eat:
    skip; \* eating
  p1_release:
    release_lock(fork1);
    release_lock(fork0);
}

fair process (phil2_proc \in {Phil2})
variables msg = "";
{
  \* Phil2: left=fork2, right=fork1. Order: fork1 then fork2
  p2_think:
    skip; \* thinking
  p2_get_first:
    acquire_lock(fork1);
  p2_get_second:
    acquire_lock(fork2);
  p2_eat:
    skip; \* eating
  p2_release:
    release_lock(fork2);
    release_lock(fork1);
}

} *)
\* BEGIN TRANSLATION (chksum(pcal) = "573ad4ba" /\ chksum(tla) = "3046dbf8")
\* Process variable msg of process phil0_proc at line 22 col 11 changed to msg_
\* Process variable msg of process phil1_proc at line 39 col 11 changed to msg_p
VARIABLES pc, fork0, fork1, fork2, msg_, msg_p, msg

vars == << pc, fork0, fork1, fork2, msg_, msg_p, msg >>

ProcSet == ({Phil0}) \cup ({Phil1}) \cup ({Phil2})

Init == (* Global variables *)
        /\ fork0 = "FREE"
        /\ fork1 = "FREE"
        /\ fork2 = "FREE"
        (* Process phil0_proc *)
        /\ msg_ = [self \in {Phil0} |-> ""]
        (* Process phil1_proc *)
        /\ msg_p = [self \in {Phil1} |-> ""]
        (* Process phil2_proc *)
        /\ msg = [self \in {Phil2} |-> ""]
        /\ pc = [self \in ProcSet |-> CASE self \in {Phil0} -> "p0_think"
                                        [] self \in {Phil1} -> "p1_think"
                                        [] self \in {Phil2} -> "p2_think"]

p0_think(self) == /\ pc[self] = "p0_think"
                  /\ TRUE
                  /\ pc' = [pc EXCEPT ![self] = "p0_get_first"]
                  /\ UNCHANGED << fork0, fork1, fork2, msg_, msg_p, msg >>

p0_get_first(self) == /\ pc[self] = "p0_get_first"
                      /\ fork0 = "FREE"
                      /\ fork0' = self
                      /\ pc' = [pc EXCEPT ![self] = "p0_get_second"]
                      /\ UNCHANGED << fork1, fork2, msg_, msg_p, msg >>

p0_get_second(self) == /\ pc[self] = "p0_get_second"
                       /\ fork2 = "FREE"
                       /\ fork2' = self
                       /\ pc' = [pc EXCEPT ![self] = "p0_eat"]
                       /\ UNCHANGED << fork0, fork1, msg_, msg_p, msg >>

p0_eat(self) == /\ pc[self] = "p0_eat"
                /\ TRUE
                /\ pc' = [pc EXCEPT ![self] = "p0_release"]
                /\ UNCHANGED << fork0, fork1, fork2, msg_, msg_p, msg >>

p0_release(self) == /\ pc[self] = "p0_release"
                    /\ fork2' = "FREE"
                    /\ fork0' = "FREE"
                    /\ pc' = [pc EXCEPT ![self] = "Done"]
                    /\ UNCHANGED << fork1, msg_, msg_p, msg >>

phil0_proc(self) == p0_think(self) \/ p0_get_first(self)
                       \/ p0_get_second(self) \/ p0_eat(self)
                       \/ p0_release(self)

p1_think(self) == /\ pc[self] = "p1_think"
                  /\ TRUE
                  /\ pc' = [pc EXCEPT ![self] = "p1_get_first"]
                  /\ UNCHANGED << fork0, fork1, fork2, msg_, msg_p, msg >>

p1_get_first(self) == /\ pc[self] = "p1_get_first"
                      /\ fork0 = "FREE"
                      /\ fork0' = self
                      /\ pc' = [pc EXCEPT ![self] = "p1_get_second"]
                      /\ UNCHANGED << fork1, fork2, msg_, msg_p, msg >>

p1_get_second(self) == /\ pc[self] = "p1_get_second"
                       /\ fork1 = "FREE"
                       /\ fork1' = self
                       /\ pc' = [pc EXCEPT ![self] = "p1_eat"]
                       /\ UNCHANGED << fork0, fork2, msg_, msg_p, msg >>

p1_eat(self) == /\ pc[self] = "p1_eat"
                /\ TRUE
                /\ pc' = [pc EXCEPT ![self] = "p1_release"]
                /\ UNCHANGED << fork0, fork1, fork2, msg_, msg_p, msg >>

p1_release(self) == /\ pc[self] = "p1_release"
                    /\ fork1' = "FREE"
                    /\ fork0' = "FREE"
                    /\ pc' = [pc EXCEPT ![self] = "Done"]
                    /\ UNCHANGED << fork2, msg_, msg_p, msg >>

phil1_proc(self) == p1_think(self) \/ p1_get_first(self)
                       \/ p1_get_second(self) \/ p1_eat(self)
                       \/ p1_release(self)

p2_think(self) == /\ pc[self] = "p2_think"
                  /\ TRUE
                  /\ pc' = [pc EXCEPT ![self] = "p2_get_first"]
                  /\ UNCHANGED << fork0, fork1, fork2, msg_, msg_p, msg >>

p2_get_first(self) == /\ pc[self] = "p2_get_first"
                      /\ fork1 = "FREE"
                      /\ fork1' = self
                      /\ pc' = [pc EXCEPT ![self] = "p2_get_second"]
                      /\ UNCHANGED << fork0, fork2, msg_, msg_p, msg >>

p2_get_second(self) == /\ pc[self] = "p2_get_second"
                       /\ fork2 = "FREE"
                       /\ fork2' = self
                       /\ pc' = [pc EXCEPT ![self] = "p2_eat"]
                       /\ UNCHANGED << fork0, fork1, msg_, msg_p, msg >>

p2_eat(self) == /\ pc[self] = "p2_eat"
                /\ TRUE
                /\ pc' = [pc EXCEPT ![self] = "p2_release"]
                /\ UNCHANGED << fork0, fork1, fork2, msg_, msg_p, msg >>

p2_release(self) == /\ pc[self] = "p2_release"
                    /\ fork2' = "FREE"
                    /\ fork1' = "FREE"
                    /\ pc' = [pc EXCEPT ![self] = "Done"]
                    /\ UNCHANGED << fork0, msg_, msg_p, msg >>

phil2_proc(self) == p2_think(self) \/ p2_get_first(self)
                       \/ p2_get_second(self) \/ p2_eat(self)
                       \/ p2_release(self)

(* Allow infinite stuttering to prevent deadlock on termination. *)
Terminating == /\ \A self \in ProcSet: pc[self] = "Done"
               /\ UNCHANGED vars

Next == (\E self \in {Phil0}: phil0_proc(self))
           \/ (\E self \in {Phil1}: phil1_proc(self))
           \/ (\E self \in {Phil2}: phil2_proc(self))
           \/ Terminating

Spec == /\ Init /\ [][Next]_vars
        /\ \A self \in {Phil0} : WF_vars(phil0_proc(self))
        /\ \A self \in {Phil1} : WF_vars(phil1_proc(self))
        /\ \A self \in {Phil2} : WF_vars(phil2_proc(self))

Termination == <>(\A self \in ProcSet: pc[self] = "Done")

\* END TRANSLATION 

AllDone == \A p \in {Phil0, Phil1, Phil2}: pc[p] = "Done"

TypeInvariant ==
  /\ \A p \in {Phil0, Phil1, Phil2}: pc[p] \in STRING
  /\ fork0 \in {Phil0, Phil1, Phil2, "FREE"}
  /\ fork1 \in {Phil0, Phil1, Phil2, "FREE"}
  /\ fork2 \in {Phil0, Phil1, Phil2, "FREE"}

NoOrphanLocks ==
  AllDone => (fork0 = "FREE" /\ fork1 = "FREE" /\ fork2 = "FREE")

====
