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