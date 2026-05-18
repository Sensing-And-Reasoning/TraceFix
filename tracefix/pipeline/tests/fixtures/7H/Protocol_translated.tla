---- MODULE Protocol ----
EXTENDS Integers, Sequences, TLC

CONSTANTS WriterA, WriterB, WriterC, FigCreator, FactChecker, Reviewer, Eic

(* --algorithm Protocol {
variables
  wC_to_wB = <<>>; \* writerC -> writerB, labels: ['stable']
  wB_to_wA = <<>>; \* writerB -> writerA, labels: ['stable']
  wC_to_wA = <<>>; \* writerC -> writerA, labels: ['stable']
  wA_to_fig = <<>>; \* writerA -> figCreator, labels: ['fig_request']
  wB_to_fig = <<>>; \* writerB -> figCreator, labels: ['fig_request']
  wC_to_fig = <<>>; \* writerC -> figCreator, labels: ['fig_request']
  fig_to_wA = <<>>; \* figCreator -> writerA, labels: ['fig_done']
  fig_to_wB = <<>>; \* figCreator -> writerB, labels: ['fig_done']
  fig_to_wC = <<>>; \* figCreator -> writerC, labels: ['fig_done']
  wA_to_fc = <<>>; \* writerA -> factChecker, labels: ['ready']
  wB_to_fc = <<>>; \* writerB -> factChecker, labels: ['ready']
  wC_to_fc = <<>>; \* writerC -> factChecker, labels: ['ready']
  fc_to_wA = <<>>; \* factChecker -> writerA, labels: ['ok', 'revise']
  fc_to_wB = <<>>; \* factChecker -> writerB, labels: ['ok', 'revise']
  fc_to_wC = <<>>; \* factChecker -> writerC, labels: ['ok', 'revise']
  eic_to_rev = <<>>; \* eic -> reviewer, labels: ['assign']
  rev_to_wA = <<>>; \* reviewer -> writerA, labels: ['ok', 'minor', 'major']
  rev_to_wB = <<>>; \* reviewer -> writerB, labels: ['ok', 'minor', 'major']
  rev_to_wC = <<>>; \* reviewer -> writerC, labels: ['ok', 'minor', 'major']
  wA_to_rev = <<>>; \* writerA -> reviewer, labels: ['ready', 'revised']
  wB_to_rev = <<>>; \* writerB -> reviewer, labels: ['ready', 'revised']
  wC_to_rev = <<>>; \* writerC -> reviewer, labels: ['ready', 'revised']
  eic_to_wA = <<>>; \* eic -> writerA, labels: ['decision']
  eic_to_wB = <<>>; \* eic -> writerB, labels: ['decision']
  eic_to_wC = <<>>; \* eic -> writerC, labels: ['decision']
  partI_lock = "FREE"; \* Lock
  ch3_lock = "FREE"; \* Lock
  ch4_lock = "FREE"; \* Lock
  fig_lock = "FREE"; \* Lock
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

\* ============ WriterC: chapter 4 (evaluation) ============
\* Writes first since B depends on C's results, A depends on B+C
fair process (writerC_proc \in {WriterC})
variables msg = "";
{
  wc_write:
    acquire_lock(ch4_lock);
  wc_write_done:
    release_lock(ch4_lock);

  \* Signal stable results to writerB (ch3 refs ch4 data) and writerA
  wc_signal_b:
    send(wC_to_wB, "stable");
    send(wC_to_wA, "stable");

  \* Request figure
  wc_fig_req:
    send(wC_to_fig, "fig_request");
  wc_fig_wait:
    receive(fig_to_wC, msg);

  \* Update references
  wc_ref:
    acquire_lock(ref_lock);
  wc_ref_done:
    release_lock(ref_lock);

  \* Submit to fact checker
  wc_sub_fc:
    send(wC_to_fc, "ready");
  wc_fc_wait:
    receive(fc_to_wC, msg);
  wc_fc_check:
    if (msg = "revise") {
    wc_fc_fix:
      acquire_lock(ch4_lock);
    wc_fc_fix_done:
      release_lock(ch4_lock);
    };

  \* Submit to reviewer
  wc_sub_rev:
    send(wC_to_rev, "ready");
  wc_rev_wait:
    receive(rev_to_wC, msg);
  wc_rev_check:
    if (msg = "major") {
    wc_major_fix:
      acquire_lock(ch4_lock);
    wc_major_done:
      release_lock(ch4_lock);
      send(wC_to_rev, "revised");
    wc_rerev_wait:
      receive(rev_to_wC, msg);
    } else if (msg = "minor") {
    wc_minor_fix:
      acquire_lock(ch4_lock);
    wc_minor_done:
      release_lock(ch4_lock);
    };

  \* Wait for EIC editorial decision
  wc_eic_wait:
    receive(eic_to_wC, msg);
  wc_eic_apply:
    acquire_lock(ch4_lock);
  wc_eic_done:
    release_lock(ch4_lock);
}

\* ============ WriterB: chapter 3 (core contribution) ============
\* Waits for WriterC's stable results before finalizing ch3 references
fair process (writerB_proc \in {WriterB})
variables msg = "";
{
  \* Initial draft of ch3
  wb_write:
    acquire_lock(ch3_lock);
  wb_init_done:
    release_lock(ch3_lock);

  \* Wait for writerC's stable (ch3 references ch4 evaluation data)
  wb_wait_c:
    receive(wC_to_wB, msg);

  \* Finalize ch3 with cross-references
  wb_finalize:
    acquire_lock(ch3_lock);
  wb_fin_done:
    release_lock(ch3_lock);

  \* Signal stable to writerA (Part I ch2 frames ch3 contribution)
  wb_signal_a:
    send(wB_to_wA, "stable");

  \* Request figure
  wb_fig_req:
    send(wB_to_fig, "fig_request");
  wb_fig_wait:
    receive(fig_to_wB, msg);

  \* Update references
  wb_ref:
    acquire_lock(ref_lock);
  wb_ref_done:
    release_lock(ref_lock);

  \* Submit to fact checker
  wb_sub_fc:
    send(wB_to_fc, "ready");
  wb_fc_wait:
    receive(fc_to_wB, msg);
  wb_fc_check:
    if (msg = "revise") {
    wb_fc_fix:
      acquire_lock(ch3_lock);
    wb_fc_fix_done:
      release_lock(ch3_lock);
    };

  \* Submit to reviewer
  wb_sub_rev:
    send(wB_to_rev, "ready");
  wb_rev_wait:
    receive(rev_to_wB, msg);
  wb_rev_check:
    if (msg = "major") {
    wb_major_fix:
      acquire_lock(ch3_lock);
    wb_major_done:
      release_lock(ch3_lock);
      send(wB_to_rev, "revised");
    wb_rerev_wait:
      receive(rev_to_wB, msg);
    } else if (msg = "minor") {
    wb_minor_fix:
      acquire_lock(ch3_lock);
    wb_minor_done:
      release_lock(ch3_lock);
    };

  \* Wait for EIC editorial decision
  wb_eic_wait:
    receive(eic_to_wB, msg);
  wb_eic_apply:
    acquire_lock(ch3_lock);
  wb_eic_done:
    release_lock(ch3_lock);
}

\* ============ WriterA: Part I (chapters 1-2) ============
\* Waits for both B and C stable signals before finalizing Part I
fair process (writerA_proc \in {WriterA})
variables msg = "";
{
  \* Initial draft of Part I
  wa_write:
    acquire_lock(partI_lock);
  wa_init_done:
    release_lock(partI_lock);

  \* Wait for writerB stable (ch3 done) and writerC stable (ch4 done)
  wa_wait_b:
    receive(wB_to_wA, msg);
  wa_wait_c:
    receive(wC_to_wA, msg);

  \* Finalize Part I with cross-references to ch3 and ch4
  wa_finalize:
    acquire_lock(partI_lock);
  wa_fin_done:
    release_lock(partI_lock);

  \* Request figure
  wa_fig_req:
    send(wA_to_fig, "fig_request");
  wa_fig_wait:
    receive(fig_to_wA, msg);

  \* Update references
  wa_ref:
    acquire_lock(ref_lock);
  wa_ref_done:
    release_lock(ref_lock);

  \* Submit to fact checker
  wa_sub_fc:
    send(wA_to_fc, "ready");
  wa_fc_wait:
    receive(fc_to_wA, msg);
  wa_fc_check:
    if (msg = "revise") {
    wa_fc_fix:
      acquire_lock(partI_lock);
    wa_fc_fix_done:
      release_lock(partI_lock);
    };

  \* Submit to reviewer
  wa_sub_rev:
    send(wA_to_rev, "ready");
  wa_rev_wait:
    receive(rev_to_wA, msg);
  wa_rev_check:
    if (msg = "major") {
    wa_major_fix:
      acquire_lock(partI_lock);
    wa_major_done:
      release_lock(partI_lock);
      send(wA_to_rev, "revised");
    wa_rerev_wait:
      receive(rev_to_wA, msg);
    } else if (msg = "minor") {
    wa_minor_fix:
      acquire_lock(partI_lock);
    wa_minor_done:
      release_lock(partI_lock);
    };

  \* Wait for EIC editorial decision
  wa_eic_wait:
    receive(eic_to_wA, msg);
  wa_eic_apply:
    acquire_lock(partI_lock);
  wa_eic_done:
    release_lock(partI_lock);
}

\* ============ FigCreator ============
\* Collects figure requests from all 3 writers, inserts figures
fair process (figCreator_proc \in {FigCreator})
variables msg = "", gotA = FALSE, gotB = FALSE, gotC = FALSE;
{
  fg_collect:
    while (~gotA \/ ~gotB \/ ~gotC) {
      fg_recv:
        either {
          receive(wA_to_fig, msg);
          gotA := TRUE;
        } or {
          receive(wB_to_fig, msg);
          gotB := TRUE;
        } or {
          receive(wC_to_fig, msg);
          gotC := TRUE;
        };
    };

  \* Insert figures using consistent lock ordering: partI < ch3 < ch4
  fg_fig:
    acquire_lock(fig_lock);
  fg_partI:
    acquire_lock(partI_lock);
  fg_partI_done:
    release_lock(partI_lock);
  fg_ch3:
    acquire_lock(ch3_lock);
  fg_ch3_done:
    release_lock(ch3_lock);
  fg_ch4:
    acquire_lock(ch4_lock);
  fg_ch4_done:
    release_lock(ch4_lock);
  fg_fig_done:
    release_lock(fig_lock);

  \* Notify all writers
  fg_notify:
    send(fig_to_wA, "fig_done");
    send(fig_to_wB, "fig_done");
    send(fig_to_wC, "fig_done");
}

\* ============ FactChecker ============
\* Collects ready signals from all writers, verifies cross-chapter data consistency
fair process (factChecker_proc \in {FactChecker})
variables msg = "", gotA = FALSE, gotB = FALSE, gotC = FALSE;
{
  fk_collect:
    while (~gotA \/ ~gotB \/ ~gotC) {
      fk_recv:
        either {
          receive(wA_to_fc, msg);
          gotA := TRUE;
        } or {
          receive(wB_to_fc, msg);
          gotB := TRUE;
        } or {
          receive(wC_to_fc, msg);
          gotC := TRUE;
        };
    };

  \* Sequential read access using lock ordering: partI < ch3 < ch4
  fk_partI:
    acquire_lock(partI_lock);
  fk_partI_done:
    release_lock(partI_lock);
  fk_ch3:
    acquire_lock(ch3_lock);
  fk_ch3_done:
    release_lock(ch3_lock);
  fk_ch4:
    acquire_lock(ch4_lock);
  fk_ch4_done:
    release_lock(ch4_lock);

  \* Send fact check results (nondeterministic per writer)
  fk_decide_a:
    either {
      send(fc_to_wA, "ok");
    } or {
      send(fc_to_wA, "revise");
    };
  fk_decide_b:
    either {
      send(fc_to_wB, "ok");
    } or {
      send(fc_to_wB, "revise");
    };
  fk_decide_c:
    either {
      send(fc_to_wC, "ok");
    } or {
      send(fc_to_wC, "revise");
    };
}

\* ============ Reviewer ============
\* Waits for EIC assignment, then reviews all chapters
fair process (reviewer_proc \in {Reviewer})
variables msg = "", gotA = FALSE, gotB = FALSE, gotC = FALSE;
{
  \* Wait for EIC to assign review
  rv_assign:
    receive(eic_to_rev, msg);

  \* Collect ready submissions from all writers
  rv_collect:
    while (~gotA \/ ~gotB \/ ~gotC) {
      rv_recv:
        either {
          receive(wA_to_rev, msg);
          gotA := TRUE;
        } or {
          receive(wB_to_rev, msg);
          gotB := TRUE;
        } or {
          receive(wC_to_rev, msg);
          gotC := TRUE;
        };
    };

  \* Review chapters (lock ordering: partI < ch3 < ch4)
  rv_partI:
    acquire_lock(partI_lock);
  rv_partI_done:
    release_lock(partI_lock);
  rv_ch3:
    acquire_lock(ch3_lock);
  rv_ch3_done:
    release_lock(ch3_lock);
  rv_ch4:
    acquire_lock(ch4_lock);
  rv_ch4_done:
    release_lock(ch4_lock);

  \* Send review results per writer (ok/minor/major)
  \* Major: writer resubmits and reviewer re-reviews (sends ok after)
  rv_decide_a:
    either {
      send(rev_to_wA, "ok");
    } or {
      send(rev_to_wA, "minor");
    } or {
      send(rev_to_wA, "major");
    rv_rerecv_a:
      receive(wA_to_rev, msg);
    rv_rerev_a:
      send(rev_to_wA, "ok");
    };
  rv_decide_b:
    either {
      send(rev_to_wB, "ok");
    } or {
      send(rev_to_wB, "minor");
    } or {
      send(rev_to_wB, "major");
    rv_rerecv_b:
      receive(wB_to_rev, msg);
    rv_rerev_b:
      send(rev_to_wB, "ok");
    };
  rv_decide_c:
    either {
      send(rev_to_wC, "ok");
    } or {
      send(rev_to_wC, "minor");
    } or {
      send(rev_to_wC, "major");
    rv_rerecv_c:
      receive(wC_to_rev, msg);
    rv_rerev_c:
      send(rev_to_wC, "ok");
    };
}

\* ============ Editor-in-Chief ============
\* Assigns reviewer, then broadcasts editorial decisions to all writers
fair process (eic_proc \in {Eic})
variables msg = "";
{
  ei_assign:
    send(eic_to_rev, "assign");
  ei_decide:
    send(eic_to_wA, "decision");
    send(eic_to_wB, "decision");
    send(eic_to_wC, "decision");
}

} *)
\* BEGIN TRANSLATION (chksum(pcal) = "d4cf4293" /\ chksum(tla) = "5debcffc")
\* Process variable msg of process writerC_proc at line 61 col 11 changed to msg_
\* Process variable msg of process writerB_proc at line 131 col 11 changed to msg_w
\* Process variable msg of process writerA_proc at line 211 col 11 changed to msg_wr
\* Process variable msg of process figCreator_proc at line 289 col 11 changed to msg_f
\* Process variable gotA of process figCreator_proc at line 289 col 21 changed to gotA_
\* Process variable gotB of process figCreator_proc at line 289 col 35 changed to gotB_
\* Process variable gotC of process figCreator_proc at line 289 col 49 changed to gotC_
\* Process variable msg of process factChecker_proc at line 334 col 11 changed to msg_fa
\* Process variable gotA of process factChecker_proc at line 334 col 21 changed to gotA_f
\* Process variable gotB of process factChecker_proc at line 334 col 35 changed to gotB_f
\* Process variable gotC of process factChecker_proc at line 334 col 49 changed to gotC_f
\* Process variable msg of process reviewer_proc at line 389 col 11 changed to msg_r
VARIABLES pc, wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, wB_to_fig, wC_to_fig, 
          fig_to_wA, fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
          fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, rev_to_wA, rev_to_wB, 
          rev_to_wC, wA_to_rev, wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
          eic_to_wC, partI_lock, ch3_lock, ch4_lock, fig_lock, ref_lock, msg_, 
          msg_w, msg_wr, msg_f, gotA_, gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
          gotC_f, msg_r, gotA, gotB, gotC, msg

vars == << pc, wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, wB_to_fig, wC_to_fig, 
           fig_to_wA, fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
           fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, rev_to_wA, rev_to_wB, 
           rev_to_wC, wA_to_rev, wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
           eic_to_wC, partI_lock, ch3_lock, ch4_lock, fig_lock, ref_lock, 
           msg_, msg_w, msg_wr, msg_f, gotA_, gotB_, gotC_, msg_fa, gotA_f, 
           gotB_f, gotC_f, msg_r, gotA, gotB, gotC, msg >>

ProcSet == ({WriterC}) \cup ({WriterB}) \cup ({WriterA}) \cup ({FigCreator}) \cup ({FactChecker}) \cup ({Reviewer}) \cup ({Eic})

Init == (* Global variables *)
        /\ wC_to_wB = <<>>
        /\ wB_to_wA = <<>>
        /\ wC_to_wA = <<>>
        /\ wA_to_fig = <<>>
        /\ wB_to_fig = <<>>
        /\ wC_to_fig = <<>>
        /\ fig_to_wA = <<>>
        /\ fig_to_wB = <<>>
        /\ fig_to_wC = <<>>
        /\ wA_to_fc = <<>>
        /\ wB_to_fc = <<>>
        /\ wC_to_fc = <<>>
        /\ fc_to_wA = <<>>
        /\ fc_to_wB = <<>>
        /\ fc_to_wC = <<>>
        /\ eic_to_rev = <<>>
        /\ rev_to_wA = <<>>
        /\ rev_to_wB = <<>>
        /\ rev_to_wC = <<>>
        /\ wA_to_rev = <<>>
        /\ wB_to_rev = <<>>
        /\ wC_to_rev = <<>>
        /\ eic_to_wA = <<>>
        /\ eic_to_wB = <<>>
        /\ eic_to_wC = <<>>
        /\ partI_lock = "FREE"
        /\ ch3_lock = "FREE"
        /\ ch4_lock = "FREE"
        /\ fig_lock = "FREE"
        /\ ref_lock = "FREE"
        (* Process writerC_proc *)
        /\ msg_ = [self \in {WriterC} |-> ""]
        (* Process writerB_proc *)
        /\ msg_w = [self \in {WriterB} |-> ""]
        (* Process writerA_proc *)
        /\ msg_wr = [self \in {WriterA} |-> ""]
        (* Process figCreator_proc *)
        /\ msg_f = [self \in {FigCreator} |-> ""]
        /\ gotA_ = [self \in {FigCreator} |-> FALSE]
        /\ gotB_ = [self \in {FigCreator} |-> FALSE]
        /\ gotC_ = [self \in {FigCreator} |-> FALSE]
        (* Process factChecker_proc *)
        /\ msg_fa = [self \in {FactChecker} |-> ""]
        /\ gotA_f = [self \in {FactChecker} |-> FALSE]
        /\ gotB_f = [self \in {FactChecker} |-> FALSE]
        /\ gotC_f = [self \in {FactChecker} |-> FALSE]
        (* Process reviewer_proc *)
        /\ msg_r = [self \in {Reviewer} |-> ""]
        /\ gotA = [self \in {Reviewer} |-> FALSE]
        /\ gotB = [self \in {Reviewer} |-> FALSE]
        /\ gotC = [self \in {Reviewer} |-> FALSE]
        (* Process eic_proc *)
        /\ msg = [self \in {Eic} |-> ""]
        /\ pc = [self \in ProcSet |-> CASE self \in {WriterC} -> "wc_write"
                                        [] self \in {WriterB} -> "wb_write"
                                        [] self \in {WriterA} -> "wa_write"
                                        [] self \in {FigCreator} -> "fg_collect"
                                        [] self \in {FactChecker} -> "fk_collect"
                                        [] self \in {Reviewer} -> "rv_assign"
                                        [] self \in {Eic} -> "ei_assign"]

wc_write(self) == /\ pc[self] = "wc_write"
                  /\ ch4_lock = "FREE"
                  /\ ch4_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "wc_write_done"]
                  /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                  wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                  fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                  fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                  rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                  wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                  eic_to_wC, partI_lock, ch3_lock, fig_lock, 
                                  ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                  gotB_, gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                  msg_r, gotA, gotB, gotC, msg >>

wc_write_done(self) == /\ pc[self] = "wc_write_done"
                       /\ ch4_lock' = "FREE"
                       /\ pc' = [pc EXCEPT ![self] = "wc_signal_b"]
                       /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                       wB_to_fig, wC_to_fig, fig_to_wA, 
                                       fig_to_wB, fig_to_wC, wA_to_fc, 
                                       wB_to_fc, wC_to_fc, fc_to_wA, fc_to_wB, 
                                       fc_to_wC, eic_to_rev, rev_to_wA, 
                                       rev_to_wB, rev_to_wC, wA_to_rev, 
                                       wB_to_rev, wC_to_rev, eic_to_wA, 
                                       eic_to_wB, eic_to_wC, partI_lock, 
                                       ch3_lock, fig_lock, ref_lock, msg_, 
                                       msg_w, msg_wr, msg_f, gotA_, gotB_, 
                                       gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                       msg_r, gotA, gotB, gotC, msg >>

wc_signal_b(self) == /\ pc[self] = "wc_signal_b"
                     /\ wC_to_wB' = Append(wC_to_wB, "stable")
                     /\ wC_to_wA' = Append(wC_to_wA, "stable")
                     /\ pc' = [pc EXCEPT ![self] = "wc_fig_req"]
                     /\ UNCHANGED << wB_to_wA, wA_to_fig, wB_to_fig, wC_to_fig, 
                                     fig_to_wA, fig_to_wB, fig_to_wC, wA_to_fc, 
                                     wB_to_fc, wC_to_fc, fc_to_wA, fc_to_wB, 
                                     fc_to_wC, eic_to_rev, rev_to_wA, 
                                     rev_to_wB, rev_to_wC, wA_to_rev, 
                                     wB_to_rev, wC_to_rev, eic_to_wA, 
                                     eic_to_wB, eic_to_wC, partI_lock, 
                                     ch3_lock, ch4_lock, fig_lock, ref_lock, 
                                     msg_, msg_w, msg_wr, msg_f, gotA_, gotB_, 
                                     gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                     msg_r, gotA, gotB, gotC, msg >>

wc_fig_req(self) == /\ pc[self] = "wc_fig_req"
                    /\ wC_to_fig' = Append(wC_to_fig, "fig_request")
                    /\ pc' = [pc EXCEPT ![self] = "wc_fig_wait"]
                    /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                    wB_to_fig, fig_to_wA, fig_to_wB, fig_to_wC, 
                                    wA_to_fc, wB_to_fc, wC_to_fc, fc_to_wA, 
                                    fc_to_wB, fc_to_wC, eic_to_rev, rev_to_wA, 
                                    rev_to_wB, rev_to_wC, wA_to_rev, wB_to_rev, 
                                    wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                    partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                    ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                    gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                    gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                    msg >>

wc_fig_wait(self) == /\ pc[self] = "wc_fig_wait"
                     /\ Len(fig_to_wC) > 0
                     /\ msg_' = [msg_ EXCEPT ![self] = Head(fig_to_wC)]
                     /\ fig_to_wC' = Tail(fig_to_wC)
                     /\ pc' = [pc EXCEPT ![self] = "wc_ref"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, wA_to_fc, wB_to_fc, wC_to_fc, 
                                     fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                     rev_to_wA, rev_to_wB, rev_to_wC, 
                                     wA_to_rev, wB_to_rev, wC_to_rev, 
                                     eic_to_wA, eic_to_wB, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_w, msg_wr, msg_f, gotA_, 
                                     gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                     gotC_f, msg_r, gotA, gotB, gotC, msg >>

wc_ref(self) == /\ pc[self] = "wc_ref"
                /\ ref_lock = "FREE"
                /\ ref_lock' = self
                /\ pc' = [pc EXCEPT ![self] = "wc_ref_done"]
                /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                eic_to_wC, partI_lock, ch3_lock, ch4_lock, 
                                fig_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                gotB_, gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                msg_r, gotA, gotB, gotC, msg >>

wc_ref_done(self) == /\ pc[self] = "wc_ref_done"
                     /\ ref_lock' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "wc_sub_fc"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, partI_lock, ch3_lock, ch4_lock, 
                                     fig_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

wc_sub_fc(self) == /\ pc[self] = "wc_sub_fc"
                   /\ wC_to_fc' = Append(wC_to_fc, "ready")
                   /\ pc' = [pc EXCEPT ![self] = "wc_fc_wait"]
                   /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                   wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                   fig_to_wC, wA_to_fc, wB_to_fc, fc_to_wA, 
                                   fc_to_wB, fc_to_wC, eic_to_rev, rev_to_wA, 
                                   rev_to_wB, rev_to_wC, wA_to_rev, wB_to_rev, 
                                   wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                   partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                   ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                   gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                   gotC_f, msg_r, gotA, gotB, gotC, msg >>

wc_fc_wait(self) == /\ pc[self] = "wc_fc_wait"
                    /\ Len(fc_to_wC) > 0
                    /\ msg_' = [msg_ EXCEPT ![self] = Head(fc_to_wC)]
                    /\ fc_to_wC' = Tail(fc_to_wC)
                    /\ pc' = [pc EXCEPT ![self] = "wc_fc_check"]
                    /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                    wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                    fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                    fc_to_wA, fc_to_wB, eic_to_rev, rev_to_wA, 
                                    rev_to_wB, rev_to_wC, wA_to_rev, wB_to_rev, 
                                    wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                    partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                    ref_lock, msg_w, msg_wr, msg_f, gotA_, 
                                    gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                    gotC_f, msg_r, gotA, gotB, gotC, msg >>

wc_fc_check(self) == /\ pc[self] = "wc_fc_check"
                     /\ IF msg_[self] = "revise"
                           THEN /\ pc' = [pc EXCEPT ![self] = "wc_fc_fix"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "wc_sub_rev"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, partI_lock, ch3_lock, ch4_lock, 
                                     fig_lock, ref_lock, msg_, msg_w, msg_wr, 
                                     msg_f, gotA_, gotB_, gotC_, msg_fa, 
                                     gotA_f, gotB_f, gotC_f, msg_r, gotA, gotB, 
                                     gotC, msg >>

wc_fc_fix(self) == /\ pc[self] = "wc_fc_fix"
                   /\ ch4_lock = "FREE"
                   /\ ch4_lock' = self
                   /\ pc' = [pc EXCEPT ![self] = "wc_fc_fix_done"]
                   /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                   wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                   fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                   fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                   rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                   wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                   eic_to_wC, partI_lock, ch3_lock, fig_lock, 
                                   ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                   gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                   gotC_f, msg_r, gotA, gotB, gotC, msg >>

wc_fc_fix_done(self) == /\ pc[self] = "wc_fc_fix_done"
                        /\ ch4_lock' = "FREE"
                        /\ pc' = [pc EXCEPT ![self] = "wc_sub_rev"]
                        /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, 
                                        wA_to_fig, wB_to_fig, wC_to_fig, 
                                        fig_to_wA, fig_to_wB, fig_to_wC, 
                                        wA_to_fc, wB_to_fc, wC_to_fc, fc_to_wA, 
                                        fc_to_wB, fc_to_wC, eic_to_rev, 
                                        rev_to_wA, rev_to_wB, rev_to_wC, 
                                        wA_to_rev, wB_to_rev, wC_to_rev, 
                                        eic_to_wA, eic_to_wB, eic_to_wC, 
                                        partI_lock, ch3_lock, fig_lock, 
                                        ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                        gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                        gotB_f, gotC_f, msg_r, gotA, gotB, 
                                        gotC, msg >>

wc_sub_rev(self) == /\ pc[self] = "wc_sub_rev"
                    /\ wC_to_rev' = Append(wC_to_rev, "ready")
                    /\ pc' = [pc EXCEPT ![self] = "wc_rev_wait"]
                    /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                    wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                    fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                    fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                    rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                    wB_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                    partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                    ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                    gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                    gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                    msg >>

wc_rev_wait(self) == /\ pc[self] = "wc_rev_wait"
                     /\ Len(rev_to_wC) > 0
                     /\ msg_' = [msg_ EXCEPT ![self] = Head(rev_to_wC)]
                     /\ rev_to_wC' = Tail(rev_to_wC)
                     /\ pc' = [pc EXCEPT ![self] = "wc_rev_check"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     wA_to_rev, wB_to_rev, wC_to_rev, 
                                     eic_to_wA, eic_to_wB, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_w, msg_wr, msg_f, gotA_, 
                                     gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                     gotC_f, msg_r, gotA, gotB, gotC, msg >>

wc_rev_check(self) == /\ pc[self] = "wc_rev_check"
                      /\ IF msg_[self] = "major"
                            THEN /\ pc' = [pc EXCEPT ![self] = "wc_major_fix"]
                            ELSE /\ IF msg_[self] = "minor"
                                       THEN /\ pc' = [pc EXCEPT ![self] = "wc_minor_fix"]
                                       ELSE /\ pc' = [pc EXCEPT ![self] = "wc_eic_wait"]
                      /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                      wB_to_fig, wC_to_fig, fig_to_wA, 
                                      fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                      wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                      eic_to_rev, rev_to_wA, rev_to_wB, 
                                      rev_to_wC, wA_to_rev, wB_to_rev, 
                                      wC_to_rev, eic_to_wA, eic_to_wB, 
                                      eic_to_wC, partI_lock, ch3_lock, 
                                      ch4_lock, fig_lock, ref_lock, msg_, 
                                      msg_w, msg_wr, msg_f, gotA_, gotB_, 
                                      gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                      msg_r, gotA, gotB, gotC, msg >>

wc_major_fix(self) == /\ pc[self] = "wc_major_fix"
                      /\ ch4_lock = "FREE"
                      /\ ch4_lock' = self
                      /\ pc' = [pc EXCEPT ![self] = "wc_major_done"]
                      /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                      wB_to_fig, wC_to_fig, fig_to_wA, 
                                      fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                      wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                      eic_to_rev, rev_to_wA, rev_to_wB, 
                                      rev_to_wC, wA_to_rev, wB_to_rev, 
                                      wC_to_rev, eic_to_wA, eic_to_wB, 
                                      eic_to_wC, partI_lock, ch3_lock, 
                                      fig_lock, ref_lock, msg_, msg_w, msg_wr, 
                                      msg_f, gotA_, gotB_, gotC_, msg_fa, 
                                      gotA_f, gotB_f, gotC_f, msg_r, gotA, 
                                      gotB, gotC, msg >>

wc_major_done(self) == /\ pc[self] = "wc_major_done"
                       /\ ch4_lock' = "FREE"
                       /\ wC_to_rev' = Append(wC_to_rev, "revised")
                       /\ pc' = [pc EXCEPT ![self] = "wc_rerev_wait"]
                       /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                       wB_to_fig, wC_to_fig, fig_to_wA, 
                                       fig_to_wB, fig_to_wC, wA_to_fc, 
                                       wB_to_fc, wC_to_fc, fc_to_wA, fc_to_wB, 
                                       fc_to_wC, eic_to_rev, rev_to_wA, 
                                       rev_to_wB, rev_to_wC, wA_to_rev, 
                                       wB_to_rev, eic_to_wA, eic_to_wB, 
                                       eic_to_wC, partI_lock, ch3_lock, 
                                       fig_lock, ref_lock, msg_, msg_w, msg_wr, 
                                       msg_f, gotA_, gotB_, gotC_, msg_fa, 
                                       gotA_f, gotB_f, gotC_f, msg_r, gotA, 
                                       gotB, gotC, msg >>

wc_rerev_wait(self) == /\ pc[self] = "wc_rerev_wait"
                       /\ Len(rev_to_wC) > 0
                       /\ msg_' = [msg_ EXCEPT ![self] = Head(rev_to_wC)]
                       /\ rev_to_wC' = Tail(rev_to_wC)
                       /\ pc' = [pc EXCEPT ![self] = "wc_eic_wait"]
                       /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                       wB_to_fig, wC_to_fig, fig_to_wA, 
                                       fig_to_wB, fig_to_wC, wA_to_fc, 
                                       wB_to_fc, wC_to_fc, fc_to_wA, fc_to_wB, 
                                       fc_to_wC, eic_to_rev, rev_to_wA, 
                                       rev_to_wB, wA_to_rev, wB_to_rev, 
                                       wC_to_rev, eic_to_wA, eic_to_wB, 
                                       eic_to_wC, partI_lock, ch3_lock, 
                                       ch4_lock, fig_lock, ref_lock, msg_w, 
                                       msg_wr, msg_f, gotA_, gotB_, gotC_, 
                                       msg_fa, gotA_f, gotB_f, gotC_f, msg_r, 
                                       gotA, gotB, gotC, msg >>

wc_minor_fix(self) == /\ pc[self] = "wc_minor_fix"
                      /\ ch4_lock = "FREE"
                      /\ ch4_lock' = self
                      /\ pc' = [pc EXCEPT ![self] = "wc_minor_done"]
                      /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                      wB_to_fig, wC_to_fig, fig_to_wA, 
                                      fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                      wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                      eic_to_rev, rev_to_wA, rev_to_wB, 
                                      rev_to_wC, wA_to_rev, wB_to_rev, 
                                      wC_to_rev, eic_to_wA, eic_to_wB, 
                                      eic_to_wC, partI_lock, ch3_lock, 
                                      fig_lock, ref_lock, msg_, msg_w, msg_wr, 
                                      msg_f, gotA_, gotB_, gotC_, msg_fa, 
                                      gotA_f, gotB_f, gotC_f, msg_r, gotA, 
                                      gotB, gotC, msg >>

wc_minor_done(self) == /\ pc[self] = "wc_minor_done"
                       /\ ch4_lock' = "FREE"
                       /\ pc' = [pc EXCEPT ![self] = "wc_eic_wait"]
                       /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                       wB_to_fig, wC_to_fig, fig_to_wA, 
                                       fig_to_wB, fig_to_wC, wA_to_fc, 
                                       wB_to_fc, wC_to_fc, fc_to_wA, fc_to_wB, 
                                       fc_to_wC, eic_to_rev, rev_to_wA, 
                                       rev_to_wB, rev_to_wC, wA_to_rev, 
                                       wB_to_rev, wC_to_rev, eic_to_wA, 
                                       eic_to_wB, eic_to_wC, partI_lock, 
                                       ch3_lock, fig_lock, ref_lock, msg_, 
                                       msg_w, msg_wr, msg_f, gotA_, gotB_, 
                                       gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                       msg_r, gotA, gotB, gotC, msg >>

wc_eic_wait(self) == /\ pc[self] = "wc_eic_wait"
                     /\ Len(eic_to_wC) > 0
                     /\ msg_' = [msg_ EXCEPT ![self] = Head(eic_to_wC)]
                     /\ eic_to_wC' = Tail(eic_to_wC)
                     /\ pc' = [pc EXCEPT ![self] = "wc_eic_apply"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_w, msg_wr, msg_f, gotA_, 
                                     gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                     gotC_f, msg_r, gotA, gotB, gotC, msg >>

wc_eic_apply(self) == /\ pc[self] = "wc_eic_apply"
                      /\ ch4_lock = "FREE"
                      /\ ch4_lock' = self
                      /\ pc' = [pc EXCEPT ![self] = "wc_eic_done"]
                      /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                      wB_to_fig, wC_to_fig, fig_to_wA, 
                                      fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                      wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                      eic_to_rev, rev_to_wA, rev_to_wB, 
                                      rev_to_wC, wA_to_rev, wB_to_rev, 
                                      wC_to_rev, eic_to_wA, eic_to_wB, 
                                      eic_to_wC, partI_lock, ch3_lock, 
                                      fig_lock, ref_lock, msg_, msg_w, msg_wr, 
                                      msg_f, gotA_, gotB_, gotC_, msg_fa, 
                                      gotA_f, gotB_f, gotC_f, msg_r, gotA, 
                                      gotB, gotC, msg >>

wc_eic_done(self) == /\ pc[self] = "wc_eic_done"
                     /\ ch4_lock' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "Done"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, partI_lock, ch3_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

writerC_proc(self) == wc_write(self) \/ wc_write_done(self)
                         \/ wc_signal_b(self) \/ wc_fig_req(self)
                         \/ wc_fig_wait(self) \/ wc_ref(self)
                         \/ wc_ref_done(self) \/ wc_sub_fc(self)
                         \/ wc_fc_wait(self) \/ wc_fc_check(self)
                         \/ wc_fc_fix(self) \/ wc_fc_fix_done(self)
                         \/ wc_sub_rev(self) \/ wc_rev_wait(self)
                         \/ wc_rev_check(self) \/ wc_major_fix(self)
                         \/ wc_major_done(self) \/ wc_rerev_wait(self)
                         \/ wc_minor_fix(self) \/ wc_minor_done(self)
                         \/ wc_eic_wait(self) \/ wc_eic_apply(self)
                         \/ wc_eic_done(self)

wb_write(self) == /\ pc[self] = "wb_write"
                  /\ ch3_lock = "FREE"
                  /\ ch3_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "wb_init_done"]
                  /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                  wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                  fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                  fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                  rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                  wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                  eic_to_wC, partI_lock, ch4_lock, fig_lock, 
                                  ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                  gotB_, gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                  msg_r, gotA, gotB, gotC, msg >>

wb_init_done(self) == /\ pc[self] = "wb_init_done"
                      /\ ch3_lock' = "FREE"
                      /\ pc' = [pc EXCEPT ![self] = "wb_wait_c"]
                      /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                      wB_to_fig, wC_to_fig, fig_to_wA, 
                                      fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                      wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                      eic_to_rev, rev_to_wA, rev_to_wB, 
                                      rev_to_wC, wA_to_rev, wB_to_rev, 
                                      wC_to_rev, eic_to_wA, eic_to_wB, 
                                      eic_to_wC, partI_lock, ch4_lock, 
                                      fig_lock, ref_lock, msg_, msg_w, msg_wr, 
                                      msg_f, gotA_, gotB_, gotC_, msg_fa, 
                                      gotA_f, gotB_f, gotC_f, msg_r, gotA, 
                                      gotB, gotC, msg >>

wb_wait_c(self) == /\ pc[self] = "wb_wait_c"
                   /\ Len(wC_to_wB) > 0
                   /\ msg_w' = [msg_w EXCEPT ![self] = Head(wC_to_wB)]
                   /\ wC_to_wB' = Tail(wC_to_wB)
                   /\ pc' = [pc EXCEPT ![self] = "wb_finalize"]
                   /\ UNCHANGED << wB_to_wA, wC_to_wA, wA_to_fig, wB_to_fig, 
                                   wC_to_fig, fig_to_wA, fig_to_wB, fig_to_wC, 
                                   wA_to_fc, wB_to_fc, wC_to_fc, fc_to_wA, 
                                   fc_to_wB, fc_to_wC, eic_to_rev, rev_to_wA, 
                                   rev_to_wB, rev_to_wC, wA_to_rev, wB_to_rev, 
                                   wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                   partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                   ref_lock, msg_, msg_wr, msg_f, gotA_, gotB_, 
                                   gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                   msg_r, gotA, gotB, gotC, msg >>

wb_finalize(self) == /\ pc[self] = "wb_finalize"
                     /\ ch3_lock = "FREE"
                     /\ ch3_lock' = self
                     /\ pc' = [pc EXCEPT ![self] = "wb_fin_done"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, partI_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

wb_fin_done(self) == /\ pc[self] = "wb_fin_done"
                     /\ ch3_lock' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "wb_signal_a"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, partI_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

wb_signal_a(self) == /\ pc[self] = "wb_signal_a"
                     /\ wB_to_wA' = Append(wB_to_wA, "stable")
                     /\ pc' = [pc EXCEPT ![self] = "wb_fig_req"]
                     /\ UNCHANGED << wC_to_wB, wC_to_wA, wA_to_fig, wB_to_fig, 
                                     wC_to_fig, fig_to_wA, fig_to_wB, 
                                     fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                     fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                     rev_to_wA, rev_to_wB, rev_to_wC, 
                                     wA_to_rev, wB_to_rev, wC_to_rev, 
                                     eic_to_wA, eic_to_wB, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

wb_fig_req(self) == /\ pc[self] = "wb_fig_req"
                    /\ wB_to_fig' = Append(wB_to_fig, "fig_request")
                    /\ pc' = [pc EXCEPT ![self] = "wb_fig_wait"]
                    /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                    wC_to_fig, fig_to_wA, fig_to_wB, fig_to_wC, 
                                    wA_to_fc, wB_to_fc, wC_to_fc, fc_to_wA, 
                                    fc_to_wB, fc_to_wC, eic_to_rev, rev_to_wA, 
                                    rev_to_wB, rev_to_wC, wA_to_rev, wB_to_rev, 
                                    wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                    partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                    ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                    gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                    gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                    msg >>

wb_fig_wait(self) == /\ pc[self] = "wb_fig_wait"
                     /\ Len(fig_to_wB) > 0
                     /\ msg_w' = [msg_w EXCEPT ![self] = Head(fig_to_wB)]
                     /\ fig_to_wB' = Tail(fig_to_wB)
                     /\ pc' = [pc EXCEPT ![self] = "wb_ref"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                     fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                     rev_to_wA, rev_to_wB, rev_to_wC, 
                                     wA_to_rev, wB_to_rev, wC_to_rev, 
                                     eic_to_wA, eic_to_wB, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_wr, msg_f, gotA_, 
                                     gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                     gotC_f, msg_r, gotA, gotB, gotC, msg >>

wb_ref(self) == /\ pc[self] = "wb_ref"
                /\ ref_lock = "FREE"
                /\ ref_lock' = self
                /\ pc' = [pc EXCEPT ![self] = "wb_ref_done"]
                /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                eic_to_wC, partI_lock, ch3_lock, ch4_lock, 
                                fig_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                gotB_, gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                msg_r, gotA, gotB, gotC, msg >>

wb_ref_done(self) == /\ pc[self] = "wb_ref_done"
                     /\ ref_lock' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "wb_sub_fc"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, partI_lock, ch3_lock, ch4_lock, 
                                     fig_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

wb_sub_fc(self) == /\ pc[self] = "wb_sub_fc"
                   /\ wB_to_fc' = Append(wB_to_fc, "ready")
                   /\ pc' = [pc EXCEPT ![self] = "wb_fc_wait"]
                   /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                   wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                   fig_to_wC, wA_to_fc, wC_to_fc, fc_to_wA, 
                                   fc_to_wB, fc_to_wC, eic_to_rev, rev_to_wA, 
                                   rev_to_wB, rev_to_wC, wA_to_rev, wB_to_rev, 
                                   wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                   partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                   ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                   gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                   gotC_f, msg_r, gotA, gotB, gotC, msg >>

wb_fc_wait(self) == /\ pc[self] = "wb_fc_wait"
                    /\ Len(fc_to_wB) > 0
                    /\ msg_w' = [msg_w EXCEPT ![self] = Head(fc_to_wB)]
                    /\ fc_to_wB' = Tail(fc_to_wB)
                    /\ pc' = [pc EXCEPT ![self] = "wb_fc_check"]
                    /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                    wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                    fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                    fc_to_wA, fc_to_wC, eic_to_rev, rev_to_wA, 
                                    rev_to_wB, rev_to_wC, wA_to_rev, wB_to_rev, 
                                    wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                    partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                    ref_lock, msg_, msg_wr, msg_f, gotA_, 
                                    gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                    gotC_f, msg_r, gotA, gotB, gotC, msg >>

wb_fc_check(self) == /\ pc[self] = "wb_fc_check"
                     /\ IF msg_w[self] = "revise"
                           THEN /\ pc' = [pc EXCEPT ![self] = "wb_fc_fix"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "wb_sub_rev"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, partI_lock, ch3_lock, ch4_lock, 
                                     fig_lock, ref_lock, msg_, msg_w, msg_wr, 
                                     msg_f, gotA_, gotB_, gotC_, msg_fa, 
                                     gotA_f, gotB_f, gotC_f, msg_r, gotA, gotB, 
                                     gotC, msg >>

wb_fc_fix(self) == /\ pc[self] = "wb_fc_fix"
                   /\ ch3_lock = "FREE"
                   /\ ch3_lock' = self
                   /\ pc' = [pc EXCEPT ![self] = "wb_fc_fix_done"]
                   /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                   wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                   fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                   fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                   rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                   wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                   eic_to_wC, partI_lock, ch4_lock, fig_lock, 
                                   ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                   gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                   gotC_f, msg_r, gotA, gotB, gotC, msg >>

wb_fc_fix_done(self) == /\ pc[self] = "wb_fc_fix_done"
                        /\ ch3_lock' = "FREE"
                        /\ pc' = [pc EXCEPT ![self] = "wb_sub_rev"]
                        /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, 
                                        wA_to_fig, wB_to_fig, wC_to_fig, 
                                        fig_to_wA, fig_to_wB, fig_to_wC, 
                                        wA_to_fc, wB_to_fc, wC_to_fc, fc_to_wA, 
                                        fc_to_wB, fc_to_wC, eic_to_rev, 
                                        rev_to_wA, rev_to_wB, rev_to_wC, 
                                        wA_to_rev, wB_to_rev, wC_to_rev, 
                                        eic_to_wA, eic_to_wB, eic_to_wC, 
                                        partI_lock, ch4_lock, fig_lock, 
                                        ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                        gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                        gotB_f, gotC_f, msg_r, gotA, gotB, 
                                        gotC, msg >>

wb_sub_rev(self) == /\ pc[self] = "wb_sub_rev"
                    /\ wB_to_rev' = Append(wB_to_rev, "ready")
                    /\ pc' = [pc EXCEPT ![self] = "wb_rev_wait"]
                    /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                    wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                    fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                    fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                    rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                    wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                    partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                    ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                    gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                    gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                    msg >>

wb_rev_wait(self) == /\ pc[self] = "wb_rev_wait"
                     /\ Len(rev_to_wB) > 0
                     /\ msg_w' = [msg_w EXCEPT ![self] = Head(rev_to_wB)]
                     /\ rev_to_wB' = Tail(rev_to_wB)
                     /\ pc' = [pc EXCEPT ![self] = "wb_rev_check"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wC, 
                                     wA_to_rev, wB_to_rev, wC_to_rev, 
                                     eic_to_wA, eic_to_wB, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_wr, msg_f, gotA_, 
                                     gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                     gotC_f, msg_r, gotA, gotB, gotC, msg >>

wb_rev_check(self) == /\ pc[self] = "wb_rev_check"
                      /\ IF msg_w[self] = "major"
                            THEN /\ pc' = [pc EXCEPT ![self] = "wb_major_fix"]
                            ELSE /\ IF msg_w[self] = "minor"
                                       THEN /\ pc' = [pc EXCEPT ![self] = "wb_minor_fix"]
                                       ELSE /\ pc' = [pc EXCEPT ![self] = "wb_eic_wait"]
                      /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                      wB_to_fig, wC_to_fig, fig_to_wA, 
                                      fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                      wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                      eic_to_rev, rev_to_wA, rev_to_wB, 
                                      rev_to_wC, wA_to_rev, wB_to_rev, 
                                      wC_to_rev, eic_to_wA, eic_to_wB, 
                                      eic_to_wC, partI_lock, ch3_lock, 
                                      ch4_lock, fig_lock, ref_lock, msg_, 
                                      msg_w, msg_wr, msg_f, gotA_, gotB_, 
                                      gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                      msg_r, gotA, gotB, gotC, msg >>

wb_major_fix(self) == /\ pc[self] = "wb_major_fix"
                      /\ ch3_lock = "FREE"
                      /\ ch3_lock' = self
                      /\ pc' = [pc EXCEPT ![self] = "wb_major_done"]
                      /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                      wB_to_fig, wC_to_fig, fig_to_wA, 
                                      fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                      wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                      eic_to_rev, rev_to_wA, rev_to_wB, 
                                      rev_to_wC, wA_to_rev, wB_to_rev, 
                                      wC_to_rev, eic_to_wA, eic_to_wB, 
                                      eic_to_wC, partI_lock, ch4_lock, 
                                      fig_lock, ref_lock, msg_, msg_w, msg_wr, 
                                      msg_f, gotA_, gotB_, gotC_, msg_fa, 
                                      gotA_f, gotB_f, gotC_f, msg_r, gotA, 
                                      gotB, gotC, msg >>

wb_major_done(self) == /\ pc[self] = "wb_major_done"
                       /\ ch3_lock' = "FREE"
                       /\ wB_to_rev' = Append(wB_to_rev, "revised")
                       /\ pc' = [pc EXCEPT ![self] = "wb_rerev_wait"]
                       /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                       wB_to_fig, wC_to_fig, fig_to_wA, 
                                       fig_to_wB, fig_to_wC, wA_to_fc, 
                                       wB_to_fc, wC_to_fc, fc_to_wA, fc_to_wB, 
                                       fc_to_wC, eic_to_rev, rev_to_wA, 
                                       rev_to_wB, rev_to_wC, wA_to_rev, 
                                       wC_to_rev, eic_to_wA, eic_to_wB, 
                                       eic_to_wC, partI_lock, ch4_lock, 
                                       fig_lock, ref_lock, msg_, msg_w, msg_wr, 
                                       msg_f, gotA_, gotB_, gotC_, msg_fa, 
                                       gotA_f, gotB_f, gotC_f, msg_r, gotA, 
                                       gotB, gotC, msg >>

wb_rerev_wait(self) == /\ pc[self] = "wb_rerev_wait"
                       /\ Len(rev_to_wB) > 0
                       /\ msg_w' = [msg_w EXCEPT ![self] = Head(rev_to_wB)]
                       /\ rev_to_wB' = Tail(rev_to_wB)
                       /\ pc' = [pc EXCEPT ![self] = "wb_eic_wait"]
                       /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                       wB_to_fig, wC_to_fig, fig_to_wA, 
                                       fig_to_wB, fig_to_wC, wA_to_fc, 
                                       wB_to_fc, wC_to_fc, fc_to_wA, fc_to_wB, 
                                       fc_to_wC, eic_to_rev, rev_to_wA, 
                                       rev_to_wC, wA_to_rev, wB_to_rev, 
                                       wC_to_rev, eic_to_wA, eic_to_wB, 
                                       eic_to_wC, partI_lock, ch3_lock, 
                                       ch4_lock, fig_lock, ref_lock, msg_, 
                                       msg_wr, msg_f, gotA_, gotB_, gotC_, 
                                       msg_fa, gotA_f, gotB_f, gotC_f, msg_r, 
                                       gotA, gotB, gotC, msg >>

wb_minor_fix(self) == /\ pc[self] = "wb_minor_fix"
                      /\ ch3_lock = "FREE"
                      /\ ch3_lock' = self
                      /\ pc' = [pc EXCEPT ![self] = "wb_minor_done"]
                      /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                      wB_to_fig, wC_to_fig, fig_to_wA, 
                                      fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                      wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                      eic_to_rev, rev_to_wA, rev_to_wB, 
                                      rev_to_wC, wA_to_rev, wB_to_rev, 
                                      wC_to_rev, eic_to_wA, eic_to_wB, 
                                      eic_to_wC, partI_lock, ch4_lock, 
                                      fig_lock, ref_lock, msg_, msg_w, msg_wr, 
                                      msg_f, gotA_, gotB_, gotC_, msg_fa, 
                                      gotA_f, gotB_f, gotC_f, msg_r, gotA, 
                                      gotB, gotC, msg >>

wb_minor_done(self) == /\ pc[self] = "wb_minor_done"
                       /\ ch3_lock' = "FREE"
                       /\ pc' = [pc EXCEPT ![self] = "wb_eic_wait"]
                       /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                       wB_to_fig, wC_to_fig, fig_to_wA, 
                                       fig_to_wB, fig_to_wC, wA_to_fc, 
                                       wB_to_fc, wC_to_fc, fc_to_wA, fc_to_wB, 
                                       fc_to_wC, eic_to_rev, rev_to_wA, 
                                       rev_to_wB, rev_to_wC, wA_to_rev, 
                                       wB_to_rev, wC_to_rev, eic_to_wA, 
                                       eic_to_wB, eic_to_wC, partI_lock, 
                                       ch4_lock, fig_lock, ref_lock, msg_, 
                                       msg_w, msg_wr, msg_f, gotA_, gotB_, 
                                       gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                       msg_r, gotA, gotB, gotC, msg >>

wb_eic_wait(self) == /\ pc[self] = "wb_eic_wait"
                     /\ Len(eic_to_wB) > 0
                     /\ msg_w' = [msg_w EXCEPT ![self] = Head(eic_to_wB)]
                     /\ eic_to_wB' = Tail(eic_to_wB)
                     /\ pc' = [pc EXCEPT ![self] = "wb_eic_apply"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_wr, msg_f, gotA_, 
                                     gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                     gotC_f, msg_r, gotA, gotB, gotC, msg >>

wb_eic_apply(self) == /\ pc[self] = "wb_eic_apply"
                      /\ ch3_lock = "FREE"
                      /\ ch3_lock' = self
                      /\ pc' = [pc EXCEPT ![self] = "wb_eic_done"]
                      /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                      wB_to_fig, wC_to_fig, fig_to_wA, 
                                      fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                      wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                      eic_to_rev, rev_to_wA, rev_to_wB, 
                                      rev_to_wC, wA_to_rev, wB_to_rev, 
                                      wC_to_rev, eic_to_wA, eic_to_wB, 
                                      eic_to_wC, partI_lock, ch4_lock, 
                                      fig_lock, ref_lock, msg_, msg_w, msg_wr, 
                                      msg_f, gotA_, gotB_, gotC_, msg_fa, 
                                      gotA_f, gotB_f, gotC_f, msg_r, gotA, 
                                      gotB, gotC, msg >>

wb_eic_done(self) == /\ pc[self] = "wb_eic_done"
                     /\ ch3_lock' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "Done"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, partI_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

writerB_proc(self) == wb_write(self) \/ wb_init_done(self)
                         \/ wb_wait_c(self) \/ wb_finalize(self)
                         \/ wb_fin_done(self) \/ wb_signal_a(self)
                         \/ wb_fig_req(self) \/ wb_fig_wait(self)
                         \/ wb_ref(self) \/ wb_ref_done(self)
                         \/ wb_sub_fc(self) \/ wb_fc_wait(self)
                         \/ wb_fc_check(self) \/ wb_fc_fix(self)
                         \/ wb_fc_fix_done(self) \/ wb_sub_rev(self)
                         \/ wb_rev_wait(self) \/ wb_rev_check(self)
                         \/ wb_major_fix(self) \/ wb_major_done(self)
                         \/ wb_rerev_wait(self) \/ wb_minor_fix(self)
                         \/ wb_minor_done(self) \/ wb_eic_wait(self)
                         \/ wb_eic_apply(self) \/ wb_eic_done(self)

wa_write(self) == /\ pc[self] = "wa_write"
                  /\ partI_lock = "FREE"
                  /\ partI_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "wa_init_done"]
                  /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                  wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                  fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                  fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                  rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                  wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                  eic_to_wC, ch3_lock, ch4_lock, fig_lock, 
                                  ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                  gotB_, gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                  msg_r, gotA, gotB, gotC, msg >>

wa_init_done(self) == /\ pc[self] = "wa_init_done"
                      /\ partI_lock' = "FREE"
                      /\ pc' = [pc EXCEPT ![self] = "wa_wait_b"]
                      /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                      wB_to_fig, wC_to_fig, fig_to_wA, 
                                      fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                      wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                      eic_to_rev, rev_to_wA, rev_to_wB, 
                                      rev_to_wC, wA_to_rev, wB_to_rev, 
                                      wC_to_rev, eic_to_wA, eic_to_wB, 
                                      eic_to_wC, ch3_lock, ch4_lock, fig_lock, 
                                      ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                      gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                      gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                      msg >>

wa_wait_b(self) == /\ pc[self] = "wa_wait_b"
                   /\ Len(wB_to_wA) > 0
                   /\ msg_wr' = [msg_wr EXCEPT ![self] = Head(wB_to_wA)]
                   /\ wB_to_wA' = Tail(wB_to_wA)
                   /\ pc' = [pc EXCEPT ![self] = "wa_wait_c"]
                   /\ UNCHANGED << wC_to_wB, wC_to_wA, wA_to_fig, wB_to_fig, 
                                   wC_to_fig, fig_to_wA, fig_to_wB, fig_to_wC, 
                                   wA_to_fc, wB_to_fc, wC_to_fc, fc_to_wA, 
                                   fc_to_wB, fc_to_wC, eic_to_rev, rev_to_wA, 
                                   rev_to_wB, rev_to_wC, wA_to_rev, wB_to_rev, 
                                   wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                   partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                   ref_lock, msg_, msg_w, msg_f, gotA_, gotB_, 
                                   gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                   msg_r, gotA, gotB, gotC, msg >>

wa_wait_c(self) == /\ pc[self] = "wa_wait_c"
                   /\ Len(wC_to_wA) > 0
                   /\ msg_wr' = [msg_wr EXCEPT ![self] = Head(wC_to_wA)]
                   /\ wC_to_wA' = Tail(wC_to_wA)
                   /\ pc' = [pc EXCEPT ![self] = "wa_finalize"]
                   /\ UNCHANGED << wC_to_wB, wB_to_wA, wA_to_fig, wB_to_fig, 
                                   wC_to_fig, fig_to_wA, fig_to_wB, fig_to_wC, 
                                   wA_to_fc, wB_to_fc, wC_to_fc, fc_to_wA, 
                                   fc_to_wB, fc_to_wC, eic_to_rev, rev_to_wA, 
                                   rev_to_wB, rev_to_wC, wA_to_rev, wB_to_rev, 
                                   wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                   partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                   ref_lock, msg_, msg_w, msg_f, gotA_, gotB_, 
                                   gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                   msg_r, gotA, gotB, gotC, msg >>

wa_finalize(self) == /\ pc[self] = "wa_finalize"
                     /\ partI_lock = "FREE"
                     /\ partI_lock' = self
                     /\ pc' = [pc EXCEPT ![self] = "wa_fin_done"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

wa_fin_done(self) == /\ pc[self] = "wa_fin_done"
                     /\ partI_lock' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "wa_fig_req"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

wa_fig_req(self) == /\ pc[self] = "wa_fig_req"
                    /\ wA_to_fig' = Append(wA_to_fig, "fig_request")
                    /\ pc' = [pc EXCEPT ![self] = "wa_fig_wait"]
                    /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wB_to_fig, 
                                    wC_to_fig, fig_to_wA, fig_to_wB, fig_to_wC, 
                                    wA_to_fc, wB_to_fc, wC_to_fc, fc_to_wA, 
                                    fc_to_wB, fc_to_wC, eic_to_rev, rev_to_wA, 
                                    rev_to_wB, rev_to_wC, wA_to_rev, wB_to_rev, 
                                    wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                    partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                    ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                    gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                    gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                    msg >>

wa_fig_wait(self) == /\ pc[self] = "wa_fig_wait"
                     /\ Len(fig_to_wA) > 0
                     /\ msg_wr' = [msg_wr EXCEPT ![self] = Head(fig_to_wA)]
                     /\ fig_to_wA' = Tail(fig_to_wA)
                     /\ pc' = [pc EXCEPT ![self] = "wa_ref"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wB, 
                                     fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                     fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                     rev_to_wA, rev_to_wB, rev_to_wC, 
                                     wA_to_rev, wB_to_rev, wC_to_rev, 
                                     eic_to_wA, eic_to_wB, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_f, gotA_, 
                                     gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                     gotC_f, msg_r, gotA, gotB, gotC, msg >>

wa_ref(self) == /\ pc[self] = "wa_ref"
                /\ ref_lock = "FREE"
                /\ ref_lock' = self
                /\ pc' = [pc EXCEPT ![self] = "wa_ref_done"]
                /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                eic_to_wC, partI_lock, ch3_lock, ch4_lock, 
                                fig_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                gotB_, gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                msg_r, gotA, gotB, gotC, msg >>

wa_ref_done(self) == /\ pc[self] = "wa_ref_done"
                     /\ ref_lock' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "wa_sub_fc"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, partI_lock, ch3_lock, ch4_lock, 
                                     fig_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

wa_sub_fc(self) == /\ pc[self] = "wa_sub_fc"
                   /\ wA_to_fc' = Append(wA_to_fc, "ready")
                   /\ pc' = [pc EXCEPT ![self] = "wa_fc_wait"]
                   /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                   wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                   fig_to_wC, wB_to_fc, wC_to_fc, fc_to_wA, 
                                   fc_to_wB, fc_to_wC, eic_to_rev, rev_to_wA, 
                                   rev_to_wB, rev_to_wC, wA_to_rev, wB_to_rev, 
                                   wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                   partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                   ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                   gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                   gotC_f, msg_r, gotA, gotB, gotC, msg >>

wa_fc_wait(self) == /\ pc[self] = "wa_fc_wait"
                    /\ Len(fc_to_wA) > 0
                    /\ msg_wr' = [msg_wr EXCEPT ![self] = Head(fc_to_wA)]
                    /\ fc_to_wA' = Tail(fc_to_wA)
                    /\ pc' = [pc EXCEPT ![self] = "wa_fc_check"]
                    /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                    wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                    fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                    fc_to_wB, fc_to_wC, eic_to_rev, rev_to_wA, 
                                    rev_to_wB, rev_to_wC, wA_to_rev, wB_to_rev, 
                                    wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                    partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                    ref_lock, msg_, msg_w, msg_f, gotA_, gotB_, 
                                    gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                    msg_r, gotA, gotB, gotC, msg >>

wa_fc_check(self) == /\ pc[self] = "wa_fc_check"
                     /\ IF msg_wr[self] = "revise"
                           THEN /\ pc' = [pc EXCEPT ![self] = "wa_fc_fix"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "wa_sub_rev"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, partI_lock, ch3_lock, ch4_lock, 
                                     fig_lock, ref_lock, msg_, msg_w, msg_wr, 
                                     msg_f, gotA_, gotB_, gotC_, msg_fa, 
                                     gotA_f, gotB_f, gotC_f, msg_r, gotA, gotB, 
                                     gotC, msg >>

wa_fc_fix(self) == /\ pc[self] = "wa_fc_fix"
                   /\ partI_lock = "FREE"
                   /\ partI_lock' = self
                   /\ pc' = [pc EXCEPT ![self] = "wa_fc_fix_done"]
                   /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                   wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                   fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                   fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                   rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                   wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                   eic_to_wC, ch3_lock, ch4_lock, fig_lock, 
                                   ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                   gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                   gotC_f, msg_r, gotA, gotB, gotC, msg >>

wa_fc_fix_done(self) == /\ pc[self] = "wa_fc_fix_done"
                        /\ partI_lock' = "FREE"
                        /\ pc' = [pc EXCEPT ![self] = "wa_sub_rev"]
                        /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, 
                                        wA_to_fig, wB_to_fig, wC_to_fig, 
                                        fig_to_wA, fig_to_wB, fig_to_wC, 
                                        wA_to_fc, wB_to_fc, wC_to_fc, fc_to_wA, 
                                        fc_to_wB, fc_to_wC, eic_to_rev, 
                                        rev_to_wA, rev_to_wB, rev_to_wC, 
                                        wA_to_rev, wB_to_rev, wC_to_rev, 
                                        eic_to_wA, eic_to_wB, eic_to_wC, 
                                        ch3_lock, ch4_lock, fig_lock, ref_lock, 
                                        msg_, msg_w, msg_wr, msg_f, gotA_, 
                                        gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                        gotC_f, msg_r, gotA, gotB, gotC, msg >>

wa_sub_rev(self) == /\ pc[self] = "wa_sub_rev"
                    /\ wA_to_rev' = Append(wA_to_rev, "ready")
                    /\ pc' = [pc EXCEPT ![self] = "wa_rev_wait"]
                    /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                    wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                    fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                    fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                    rev_to_wA, rev_to_wB, rev_to_wC, wB_to_rev, 
                                    wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                    partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                    ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                    gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                    gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                    msg >>

wa_rev_wait(self) == /\ pc[self] = "wa_rev_wait"
                     /\ Len(rev_to_wA) > 0
                     /\ msg_wr' = [msg_wr EXCEPT ![self] = Head(rev_to_wA)]
                     /\ rev_to_wA' = Tail(rev_to_wA)
                     /\ pc' = [pc EXCEPT ![self] = "wa_rev_check"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wB, rev_to_wC, 
                                     wA_to_rev, wB_to_rev, wC_to_rev, 
                                     eic_to_wA, eic_to_wB, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_f, gotA_, 
                                     gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                     gotC_f, msg_r, gotA, gotB, gotC, msg >>

wa_rev_check(self) == /\ pc[self] = "wa_rev_check"
                      /\ IF msg_wr[self] = "major"
                            THEN /\ pc' = [pc EXCEPT ![self] = "wa_major_fix"]
                            ELSE /\ IF msg_wr[self] = "minor"
                                       THEN /\ pc' = [pc EXCEPT ![self] = "wa_minor_fix"]
                                       ELSE /\ pc' = [pc EXCEPT ![self] = "wa_eic_wait"]
                      /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                      wB_to_fig, wC_to_fig, fig_to_wA, 
                                      fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                      wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                      eic_to_rev, rev_to_wA, rev_to_wB, 
                                      rev_to_wC, wA_to_rev, wB_to_rev, 
                                      wC_to_rev, eic_to_wA, eic_to_wB, 
                                      eic_to_wC, partI_lock, ch3_lock, 
                                      ch4_lock, fig_lock, ref_lock, msg_, 
                                      msg_w, msg_wr, msg_f, gotA_, gotB_, 
                                      gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                      msg_r, gotA, gotB, gotC, msg >>

wa_major_fix(self) == /\ pc[self] = "wa_major_fix"
                      /\ partI_lock = "FREE"
                      /\ partI_lock' = self
                      /\ pc' = [pc EXCEPT ![self] = "wa_major_done"]
                      /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                      wB_to_fig, wC_to_fig, fig_to_wA, 
                                      fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                      wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                      eic_to_rev, rev_to_wA, rev_to_wB, 
                                      rev_to_wC, wA_to_rev, wB_to_rev, 
                                      wC_to_rev, eic_to_wA, eic_to_wB, 
                                      eic_to_wC, ch3_lock, ch4_lock, fig_lock, 
                                      ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                      gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                      gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                      msg >>

wa_major_done(self) == /\ pc[self] = "wa_major_done"
                       /\ partI_lock' = "FREE"
                       /\ wA_to_rev' = Append(wA_to_rev, "revised")
                       /\ pc' = [pc EXCEPT ![self] = "wa_rerev_wait"]
                       /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                       wB_to_fig, wC_to_fig, fig_to_wA, 
                                       fig_to_wB, fig_to_wC, wA_to_fc, 
                                       wB_to_fc, wC_to_fc, fc_to_wA, fc_to_wB, 
                                       fc_to_wC, eic_to_rev, rev_to_wA, 
                                       rev_to_wB, rev_to_wC, wB_to_rev, 
                                       wC_to_rev, eic_to_wA, eic_to_wB, 
                                       eic_to_wC, ch3_lock, ch4_lock, fig_lock, 
                                       ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                       gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                       gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                       msg >>

wa_rerev_wait(self) == /\ pc[self] = "wa_rerev_wait"
                       /\ Len(rev_to_wA) > 0
                       /\ msg_wr' = [msg_wr EXCEPT ![self] = Head(rev_to_wA)]
                       /\ rev_to_wA' = Tail(rev_to_wA)
                       /\ pc' = [pc EXCEPT ![self] = "wa_eic_wait"]
                       /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                       wB_to_fig, wC_to_fig, fig_to_wA, 
                                       fig_to_wB, fig_to_wC, wA_to_fc, 
                                       wB_to_fc, wC_to_fc, fc_to_wA, fc_to_wB, 
                                       fc_to_wC, eic_to_rev, rev_to_wB, 
                                       rev_to_wC, wA_to_rev, wB_to_rev, 
                                       wC_to_rev, eic_to_wA, eic_to_wB, 
                                       eic_to_wC, partI_lock, ch3_lock, 
                                       ch4_lock, fig_lock, ref_lock, msg_, 
                                       msg_w, msg_f, gotA_, gotB_, gotC_, 
                                       msg_fa, gotA_f, gotB_f, gotC_f, msg_r, 
                                       gotA, gotB, gotC, msg >>

wa_minor_fix(self) == /\ pc[self] = "wa_minor_fix"
                      /\ partI_lock = "FREE"
                      /\ partI_lock' = self
                      /\ pc' = [pc EXCEPT ![self] = "wa_minor_done"]
                      /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                      wB_to_fig, wC_to_fig, fig_to_wA, 
                                      fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                      wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                      eic_to_rev, rev_to_wA, rev_to_wB, 
                                      rev_to_wC, wA_to_rev, wB_to_rev, 
                                      wC_to_rev, eic_to_wA, eic_to_wB, 
                                      eic_to_wC, ch3_lock, ch4_lock, fig_lock, 
                                      ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                      gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                      gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                      msg >>

wa_minor_done(self) == /\ pc[self] = "wa_minor_done"
                       /\ partI_lock' = "FREE"
                       /\ pc' = [pc EXCEPT ![self] = "wa_eic_wait"]
                       /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                       wB_to_fig, wC_to_fig, fig_to_wA, 
                                       fig_to_wB, fig_to_wC, wA_to_fc, 
                                       wB_to_fc, wC_to_fc, fc_to_wA, fc_to_wB, 
                                       fc_to_wC, eic_to_rev, rev_to_wA, 
                                       rev_to_wB, rev_to_wC, wA_to_rev, 
                                       wB_to_rev, wC_to_rev, eic_to_wA, 
                                       eic_to_wB, eic_to_wC, ch3_lock, 
                                       ch4_lock, fig_lock, ref_lock, msg_, 
                                       msg_w, msg_wr, msg_f, gotA_, gotB_, 
                                       gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                       msg_r, gotA, gotB, gotC, msg >>

wa_eic_wait(self) == /\ pc[self] = "wa_eic_wait"
                     /\ Len(eic_to_wA) > 0
                     /\ msg_wr' = [msg_wr EXCEPT ![self] = Head(eic_to_wA)]
                     /\ eic_to_wA' = Tail(eic_to_wA)
                     /\ pc' = [pc EXCEPT ![self] = "wa_eic_apply"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wB, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_f, gotA_, 
                                     gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                     gotC_f, msg_r, gotA, gotB, gotC, msg >>

wa_eic_apply(self) == /\ pc[self] = "wa_eic_apply"
                      /\ partI_lock = "FREE"
                      /\ partI_lock' = self
                      /\ pc' = [pc EXCEPT ![self] = "wa_eic_done"]
                      /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                      wB_to_fig, wC_to_fig, fig_to_wA, 
                                      fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                      wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                      eic_to_rev, rev_to_wA, rev_to_wB, 
                                      rev_to_wC, wA_to_rev, wB_to_rev, 
                                      wC_to_rev, eic_to_wA, eic_to_wB, 
                                      eic_to_wC, ch3_lock, ch4_lock, fig_lock, 
                                      ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                      gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                      gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                      msg >>

wa_eic_done(self) == /\ pc[self] = "wa_eic_done"
                     /\ partI_lock' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "Done"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

writerA_proc(self) == wa_write(self) \/ wa_init_done(self)
                         \/ wa_wait_b(self) \/ wa_wait_c(self)
                         \/ wa_finalize(self) \/ wa_fin_done(self)
                         \/ wa_fig_req(self) \/ wa_fig_wait(self)
                         \/ wa_ref(self) \/ wa_ref_done(self)
                         \/ wa_sub_fc(self) \/ wa_fc_wait(self)
                         \/ wa_fc_check(self) \/ wa_fc_fix(self)
                         \/ wa_fc_fix_done(self) \/ wa_sub_rev(self)
                         \/ wa_rev_wait(self) \/ wa_rev_check(self)
                         \/ wa_major_fix(self) \/ wa_major_done(self)
                         \/ wa_rerev_wait(self) \/ wa_minor_fix(self)
                         \/ wa_minor_done(self) \/ wa_eic_wait(self)
                         \/ wa_eic_apply(self) \/ wa_eic_done(self)

fg_collect(self) == /\ pc[self] = "fg_collect"
                    /\ IF ~gotA_[self] \/ ~gotB_[self] \/ ~gotC_[self]
                          THEN /\ pc' = [pc EXCEPT ![self] = "fg_recv"]
                          ELSE /\ pc' = [pc EXCEPT ![self] = "fg_fig"]
                    /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                    wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                    fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                    fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                    rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                    wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                    eic_to_wC, partI_lock, ch3_lock, ch4_lock, 
                                    fig_lock, ref_lock, msg_, msg_w, msg_wr, 
                                    msg_f, gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                    gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                    msg >>

fg_recv(self) == /\ pc[self] = "fg_recv"
                 /\ \/ /\ Len(wA_to_fig) > 0
                       /\ msg_f' = [msg_f EXCEPT ![self] = Head(wA_to_fig)]
                       /\ wA_to_fig' = Tail(wA_to_fig)
                       /\ gotA_' = [gotA_ EXCEPT ![self] = TRUE]
                       /\ UNCHANGED <<wB_to_fig, wC_to_fig, gotB_, gotC_>>
                    \/ /\ Len(wB_to_fig) > 0
                       /\ msg_f' = [msg_f EXCEPT ![self] = Head(wB_to_fig)]
                       /\ wB_to_fig' = Tail(wB_to_fig)
                       /\ gotB_' = [gotB_ EXCEPT ![self] = TRUE]
                       /\ UNCHANGED <<wA_to_fig, wC_to_fig, gotA_, gotC_>>
                    \/ /\ Len(wC_to_fig) > 0
                       /\ msg_f' = [msg_f EXCEPT ![self] = Head(wC_to_fig)]
                       /\ wC_to_fig' = Tail(wC_to_fig)
                       /\ gotC_' = [gotC_ EXCEPT ![self] = TRUE]
                       /\ UNCHANGED <<wA_to_fig, wB_to_fig, gotA_, gotB_>>
                 /\ pc' = [pc EXCEPT ![self] = "fg_collect"]
                 /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, fig_to_wA, 
                                 fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                 wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                 eic_to_rev, rev_to_wA, rev_to_wB, rev_to_wC, 
                                 wA_to_rev, wB_to_rev, wC_to_rev, eic_to_wA, 
                                 eic_to_wB, eic_to_wC, partI_lock, ch3_lock, 
                                 ch4_lock, fig_lock, ref_lock, msg_, msg_w, 
                                 msg_wr, msg_fa, gotA_f, gotB_f, gotC_f, msg_r, 
                                 gotA, gotB, gotC, msg >>

fg_fig(self) == /\ pc[self] = "fg_fig"
                /\ fig_lock = "FREE"
                /\ fig_lock' = self
                /\ pc' = [pc EXCEPT ![self] = "fg_partI"]
                /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                eic_to_wC, partI_lock, ch3_lock, ch4_lock, 
                                ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                gotB_, gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                msg_r, gotA, gotB, gotC, msg >>

fg_partI(self) == /\ pc[self] = "fg_partI"
                  /\ partI_lock = "FREE"
                  /\ partI_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "fg_partI_done"]
                  /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                  wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                  fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                  fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                  rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                  wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                  eic_to_wC, ch3_lock, ch4_lock, fig_lock, 
                                  ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                  gotB_, gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                  msg_r, gotA, gotB, gotC, msg >>

fg_partI_done(self) == /\ pc[self] = "fg_partI_done"
                       /\ partI_lock' = "FREE"
                       /\ pc' = [pc EXCEPT ![self] = "fg_ch3"]
                       /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                       wB_to_fig, wC_to_fig, fig_to_wA, 
                                       fig_to_wB, fig_to_wC, wA_to_fc, 
                                       wB_to_fc, wC_to_fc, fc_to_wA, fc_to_wB, 
                                       fc_to_wC, eic_to_rev, rev_to_wA, 
                                       rev_to_wB, rev_to_wC, wA_to_rev, 
                                       wB_to_rev, wC_to_rev, eic_to_wA, 
                                       eic_to_wB, eic_to_wC, ch3_lock, 
                                       ch4_lock, fig_lock, ref_lock, msg_, 
                                       msg_w, msg_wr, msg_f, gotA_, gotB_, 
                                       gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                       msg_r, gotA, gotB, gotC, msg >>

fg_ch3(self) == /\ pc[self] = "fg_ch3"
                /\ ch3_lock = "FREE"
                /\ ch3_lock' = self
                /\ pc' = [pc EXCEPT ![self] = "fg_ch3_done"]
                /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                eic_to_wC, partI_lock, ch4_lock, fig_lock, 
                                ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                gotB_, gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                msg_r, gotA, gotB, gotC, msg >>

fg_ch3_done(self) == /\ pc[self] = "fg_ch3_done"
                     /\ ch3_lock' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "fg_ch4"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, partI_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

fg_ch4(self) == /\ pc[self] = "fg_ch4"
                /\ ch4_lock = "FREE"
                /\ ch4_lock' = self
                /\ pc' = [pc EXCEPT ![self] = "fg_ch4_done"]
                /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                eic_to_wC, partI_lock, ch3_lock, fig_lock, 
                                ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                gotB_, gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                msg_r, gotA, gotB, gotC, msg >>

fg_ch4_done(self) == /\ pc[self] = "fg_ch4_done"
                     /\ ch4_lock' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "fg_fig_done"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, partI_lock, ch3_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

fg_fig_done(self) == /\ pc[self] = "fg_fig_done"
                     /\ fig_lock' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "fg_notify"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, partI_lock, ch3_lock, ch4_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

fg_notify(self) == /\ pc[self] = "fg_notify"
                   /\ fig_to_wA' = Append(fig_to_wA, "fig_done")
                   /\ fig_to_wB' = Append(fig_to_wB, "fig_done")
                   /\ fig_to_wC' = Append(fig_to_wC, "fig_done")
                   /\ pc' = [pc EXCEPT ![self] = "Done"]
                   /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                   wB_to_fig, wC_to_fig, wA_to_fc, wB_to_fc, 
                                   wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                   eic_to_rev, rev_to_wA, rev_to_wB, rev_to_wC, 
                                   wA_to_rev, wB_to_rev, wC_to_rev, eic_to_wA, 
                                   eic_to_wB, eic_to_wC, partI_lock, ch3_lock, 
                                   ch4_lock, fig_lock, ref_lock, msg_, msg_w, 
                                   msg_wr, msg_f, gotA_, gotB_, gotC_, msg_fa, 
                                   gotA_f, gotB_f, gotC_f, msg_r, gotA, gotB, 
                                   gotC, msg >>

figCreator_proc(self) == fg_collect(self) \/ fg_recv(self) \/ fg_fig(self)
                            \/ fg_partI(self) \/ fg_partI_done(self)
                            \/ fg_ch3(self) \/ fg_ch3_done(self)
                            \/ fg_ch4(self) \/ fg_ch4_done(self)
                            \/ fg_fig_done(self) \/ fg_notify(self)

fk_collect(self) == /\ pc[self] = "fk_collect"
                    /\ IF ~gotA_f[self] \/ ~gotB_f[self] \/ ~gotC_f[self]
                          THEN /\ pc' = [pc EXCEPT ![self] = "fk_recv"]
                          ELSE /\ pc' = [pc EXCEPT ![self] = "fk_partI"]
                    /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                    wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                    fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                    fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                    rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                    wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                    eic_to_wC, partI_lock, ch3_lock, ch4_lock, 
                                    fig_lock, ref_lock, msg_, msg_w, msg_wr, 
                                    msg_f, gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                    gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                    msg >>

fk_recv(self) == /\ pc[self] = "fk_recv"
                 /\ \/ /\ Len(wA_to_fc) > 0
                       /\ msg_fa' = [msg_fa EXCEPT ![self] = Head(wA_to_fc)]
                       /\ wA_to_fc' = Tail(wA_to_fc)
                       /\ gotA_f' = [gotA_f EXCEPT ![self] = TRUE]
                       /\ UNCHANGED <<wB_to_fc, wC_to_fc, gotB_f, gotC_f>>
                    \/ /\ Len(wB_to_fc) > 0
                       /\ msg_fa' = [msg_fa EXCEPT ![self] = Head(wB_to_fc)]
                       /\ wB_to_fc' = Tail(wB_to_fc)
                       /\ gotB_f' = [gotB_f EXCEPT ![self] = TRUE]
                       /\ UNCHANGED <<wA_to_fc, wC_to_fc, gotA_f, gotC_f>>
                    \/ /\ Len(wC_to_fc) > 0
                       /\ msg_fa' = [msg_fa EXCEPT ![self] = Head(wC_to_fc)]
                       /\ wC_to_fc' = Tail(wC_to_fc)
                       /\ gotC_f' = [gotC_f EXCEPT ![self] = TRUE]
                       /\ UNCHANGED <<wA_to_fc, wB_to_fc, gotA_f, gotB_f>>
                 /\ pc' = [pc EXCEPT ![self] = "fk_collect"]
                 /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                 wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                 fig_to_wC, fc_to_wA, fc_to_wB, fc_to_wC, 
                                 eic_to_rev, rev_to_wA, rev_to_wB, rev_to_wC, 
                                 wA_to_rev, wB_to_rev, wC_to_rev, eic_to_wA, 
                                 eic_to_wB, eic_to_wC, partI_lock, ch3_lock, 
                                 ch4_lock, fig_lock, ref_lock, msg_, msg_w, 
                                 msg_wr, msg_f, gotA_, gotB_, gotC_, msg_r, 
                                 gotA, gotB, gotC, msg >>

fk_partI(self) == /\ pc[self] = "fk_partI"
                  /\ partI_lock = "FREE"
                  /\ partI_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "fk_partI_done"]
                  /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                  wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                  fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                  fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                  rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                  wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                  eic_to_wC, ch3_lock, ch4_lock, fig_lock, 
                                  ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                  gotB_, gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                  msg_r, gotA, gotB, gotC, msg >>

fk_partI_done(self) == /\ pc[self] = "fk_partI_done"
                       /\ partI_lock' = "FREE"
                       /\ pc' = [pc EXCEPT ![self] = "fk_ch3"]
                       /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                       wB_to_fig, wC_to_fig, fig_to_wA, 
                                       fig_to_wB, fig_to_wC, wA_to_fc, 
                                       wB_to_fc, wC_to_fc, fc_to_wA, fc_to_wB, 
                                       fc_to_wC, eic_to_rev, rev_to_wA, 
                                       rev_to_wB, rev_to_wC, wA_to_rev, 
                                       wB_to_rev, wC_to_rev, eic_to_wA, 
                                       eic_to_wB, eic_to_wC, ch3_lock, 
                                       ch4_lock, fig_lock, ref_lock, msg_, 
                                       msg_w, msg_wr, msg_f, gotA_, gotB_, 
                                       gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                       msg_r, gotA, gotB, gotC, msg >>

fk_ch3(self) == /\ pc[self] = "fk_ch3"
                /\ ch3_lock = "FREE"
                /\ ch3_lock' = self
                /\ pc' = [pc EXCEPT ![self] = "fk_ch3_done"]
                /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                eic_to_wC, partI_lock, ch4_lock, fig_lock, 
                                ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                gotB_, gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                msg_r, gotA, gotB, gotC, msg >>

fk_ch3_done(self) == /\ pc[self] = "fk_ch3_done"
                     /\ ch3_lock' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "fk_ch4"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, partI_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

fk_ch4(self) == /\ pc[self] = "fk_ch4"
                /\ ch4_lock = "FREE"
                /\ ch4_lock' = self
                /\ pc' = [pc EXCEPT ![self] = "fk_ch4_done"]
                /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                eic_to_wC, partI_lock, ch3_lock, fig_lock, 
                                ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                gotB_, gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                msg_r, gotA, gotB, gotC, msg >>

fk_ch4_done(self) == /\ pc[self] = "fk_ch4_done"
                     /\ ch4_lock' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "fk_decide_a"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, partI_lock, ch3_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

fk_decide_a(self) == /\ pc[self] = "fk_decide_a"
                     /\ \/ /\ fc_to_wA' = Append(fc_to_wA, "ok")
                        \/ /\ fc_to_wA' = Append(fc_to_wA, "revise")
                     /\ pc' = [pc EXCEPT ![self] = "fk_decide_b"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wB, fc_to_wC, eic_to_rev, 
                                     rev_to_wA, rev_to_wB, rev_to_wC, 
                                     wA_to_rev, wB_to_rev, wC_to_rev, 
                                     eic_to_wA, eic_to_wB, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

fk_decide_b(self) == /\ pc[self] = "fk_decide_b"
                     /\ \/ /\ fc_to_wB' = Append(fc_to_wB, "ok")
                        \/ /\ fc_to_wB' = Append(fc_to_wB, "revise")
                     /\ pc' = [pc EXCEPT ![self] = "fk_decide_c"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wC, eic_to_rev, 
                                     rev_to_wA, rev_to_wB, rev_to_wC, 
                                     wA_to_rev, wB_to_rev, wC_to_rev, 
                                     eic_to_wA, eic_to_wB, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

fk_decide_c(self) == /\ pc[self] = "fk_decide_c"
                     /\ \/ /\ fc_to_wC' = Append(fc_to_wC, "ok")
                        \/ /\ fc_to_wC' = Append(fc_to_wC, "revise")
                     /\ pc' = [pc EXCEPT ![self] = "Done"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, eic_to_rev, 
                                     rev_to_wA, rev_to_wB, rev_to_wC, 
                                     wA_to_rev, wB_to_rev, wC_to_rev, 
                                     eic_to_wA, eic_to_wB, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

factChecker_proc(self) == fk_collect(self) \/ fk_recv(self)
                             \/ fk_partI(self) \/ fk_partI_done(self)
                             \/ fk_ch3(self) \/ fk_ch3_done(self)
                             \/ fk_ch4(self) \/ fk_ch4_done(self)
                             \/ fk_decide_a(self) \/ fk_decide_b(self)
                             \/ fk_decide_c(self)

rv_assign(self) == /\ pc[self] = "rv_assign"
                   /\ Len(eic_to_rev) > 0
                   /\ msg_r' = [msg_r EXCEPT ![self] = Head(eic_to_rev)]
                   /\ eic_to_rev' = Tail(eic_to_rev)
                   /\ pc' = [pc EXCEPT ![self] = "rv_collect"]
                   /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                   wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                   fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                   fc_to_wA, fc_to_wB, fc_to_wC, rev_to_wA, 
                                   rev_to_wB, rev_to_wC, wA_to_rev, wB_to_rev, 
                                   wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                   partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                   ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                   gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                   gotC_f, gotA, gotB, gotC, msg >>

rv_collect(self) == /\ pc[self] = "rv_collect"
                    /\ IF ~gotA[self] \/ ~gotB[self] \/ ~gotC[self]
                          THEN /\ pc' = [pc EXCEPT ![self] = "rv_recv"]
                          ELSE /\ pc' = [pc EXCEPT ![self] = "rv_partI"]
                    /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                    wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                    fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                    fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                    rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                    wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                    eic_to_wC, partI_lock, ch3_lock, ch4_lock, 
                                    fig_lock, ref_lock, msg_, msg_w, msg_wr, 
                                    msg_f, gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                    gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                    msg >>

rv_recv(self) == /\ pc[self] = "rv_recv"
                 /\ \/ /\ Len(wA_to_rev) > 0
                       /\ msg_r' = [msg_r EXCEPT ![self] = Head(wA_to_rev)]
                       /\ wA_to_rev' = Tail(wA_to_rev)
                       /\ gotA' = [gotA EXCEPT ![self] = TRUE]
                       /\ UNCHANGED <<wB_to_rev, wC_to_rev, gotB, gotC>>
                    \/ /\ Len(wB_to_rev) > 0
                       /\ msg_r' = [msg_r EXCEPT ![self] = Head(wB_to_rev)]
                       /\ wB_to_rev' = Tail(wB_to_rev)
                       /\ gotB' = [gotB EXCEPT ![self] = TRUE]
                       /\ UNCHANGED <<wA_to_rev, wC_to_rev, gotA, gotC>>
                    \/ /\ Len(wC_to_rev) > 0
                       /\ msg_r' = [msg_r EXCEPT ![self] = Head(wC_to_rev)]
                       /\ wC_to_rev' = Tail(wC_to_rev)
                       /\ gotC' = [gotC EXCEPT ![self] = TRUE]
                       /\ UNCHANGED <<wA_to_rev, wB_to_rev, gotA, gotB>>
                 /\ pc' = [pc EXCEPT ![self] = "rv_collect"]
                 /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                 wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                 fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                 fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                 rev_to_wA, rev_to_wB, rev_to_wC, eic_to_wA, 
                                 eic_to_wB, eic_to_wC, partI_lock, ch3_lock, 
                                 ch4_lock, fig_lock, ref_lock, msg_, msg_w, 
                                 msg_wr, msg_f, gotA_, gotB_, gotC_, msg_fa, 
                                 gotA_f, gotB_f, gotC_f, msg >>

rv_partI(self) == /\ pc[self] = "rv_partI"
                  /\ partI_lock = "FREE"
                  /\ partI_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "rv_partI_done"]
                  /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                  wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                  fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                  fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                  rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                  wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                  eic_to_wC, ch3_lock, ch4_lock, fig_lock, 
                                  ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                  gotB_, gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                  msg_r, gotA, gotB, gotC, msg >>

rv_partI_done(self) == /\ pc[self] = "rv_partI_done"
                       /\ partI_lock' = "FREE"
                       /\ pc' = [pc EXCEPT ![self] = "rv_ch3"]
                       /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                       wB_to_fig, wC_to_fig, fig_to_wA, 
                                       fig_to_wB, fig_to_wC, wA_to_fc, 
                                       wB_to_fc, wC_to_fc, fc_to_wA, fc_to_wB, 
                                       fc_to_wC, eic_to_rev, rev_to_wA, 
                                       rev_to_wB, rev_to_wC, wA_to_rev, 
                                       wB_to_rev, wC_to_rev, eic_to_wA, 
                                       eic_to_wB, eic_to_wC, ch3_lock, 
                                       ch4_lock, fig_lock, ref_lock, msg_, 
                                       msg_w, msg_wr, msg_f, gotA_, gotB_, 
                                       gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                       msg_r, gotA, gotB, gotC, msg >>

rv_ch3(self) == /\ pc[self] = "rv_ch3"
                /\ ch3_lock = "FREE"
                /\ ch3_lock' = self
                /\ pc' = [pc EXCEPT ![self] = "rv_ch3_done"]
                /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                eic_to_wC, partI_lock, ch4_lock, fig_lock, 
                                ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                gotB_, gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                msg_r, gotA, gotB, gotC, msg >>

rv_ch3_done(self) == /\ pc[self] = "rv_ch3_done"
                     /\ ch3_lock' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "rv_ch4"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, partI_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

rv_ch4(self) == /\ pc[self] = "rv_ch4"
                /\ ch4_lock = "FREE"
                /\ ch4_lock' = self
                /\ pc' = [pc EXCEPT ![self] = "rv_ch4_done"]
                /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                wB_to_rev, wC_to_rev, eic_to_wA, eic_to_wB, 
                                eic_to_wC, partI_lock, ch3_lock, fig_lock, 
                                ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                gotB_, gotC_, msg_fa, gotA_f, gotB_f, gotC_f, 
                                msg_r, gotA, gotB, gotC, msg >>

rv_ch4_done(self) == /\ pc[self] = "rv_ch4_done"
                     /\ ch4_lock' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "rv_decide_a"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     wC_to_rev, eic_to_wA, eic_to_wB, 
                                     eic_to_wC, partI_lock, ch3_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

rv_decide_a(self) == /\ pc[self] = "rv_decide_a"
                     /\ \/ /\ rev_to_wA' = Append(rev_to_wA, "ok")
                           /\ pc' = [pc EXCEPT ![self] = "rv_decide_b"]
                        \/ /\ rev_to_wA' = Append(rev_to_wA, "minor")
                           /\ pc' = [pc EXCEPT ![self] = "rv_decide_b"]
                        \/ /\ rev_to_wA' = Append(rev_to_wA, "major")
                           /\ pc' = [pc EXCEPT ![self] = "rv_rerecv_a"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wB, rev_to_wC, 
                                     wA_to_rev, wB_to_rev, wC_to_rev, 
                                     eic_to_wA, eic_to_wB, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

rv_rerecv_a(self) == /\ pc[self] = "rv_rerecv_a"
                     /\ Len(wA_to_rev) > 0
                     /\ msg_r' = [msg_r EXCEPT ![self] = Head(wA_to_rev)]
                     /\ wA_to_rev' = Tail(wA_to_rev)
                     /\ pc' = [pc EXCEPT ![self] = "rv_rerev_a"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wB_to_rev, wC_to_rev, 
                                     eic_to_wA, eic_to_wB, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, gotA, gotB, gotC, msg >>

rv_rerev_a(self) == /\ pc[self] = "rv_rerev_a"
                    /\ rev_to_wA' = Append(rev_to_wA, "ok")
                    /\ pc' = [pc EXCEPT ![self] = "rv_decide_b"]
                    /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                    wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                    fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                    fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                    rev_to_wB, rev_to_wC, wA_to_rev, wB_to_rev, 
                                    wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                    partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                    ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                    gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                    gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                    msg >>

rv_decide_b(self) == /\ pc[self] = "rv_decide_b"
                     /\ \/ /\ rev_to_wB' = Append(rev_to_wB, "ok")
                           /\ pc' = [pc EXCEPT ![self] = "rv_decide_c"]
                        \/ /\ rev_to_wB' = Append(rev_to_wB, "minor")
                           /\ pc' = [pc EXCEPT ![self] = "rv_decide_c"]
                        \/ /\ rev_to_wB' = Append(rev_to_wB, "major")
                           /\ pc' = [pc EXCEPT ![self] = "rv_rerecv_b"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wC, 
                                     wA_to_rev, wB_to_rev, wC_to_rev, 
                                     eic_to_wA, eic_to_wB, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

rv_rerecv_b(self) == /\ pc[self] = "rv_rerecv_b"
                     /\ Len(wB_to_rev) > 0
                     /\ msg_r' = [msg_r EXCEPT ![self] = Head(wB_to_rev)]
                     /\ wB_to_rev' = Tail(wB_to_rev)
                     /\ pc' = [pc EXCEPT ![self] = "rv_rerev_b"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wC_to_rev, 
                                     eic_to_wA, eic_to_wB, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, gotA, gotB, gotC, msg >>

rv_rerev_b(self) == /\ pc[self] = "rv_rerev_b"
                    /\ rev_to_wB' = Append(rev_to_wB, "ok")
                    /\ pc' = [pc EXCEPT ![self] = "rv_decide_c"]
                    /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                    wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                    fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                    fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                    rev_to_wA, rev_to_wC, wA_to_rev, wB_to_rev, 
                                    wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                    partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                    ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                    gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                    gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                    msg >>

rv_decide_c(self) == /\ pc[self] = "rv_decide_c"
                     /\ \/ /\ rev_to_wC' = Append(rev_to_wC, "ok")
                           /\ pc' = [pc EXCEPT ![self] = "Done"]
                        \/ /\ rev_to_wC' = Append(rev_to_wC, "minor")
                           /\ pc' = [pc EXCEPT ![self] = "Done"]
                        \/ /\ rev_to_wC' = Append(rev_to_wC, "major")
                           /\ pc' = [pc EXCEPT ![self] = "rv_rerecv_c"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     wA_to_rev, wB_to_rev, wC_to_rev, 
                                     eic_to_wA, eic_to_wB, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                     msg >>

rv_rerecv_c(self) == /\ pc[self] = "rv_rerecv_c"
                     /\ Len(wC_to_rev) > 0
                     /\ msg_r' = [msg_r EXCEPT ![self] = Head(wC_to_rev)]
                     /\ wC_to_rev' = Tail(wC_to_rev)
                     /\ pc' = [pc EXCEPT ![self] = "rv_rerev_c"]
                     /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                     wB_to_fig, wC_to_fig, fig_to_wA, 
                                     fig_to_wB, fig_to_wC, wA_to_fc, wB_to_fc, 
                                     wC_to_fc, fc_to_wA, fc_to_wB, fc_to_wC, 
                                     eic_to_rev, rev_to_wA, rev_to_wB, 
                                     rev_to_wC, wA_to_rev, wB_to_rev, 
                                     eic_to_wA, eic_to_wB, eic_to_wC, 
                                     partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                     ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                     gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                     gotB_f, gotC_f, gotA, gotB, gotC, msg >>

rv_rerev_c(self) == /\ pc[self] = "rv_rerev_c"
                    /\ rev_to_wC' = Append(rev_to_wC, "ok")
                    /\ pc' = [pc EXCEPT ![self] = "Done"]
                    /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                    wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                    fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                    fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                    rev_to_wA, rev_to_wB, wA_to_rev, wB_to_rev, 
                                    wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                    partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                    ref_lock, msg_, msg_w, msg_wr, msg_f, 
                                    gotA_, gotB_, gotC_, msg_fa, gotA_f, 
                                    gotB_f, gotC_f, msg_r, gotA, gotB, gotC, 
                                    msg >>

reviewer_proc(self) == rv_assign(self) \/ rv_collect(self) \/ rv_recv(self)
                          \/ rv_partI(self) \/ rv_partI_done(self)
                          \/ rv_ch3(self) \/ rv_ch3_done(self)
                          \/ rv_ch4(self) \/ rv_ch4_done(self)
                          \/ rv_decide_a(self) \/ rv_rerecv_a(self)
                          \/ rv_rerev_a(self) \/ rv_decide_b(self)
                          \/ rv_rerecv_b(self) \/ rv_rerev_b(self)
                          \/ rv_decide_c(self) \/ rv_rerecv_c(self)
                          \/ rv_rerev_c(self)

ei_assign(self) == /\ pc[self] = "ei_assign"
                   /\ eic_to_rev' = Append(eic_to_rev, "assign")
                   /\ pc' = [pc EXCEPT ![self] = "ei_decide"]
                   /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                   wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                   fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                   fc_to_wA, fc_to_wB, fc_to_wC, rev_to_wA, 
                                   rev_to_wB, rev_to_wC, wA_to_rev, wB_to_rev, 
                                   wC_to_rev, eic_to_wA, eic_to_wB, eic_to_wC, 
                                   partI_lock, ch3_lock, ch4_lock, fig_lock, 
                                   ref_lock, msg_, msg_w, msg_wr, msg_f, gotA_, 
                                   gotB_, gotC_, msg_fa, gotA_f, gotB_f, 
                                   gotC_f, msg_r, gotA, gotB, gotC, msg >>

ei_decide(self) == /\ pc[self] = "ei_decide"
                   /\ eic_to_wA' = Append(eic_to_wA, "decision")
                   /\ eic_to_wB' = Append(eic_to_wB, "decision")
                   /\ eic_to_wC' = Append(eic_to_wC, "decision")
                   /\ pc' = [pc EXCEPT ![self] = "Done"]
                   /\ UNCHANGED << wC_to_wB, wB_to_wA, wC_to_wA, wA_to_fig, 
                                   wB_to_fig, wC_to_fig, fig_to_wA, fig_to_wB, 
                                   fig_to_wC, wA_to_fc, wB_to_fc, wC_to_fc, 
                                   fc_to_wA, fc_to_wB, fc_to_wC, eic_to_rev, 
                                   rev_to_wA, rev_to_wB, rev_to_wC, wA_to_rev, 
                                   wB_to_rev, wC_to_rev, partI_lock, ch3_lock, 
                                   ch4_lock, fig_lock, ref_lock, msg_, msg_w, 
                                   msg_wr, msg_f, gotA_, gotB_, gotC_, msg_fa, 
                                   gotA_f, gotB_f, gotC_f, msg_r, gotA, gotB, 
                                   gotC, msg >>

eic_proc(self) == ei_assign(self) \/ ei_decide(self)

(* Allow infinite stuttering to prevent deadlock on termination. *)
Terminating == /\ \A self \in ProcSet: pc[self] = "Done"
               /\ UNCHANGED vars

Next == (\E self \in {WriterC}: writerC_proc(self))
           \/ (\E self \in {WriterB}: writerB_proc(self))
           \/ (\E self \in {WriterA}: writerA_proc(self))
           \/ (\E self \in {FigCreator}: figCreator_proc(self))
           \/ (\E self \in {FactChecker}: factChecker_proc(self))
           \/ (\E self \in {Reviewer}: reviewer_proc(self))
           \/ (\E self \in {Eic}: eic_proc(self))
           \/ Terminating

Spec == /\ Init /\ [][Next]_vars
        /\ \A self \in {WriterC} : WF_vars(writerC_proc(self))
        /\ \A self \in {WriterB} : WF_vars(writerB_proc(self))
        /\ \A self \in {WriterA} : WF_vars(writerA_proc(self))
        /\ \A self \in {FigCreator} : WF_vars(figCreator_proc(self))
        /\ \A self \in {FactChecker} : WF_vars(factChecker_proc(self))
        /\ \A self \in {Reviewer} : WF_vars(reviewer_proc(self))
        /\ \A self \in {Eic} : WF_vars(eic_proc(self))

Termination == <>(\A self \in ProcSet: pc[self] = "Done")

\* END TRANSLATION 

AllDone == \A p \in {WriterA, WriterB, WriterC, FigCreator, FactChecker, Reviewer, Eic}: pc[p] = "Done"

TypeInvariant ==
  /\ \A p \in {WriterA, WriterB, WriterC, FigCreator, FactChecker, Reviewer, Eic}: pc[p] \in STRING
  /\ partI_lock \in {WriterA, WriterB, WriterC, FigCreator, FactChecker, Reviewer, Eic, "FREE"}
  /\ ch3_lock \in {WriterA, WriterB, WriterC, FigCreator, FactChecker, Reviewer, Eic, "FREE"}
  /\ ch4_lock \in {WriterA, WriterB, WriterC, FigCreator, FactChecker, Reviewer, Eic, "FREE"}
  /\ fig_lock \in {WriterA, WriterB, WriterC, FigCreator, FactChecker, Reviewer, Eic, "FREE"}
  /\ ref_lock \in {WriterA, WriterB, WriterC, FigCreator, FactChecker, Reviewer, Eic, "FREE"}
  /\ wC_to_wB \in Seq(STRING)
  /\ wB_to_wA \in Seq(STRING)
  /\ wC_to_wA \in Seq(STRING)
  /\ wA_to_fig \in Seq(STRING)
  /\ wB_to_fig \in Seq(STRING)
  /\ wC_to_fig \in Seq(STRING)
  /\ fig_to_wA \in Seq(STRING)
  /\ fig_to_wB \in Seq(STRING)
  /\ fig_to_wC \in Seq(STRING)
  /\ wA_to_fc \in Seq(STRING)
  /\ wB_to_fc \in Seq(STRING)
  /\ wC_to_fc \in Seq(STRING)
  /\ fc_to_wA \in Seq(STRING)
  /\ fc_to_wB \in Seq(STRING)
  /\ fc_to_wC \in Seq(STRING)
  /\ eic_to_rev \in Seq(STRING)
  /\ rev_to_wA \in Seq(STRING)
  /\ rev_to_wB \in Seq(STRING)
  /\ rev_to_wC \in Seq(STRING)
  /\ wA_to_rev \in Seq(STRING)
  /\ wB_to_rev \in Seq(STRING)
  /\ wC_to_rev \in Seq(STRING)
  /\ eic_to_wA \in Seq(STRING)
  /\ eic_to_wB \in Seq(STRING)
  /\ eic_to_wC \in Seq(STRING)

NoOrphanLocks ==
  AllDone => (partI_lock = "FREE" /\ ch3_lock = "FREE" /\ ch4_lock = "FREE" /\ fig_lock = "FREE" /\ ref_lock = "FREE")

ChannelsDrained ==
  AllDone => (Len(wC_to_wB) = 0 /\ Len(wB_to_wA) = 0 /\ Len(wC_to_wA) = 0 /\ Len(wA_to_fig) = 0 /\ Len(wB_to_fig) = 0 /\ Len(wC_to_fig) = 0 /\ Len(fig_to_wA) = 0 /\ Len(fig_to_wB) = 0 /\ Len(fig_to_wC) = 0 /\ Len(wA_to_fc) = 0 /\ Len(wB_to_fc) = 0 /\ Len(wC_to_fc) = 0 /\ Len(fc_to_wA) = 0 /\ Len(fc_to_wB) = 0 /\ Len(fc_to_wC) = 0 /\ Len(eic_to_rev) = 0 /\ Len(rev_to_wA) = 0 /\ Len(rev_to_wB) = 0 /\ Len(rev_to_wC) = 0 /\ Len(wA_to_rev) = 0 /\ Len(wB_to_rev) = 0 /\ Len(wC_to_rev) = 0 /\ Len(eic_to_wA) = 0 /\ Len(eic_to_wB) = 0 /\ Len(eic_to_wC) = 0)

ChannelBound ==
  Len(wC_to_wB) <= 3 /\ Len(wB_to_wA) <= 3 /\ Len(wC_to_wA) <= 3 /\ Len(wA_to_fig) <= 3 /\ Len(wB_to_fig) <= 3 /\ Len(wC_to_fig) <= 3 /\ Len(fig_to_wA) <= 3 /\ Len(fig_to_wB) <= 3 /\ Len(fig_to_wC) <= 3 /\ Len(wA_to_fc) <= 3 /\ Len(wB_to_fc) <= 3 /\ Len(wC_to_fc) <= 3 /\ Len(fc_to_wA) <= 3 /\ Len(fc_to_wB) <= 3 /\ Len(fc_to_wC) <= 3 /\ Len(eic_to_rev) <= 3 /\ Len(rev_to_wA) <= 3 /\ Len(rev_to_wB) <= 3 /\ Len(rev_to_wC) <= 3 /\ Len(wA_to_rev) <= 3 /\ Len(wB_to_rev) <= 3 /\ Len(wC_to_rev) <= 3 /\ Len(eic_to_wA) <= 3 /\ Len(eic_to_wB) <= 3 /\ Len(eic_to_wC) <= 3

====
