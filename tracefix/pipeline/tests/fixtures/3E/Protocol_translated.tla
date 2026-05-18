---- MODULE Protocol ----
EXTENDS Integers, Sequences, TLC

CONSTANTS ResearcherA, ResearcherB, Editor

(* --algorithm Protocol {
variables
  resA_to_editor = <<>>; \* researcherA -> editor, labels: ['submit']
  resB_to_editor = <<>>; \* researcherB -> editor, labels: ['submit']
  editor_to_resA = <<>>; \* editor -> researcherA, labels: ['revise', 'accept']
  editor_to_resB = <<>>; \* editor -> researcherB, labels: ['revise', 'accept']
  doc_lock = "FREE"; \* Lock
  ref_lock = "FREE"; \* Lock

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

fair process (researcherA_proc \in {ResearcherA})
variables msg = "";
{
  ra_write:
    acquire_lock(doc_lock);
  ra_release_doc:
    release_lock(doc_lock);
  ra_ref:
    acquire_lock(ref_lock);
  ra_release_ref:
    release_lock(ref_lock);
    send(resA_to_editor, "submit");
  ra_wait:
    receive(editor_to_resA, msg);
  ra_check:
    if (msg = "accept") {
      goto ra_done;
    } else {
      goto ra_write;
    };
  ra_done:
    skip;
}

fair process (researcherB_proc \in {ResearcherB})
variables msg = "";
{
  rb_write:
    acquire_lock(doc_lock);
  rb_release_doc:
    release_lock(doc_lock);
  rb_ref:
    acquire_lock(ref_lock);
  rb_release_ref:
    release_lock(ref_lock);
    send(resB_to_editor, "submit");
  rb_wait:
    receive(editor_to_resB, msg);
  rb_check:
    if (msg = "accept") {
      goto rb_done;
    } else {
      goto rb_write;
    };
  rb_done:
    skip;
}

fair process (editor_proc \in {Editor})
variables msg = "", gotA = FALSE, gotB = FALSE;
{
  e_collect:
    while (~gotA \/ ~gotB) {
      e_recv:
        either {
          receive(resA_to_editor, msg);
          gotA := TRUE;
        } or {
          receive(resB_to_editor, msg);
          gotB := TRUE;
        };
    };

  e_review:
    acquire_lock(doc_lock);
  e_decide:
    either {
      \* both sections consistent - accept
      release_lock(doc_lock);
      send(editor_to_resA, "accept");
      send(editor_to_resB, "accept");
    } or {
      \* researcher A needs revision
      release_lock(doc_lock);
      send(editor_to_resA, "revise");
      send(editor_to_resB, "accept");
    e_rewaitA:
      receive(resA_to_editor, msg);
    e_rerev_a:
      acquire_lock(doc_lock);
    e_refin_a:
      release_lock(doc_lock);
      send(editor_to_resA, "accept");
    } or {
      \* researcher B needs revision
      release_lock(doc_lock);
      send(editor_to_resB, "revise");
      send(editor_to_resA, "accept");
    e_rewaitB:
      receive(resB_to_editor, msg);
    e_rerev_b:
      acquire_lock(doc_lock);
    e_refin_b:
      release_lock(doc_lock);
      send(editor_to_resB, "accept");
    } or {
      \* both need revision
      release_lock(doc_lock);
      send(editor_to_resA, "revise");
      send(editor_to_resB, "revise");
      gotA := FALSE;
      gotB := FALSE;
      goto e_collect;
    };
  e_done:
    skip;
}

} *)
\* BEGIN TRANSLATION (chksum(pcal) = "35d8c87a" /\ chksum(tla) = "4de6fb9d")
\* Process variable msg of process researcherA_proc at line 35 col 11 changed to msg_
\* Process variable msg of process researcherB_proc at line 59 col 11 changed to msg_r
VARIABLES pc, resA_to_editor, resB_to_editor, editor_to_resA, editor_to_resB, 
          doc_lock, ref_lock, msg_, msg_r, msg, gotA, gotB

vars == << pc, resA_to_editor, resB_to_editor, editor_to_resA, editor_to_resB, 
           doc_lock, ref_lock, msg_, msg_r, msg, gotA, gotB >>

ProcSet == ({ResearcherA}) \cup ({ResearcherB}) \cup ({Editor})

Init == (* Global variables *)
        /\ resA_to_editor = <<>>
        /\ resB_to_editor = <<>>
        /\ editor_to_resA = <<>>
        /\ editor_to_resB = <<>>
        /\ doc_lock = "FREE"
        /\ ref_lock = "FREE"
        (* Process researcherA_proc *)
        /\ msg_ = [self \in {ResearcherA} |-> ""]
        (* Process researcherB_proc *)
        /\ msg_r = [self \in {ResearcherB} |-> ""]
        (* Process editor_proc *)
        /\ msg = [self \in {Editor} |-> ""]
        /\ gotA = [self \in {Editor} |-> FALSE]
        /\ gotB = [self \in {Editor} |-> FALSE]
        /\ pc = [self \in ProcSet |-> CASE self \in {ResearcherA} -> "ra_write"
                                        [] self \in {ResearcherB} -> "rb_write"
                                        [] self \in {Editor} -> "e_collect"]

ra_write(self) == /\ pc[self] = "ra_write"
                  /\ doc_lock = "FREE"
                  /\ doc_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "ra_release_doc"]
                  /\ UNCHANGED << resA_to_editor, resB_to_editor, 
                                  editor_to_resA, editor_to_resB, ref_lock, 
                                  msg_, msg_r, msg, gotA, gotB >>

ra_release_doc(self) == /\ pc[self] = "ra_release_doc"
                        /\ doc_lock' = "FREE"
                        /\ pc' = [pc EXCEPT ![self] = "ra_ref"]
                        /\ UNCHANGED << resA_to_editor, resB_to_editor, 
                                        editor_to_resA, editor_to_resB, 
                                        ref_lock, msg_, msg_r, msg, gotA, gotB >>

ra_ref(self) == /\ pc[self] = "ra_ref"
                /\ ref_lock = "FREE"
                /\ ref_lock' = self
                /\ pc' = [pc EXCEPT ![self] = "ra_release_ref"]
                /\ UNCHANGED << resA_to_editor, resB_to_editor, editor_to_resA, 
                                editor_to_resB, doc_lock, msg_, msg_r, msg, 
                                gotA, gotB >>

ra_release_ref(self) == /\ pc[self] = "ra_release_ref"
                        /\ ref_lock' = "FREE"
                        /\ resA_to_editor' = Append(resA_to_editor, "submit")
                        /\ pc' = [pc EXCEPT ![self] = "ra_wait"]
                        /\ UNCHANGED << resB_to_editor, editor_to_resA, 
                                        editor_to_resB, doc_lock, msg_, msg_r, 
                                        msg, gotA, gotB >>

ra_wait(self) == /\ pc[self] = "ra_wait"
                 /\ Len(editor_to_resA) > 0
                 /\ msg_' = [msg_ EXCEPT ![self] = Head(editor_to_resA)]
                 /\ editor_to_resA' = Tail(editor_to_resA)
                 /\ pc' = [pc EXCEPT ![self] = "ra_check"]
                 /\ UNCHANGED << resA_to_editor, resB_to_editor, 
                                 editor_to_resB, doc_lock, ref_lock, msg_r, 
                                 msg, gotA, gotB >>

ra_check(self) == /\ pc[self] = "ra_check"
                  /\ IF msg_[self] = "accept"
                        THEN /\ pc' = [pc EXCEPT ![self] = "ra_done"]
                        ELSE /\ pc' = [pc EXCEPT ![self] = "ra_write"]
                  /\ UNCHANGED << resA_to_editor, resB_to_editor, 
                                  editor_to_resA, editor_to_resB, doc_lock, 
                                  ref_lock, msg_, msg_r, msg, gotA, gotB >>

ra_done(self) == /\ pc[self] = "ra_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << resA_to_editor, resB_to_editor, 
                                 editor_to_resA, editor_to_resB, doc_lock, 
                                 ref_lock, msg_, msg_r, msg, gotA, gotB >>

researcherA_proc(self) == ra_write(self) \/ ra_release_doc(self)
                             \/ ra_ref(self) \/ ra_release_ref(self)
                             \/ ra_wait(self) \/ ra_check(self)
                             \/ ra_done(self)

rb_write(self) == /\ pc[self] = "rb_write"
                  /\ doc_lock = "FREE"
                  /\ doc_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "rb_release_doc"]
                  /\ UNCHANGED << resA_to_editor, resB_to_editor, 
                                  editor_to_resA, editor_to_resB, ref_lock, 
                                  msg_, msg_r, msg, gotA, gotB >>

rb_release_doc(self) == /\ pc[self] = "rb_release_doc"
                        /\ doc_lock' = "FREE"
                        /\ pc' = [pc EXCEPT ![self] = "rb_ref"]
                        /\ UNCHANGED << resA_to_editor, resB_to_editor, 
                                        editor_to_resA, editor_to_resB, 
                                        ref_lock, msg_, msg_r, msg, gotA, gotB >>

rb_ref(self) == /\ pc[self] = "rb_ref"
                /\ ref_lock = "FREE"
                /\ ref_lock' = self
                /\ pc' = [pc EXCEPT ![self] = "rb_release_ref"]
                /\ UNCHANGED << resA_to_editor, resB_to_editor, editor_to_resA, 
                                editor_to_resB, doc_lock, msg_, msg_r, msg, 
                                gotA, gotB >>

rb_release_ref(self) == /\ pc[self] = "rb_release_ref"
                        /\ ref_lock' = "FREE"
                        /\ resB_to_editor' = Append(resB_to_editor, "submit")
                        /\ pc' = [pc EXCEPT ![self] = "rb_wait"]
                        /\ UNCHANGED << resA_to_editor, editor_to_resA, 
                                        editor_to_resB, doc_lock, msg_, msg_r, 
                                        msg, gotA, gotB >>

rb_wait(self) == /\ pc[self] = "rb_wait"
                 /\ Len(editor_to_resB) > 0
                 /\ msg_r' = [msg_r EXCEPT ![self] = Head(editor_to_resB)]
                 /\ editor_to_resB' = Tail(editor_to_resB)
                 /\ pc' = [pc EXCEPT ![self] = "rb_check"]
                 /\ UNCHANGED << resA_to_editor, resB_to_editor, 
                                 editor_to_resA, doc_lock, ref_lock, msg_, msg, 
                                 gotA, gotB >>

rb_check(self) == /\ pc[self] = "rb_check"
                  /\ IF msg_r[self] = "accept"
                        THEN /\ pc' = [pc EXCEPT ![self] = "rb_done"]
                        ELSE /\ pc' = [pc EXCEPT ![self] = "rb_write"]
                  /\ UNCHANGED << resA_to_editor, resB_to_editor, 
                                  editor_to_resA, editor_to_resB, doc_lock, 
                                  ref_lock, msg_, msg_r, msg, gotA, gotB >>

rb_done(self) == /\ pc[self] = "rb_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << resA_to_editor, resB_to_editor, 
                                 editor_to_resA, editor_to_resB, doc_lock, 
                                 ref_lock, msg_, msg_r, msg, gotA, gotB >>

researcherB_proc(self) == rb_write(self) \/ rb_release_doc(self)
                             \/ rb_ref(self) \/ rb_release_ref(self)
                             \/ rb_wait(self) \/ rb_check(self)
                             \/ rb_done(self)

e_collect(self) == /\ pc[self] = "e_collect"
                   /\ IF ~gotA[self] \/ ~gotB[self]
                         THEN /\ pc' = [pc EXCEPT ![self] = "e_recv"]
                         ELSE /\ pc' = [pc EXCEPT ![self] = "e_review"]
                   /\ UNCHANGED << resA_to_editor, resB_to_editor, 
                                   editor_to_resA, editor_to_resB, doc_lock, 
                                   ref_lock, msg_, msg_r, msg, gotA, gotB >>

e_recv(self) == /\ pc[self] = "e_recv"
                /\ \/ /\ Len(resA_to_editor) > 0
                      /\ msg' = [msg EXCEPT ![self] = Head(resA_to_editor)]
                      /\ resA_to_editor' = Tail(resA_to_editor)
                      /\ gotA' = [gotA EXCEPT ![self] = TRUE]
                      /\ UNCHANGED <<resB_to_editor, gotB>>
                   \/ /\ Len(resB_to_editor) > 0
                      /\ msg' = [msg EXCEPT ![self] = Head(resB_to_editor)]
                      /\ resB_to_editor' = Tail(resB_to_editor)
                      /\ gotB' = [gotB EXCEPT ![self] = TRUE]
                      /\ UNCHANGED <<resA_to_editor, gotA>>
                /\ pc' = [pc EXCEPT ![self] = "e_collect"]
                /\ UNCHANGED << editor_to_resA, editor_to_resB, doc_lock, 
                                ref_lock, msg_, msg_r >>

e_review(self) == /\ pc[self] = "e_review"
                  /\ doc_lock = "FREE"
                  /\ doc_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "e_decide"]
                  /\ UNCHANGED << resA_to_editor, resB_to_editor, 
                                  editor_to_resA, editor_to_resB, ref_lock, 
                                  msg_, msg_r, msg, gotA, gotB >>

e_decide(self) == /\ pc[self] = "e_decide"
                  /\ \/ /\ doc_lock' = "FREE"
                        /\ editor_to_resA' = Append(editor_to_resA, "accept")
                        /\ editor_to_resB' = Append(editor_to_resB, "accept")
                        /\ pc' = [pc EXCEPT ![self] = "e_done"]
                        /\ UNCHANGED <<gotA, gotB>>
                     \/ /\ doc_lock' = "FREE"
                        /\ editor_to_resA' = Append(editor_to_resA, "revise")
                        /\ editor_to_resB' = Append(editor_to_resB, "accept")
                        /\ pc' = [pc EXCEPT ![self] = "e_rewaitA"]
                        /\ UNCHANGED <<gotA, gotB>>
                     \/ /\ doc_lock' = "FREE"
                        /\ editor_to_resB' = Append(editor_to_resB, "revise")
                        /\ editor_to_resA' = Append(editor_to_resA, "accept")
                        /\ pc' = [pc EXCEPT ![self] = "e_rewaitB"]
                        /\ UNCHANGED <<gotA, gotB>>
                     \/ /\ doc_lock' = "FREE"
                        /\ editor_to_resA' = Append(editor_to_resA, "revise")
                        /\ editor_to_resB' = Append(editor_to_resB, "revise")
                        /\ gotA' = [gotA EXCEPT ![self] = FALSE]
                        /\ gotB' = [gotB EXCEPT ![self] = FALSE]
                        /\ pc' = [pc EXCEPT ![self] = "e_collect"]
                  /\ UNCHANGED << resA_to_editor, resB_to_editor, ref_lock, 
                                  msg_, msg_r, msg >>

e_rewaitA(self) == /\ pc[self] = "e_rewaitA"
                   /\ Len(resA_to_editor) > 0
                   /\ msg' = [msg EXCEPT ![self] = Head(resA_to_editor)]
                   /\ resA_to_editor' = Tail(resA_to_editor)
                   /\ pc' = [pc EXCEPT ![self] = "e_rerev_a"]
                   /\ UNCHANGED << resB_to_editor, editor_to_resA, 
                                   editor_to_resB, doc_lock, ref_lock, msg_, 
                                   msg_r, gotA, gotB >>

e_rerev_a(self) == /\ pc[self] = "e_rerev_a"
                   /\ doc_lock = "FREE"
                   /\ doc_lock' = self
                   /\ pc' = [pc EXCEPT ![self] = "e_refin_a"]
                   /\ UNCHANGED << resA_to_editor, resB_to_editor, 
                                   editor_to_resA, editor_to_resB, ref_lock, 
                                   msg_, msg_r, msg, gotA, gotB >>

e_refin_a(self) == /\ pc[self] = "e_refin_a"
                   /\ doc_lock' = "FREE"
                   /\ editor_to_resA' = Append(editor_to_resA, "accept")
                   /\ pc' = [pc EXCEPT ![self] = "e_done"]
                   /\ UNCHANGED << resA_to_editor, resB_to_editor, 
                                   editor_to_resB, ref_lock, msg_, msg_r, msg, 
                                   gotA, gotB >>

e_rewaitB(self) == /\ pc[self] = "e_rewaitB"
                   /\ Len(resB_to_editor) > 0
                   /\ msg' = [msg EXCEPT ![self] = Head(resB_to_editor)]
                   /\ resB_to_editor' = Tail(resB_to_editor)
                   /\ pc' = [pc EXCEPT ![self] = "e_rerev_b"]
                   /\ UNCHANGED << resA_to_editor, editor_to_resA, 
                                   editor_to_resB, doc_lock, ref_lock, msg_, 
                                   msg_r, gotA, gotB >>

e_rerev_b(self) == /\ pc[self] = "e_rerev_b"
                   /\ doc_lock = "FREE"
                   /\ doc_lock' = self
                   /\ pc' = [pc EXCEPT ![self] = "e_refin_b"]
                   /\ UNCHANGED << resA_to_editor, resB_to_editor, 
                                   editor_to_resA, editor_to_resB, ref_lock, 
                                   msg_, msg_r, msg, gotA, gotB >>

e_refin_b(self) == /\ pc[self] = "e_refin_b"
                   /\ doc_lock' = "FREE"
                   /\ editor_to_resB' = Append(editor_to_resB, "accept")
                   /\ pc' = [pc EXCEPT ![self] = "e_done"]
                   /\ UNCHANGED << resA_to_editor, resB_to_editor, 
                                   editor_to_resA, ref_lock, msg_, msg_r, msg, 
                                   gotA, gotB >>

e_done(self) == /\ pc[self] = "e_done"
                /\ TRUE
                /\ pc' = [pc EXCEPT ![self] = "Done"]
                /\ UNCHANGED << resA_to_editor, resB_to_editor, editor_to_resA, 
                                editor_to_resB, doc_lock, ref_lock, msg_, 
                                msg_r, msg, gotA, gotB >>

editor_proc(self) == e_collect(self) \/ e_recv(self) \/ e_review(self)
                        \/ e_decide(self) \/ e_rewaitA(self)
                        \/ e_rerev_a(self) \/ e_refin_a(self)
                        \/ e_rewaitB(self) \/ e_rerev_b(self)
                        \/ e_refin_b(self) \/ e_done(self)

(* Allow infinite stuttering to prevent deadlock on termination. *)
Terminating == /\ \A self \in ProcSet: pc[self] = "Done"
               /\ UNCHANGED vars

Next == (\E self \in {ResearcherA}: researcherA_proc(self))
           \/ (\E self \in {ResearcherB}: researcherB_proc(self))
           \/ (\E self \in {Editor}: editor_proc(self))
           \/ Terminating

Spec == /\ Init /\ [][Next]_vars
        /\ \A self \in {ResearcherA} : WF_vars(researcherA_proc(self))
        /\ \A self \in {ResearcherB} : WF_vars(researcherB_proc(self))
        /\ \A self \in {Editor} : WF_vars(editor_proc(self))

Termination == <>(\A self \in ProcSet: pc[self] = "Done")

\* END TRANSLATION 

AllDone == \A p \in {ResearcherA, ResearcherB, Editor}: pc[p] = "Done"

TypeInvariant ==
  /\ \A p \in {ResearcherA, ResearcherB, Editor}: pc[p] \in STRING
  /\ doc_lock \in {ResearcherA, ResearcherB, Editor, "FREE"}
  /\ ref_lock \in {ResearcherA, ResearcherB, Editor, "FREE"}
  /\ resA_to_editor \in Seq(STRING)
  /\ resB_to_editor \in Seq(STRING)
  /\ editor_to_resA \in Seq(STRING)
  /\ editor_to_resB \in Seq(STRING)

NoOrphanLocks ==
  AllDone => (doc_lock = "FREE" /\ ref_lock = "FREE")

ChannelsDrained ==
  AllDone => (Len(resA_to_editor) = 0 /\ Len(resB_to_editor) = 0 /\ Len(editor_to_resA) = 0 /\ Len(editor_to_resB) = 0)

ChannelBound ==
  Len(resA_to_editor) <= 3 /\ Len(resB_to_editor) <= 3 /\ Len(editor_to_resA) <= 3 /\ Len(editor_to_resB) <= 3

====
