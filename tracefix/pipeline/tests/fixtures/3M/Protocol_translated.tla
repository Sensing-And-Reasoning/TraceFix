---- MODULE Protocol ----
EXTENDS Integers, Sequences, TLC

CONSTANTS ResearcherA, ResearcherB, ResearcherC, Factchecker, Editor

(* --algorithm Protocol {
variables
  resA_to_fc = <<>>; \* researcherA -> factchecker, labels: ['submit']
  resB_to_fc = <<>>; \* researcherB -> factchecker, labels: ['submit']
  resC_to_fc = <<>>; \* researcherC -> factchecker, labels: ['submit']
  fc_to_resA = <<>>; \* factchecker -> researcherA, labels: ['pass', 'flag']
  fc_to_resB = <<>>; \* factchecker -> researcherB, labels: ['pass', 'flag']
  fc_to_resC = <<>>; \* factchecker -> researcherC, labels: ['pass', 'flag']
  fc_to_editor = <<>>; \* factchecker -> editor, labels: ['passedA', 'passedB', 'passedC']
  editor_to_resA = <<>>; \* editor -> researcherA, labels: ['accept', 'revise']
  editor_to_resB = <<>>; \* editor -> researcherB, labels: ['accept', 'revise']
  editor_to_resC = <<>>; \* editor -> researcherC, labels: ['accept', 'revise']
  resA_to_editor = <<>>; \* researcherA -> editor, labels: ['resubmit']
  resB_to_editor = <<>>; \* researcherB -> editor, labels: ['resubmit']
  resC_to_editor = <<>>; \* researcherC -> editor, labels: ['resubmit']
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
  ra_rel_doc:
    release_lock(doc_lock);
  ra_ref:
    acquire_lock(ref_lock);
  ra_rel_ref:
    release_lock(ref_lock);
    send(resA_to_fc, "submit");
  ra_wait_fc:
    receive(fc_to_resA, msg);
  ra_check_fc:
    if (msg = "flag") {
      goto ra_write;
    };
  \* passed fact check, wait for editor
  ra_wait_ed:
    receive(editor_to_resA, msg);
  ra_check_ed:
    if (msg = "accept") {
      goto ra_done;
    };
  \* revise for consistency
  ra_revise:
    acquire_lock(doc_lock);
  ra_rev_rel:
    release_lock(doc_lock);
    send(resA_to_editor, "resubmit");
  ra_wait_ed2:
    receive(editor_to_resA, msg);
  ra_done:
    skip;
}

fair process (researcherB_proc \in {ResearcherB})
variables msg = "";
{
  rb_write:
    acquire_lock(doc_lock);
  rb_rel_doc:
    release_lock(doc_lock);
  rb_ref:
    acquire_lock(ref_lock);
  rb_rel_ref:
    release_lock(ref_lock);
    send(resB_to_fc, "submit");
  rb_wait_fc:
    receive(fc_to_resB, msg);
  rb_check_fc:
    if (msg = "flag") {
      goto rb_write;
    };
  rb_wait_ed:
    receive(editor_to_resB, msg);
  rb_check_ed:
    if (msg = "accept") {
      goto rb_done;
    };
  rb_revise:
    acquire_lock(doc_lock);
  rb_rev_rel:
    release_lock(doc_lock);
    send(resB_to_editor, "resubmit");
  rb_wait_ed2:
    receive(editor_to_resB, msg);
  rb_done:
    skip;
}

fair process (researcherC_proc \in {ResearcherC})
variables msg = "";
{
  rc_write:
    acquire_lock(doc_lock);
  rc_rel_doc:
    release_lock(doc_lock);
  rc_ref:
    acquire_lock(ref_lock);
  rc_rel_ref:
    release_lock(ref_lock);
    send(resC_to_fc, "submit");
  rc_wait_fc:
    receive(fc_to_resC, msg);
  rc_check_fc:
    if (msg = "flag") {
      goto rc_write;
    };
  rc_wait_ed:
    receive(editor_to_resC, msg);
  rc_check_ed:
    if (msg = "accept") {
      goto rc_done;
    };
  rc_revise:
    acquire_lock(doc_lock);
  rc_rev_rel:
    release_lock(doc_lock);
    send(resC_to_editor, "resubmit");
  rc_wait_ed2:
    receive(editor_to_resC, msg);
  rc_done:
    skip;
}

fair process (factchecker_proc \in {Factchecker})
variables msg = "", doneA = FALSE, doneB = FALSE, doneC = FALSE;
{
  fc_loop:
    while (~doneA \/ ~doneB \/ ~doneC) {
      fc_recv:
        either {
          receive(resA_to_fc, msg);
        fc_checkA:
          either {
            send(fc_to_resA, "pass");
            send(fc_to_editor, "passedA");
            doneA := TRUE;
          } or {
            send(fc_to_resA, "flag");
          };
        } or {
          receive(resB_to_fc, msg);
        fc_checkB:
          either {
            send(fc_to_resB, "pass");
            send(fc_to_editor, "passedB");
            doneB := TRUE;
          } or {
            send(fc_to_resB, "flag");
          };
        } or {
          receive(resC_to_fc, msg);
        fc_checkC:
          either {
            send(fc_to_resC, "pass");
            send(fc_to_editor, "passedC");
            doneC := TRUE;
          } or {
            send(fc_to_resC, "flag");
          };
        };
    };
  fc_done:
    skip;
}

fair process (editor_proc \in {Editor})
variables msg = "", gotA = FALSE, gotB = FALSE, gotC = FALSE;
{
  \* collect all 3 passed notifications from fact checker
  ed_collect:
    while (~gotA \/ ~gotB \/ ~gotC) {
      ed_recv:
        receive(fc_to_editor, msg);
      ed_dispatch:
        if (msg = "passedA") {
          gotA := TRUE;
        } else if (msg = "passedB") {
          gotB := TRUE;
        } else {
          gotC := TRUE;
        };
    };

  \* review with doc lock
  ed_review:
    acquire_lock(doc_lock);
  ed_decide:
    either {
      \* all consistent - accept all
      release_lock(doc_lock);
      send(editor_to_resA, "accept");
      send(editor_to_resB, "accept");
      send(editor_to_resC, "accept");
    } or {
      \* cross-section inconsistencies - revise all
      release_lock(doc_lock);
      send(editor_to_resA, "revise");
      send(editor_to_resB, "revise");
      send(editor_to_resC, "revise");
    ed_wait_resub_a:
      receive(resA_to_editor, msg);
    ed_wait_resub_b:
      receive(resB_to_editor, msg);
    ed_wait_resub_c:
      receive(resC_to_editor, msg);
    ed_finalize:
      acquire_lock(doc_lock);
    ed_fin_rel:
      release_lock(doc_lock);
      send(editor_to_resA, "accept");
      send(editor_to_resB, "accept");
      send(editor_to_resC, "accept");
    };
  ed_done:
    skip;
}

} *)
\* BEGIN TRANSLATION (chksum(pcal) = "b2daf4d6" /\ chksum(tla) = "1c632b81")
\* Process variable msg of process researcherA_proc at line 44 col 11 changed to msg_
\* Process variable msg of process researcherB_proc at line 81 col 11 changed to msg_r
\* Process variable msg of process researcherC_proc at line 116 col 11 changed to msg_re
\* Process variable msg of process factchecker_proc at line 151 col 11 changed to msg_f
VARIABLES pc, resA_to_fc, resB_to_fc, resC_to_fc, fc_to_resA, fc_to_resB, 
          fc_to_resC, fc_to_editor, editor_to_resA, editor_to_resB, 
          editor_to_resC, resA_to_editor, resB_to_editor, resC_to_editor, 
          doc_lock, ref_lock, msg_, msg_r, msg_re, msg_f, doneA, doneB, doneC, 
          msg, gotA, gotB, gotC

vars == << pc, resA_to_fc, resB_to_fc, resC_to_fc, fc_to_resA, fc_to_resB, 
           fc_to_resC, fc_to_editor, editor_to_resA, editor_to_resB, 
           editor_to_resC, resA_to_editor, resB_to_editor, resC_to_editor, 
           doc_lock, ref_lock, msg_, msg_r, msg_re, msg_f, doneA, doneB, 
           doneC, msg, gotA, gotB, gotC >>

ProcSet == ({ResearcherA}) \cup ({ResearcherB}) \cup ({ResearcherC}) \cup ({Factchecker}) \cup ({Editor})

Init == (* Global variables *)
        /\ resA_to_fc = <<>>
        /\ resB_to_fc = <<>>
        /\ resC_to_fc = <<>>
        /\ fc_to_resA = <<>>
        /\ fc_to_resB = <<>>
        /\ fc_to_resC = <<>>
        /\ fc_to_editor = <<>>
        /\ editor_to_resA = <<>>
        /\ editor_to_resB = <<>>
        /\ editor_to_resC = <<>>
        /\ resA_to_editor = <<>>
        /\ resB_to_editor = <<>>
        /\ resC_to_editor = <<>>
        /\ doc_lock = "FREE"
        /\ ref_lock = "FREE"
        (* Process researcherA_proc *)
        /\ msg_ = [self \in {ResearcherA} |-> ""]
        (* Process researcherB_proc *)
        /\ msg_r = [self \in {ResearcherB} |-> ""]
        (* Process researcherC_proc *)
        /\ msg_re = [self \in {ResearcherC} |-> ""]
        (* Process factchecker_proc *)
        /\ msg_f = [self \in {Factchecker} |-> ""]
        /\ doneA = [self \in {Factchecker} |-> FALSE]
        /\ doneB = [self \in {Factchecker} |-> FALSE]
        /\ doneC = [self \in {Factchecker} |-> FALSE]
        (* Process editor_proc *)
        /\ msg = [self \in {Editor} |-> ""]
        /\ gotA = [self \in {Editor} |-> FALSE]
        /\ gotB = [self \in {Editor} |-> FALSE]
        /\ gotC = [self \in {Editor} |-> FALSE]
        /\ pc = [self \in ProcSet |-> CASE self \in {ResearcherA} -> "ra_write"
                                        [] self \in {ResearcherB} -> "rb_write"
                                        [] self \in {ResearcherC} -> "rc_write"
                                        [] self \in {Factchecker} -> "fc_loop"
                                        [] self \in {Editor} -> "ed_collect"]

ra_write(self) == /\ pc[self] = "ra_write"
                  /\ doc_lock = "FREE"
                  /\ doc_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "ra_rel_doc"]
                  /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                  fc_to_resA, fc_to_resB, fc_to_resC, 
                                  fc_to_editor, editor_to_resA, editor_to_resB, 
                                  editor_to_resC, resA_to_editor, 
                                  resB_to_editor, resC_to_editor, ref_lock, 
                                  msg_, msg_r, msg_re, msg_f, doneA, doneB, 
                                  doneC, msg, gotA, gotB, gotC >>

ra_rel_doc(self) == /\ pc[self] = "ra_rel_doc"
                    /\ doc_lock' = "FREE"
                    /\ pc' = [pc EXCEPT ![self] = "ra_ref"]
                    /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                    fc_to_resA, fc_to_resB, fc_to_resC, 
                                    fc_to_editor, editor_to_resA, 
                                    editor_to_resB, editor_to_resC, 
                                    resA_to_editor, resB_to_editor, 
                                    resC_to_editor, ref_lock, msg_, msg_r, 
                                    msg_re, msg_f, doneA, doneB, doneC, msg, 
                                    gotA, gotB, gotC >>

ra_ref(self) == /\ pc[self] = "ra_ref"
                /\ ref_lock = "FREE"
                /\ ref_lock' = self
                /\ pc' = [pc EXCEPT ![self] = "ra_rel_ref"]
                /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, fc_to_resA, 
                                fc_to_resB, fc_to_resC, fc_to_editor, 
                                editor_to_resA, editor_to_resB, editor_to_resC, 
                                resA_to_editor, resB_to_editor, resC_to_editor, 
                                doc_lock, msg_, msg_r, msg_re, msg_f, doneA, 
                                doneB, doneC, msg, gotA, gotB, gotC >>

ra_rel_ref(self) == /\ pc[self] = "ra_rel_ref"
                    /\ ref_lock' = "FREE"
                    /\ resA_to_fc' = Append(resA_to_fc, "submit")
                    /\ pc' = [pc EXCEPT ![self] = "ra_wait_fc"]
                    /\ UNCHANGED << resB_to_fc, resC_to_fc, fc_to_resA, 
                                    fc_to_resB, fc_to_resC, fc_to_editor, 
                                    editor_to_resA, editor_to_resB, 
                                    editor_to_resC, resA_to_editor, 
                                    resB_to_editor, resC_to_editor, doc_lock, 
                                    msg_, msg_r, msg_re, msg_f, doneA, doneB, 
                                    doneC, msg, gotA, gotB, gotC >>

ra_wait_fc(self) == /\ pc[self] = "ra_wait_fc"
                    /\ Len(fc_to_resA) > 0
                    /\ msg_' = [msg_ EXCEPT ![self] = Head(fc_to_resA)]
                    /\ fc_to_resA' = Tail(fc_to_resA)
                    /\ pc' = [pc EXCEPT ![self] = "ra_check_fc"]
                    /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                    fc_to_resB, fc_to_resC, fc_to_editor, 
                                    editor_to_resA, editor_to_resB, 
                                    editor_to_resC, resA_to_editor, 
                                    resB_to_editor, resC_to_editor, doc_lock, 
                                    ref_lock, msg_r, msg_re, msg_f, doneA, 
                                    doneB, doneC, msg, gotA, gotB, gotC >>

ra_check_fc(self) == /\ pc[self] = "ra_check_fc"
                     /\ IF msg_[self] = "flag"
                           THEN /\ pc' = [pc EXCEPT ![self] = "ra_write"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "ra_wait_ed"]
                     /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                     fc_to_resA, fc_to_resB, fc_to_resC, 
                                     fc_to_editor, editor_to_resA, 
                                     editor_to_resB, editor_to_resC, 
                                     resA_to_editor, resB_to_editor, 
                                     resC_to_editor, doc_lock, ref_lock, msg_, 
                                     msg_r, msg_re, msg_f, doneA, doneB, doneC, 
                                     msg, gotA, gotB, gotC >>

ra_wait_ed(self) == /\ pc[self] = "ra_wait_ed"
                    /\ Len(editor_to_resA) > 0
                    /\ msg_' = [msg_ EXCEPT ![self] = Head(editor_to_resA)]
                    /\ editor_to_resA' = Tail(editor_to_resA)
                    /\ pc' = [pc EXCEPT ![self] = "ra_check_ed"]
                    /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                    fc_to_resA, fc_to_resB, fc_to_resC, 
                                    fc_to_editor, editor_to_resB, 
                                    editor_to_resC, resA_to_editor, 
                                    resB_to_editor, resC_to_editor, doc_lock, 
                                    ref_lock, msg_r, msg_re, msg_f, doneA, 
                                    doneB, doneC, msg, gotA, gotB, gotC >>

ra_check_ed(self) == /\ pc[self] = "ra_check_ed"
                     /\ IF msg_[self] = "accept"
                           THEN /\ pc' = [pc EXCEPT ![self] = "ra_done"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "ra_revise"]
                     /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                     fc_to_resA, fc_to_resB, fc_to_resC, 
                                     fc_to_editor, editor_to_resA, 
                                     editor_to_resB, editor_to_resC, 
                                     resA_to_editor, resB_to_editor, 
                                     resC_to_editor, doc_lock, ref_lock, msg_, 
                                     msg_r, msg_re, msg_f, doneA, doneB, doneC, 
                                     msg, gotA, gotB, gotC >>

ra_revise(self) == /\ pc[self] = "ra_revise"
                   /\ doc_lock = "FREE"
                   /\ doc_lock' = self
                   /\ pc' = [pc EXCEPT ![self] = "ra_rev_rel"]
                   /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                   fc_to_resA, fc_to_resB, fc_to_resC, 
                                   fc_to_editor, editor_to_resA, 
                                   editor_to_resB, editor_to_resC, 
                                   resA_to_editor, resB_to_editor, 
                                   resC_to_editor, ref_lock, msg_, msg_r, 
                                   msg_re, msg_f, doneA, doneB, doneC, msg, 
                                   gotA, gotB, gotC >>

ra_rev_rel(self) == /\ pc[self] = "ra_rev_rel"
                    /\ doc_lock' = "FREE"
                    /\ resA_to_editor' = Append(resA_to_editor, "resubmit")
                    /\ pc' = [pc EXCEPT ![self] = "ra_wait_ed2"]
                    /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                    fc_to_resA, fc_to_resB, fc_to_resC, 
                                    fc_to_editor, editor_to_resA, 
                                    editor_to_resB, editor_to_resC, 
                                    resB_to_editor, resC_to_editor, ref_lock, 
                                    msg_, msg_r, msg_re, msg_f, doneA, doneB, 
                                    doneC, msg, gotA, gotB, gotC >>

ra_wait_ed2(self) == /\ pc[self] = "ra_wait_ed2"
                     /\ Len(editor_to_resA) > 0
                     /\ msg_' = [msg_ EXCEPT ![self] = Head(editor_to_resA)]
                     /\ editor_to_resA' = Tail(editor_to_resA)
                     /\ pc' = [pc EXCEPT ![self] = "ra_done"]
                     /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                     fc_to_resA, fc_to_resB, fc_to_resC, 
                                     fc_to_editor, editor_to_resB, 
                                     editor_to_resC, resA_to_editor, 
                                     resB_to_editor, resC_to_editor, doc_lock, 
                                     ref_lock, msg_r, msg_re, msg_f, doneA, 
                                     doneB, doneC, msg, gotA, gotB, gotC >>

ra_done(self) == /\ pc[self] = "ra_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                 fc_to_resA, fc_to_resB, fc_to_resC, 
                                 fc_to_editor, editor_to_resA, editor_to_resB, 
                                 editor_to_resC, resA_to_editor, 
                                 resB_to_editor, resC_to_editor, doc_lock, 
                                 ref_lock, msg_, msg_r, msg_re, msg_f, doneA, 
                                 doneB, doneC, msg, gotA, gotB, gotC >>

researcherA_proc(self) == ra_write(self) \/ ra_rel_doc(self)
                             \/ ra_ref(self) \/ ra_rel_ref(self)
                             \/ ra_wait_fc(self) \/ ra_check_fc(self)
                             \/ ra_wait_ed(self) \/ ra_check_ed(self)
                             \/ ra_revise(self) \/ ra_rev_rel(self)
                             \/ ra_wait_ed2(self) \/ ra_done(self)

rb_write(self) == /\ pc[self] = "rb_write"
                  /\ doc_lock = "FREE"
                  /\ doc_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "rb_rel_doc"]
                  /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                  fc_to_resA, fc_to_resB, fc_to_resC, 
                                  fc_to_editor, editor_to_resA, editor_to_resB, 
                                  editor_to_resC, resA_to_editor, 
                                  resB_to_editor, resC_to_editor, ref_lock, 
                                  msg_, msg_r, msg_re, msg_f, doneA, doneB, 
                                  doneC, msg, gotA, gotB, gotC >>

rb_rel_doc(self) == /\ pc[self] = "rb_rel_doc"
                    /\ doc_lock' = "FREE"
                    /\ pc' = [pc EXCEPT ![self] = "rb_ref"]
                    /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                    fc_to_resA, fc_to_resB, fc_to_resC, 
                                    fc_to_editor, editor_to_resA, 
                                    editor_to_resB, editor_to_resC, 
                                    resA_to_editor, resB_to_editor, 
                                    resC_to_editor, ref_lock, msg_, msg_r, 
                                    msg_re, msg_f, doneA, doneB, doneC, msg, 
                                    gotA, gotB, gotC >>

rb_ref(self) == /\ pc[self] = "rb_ref"
                /\ ref_lock = "FREE"
                /\ ref_lock' = self
                /\ pc' = [pc EXCEPT ![self] = "rb_rel_ref"]
                /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, fc_to_resA, 
                                fc_to_resB, fc_to_resC, fc_to_editor, 
                                editor_to_resA, editor_to_resB, editor_to_resC, 
                                resA_to_editor, resB_to_editor, resC_to_editor, 
                                doc_lock, msg_, msg_r, msg_re, msg_f, doneA, 
                                doneB, doneC, msg, gotA, gotB, gotC >>

rb_rel_ref(self) == /\ pc[self] = "rb_rel_ref"
                    /\ ref_lock' = "FREE"
                    /\ resB_to_fc' = Append(resB_to_fc, "submit")
                    /\ pc' = [pc EXCEPT ![self] = "rb_wait_fc"]
                    /\ UNCHANGED << resA_to_fc, resC_to_fc, fc_to_resA, 
                                    fc_to_resB, fc_to_resC, fc_to_editor, 
                                    editor_to_resA, editor_to_resB, 
                                    editor_to_resC, resA_to_editor, 
                                    resB_to_editor, resC_to_editor, doc_lock, 
                                    msg_, msg_r, msg_re, msg_f, doneA, doneB, 
                                    doneC, msg, gotA, gotB, gotC >>

rb_wait_fc(self) == /\ pc[self] = "rb_wait_fc"
                    /\ Len(fc_to_resB) > 0
                    /\ msg_r' = [msg_r EXCEPT ![self] = Head(fc_to_resB)]
                    /\ fc_to_resB' = Tail(fc_to_resB)
                    /\ pc' = [pc EXCEPT ![self] = "rb_check_fc"]
                    /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                    fc_to_resA, fc_to_resC, fc_to_editor, 
                                    editor_to_resA, editor_to_resB, 
                                    editor_to_resC, resA_to_editor, 
                                    resB_to_editor, resC_to_editor, doc_lock, 
                                    ref_lock, msg_, msg_re, msg_f, doneA, 
                                    doneB, doneC, msg, gotA, gotB, gotC >>

rb_check_fc(self) == /\ pc[self] = "rb_check_fc"
                     /\ IF msg_r[self] = "flag"
                           THEN /\ pc' = [pc EXCEPT ![self] = "rb_write"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "rb_wait_ed"]
                     /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                     fc_to_resA, fc_to_resB, fc_to_resC, 
                                     fc_to_editor, editor_to_resA, 
                                     editor_to_resB, editor_to_resC, 
                                     resA_to_editor, resB_to_editor, 
                                     resC_to_editor, doc_lock, ref_lock, msg_, 
                                     msg_r, msg_re, msg_f, doneA, doneB, doneC, 
                                     msg, gotA, gotB, gotC >>

rb_wait_ed(self) == /\ pc[self] = "rb_wait_ed"
                    /\ Len(editor_to_resB) > 0
                    /\ msg_r' = [msg_r EXCEPT ![self] = Head(editor_to_resB)]
                    /\ editor_to_resB' = Tail(editor_to_resB)
                    /\ pc' = [pc EXCEPT ![self] = "rb_check_ed"]
                    /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                    fc_to_resA, fc_to_resB, fc_to_resC, 
                                    fc_to_editor, editor_to_resA, 
                                    editor_to_resC, resA_to_editor, 
                                    resB_to_editor, resC_to_editor, doc_lock, 
                                    ref_lock, msg_, msg_re, msg_f, doneA, 
                                    doneB, doneC, msg, gotA, gotB, gotC >>

rb_check_ed(self) == /\ pc[self] = "rb_check_ed"
                     /\ IF msg_r[self] = "accept"
                           THEN /\ pc' = [pc EXCEPT ![self] = "rb_done"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "rb_revise"]
                     /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                     fc_to_resA, fc_to_resB, fc_to_resC, 
                                     fc_to_editor, editor_to_resA, 
                                     editor_to_resB, editor_to_resC, 
                                     resA_to_editor, resB_to_editor, 
                                     resC_to_editor, doc_lock, ref_lock, msg_, 
                                     msg_r, msg_re, msg_f, doneA, doneB, doneC, 
                                     msg, gotA, gotB, gotC >>

rb_revise(self) == /\ pc[self] = "rb_revise"
                   /\ doc_lock = "FREE"
                   /\ doc_lock' = self
                   /\ pc' = [pc EXCEPT ![self] = "rb_rev_rel"]
                   /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                   fc_to_resA, fc_to_resB, fc_to_resC, 
                                   fc_to_editor, editor_to_resA, 
                                   editor_to_resB, editor_to_resC, 
                                   resA_to_editor, resB_to_editor, 
                                   resC_to_editor, ref_lock, msg_, msg_r, 
                                   msg_re, msg_f, doneA, doneB, doneC, msg, 
                                   gotA, gotB, gotC >>

rb_rev_rel(self) == /\ pc[self] = "rb_rev_rel"
                    /\ doc_lock' = "FREE"
                    /\ resB_to_editor' = Append(resB_to_editor, "resubmit")
                    /\ pc' = [pc EXCEPT ![self] = "rb_wait_ed2"]
                    /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                    fc_to_resA, fc_to_resB, fc_to_resC, 
                                    fc_to_editor, editor_to_resA, 
                                    editor_to_resB, editor_to_resC, 
                                    resA_to_editor, resC_to_editor, ref_lock, 
                                    msg_, msg_r, msg_re, msg_f, doneA, doneB, 
                                    doneC, msg, gotA, gotB, gotC >>

rb_wait_ed2(self) == /\ pc[self] = "rb_wait_ed2"
                     /\ Len(editor_to_resB) > 0
                     /\ msg_r' = [msg_r EXCEPT ![self] = Head(editor_to_resB)]
                     /\ editor_to_resB' = Tail(editor_to_resB)
                     /\ pc' = [pc EXCEPT ![self] = "rb_done"]
                     /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                     fc_to_resA, fc_to_resB, fc_to_resC, 
                                     fc_to_editor, editor_to_resA, 
                                     editor_to_resC, resA_to_editor, 
                                     resB_to_editor, resC_to_editor, doc_lock, 
                                     ref_lock, msg_, msg_re, msg_f, doneA, 
                                     doneB, doneC, msg, gotA, gotB, gotC >>

rb_done(self) == /\ pc[self] = "rb_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                 fc_to_resA, fc_to_resB, fc_to_resC, 
                                 fc_to_editor, editor_to_resA, editor_to_resB, 
                                 editor_to_resC, resA_to_editor, 
                                 resB_to_editor, resC_to_editor, doc_lock, 
                                 ref_lock, msg_, msg_r, msg_re, msg_f, doneA, 
                                 doneB, doneC, msg, gotA, gotB, gotC >>

researcherB_proc(self) == rb_write(self) \/ rb_rel_doc(self)
                             \/ rb_ref(self) \/ rb_rel_ref(self)
                             \/ rb_wait_fc(self) \/ rb_check_fc(self)
                             \/ rb_wait_ed(self) \/ rb_check_ed(self)
                             \/ rb_revise(self) \/ rb_rev_rel(self)
                             \/ rb_wait_ed2(self) \/ rb_done(self)

rc_write(self) == /\ pc[self] = "rc_write"
                  /\ doc_lock = "FREE"
                  /\ doc_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "rc_rel_doc"]
                  /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                  fc_to_resA, fc_to_resB, fc_to_resC, 
                                  fc_to_editor, editor_to_resA, editor_to_resB, 
                                  editor_to_resC, resA_to_editor, 
                                  resB_to_editor, resC_to_editor, ref_lock, 
                                  msg_, msg_r, msg_re, msg_f, doneA, doneB, 
                                  doneC, msg, gotA, gotB, gotC >>

rc_rel_doc(self) == /\ pc[self] = "rc_rel_doc"
                    /\ doc_lock' = "FREE"
                    /\ pc' = [pc EXCEPT ![self] = "rc_ref"]
                    /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                    fc_to_resA, fc_to_resB, fc_to_resC, 
                                    fc_to_editor, editor_to_resA, 
                                    editor_to_resB, editor_to_resC, 
                                    resA_to_editor, resB_to_editor, 
                                    resC_to_editor, ref_lock, msg_, msg_r, 
                                    msg_re, msg_f, doneA, doneB, doneC, msg, 
                                    gotA, gotB, gotC >>

rc_ref(self) == /\ pc[self] = "rc_ref"
                /\ ref_lock = "FREE"
                /\ ref_lock' = self
                /\ pc' = [pc EXCEPT ![self] = "rc_rel_ref"]
                /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, fc_to_resA, 
                                fc_to_resB, fc_to_resC, fc_to_editor, 
                                editor_to_resA, editor_to_resB, editor_to_resC, 
                                resA_to_editor, resB_to_editor, resC_to_editor, 
                                doc_lock, msg_, msg_r, msg_re, msg_f, doneA, 
                                doneB, doneC, msg, gotA, gotB, gotC >>

rc_rel_ref(self) == /\ pc[self] = "rc_rel_ref"
                    /\ ref_lock' = "FREE"
                    /\ resC_to_fc' = Append(resC_to_fc, "submit")
                    /\ pc' = [pc EXCEPT ![self] = "rc_wait_fc"]
                    /\ UNCHANGED << resA_to_fc, resB_to_fc, fc_to_resA, 
                                    fc_to_resB, fc_to_resC, fc_to_editor, 
                                    editor_to_resA, editor_to_resB, 
                                    editor_to_resC, resA_to_editor, 
                                    resB_to_editor, resC_to_editor, doc_lock, 
                                    msg_, msg_r, msg_re, msg_f, doneA, doneB, 
                                    doneC, msg, gotA, gotB, gotC >>

rc_wait_fc(self) == /\ pc[self] = "rc_wait_fc"
                    /\ Len(fc_to_resC) > 0
                    /\ msg_re' = [msg_re EXCEPT ![self] = Head(fc_to_resC)]
                    /\ fc_to_resC' = Tail(fc_to_resC)
                    /\ pc' = [pc EXCEPT ![self] = "rc_check_fc"]
                    /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                    fc_to_resA, fc_to_resB, fc_to_editor, 
                                    editor_to_resA, editor_to_resB, 
                                    editor_to_resC, resA_to_editor, 
                                    resB_to_editor, resC_to_editor, doc_lock, 
                                    ref_lock, msg_, msg_r, msg_f, doneA, doneB, 
                                    doneC, msg, gotA, gotB, gotC >>

rc_check_fc(self) == /\ pc[self] = "rc_check_fc"
                     /\ IF msg_re[self] = "flag"
                           THEN /\ pc' = [pc EXCEPT ![self] = "rc_write"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "rc_wait_ed"]
                     /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                     fc_to_resA, fc_to_resB, fc_to_resC, 
                                     fc_to_editor, editor_to_resA, 
                                     editor_to_resB, editor_to_resC, 
                                     resA_to_editor, resB_to_editor, 
                                     resC_to_editor, doc_lock, ref_lock, msg_, 
                                     msg_r, msg_re, msg_f, doneA, doneB, doneC, 
                                     msg, gotA, gotB, gotC >>

rc_wait_ed(self) == /\ pc[self] = "rc_wait_ed"
                    /\ Len(editor_to_resC) > 0
                    /\ msg_re' = [msg_re EXCEPT ![self] = Head(editor_to_resC)]
                    /\ editor_to_resC' = Tail(editor_to_resC)
                    /\ pc' = [pc EXCEPT ![self] = "rc_check_ed"]
                    /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                    fc_to_resA, fc_to_resB, fc_to_resC, 
                                    fc_to_editor, editor_to_resA, 
                                    editor_to_resB, resA_to_editor, 
                                    resB_to_editor, resC_to_editor, doc_lock, 
                                    ref_lock, msg_, msg_r, msg_f, doneA, doneB, 
                                    doneC, msg, gotA, gotB, gotC >>

rc_check_ed(self) == /\ pc[self] = "rc_check_ed"
                     /\ IF msg_re[self] = "accept"
                           THEN /\ pc' = [pc EXCEPT ![self] = "rc_done"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "rc_revise"]
                     /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                     fc_to_resA, fc_to_resB, fc_to_resC, 
                                     fc_to_editor, editor_to_resA, 
                                     editor_to_resB, editor_to_resC, 
                                     resA_to_editor, resB_to_editor, 
                                     resC_to_editor, doc_lock, ref_lock, msg_, 
                                     msg_r, msg_re, msg_f, doneA, doneB, doneC, 
                                     msg, gotA, gotB, gotC >>

rc_revise(self) == /\ pc[self] = "rc_revise"
                   /\ doc_lock = "FREE"
                   /\ doc_lock' = self
                   /\ pc' = [pc EXCEPT ![self] = "rc_rev_rel"]
                   /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                   fc_to_resA, fc_to_resB, fc_to_resC, 
                                   fc_to_editor, editor_to_resA, 
                                   editor_to_resB, editor_to_resC, 
                                   resA_to_editor, resB_to_editor, 
                                   resC_to_editor, ref_lock, msg_, msg_r, 
                                   msg_re, msg_f, doneA, doneB, doneC, msg, 
                                   gotA, gotB, gotC >>

rc_rev_rel(self) == /\ pc[self] = "rc_rev_rel"
                    /\ doc_lock' = "FREE"
                    /\ resC_to_editor' = Append(resC_to_editor, "resubmit")
                    /\ pc' = [pc EXCEPT ![self] = "rc_wait_ed2"]
                    /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                    fc_to_resA, fc_to_resB, fc_to_resC, 
                                    fc_to_editor, editor_to_resA, 
                                    editor_to_resB, editor_to_resC, 
                                    resA_to_editor, resB_to_editor, ref_lock, 
                                    msg_, msg_r, msg_re, msg_f, doneA, doneB, 
                                    doneC, msg, gotA, gotB, gotC >>

rc_wait_ed2(self) == /\ pc[self] = "rc_wait_ed2"
                     /\ Len(editor_to_resC) > 0
                     /\ msg_re' = [msg_re EXCEPT ![self] = Head(editor_to_resC)]
                     /\ editor_to_resC' = Tail(editor_to_resC)
                     /\ pc' = [pc EXCEPT ![self] = "rc_done"]
                     /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                     fc_to_resA, fc_to_resB, fc_to_resC, 
                                     fc_to_editor, editor_to_resA, 
                                     editor_to_resB, resA_to_editor, 
                                     resB_to_editor, resC_to_editor, doc_lock, 
                                     ref_lock, msg_, msg_r, msg_f, doneA, 
                                     doneB, doneC, msg, gotA, gotB, gotC >>

rc_done(self) == /\ pc[self] = "rc_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                 fc_to_resA, fc_to_resB, fc_to_resC, 
                                 fc_to_editor, editor_to_resA, editor_to_resB, 
                                 editor_to_resC, resA_to_editor, 
                                 resB_to_editor, resC_to_editor, doc_lock, 
                                 ref_lock, msg_, msg_r, msg_re, msg_f, doneA, 
                                 doneB, doneC, msg, gotA, gotB, gotC >>

researcherC_proc(self) == rc_write(self) \/ rc_rel_doc(self)
                             \/ rc_ref(self) \/ rc_rel_ref(self)
                             \/ rc_wait_fc(self) \/ rc_check_fc(self)
                             \/ rc_wait_ed(self) \/ rc_check_ed(self)
                             \/ rc_revise(self) \/ rc_rev_rel(self)
                             \/ rc_wait_ed2(self) \/ rc_done(self)

fc_loop(self) == /\ pc[self] = "fc_loop"
                 /\ IF ~doneA[self] \/ ~doneB[self] \/ ~doneC[self]
                       THEN /\ pc' = [pc EXCEPT ![self] = "fc_recv"]
                       ELSE /\ pc' = [pc EXCEPT ![self] = "fc_done"]
                 /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                 fc_to_resA, fc_to_resB, fc_to_resC, 
                                 fc_to_editor, editor_to_resA, editor_to_resB, 
                                 editor_to_resC, resA_to_editor, 
                                 resB_to_editor, resC_to_editor, doc_lock, 
                                 ref_lock, msg_, msg_r, msg_re, msg_f, doneA, 
                                 doneB, doneC, msg, gotA, gotB, gotC >>

fc_recv(self) == /\ pc[self] = "fc_recv"
                 /\ \/ /\ Len(resA_to_fc) > 0
                       /\ msg_f' = [msg_f EXCEPT ![self] = Head(resA_to_fc)]
                       /\ resA_to_fc' = Tail(resA_to_fc)
                       /\ pc' = [pc EXCEPT ![self] = "fc_checkA"]
                       /\ UNCHANGED <<resB_to_fc, resC_to_fc>>
                    \/ /\ Len(resB_to_fc) > 0
                       /\ msg_f' = [msg_f EXCEPT ![self] = Head(resB_to_fc)]
                       /\ resB_to_fc' = Tail(resB_to_fc)
                       /\ pc' = [pc EXCEPT ![self] = "fc_checkB"]
                       /\ UNCHANGED <<resA_to_fc, resC_to_fc>>
                    \/ /\ Len(resC_to_fc) > 0
                       /\ msg_f' = [msg_f EXCEPT ![self] = Head(resC_to_fc)]
                       /\ resC_to_fc' = Tail(resC_to_fc)
                       /\ pc' = [pc EXCEPT ![self] = "fc_checkC"]
                       /\ UNCHANGED <<resA_to_fc, resB_to_fc>>
                 /\ UNCHANGED << fc_to_resA, fc_to_resB, fc_to_resC, 
                                 fc_to_editor, editor_to_resA, editor_to_resB, 
                                 editor_to_resC, resA_to_editor, 
                                 resB_to_editor, resC_to_editor, doc_lock, 
                                 ref_lock, msg_, msg_r, msg_re, doneA, doneB, 
                                 doneC, msg, gotA, gotB, gotC >>

fc_checkA(self) == /\ pc[self] = "fc_checkA"
                   /\ \/ /\ fc_to_resA' = Append(fc_to_resA, "pass")
                         /\ fc_to_editor' = Append(fc_to_editor, "passedA")
                         /\ doneA' = [doneA EXCEPT ![self] = TRUE]
                      \/ /\ fc_to_resA' = Append(fc_to_resA, "flag")
                         /\ UNCHANGED <<fc_to_editor, doneA>>
                   /\ pc' = [pc EXCEPT ![self] = "fc_loop"]
                   /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                   fc_to_resB, fc_to_resC, editor_to_resA, 
                                   editor_to_resB, editor_to_resC, 
                                   resA_to_editor, resB_to_editor, 
                                   resC_to_editor, doc_lock, ref_lock, msg_, 
                                   msg_r, msg_re, msg_f, doneB, doneC, msg, 
                                   gotA, gotB, gotC >>

fc_checkB(self) == /\ pc[self] = "fc_checkB"
                   /\ \/ /\ fc_to_resB' = Append(fc_to_resB, "pass")
                         /\ fc_to_editor' = Append(fc_to_editor, "passedB")
                         /\ doneB' = [doneB EXCEPT ![self] = TRUE]
                      \/ /\ fc_to_resB' = Append(fc_to_resB, "flag")
                         /\ UNCHANGED <<fc_to_editor, doneB>>
                   /\ pc' = [pc EXCEPT ![self] = "fc_loop"]
                   /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                   fc_to_resA, fc_to_resC, editor_to_resA, 
                                   editor_to_resB, editor_to_resC, 
                                   resA_to_editor, resB_to_editor, 
                                   resC_to_editor, doc_lock, ref_lock, msg_, 
                                   msg_r, msg_re, msg_f, doneA, doneC, msg, 
                                   gotA, gotB, gotC >>

fc_checkC(self) == /\ pc[self] = "fc_checkC"
                   /\ \/ /\ fc_to_resC' = Append(fc_to_resC, "pass")
                         /\ fc_to_editor' = Append(fc_to_editor, "passedC")
                         /\ doneC' = [doneC EXCEPT ![self] = TRUE]
                      \/ /\ fc_to_resC' = Append(fc_to_resC, "flag")
                         /\ UNCHANGED <<fc_to_editor, doneC>>
                   /\ pc' = [pc EXCEPT ![self] = "fc_loop"]
                   /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                   fc_to_resA, fc_to_resB, editor_to_resA, 
                                   editor_to_resB, editor_to_resC, 
                                   resA_to_editor, resB_to_editor, 
                                   resC_to_editor, doc_lock, ref_lock, msg_, 
                                   msg_r, msg_re, msg_f, doneA, doneB, msg, 
                                   gotA, gotB, gotC >>

fc_done(self) == /\ pc[self] = "fc_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                 fc_to_resA, fc_to_resB, fc_to_resC, 
                                 fc_to_editor, editor_to_resA, editor_to_resB, 
                                 editor_to_resC, resA_to_editor, 
                                 resB_to_editor, resC_to_editor, doc_lock, 
                                 ref_lock, msg_, msg_r, msg_re, msg_f, doneA, 
                                 doneB, doneC, msg, gotA, gotB, gotC >>

factchecker_proc(self) == fc_loop(self) \/ fc_recv(self) \/ fc_checkA(self)
                             \/ fc_checkB(self) \/ fc_checkC(self)
                             \/ fc_done(self)

ed_collect(self) == /\ pc[self] = "ed_collect"
                    /\ IF ~gotA[self] \/ ~gotB[self] \/ ~gotC[self]
                          THEN /\ pc' = [pc EXCEPT ![self] = "ed_recv"]
                          ELSE /\ pc' = [pc EXCEPT ![self] = "ed_review"]
                    /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                    fc_to_resA, fc_to_resB, fc_to_resC, 
                                    fc_to_editor, editor_to_resA, 
                                    editor_to_resB, editor_to_resC, 
                                    resA_to_editor, resB_to_editor, 
                                    resC_to_editor, doc_lock, ref_lock, msg_, 
                                    msg_r, msg_re, msg_f, doneA, doneB, doneC, 
                                    msg, gotA, gotB, gotC >>

ed_recv(self) == /\ pc[self] = "ed_recv"
                 /\ Len(fc_to_editor) > 0
                 /\ msg' = [msg EXCEPT ![self] = Head(fc_to_editor)]
                 /\ fc_to_editor' = Tail(fc_to_editor)
                 /\ pc' = [pc EXCEPT ![self] = "ed_dispatch"]
                 /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                 fc_to_resA, fc_to_resB, fc_to_resC, 
                                 editor_to_resA, editor_to_resB, 
                                 editor_to_resC, resA_to_editor, 
                                 resB_to_editor, resC_to_editor, doc_lock, 
                                 ref_lock, msg_, msg_r, msg_re, msg_f, doneA, 
                                 doneB, doneC, gotA, gotB, gotC >>

ed_dispatch(self) == /\ pc[self] = "ed_dispatch"
                     /\ IF msg[self] = "passedA"
                           THEN /\ gotA' = [gotA EXCEPT ![self] = TRUE]
                                /\ UNCHANGED << gotB, gotC >>
                           ELSE /\ IF msg[self] = "passedB"
                                      THEN /\ gotB' = [gotB EXCEPT ![self] = TRUE]
                                           /\ gotC' = gotC
                                      ELSE /\ gotC' = [gotC EXCEPT ![self] = TRUE]
                                           /\ gotB' = gotB
                                /\ gotA' = gotA
                     /\ pc' = [pc EXCEPT ![self] = "ed_collect"]
                     /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                     fc_to_resA, fc_to_resB, fc_to_resC, 
                                     fc_to_editor, editor_to_resA, 
                                     editor_to_resB, editor_to_resC, 
                                     resA_to_editor, resB_to_editor, 
                                     resC_to_editor, doc_lock, ref_lock, msg_, 
                                     msg_r, msg_re, msg_f, doneA, doneB, doneC, 
                                     msg >>

ed_review(self) == /\ pc[self] = "ed_review"
                   /\ doc_lock = "FREE"
                   /\ doc_lock' = self
                   /\ pc' = [pc EXCEPT ![self] = "ed_decide"]
                   /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                   fc_to_resA, fc_to_resB, fc_to_resC, 
                                   fc_to_editor, editor_to_resA, 
                                   editor_to_resB, editor_to_resC, 
                                   resA_to_editor, resB_to_editor, 
                                   resC_to_editor, ref_lock, msg_, msg_r, 
                                   msg_re, msg_f, doneA, doneB, doneC, msg, 
                                   gotA, gotB, gotC >>

ed_decide(self) == /\ pc[self] = "ed_decide"
                   /\ \/ /\ doc_lock' = "FREE"
                         /\ editor_to_resA' = Append(editor_to_resA, "accept")
                         /\ editor_to_resB' = Append(editor_to_resB, "accept")
                         /\ editor_to_resC' = Append(editor_to_resC, "accept")
                         /\ pc' = [pc EXCEPT ![self] = "ed_done"]
                      \/ /\ doc_lock' = "FREE"
                         /\ editor_to_resA' = Append(editor_to_resA, "revise")
                         /\ editor_to_resB' = Append(editor_to_resB, "revise")
                         /\ editor_to_resC' = Append(editor_to_resC, "revise")
                         /\ pc' = [pc EXCEPT ![self] = "ed_wait_resub_a"]
                   /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                   fc_to_resA, fc_to_resB, fc_to_resC, 
                                   fc_to_editor, resA_to_editor, 
                                   resB_to_editor, resC_to_editor, ref_lock, 
                                   msg_, msg_r, msg_re, msg_f, doneA, doneB, 
                                   doneC, msg, gotA, gotB, gotC >>

ed_wait_resub_a(self) == /\ pc[self] = "ed_wait_resub_a"
                         /\ Len(resA_to_editor) > 0
                         /\ msg' = [msg EXCEPT ![self] = Head(resA_to_editor)]
                         /\ resA_to_editor' = Tail(resA_to_editor)
                         /\ pc' = [pc EXCEPT ![self] = "ed_wait_resub_b"]
                         /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                         fc_to_resA, fc_to_resB, fc_to_resC, 
                                         fc_to_editor, editor_to_resA, 
                                         editor_to_resB, editor_to_resC, 
                                         resB_to_editor, resC_to_editor, 
                                         doc_lock, ref_lock, msg_, msg_r, 
                                         msg_re, msg_f, doneA, doneB, doneC, 
                                         gotA, gotB, gotC >>

ed_wait_resub_b(self) == /\ pc[self] = "ed_wait_resub_b"
                         /\ Len(resB_to_editor) > 0
                         /\ msg' = [msg EXCEPT ![self] = Head(resB_to_editor)]
                         /\ resB_to_editor' = Tail(resB_to_editor)
                         /\ pc' = [pc EXCEPT ![self] = "ed_wait_resub_c"]
                         /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                         fc_to_resA, fc_to_resB, fc_to_resC, 
                                         fc_to_editor, editor_to_resA, 
                                         editor_to_resB, editor_to_resC, 
                                         resA_to_editor, resC_to_editor, 
                                         doc_lock, ref_lock, msg_, msg_r, 
                                         msg_re, msg_f, doneA, doneB, doneC, 
                                         gotA, gotB, gotC >>

ed_wait_resub_c(self) == /\ pc[self] = "ed_wait_resub_c"
                         /\ Len(resC_to_editor) > 0
                         /\ msg' = [msg EXCEPT ![self] = Head(resC_to_editor)]
                         /\ resC_to_editor' = Tail(resC_to_editor)
                         /\ pc' = [pc EXCEPT ![self] = "ed_finalize"]
                         /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                         fc_to_resA, fc_to_resB, fc_to_resC, 
                                         fc_to_editor, editor_to_resA, 
                                         editor_to_resB, editor_to_resC, 
                                         resA_to_editor, resB_to_editor, 
                                         doc_lock, ref_lock, msg_, msg_r, 
                                         msg_re, msg_f, doneA, doneB, doneC, 
                                         gotA, gotB, gotC >>

ed_finalize(self) == /\ pc[self] = "ed_finalize"
                     /\ doc_lock = "FREE"
                     /\ doc_lock' = self
                     /\ pc' = [pc EXCEPT ![self] = "ed_fin_rel"]
                     /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                     fc_to_resA, fc_to_resB, fc_to_resC, 
                                     fc_to_editor, editor_to_resA, 
                                     editor_to_resB, editor_to_resC, 
                                     resA_to_editor, resB_to_editor, 
                                     resC_to_editor, ref_lock, msg_, msg_r, 
                                     msg_re, msg_f, doneA, doneB, doneC, msg, 
                                     gotA, gotB, gotC >>

ed_fin_rel(self) == /\ pc[self] = "ed_fin_rel"
                    /\ doc_lock' = "FREE"
                    /\ editor_to_resA' = Append(editor_to_resA, "accept")
                    /\ editor_to_resB' = Append(editor_to_resB, "accept")
                    /\ editor_to_resC' = Append(editor_to_resC, "accept")
                    /\ pc' = [pc EXCEPT ![self] = "ed_done"]
                    /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                    fc_to_resA, fc_to_resB, fc_to_resC, 
                                    fc_to_editor, resA_to_editor, 
                                    resB_to_editor, resC_to_editor, ref_lock, 
                                    msg_, msg_r, msg_re, msg_f, doneA, doneB, 
                                    doneC, msg, gotA, gotB, gotC >>

ed_done(self) == /\ pc[self] = "ed_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << resA_to_fc, resB_to_fc, resC_to_fc, 
                                 fc_to_resA, fc_to_resB, fc_to_resC, 
                                 fc_to_editor, editor_to_resA, editor_to_resB, 
                                 editor_to_resC, resA_to_editor, 
                                 resB_to_editor, resC_to_editor, doc_lock, 
                                 ref_lock, msg_, msg_r, msg_re, msg_f, doneA, 
                                 doneB, doneC, msg, gotA, gotB, gotC >>

editor_proc(self) == ed_collect(self) \/ ed_recv(self) \/ ed_dispatch(self)
                        \/ ed_review(self) \/ ed_decide(self)
                        \/ ed_wait_resub_a(self) \/ ed_wait_resub_b(self)
                        \/ ed_wait_resub_c(self) \/ ed_finalize(self)
                        \/ ed_fin_rel(self) \/ ed_done(self)

(* Allow infinite stuttering to prevent deadlock on termination. *)
Terminating == /\ \A self \in ProcSet: pc[self] = "Done"
               /\ UNCHANGED vars

Next == (\E self \in {ResearcherA}: researcherA_proc(self))
           \/ (\E self \in {ResearcherB}: researcherB_proc(self))
           \/ (\E self \in {ResearcherC}: researcherC_proc(self))
           \/ (\E self \in {Factchecker}: factchecker_proc(self))
           \/ (\E self \in {Editor}: editor_proc(self))
           \/ Terminating

Spec == /\ Init /\ [][Next]_vars
        /\ \A self \in {ResearcherA} : WF_vars(researcherA_proc(self))
        /\ \A self \in {ResearcherB} : WF_vars(researcherB_proc(self))
        /\ \A self \in {ResearcherC} : WF_vars(researcherC_proc(self))
        /\ \A self \in {Factchecker} : WF_vars(factchecker_proc(self))
        /\ \A self \in {Editor} : WF_vars(editor_proc(self))

Termination == <>(\A self \in ProcSet: pc[self] = "Done")

\* END TRANSLATION 

AllDone == \A p \in {ResearcherA, ResearcherB, ResearcherC, Factchecker, Editor}: pc[p] = "Done"

TypeInvariant ==
  /\ \A p \in {ResearcherA, ResearcherB, ResearcherC, Factchecker, Editor}: pc[p] \in STRING
  /\ doc_lock \in {ResearcherA, ResearcherB, ResearcherC, Factchecker, Editor, "FREE"}
  /\ ref_lock \in {ResearcherA, ResearcherB, ResearcherC, Factchecker, Editor, "FREE"}
  /\ resA_to_fc \in Seq(STRING)
  /\ resB_to_fc \in Seq(STRING)
  /\ resC_to_fc \in Seq(STRING)
  /\ fc_to_resA \in Seq(STRING)
  /\ fc_to_resB \in Seq(STRING)
  /\ fc_to_resC \in Seq(STRING)
  /\ fc_to_editor \in Seq(STRING)
  /\ editor_to_resA \in Seq(STRING)
  /\ editor_to_resB \in Seq(STRING)
  /\ editor_to_resC \in Seq(STRING)
  /\ resA_to_editor \in Seq(STRING)
  /\ resB_to_editor \in Seq(STRING)
  /\ resC_to_editor \in Seq(STRING)

NoOrphanLocks ==
  AllDone => (doc_lock = "FREE" /\ ref_lock = "FREE")

ChannelsDrained ==
  AllDone => (Len(resA_to_fc) = 0 /\ Len(resB_to_fc) = 0 /\ Len(resC_to_fc) = 0 /\ Len(fc_to_resA) = 0 /\ Len(fc_to_resB) = 0 /\ Len(fc_to_resC) = 0 /\ Len(fc_to_editor) = 0 /\ Len(editor_to_resA) = 0 /\ Len(editor_to_resB) = 0 /\ Len(editor_to_resC) = 0 /\ Len(resA_to_editor) = 0 /\ Len(resB_to_editor) = 0 /\ Len(resC_to_editor) = 0)

ChannelBound ==
  Len(resA_to_fc) <= 3 /\ Len(resB_to_fc) <= 3 /\ Len(resC_to_fc) <= 3 /\ Len(fc_to_resA) <= 3 /\ Len(fc_to_resB) <= 3 /\ Len(fc_to_resC) <= 3 /\ Len(fc_to_editor) <= 3 /\ Len(editor_to_resA) <= 3 /\ Len(editor_to_resB) <= 3 /\ Len(editor_to_resC) <= 3 /\ Len(resA_to_editor) <= 3 /\ Len(resB_to_editor) <= 3 /\ Len(resC_to_editor) <= 3

====
