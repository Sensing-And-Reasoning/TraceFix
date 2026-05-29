---- MODULE Protocol ----
EXTENDS Integers, Sequences, TLC

CONSTANTS WRITER_LOCKS, WRITER_CHANNELS, EDITOR

(* --algorithm Protocol {
variables
  locks_to_editor = <<>>; \* WRITER_LOCKS -> EDITOR, labels: ['submit']
  channels_to_editor = <<>>; \* WRITER_CHANNELS -> EDITOR, labels: ['submit']
  REPORT = "FREE"; \* Lock

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

fair process (WRITER_LOCKS_proc \in {WRITER_LOCKS})
variables msg = "";
{
  WRITER_LOCKS_draft:
    skip; \* domain: research + draft the "locks & mutual exclusion" section
  WRITER_LOCKS_acquire:
    acquire_lock(REPORT);
  WRITER_LOCKS_write:
    skip; \* domain: write the section into the shared report.md (SDK Write/Edit)
  WRITER_LOCKS_release:
    release_lock(REPORT);
  WRITER_LOCKS_submit:
    send(locks_to_editor, "submit");
}

fair process (WRITER_CHANNELS_proc \in {WRITER_CHANNELS})
variables msg = "";
{
  WRITER_CHANNELS_draft:
    skip; \* domain: research + draft the "channels & control/data plane" section
  WRITER_CHANNELS_acquire:
    acquire_lock(REPORT);
  WRITER_CHANNELS_write:
    skip; \* domain: write the section into the shared report.md (SDK Write/Edit)
  WRITER_CHANNELS_release:
    release_lock(REPORT);
  WRITER_CHANNELS_submit:
    send(channels_to_editor, "submit");
}

fair process (EDITOR_proc \in {EDITOR})
variables msg = "";
{
  EDITOR_recv_locks:
    receive(locks_to_editor, msg);
  EDITOR_recv_channels:
    receive(channels_to_editor, msg);
  EDITOR_acquire:
    acquire_lock(REPORT);
  EDITOR_finalize:
    skip; \* domain: add intro + conclusion, integrate both sections (SDK Read/Write)
  EDITOR_release:
    release_lock(REPORT);
}

} *)
\* BEGIN TRANSLATION (chksum(pcal) = "1b1842cd" /\ chksum(tla) = "a1de507d")
\* Process variable msg of process WRITER_LOCKS_proc at line 32 col 11 changed to msg_
\* Process variable msg of process WRITER_CHANNELS_proc at line 47 col 11 changed to msg_W
VARIABLES pc, locks_to_editor, channels_to_editor, REPORT, msg_, msg_W, msg

vars == << pc, locks_to_editor, channels_to_editor, REPORT, msg_, msg_W, msg
        >>

ProcSet == ({WRITER_LOCKS}) \cup ({WRITER_CHANNELS}) \cup ({EDITOR})

Init == (* Global variables *)
        /\ locks_to_editor = <<>>
        /\ channels_to_editor = <<>>
        /\ REPORT = "FREE"
        (* Process WRITER_LOCKS_proc *)
        /\ msg_ = [self \in {WRITER_LOCKS} |-> ""]
        (* Process WRITER_CHANNELS_proc *)
        /\ msg_W = [self \in {WRITER_CHANNELS} |-> ""]
        (* Process EDITOR_proc *)
        /\ msg = [self \in {EDITOR} |-> ""]
        /\ pc = [self \in ProcSet |-> CASE self \in {WRITER_LOCKS} -> "WRITER_LOCKS_draft"
                                        [] self \in {WRITER_CHANNELS} -> "WRITER_CHANNELS_draft"
                                        [] self \in {EDITOR} -> "EDITOR_recv_locks"]

WRITER_LOCKS_draft(self) == /\ pc[self] = "WRITER_LOCKS_draft"
                            /\ TRUE
                            /\ pc' = [pc EXCEPT ![self] = "WRITER_LOCKS_acquire"]
                            /\ UNCHANGED << locks_to_editor, 
                                            channels_to_editor, REPORT, msg_, 
                                            msg_W, msg >>

WRITER_LOCKS_acquire(self) == /\ pc[self] = "WRITER_LOCKS_acquire"
                              /\ REPORT = "FREE"
                              /\ REPORT' = self
                              /\ pc' = [pc EXCEPT ![self] = "WRITER_LOCKS_write"]
                              /\ UNCHANGED << locks_to_editor, 
                                              channels_to_editor, msg_, msg_W, 
                                              msg >>

WRITER_LOCKS_write(self) == /\ pc[self] = "WRITER_LOCKS_write"
                            /\ TRUE
                            /\ pc' = [pc EXCEPT ![self] = "WRITER_LOCKS_release"]
                            /\ UNCHANGED << locks_to_editor, 
                                            channels_to_editor, REPORT, msg_, 
                                            msg_W, msg >>

WRITER_LOCKS_release(self) == /\ pc[self] = "WRITER_LOCKS_release"
                              /\ REPORT' = "FREE"
                              /\ pc' = [pc EXCEPT ![self] = "WRITER_LOCKS_submit"]
                              /\ UNCHANGED << locks_to_editor, 
                                              channels_to_editor, msg_, msg_W, 
                                              msg >>

WRITER_LOCKS_submit(self) == /\ pc[self] = "WRITER_LOCKS_submit"
                             /\ locks_to_editor' = Append(locks_to_editor, "submit")
                             /\ pc' = [pc EXCEPT ![self] = "Done"]
                             /\ UNCHANGED << channels_to_editor, REPORT, msg_, 
                                             msg_W, msg >>

WRITER_LOCKS_proc(self) == WRITER_LOCKS_draft(self)
                              \/ WRITER_LOCKS_acquire(self)
                              \/ WRITER_LOCKS_write(self)
                              \/ WRITER_LOCKS_release(self)
                              \/ WRITER_LOCKS_submit(self)

WRITER_CHANNELS_draft(self) == /\ pc[self] = "WRITER_CHANNELS_draft"
                               /\ TRUE
                               /\ pc' = [pc EXCEPT ![self] = "WRITER_CHANNELS_acquire"]
                               /\ UNCHANGED << locks_to_editor, 
                                               channels_to_editor, REPORT, 
                                               msg_, msg_W, msg >>

WRITER_CHANNELS_acquire(self) == /\ pc[self] = "WRITER_CHANNELS_acquire"
                                 /\ REPORT = "FREE"
                                 /\ REPORT' = self
                                 /\ pc' = [pc EXCEPT ![self] = "WRITER_CHANNELS_write"]
                                 /\ UNCHANGED << locks_to_editor, 
                                                 channels_to_editor, msg_, 
                                                 msg_W, msg >>

WRITER_CHANNELS_write(self) == /\ pc[self] = "WRITER_CHANNELS_write"
                               /\ TRUE
                               /\ pc' = [pc EXCEPT ![self] = "WRITER_CHANNELS_release"]
                               /\ UNCHANGED << locks_to_editor, 
                                               channels_to_editor, REPORT, 
                                               msg_, msg_W, msg >>

WRITER_CHANNELS_release(self) == /\ pc[self] = "WRITER_CHANNELS_release"
                                 /\ REPORT' = "FREE"
                                 /\ pc' = [pc EXCEPT ![self] = "WRITER_CHANNELS_submit"]
                                 /\ UNCHANGED << locks_to_editor, 
                                                 channels_to_editor, msg_, 
                                                 msg_W, msg >>

WRITER_CHANNELS_submit(self) == /\ pc[self] = "WRITER_CHANNELS_submit"
                                /\ channels_to_editor' = Append(channels_to_editor, "submit")
                                /\ pc' = [pc EXCEPT ![self] = "Done"]
                                /\ UNCHANGED << locks_to_editor, REPORT, msg_, 
                                                msg_W, msg >>

WRITER_CHANNELS_proc(self) == WRITER_CHANNELS_draft(self)
                                 \/ WRITER_CHANNELS_acquire(self)
                                 \/ WRITER_CHANNELS_write(self)
                                 \/ WRITER_CHANNELS_release(self)
                                 \/ WRITER_CHANNELS_submit(self)

EDITOR_recv_locks(self) == /\ pc[self] = "EDITOR_recv_locks"
                           /\ Len(locks_to_editor) > 0
                           /\ msg' = [msg EXCEPT ![self] = Head(locks_to_editor)]
                           /\ locks_to_editor' = Tail(locks_to_editor)
                           /\ pc' = [pc EXCEPT ![self] = "EDITOR_recv_channels"]
                           /\ UNCHANGED << channels_to_editor, REPORT, msg_, 
                                           msg_W >>

EDITOR_recv_channels(self) == /\ pc[self] = "EDITOR_recv_channels"
                              /\ Len(channels_to_editor) > 0
                              /\ msg' = [msg EXCEPT ![self] = Head(channels_to_editor)]
                              /\ channels_to_editor' = Tail(channels_to_editor)
                              /\ pc' = [pc EXCEPT ![self] = "EDITOR_acquire"]
                              /\ UNCHANGED << locks_to_editor, REPORT, msg_, 
                                              msg_W >>

EDITOR_acquire(self) == /\ pc[self] = "EDITOR_acquire"
                        /\ REPORT = "FREE"
                        /\ REPORT' = self
                        /\ pc' = [pc EXCEPT ![self] = "EDITOR_finalize"]
                        /\ UNCHANGED << locks_to_editor, channels_to_editor, 
                                        msg_, msg_W, msg >>

EDITOR_finalize(self) == /\ pc[self] = "EDITOR_finalize"
                         /\ TRUE
                         /\ pc' = [pc EXCEPT ![self] = "EDITOR_release"]
                         /\ UNCHANGED << locks_to_editor, channels_to_editor, 
                                         REPORT, msg_, msg_W, msg >>

EDITOR_release(self) == /\ pc[self] = "EDITOR_release"
                        /\ REPORT' = "FREE"
                        /\ pc' = [pc EXCEPT ![self] = "Done"]
                        /\ UNCHANGED << locks_to_editor, channels_to_editor, 
                                        msg_, msg_W, msg >>

EDITOR_proc(self) == EDITOR_recv_locks(self) \/ EDITOR_recv_channels(self)
                        \/ EDITOR_acquire(self) \/ EDITOR_finalize(self)
                        \/ EDITOR_release(self)

(* Allow infinite stuttering to prevent deadlock on termination. *)
Terminating == /\ \A self \in ProcSet: pc[self] = "Done"
               /\ UNCHANGED vars

Next == (\E self \in {WRITER_LOCKS}: WRITER_LOCKS_proc(self))
           \/ (\E self \in {WRITER_CHANNELS}: WRITER_CHANNELS_proc(self))
           \/ (\E self \in {EDITOR}: EDITOR_proc(self))
           \/ Terminating

Spec == /\ Init /\ [][Next]_vars
        /\ \A self \in {WRITER_LOCKS} : WF_vars(WRITER_LOCKS_proc(self))
        /\ \A self \in {WRITER_CHANNELS} : WF_vars(WRITER_CHANNELS_proc(self))
        /\ \A self \in {EDITOR} : WF_vars(EDITOR_proc(self))

Termination == <>(\A self \in ProcSet: pc[self] = "Done")

\* END TRANSLATION 

AllDone == \A p \in {WRITER_LOCKS, WRITER_CHANNELS, EDITOR}: pc[p] = "Done"

TypeInvariant ==
  /\ \A p \in {WRITER_LOCKS, WRITER_CHANNELS, EDITOR}: pc[p] \in STRING
  /\ REPORT \in {WRITER_LOCKS, WRITER_CHANNELS, EDITOR, "FREE"}
  /\ locks_to_editor \in Seq(STRING)
  /\ channels_to_editor \in Seq(STRING)

NoOrphanLocks ==
  AllDone => (REPORT = "FREE")

ChannelsDrained ==
  AllDone => (Len(locks_to_editor) = 0 /\ Len(channels_to_editor) = 0)

ChannelBound ==
  Len(locks_to_editor) <= 3 /\ Len(channels_to_editor) <= 3

====
