---- MODULE Protocol ----
EXTENDS Integers, Sequences, TLC

CONSTANTS TechA, TechB, Supervisor

(* --algorithm Protocol {
variables
  techA_to_sup = <<>>; \* techA -> supervisor, labels: ['job_done']
  techB_to_sup = <<>>; \* techB -> supervisor, labels: ['job_done']
  lathe_lock = "FREE"; \* Lock
  mill_lock = "FREE"; \* Lock

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

fair process (techA_proc \in {TechA})
variables msg = "", did_lathe = FALSE, did_mill = FALSE;
{
  ta_choose:
    either {
      \* Try lathe first
      acquire_lock(lathe_lock);
    ta_lathe_work:
      release_lock(lathe_lock);
      did_lathe := TRUE;
      send(techA_to_sup, "job_done");
    } or {
      \* Try mill first
      acquire_lock(mill_lock);
    ta_mill_work:
      release_lock(mill_lock);
      did_mill := TRUE;
      send(techA_to_sup, "job_done");
    };
  ta_second:
    if (did_lathe) {
      \* Need to do mill job
      acquire_lock(mill_lock);
    ta_mill_work2:
      release_lock(mill_lock);
      send(techA_to_sup, "job_done");
    } else {
      \* Need to do lathe job
      acquire_lock(lathe_lock);
    ta_lathe_work2:
      release_lock(lathe_lock);
      send(techA_to_sup, "job_done");
    };
  ta_done:
    skip;
}

fair process (techB_proc \in {TechB})
variables msg = "", did_lathe = FALSE, did_mill = FALSE;
{
  tb_choose:
    either {
      \* Try lathe first
      acquire_lock(lathe_lock);
    tb_lathe_work:
      release_lock(lathe_lock);
      did_lathe := TRUE;
      send(techB_to_sup, "job_done");
    } or {
      \* Try mill first
      acquire_lock(mill_lock);
    tb_mill_work:
      release_lock(mill_lock);
      did_mill := TRUE;
      send(techB_to_sup, "job_done");
    };
  tb_second:
    if (did_lathe) {
      \* Need to do mill job
      acquire_lock(mill_lock);
    tb_mill_work2:
      release_lock(mill_lock);
      send(techB_to_sup, "job_done");
    } else {
      \* Need to do lathe job
      acquire_lock(lathe_lock);
    tb_lathe_work2:
      release_lock(lathe_lock);
      send(techB_to_sup, "job_done");
    };
  tb_done:
    skip;
}

fair process (supervisor_proc \in {Supervisor})
variables msg = "", count = 0;
{
  sup_collect:
    while (count < 4) {
      sup_recv:
        either {
          receive(techA_to_sup, msg);
        } or {
          receive(techB_to_sup, msg);
        };
        count := count + 1;
    };
  sup_done:
    skip;
}

} *)
\* BEGIN TRANSLATION (chksum(pcal) = "4108c20b" /\ chksum(tla) = "d9b0a6bc")
\* Process variable msg of process techA_proc at line 33 col 11 changed to msg_
\* Process variable did_lathe of process techA_proc at line 33 col 21 changed to did_lathe_
\* Process variable did_mill of process techA_proc at line 33 col 40 changed to did_mill_
\* Process variable msg of process techB_proc at line 70 col 11 changed to msg_t
VARIABLES pc, techA_to_sup, techB_to_sup, lathe_lock, mill_lock, msg_, 
          did_lathe_, did_mill_, msg_t, did_lathe, did_mill, msg, count

vars == << pc, techA_to_sup, techB_to_sup, lathe_lock, mill_lock, msg_, 
           did_lathe_, did_mill_, msg_t, did_lathe, did_mill, msg, count >>

ProcSet == ({TechA}) \cup ({TechB}) \cup ({Supervisor})

Init == (* Global variables *)
        /\ techA_to_sup = <<>>
        /\ techB_to_sup = <<>>
        /\ lathe_lock = "FREE"
        /\ mill_lock = "FREE"
        (* Process techA_proc *)
        /\ msg_ = [self \in {TechA} |-> ""]
        /\ did_lathe_ = [self \in {TechA} |-> FALSE]
        /\ did_mill_ = [self \in {TechA} |-> FALSE]
        (* Process techB_proc *)
        /\ msg_t = [self \in {TechB} |-> ""]
        /\ did_lathe = [self \in {TechB} |-> FALSE]
        /\ did_mill = [self \in {TechB} |-> FALSE]
        (* Process supervisor_proc *)
        /\ msg = [self \in {Supervisor} |-> ""]
        /\ count = [self \in {Supervisor} |-> 0]
        /\ pc = [self \in ProcSet |-> CASE self \in {TechA} -> "ta_choose"
                                        [] self \in {TechB} -> "tb_choose"
                                        [] self \in {Supervisor} -> "sup_collect"]

ta_choose(self) == /\ pc[self] = "ta_choose"
                   /\ \/ /\ lathe_lock = "FREE"
                         /\ lathe_lock' = self
                         /\ pc' = [pc EXCEPT ![self] = "ta_lathe_work"]
                         /\ UNCHANGED mill_lock
                      \/ /\ mill_lock = "FREE"
                         /\ mill_lock' = self
                         /\ pc' = [pc EXCEPT ![self] = "ta_mill_work"]
                         /\ UNCHANGED lathe_lock
                   /\ UNCHANGED << techA_to_sup, techB_to_sup, msg_, 
                                   did_lathe_, did_mill_, msg_t, did_lathe, 
                                   did_mill, msg, count >>

ta_lathe_work(self) == /\ pc[self] = "ta_lathe_work"
                       /\ lathe_lock' = "FREE"
                       /\ did_lathe_' = [did_lathe_ EXCEPT ![self] = TRUE]
                       /\ techA_to_sup' = Append(techA_to_sup, "job_done")
                       /\ pc' = [pc EXCEPT ![self] = "ta_second"]
                       /\ UNCHANGED << techB_to_sup, mill_lock, msg_, 
                                       did_mill_, msg_t, did_lathe, did_mill, 
                                       msg, count >>

ta_mill_work(self) == /\ pc[self] = "ta_mill_work"
                      /\ mill_lock' = "FREE"
                      /\ did_mill_' = [did_mill_ EXCEPT ![self] = TRUE]
                      /\ techA_to_sup' = Append(techA_to_sup, "job_done")
                      /\ pc' = [pc EXCEPT ![self] = "ta_second"]
                      /\ UNCHANGED << techB_to_sup, lathe_lock, msg_, 
                                      did_lathe_, msg_t, did_lathe, did_mill, 
                                      msg, count >>

ta_second(self) == /\ pc[self] = "ta_second"
                   /\ IF did_lathe_[self]
                         THEN /\ mill_lock = "FREE"
                              /\ mill_lock' = self
                              /\ pc' = [pc EXCEPT ![self] = "ta_mill_work2"]
                              /\ UNCHANGED lathe_lock
                         ELSE /\ lathe_lock = "FREE"
                              /\ lathe_lock' = self
                              /\ pc' = [pc EXCEPT ![self] = "ta_lathe_work2"]
                              /\ UNCHANGED mill_lock
                   /\ UNCHANGED << techA_to_sup, techB_to_sup, msg_, 
                                   did_lathe_, did_mill_, msg_t, did_lathe, 
                                   did_mill, msg, count >>

ta_mill_work2(self) == /\ pc[self] = "ta_mill_work2"
                       /\ mill_lock' = "FREE"
                       /\ techA_to_sup' = Append(techA_to_sup, "job_done")
                       /\ pc' = [pc EXCEPT ![self] = "ta_done"]
                       /\ UNCHANGED << techB_to_sup, lathe_lock, msg_, 
                                       did_lathe_, did_mill_, msg_t, did_lathe, 
                                       did_mill, msg, count >>

ta_lathe_work2(self) == /\ pc[self] = "ta_lathe_work2"
                        /\ lathe_lock' = "FREE"
                        /\ techA_to_sup' = Append(techA_to_sup, "job_done")
                        /\ pc' = [pc EXCEPT ![self] = "ta_done"]
                        /\ UNCHANGED << techB_to_sup, mill_lock, msg_, 
                                        did_lathe_, did_mill_, msg_t, 
                                        did_lathe, did_mill, msg, count >>

ta_done(self) == /\ pc[self] = "ta_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << techA_to_sup, techB_to_sup, lathe_lock, 
                                 mill_lock, msg_, did_lathe_, did_mill_, msg_t, 
                                 did_lathe, did_mill, msg, count >>

techA_proc(self) == ta_choose(self) \/ ta_lathe_work(self)
                       \/ ta_mill_work(self) \/ ta_second(self)
                       \/ ta_mill_work2(self) \/ ta_lathe_work2(self)
                       \/ ta_done(self)

tb_choose(self) == /\ pc[self] = "tb_choose"
                   /\ \/ /\ lathe_lock = "FREE"
                         /\ lathe_lock' = self
                         /\ pc' = [pc EXCEPT ![self] = "tb_lathe_work"]
                         /\ UNCHANGED mill_lock
                      \/ /\ mill_lock = "FREE"
                         /\ mill_lock' = self
                         /\ pc' = [pc EXCEPT ![self] = "tb_mill_work"]
                         /\ UNCHANGED lathe_lock
                   /\ UNCHANGED << techA_to_sup, techB_to_sup, msg_, 
                                   did_lathe_, did_mill_, msg_t, did_lathe, 
                                   did_mill, msg, count >>

tb_lathe_work(self) == /\ pc[self] = "tb_lathe_work"
                       /\ lathe_lock' = "FREE"
                       /\ did_lathe' = [did_lathe EXCEPT ![self] = TRUE]
                       /\ techB_to_sup' = Append(techB_to_sup, "job_done")
                       /\ pc' = [pc EXCEPT ![self] = "tb_second"]
                       /\ UNCHANGED << techA_to_sup, mill_lock, msg_, 
                                       did_lathe_, did_mill_, msg_t, did_mill, 
                                       msg, count >>

tb_mill_work(self) == /\ pc[self] = "tb_mill_work"
                      /\ mill_lock' = "FREE"
                      /\ did_mill' = [did_mill EXCEPT ![self] = TRUE]
                      /\ techB_to_sup' = Append(techB_to_sup, "job_done")
                      /\ pc' = [pc EXCEPT ![self] = "tb_second"]
                      /\ UNCHANGED << techA_to_sup, lathe_lock, msg_, 
                                      did_lathe_, did_mill_, msg_t, did_lathe, 
                                      msg, count >>

tb_second(self) == /\ pc[self] = "tb_second"
                   /\ IF did_lathe[self]
                         THEN /\ mill_lock = "FREE"
                              /\ mill_lock' = self
                              /\ pc' = [pc EXCEPT ![self] = "tb_mill_work2"]
                              /\ UNCHANGED lathe_lock
                         ELSE /\ lathe_lock = "FREE"
                              /\ lathe_lock' = self
                              /\ pc' = [pc EXCEPT ![self] = "tb_lathe_work2"]
                              /\ UNCHANGED mill_lock
                   /\ UNCHANGED << techA_to_sup, techB_to_sup, msg_, 
                                   did_lathe_, did_mill_, msg_t, did_lathe, 
                                   did_mill, msg, count >>

tb_mill_work2(self) == /\ pc[self] = "tb_mill_work2"
                       /\ mill_lock' = "FREE"
                       /\ techB_to_sup' = Append(techB_to_sup, "job_done")
                       /\ pc' = [pc EXCEPT ![self] = "tb_done"]
                       /\ UNCHANGED << techA_to_sup, lathe_lock, msg_, 
                                       did_lathe_, did_mill_, msg_t, did_lathe, 
                                       did_mill, msg, count >>

tb_lathe_work2(self) == /\ pc[self] = "tb_lathe_work2"
                        /\ lathe_lock' = "FREE"
                        /\ techB_to_sup' = Append(techB_to_sup, "job_done")
                        /\ pc' = [pc EXCEPT ![self] = "tb_done"]
                        /\ UNCHANGED << techA_to_sup, mill_lock, msg_, 
                                        did_lathe_, did_mill_, msg_t, 
                                        did_lathe, did_mill, msg, count >>

tb_done(self) == /\ pc[self] = "tb_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << techA_to_sup, techB_to_sup, lathe_lock, 
                                 mill_lock, msg_, did_lathe_, did_mill_, msg_t, 
                                 did_lathe, did_mill, msg, count >>

techB_proc(self) == tb_choose(self) \/ tb_lathe_work(self)
                       \/ tb_mill_work(self) \/ tb_second(self)
                       \/ tb_mill_work2(self) \/ tb_lathe_work2(self)
                       \/ tb_done(self)

sup_collect(self) == /\ pc[self] = "sup_collect"
                     /\ IF count[self] < 4
                           THEN /\ pc' = [pc EXCEPT ![self] = "sup_recv"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "sup_done"]
                     /\ UNCHANGED << techA_to_sup, techB_to_sup, lathe_lock, 
                                     mill_lock, msg_, did_lathe_, did_mill_, 
                                     msg_t, did_lathe, did_mill, msg, count >>

sup_recv(self) == /\ pc[self] = "sup_recv"
                  /\ \/ /\ Len(techA_to_sup) > 0
                        /\ msg' = [msg EXCEPT ![self] = Head(techA_to_sup)]
                        /\ techA_to_sup' = Tail(techA_to_sup)
                        /\ UNCHANGED techB_to_sup
                     \/ /\ Len(techB_to_sup) > 0
                        /\ msg' = [msg EXCEPT ![self] = Head(techB_to_sup)]
                        /\ techB_to_sup' = Tail(techB_to_sup)
                        /\ UNCHANGED techA_to_sup
                  /\ count' = [count EXCEPT ![self] = count[self] + 1]
                  /\ pc' = [pc EXCEPT ![self] = "sup_collect"]
                  /\ UNCHANGED << lathe_lock, mill_lock, msg_, did_lathe_, 
                                  did_mill_, msg_t, did_lathe, did_mill >>

sup_done(self) == /\ pc[self] = "sup_done"
                  /\ TRUE
                  /\ pc' = [pc EXCEPT ![self] = "Done"]
                  /\ UNCHANGED << techA_to_sup, techB_to_sup, lathe_lock, 
                                  mill_lock, msg_, did_lathe_, did_mill_, 
                                  msg_t, did_lathe, did_mill, msg, count >>

supervisor_proc(self) == sup_collect(self) \/ sup_recv(self)
                            \/ sup_done(self)

(* Allow infinite stuttering to prevent deadlock on termination. *)
Terminating == /\ \A self \in ProcSet: pc[self] = "Done"
               /\ UNCHANGED vars

Next == (\E self \in {TechA}: techA_proc(self))
           \/ (\E self \in {TechB}: techB_proc(self))
           \/ (\E self \in {Supervisor}: supervisor_proc(self))
           \/ Terminating

Spec == /\ Init /\ [][Next]_vars
        /\ \A self \in {TechA} : WF_vars(techA_proc(self))
        /\ \A self \in {TechB} : WF_vars(techB_proc(self))
        /\ \A self \in {Supervisor} : WF_vars(supervisor_proc(self))

Termination == <>(\A self \in ProcSet: pc[self] = "Done")

\* END TRANSLATION 

AllDone == \A p \in {TechA, TechB, Supervisor}: pc[p] = "Done"

TypeInvariant ==
  /\ \A p \in {TechA, TechB, Supervisor}: pc[p] \in STRING
  /\ lathe_lock \in {TechA, TechB, Supervisor, "FREE"}
  /\ mill_lock \in {TechA, TechB, Supervisor, "FREE"}
  /\ techA_to_sup \in Seq(STRING)
  /\ techB_to_sup \in Seq(STRING)

NoOrphanLocks ==
  AllDone => (lathe_lock = "FREE" /\ mill_lock = "FREE")

ChannelsDrained ==
  AllDone => (Len(techA_to_sup) = 0 /\ Len(techB_to_sup) = 0)

ChannelBound ==
  Len(techA_to_sup) <= 3 /\ Len(techB_to_sup) <= 3

====
