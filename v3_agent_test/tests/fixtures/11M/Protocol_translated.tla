---- MODULE Protocol ----
EXTENDS Integers, Sequences, TLC

CONSTANTS WorkerA, WorkerB, WorkerC, Inspector, Dispatcher

(* --algorithm Protocol {
variables
  wA_to_insp = <<>>; \* workerA -> inspector, labels: ['inspect']
  wB_to_insp = <<>>; \* workerB -> inspector, labels: ['inspect']
  wC_to_insp = <<>>; \* workerC -> inspector, labels: ['inspect']
  insp_to_wA = <<>>; \* inspector -> workerA, labels: ['pass', 'fail']
  insp_to_wB = <<>>; \* inspector -> workerB, labels: ['pass', 'fail']
  insp_to_wC = <<>>; \* inspector -> workerC, labels: ['pass', 'fail']
  insp_to_disp = <<>>; \* inspector -> dispatcher, labels: ['fail_A', 'fail_B', 'fail_C', 'all_done']
  disp_to_wA = <<>>; \* dispatcher -> workerA, labels: ['rework']
  disp_to_wB = <<>>; \* dispatcher -> workerB, labels: ['rework']
  disp_to_wC = <<>>; \* dispatcher -> workerC, labels: ['rework']
  station_alpha = "FREE"; \* Lock
  station_beta = "FREE"; \* Lock
  station_gamma = "FREE"; \* Lock
  tool_cabinet = 2; \* Counter (non-negative)

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

macro acquire_counter(ctr) {
  await ctr > 0;
  ctr := ctr - 1;
}

macro release_counter(ctr) {
  ctr := ctr + 1;
}

fair process (workerA_proc \in {WorkerA})
variables msg = "", did_first = FALSE, job1_passed = FALSE, job2_passed = FALSE;
{
  \* Worker A: Job 1 = station_alpha (needs tool), Job 2 = station_beta (no tool)
  \* Nondeterministic choice of first job
  wa_choose:
    either {
      \* Do job1 first (station_alpha + tool)
      acquire_lock(station_alpha);
    wa_j1_tool:
      acquire_counter(tool_cabinet);
    wa_j1_work:
      release_counter(tool_cabinet);
      release_lock(station_alpha);
      send(wA_to_insp, "inspect");
    wa_j1_result:
      receive(insp_to_wA, msg);
    wa_j1_check:
      if (msg = "pass") {
        job1_passed := TRUE;
        did_first := TRUE;
      } else {
        \* fail: wait for rework order
      wa_j1_rework:
        receive(disp_to_wA, msg);
        goto wa_choose;
      };
    } or {
      \* Do job2 first (station_beta, no tool)
      acquire_lock(station_beta);
    wa_j2_work:
      release_lock(station_beta);
      send(wA_to_insp, "inspect");
    wa_j2_result:
      receive(insp_to_wA, msg);
    wa_j2_check:
      if (msg = "pass") {
        job2_passed := TRUE;
        did_first := TRUE;
      } else {
      wa_j2_rework:
        receive(disp_to_wA, msg);
        goto wa_choose;
      };
    };

  \* Second job: do whichever wasn't done
  wa_second:
    if (job1_passed /\ ~job2_passed) {
      \* Need to do job2
      acquire_lock(station_beta);
    wa_s2_work:
      release_lock(station_beta);
      send(wA_to_insp, "inspect");
    wa_s2_result:
      receive(insp_to_wA, msg);
    wa_s2_check:
      if (msg = "pass") {
        job2_passed := TRUE;
      } else {
      wa_s2_rework:
        receive(disp_to_wA, msg);
        goto wa_second;
      };
    } else {
      \* Need to do job1
      acquire_lock(station_alpha);
    wa_s1_tool:
      acquire_counter(tool_cabinet);
    wa_s1_work:
      release_counter(tool_cabinet);
      release_lock(station_alpha);
      send(wA_to_insp, "inspect");
    wa_s1_result:
      receive(insp_to_wA, msg);
    wa_s1_check:
      if (msg = "pass") {
        job1_passed := TRUE;
      } else {
      wa_s1_rework:
        receive(disp_to_wA, msg);
        goto wa_second;
      };
    };
  wa_done:
    skip;
}

fair process (workerB_proc \in {WorkerB})
variables msg = "", did_first = FALSE, job1_passed = FALSE, job2_passed = FALSE;
{
  \* Worker B: Job 1 = station_beta (needs tool), Job 2 = station_gamma (no tool)
  wb_choose:
    either {
      \* Do job1 first (station_beta + tool)
      acquire_lock(station_beta);
    wb_j1_tool:
      acquire_counter(tool_cabinet);
    wb_j1_work:
      release_counter(tool_cabinet);
      release_lock(station_beta);
      send(wB_to_insp, "inspect");
    wb_j1_result:
      receive(insp_to_wB, msg);
    wb_j1_check:
      if (msg = "pass") {
        job1_passed := TRUE;
        did_first := TRUE;
      } else {
      wb_j1_rework:
        receive(disp_to_wB, msg);
        goto wb_choose;
      };
    } or {
      \* Do job2 first (station_gamma, no tool)
      acquire_lock(station_gamma);
    wb_j2_work:
      release_lock(station_gamma);
      send(wB_to_insp, "inspect");
    wb_j2_result:
      receive(insp_to_wB, msg);
    wb_j2_check:
      if (msg = "pass") {
        job2_passed := TRUE;
        did_first := TRUE;
      } else {
      wb_j2_rework:
        receive(disp_to_wB, msg);
        goto wb_choose;
      };
    };

  wb_second:
    if (job1_passed /\ ~job2_passed) {
      acquire_lock(station_gamma);
    wb_s2_work:
      release_lock(station_gamma);
      send(wB_to_insp, "inspect");
    wb_s2_result:
      receive(insp_to_wB, msg);
    wb_s2_check:
      if (msg = "pass") {
        job2_passed := TRUE;
      } else {
      wb_s2_rework:
        receive(disp_to_wB, msg);
        goto wb_second;
      };
    } else {
      acquire_lock(station_beta);
    wb_s1_tool:
      acquire_counter(tool_cabinet);
    wb_s1_work:
      release_counter(tool_cabinet);
      release_lock(station_beta);
      send(wB_to_insp, "inspect");
    wb_s1_result:
      receive(insp_to_wB, msg);
    wb_s1_check:
      if (msg = "pass") {
        job1_passed := TRUE;
      } else {
      wb_s1_rework:
        receive(disp_to_wB, msg);
        goto wb_second;
      };
    };
  wb_done:
    skip;
}

fair process (workerC_proc \in {WorkerC})
variables msg = "", did_first = FALSE, job1_passed = FALSE, job2_passed = FALSE;
{
  \* Worker C: Job 1 = station_gamma (needs tool), Job 2 = station_alpha (no tool)
  wc_choose:
    either {
      \* Do job1 first (station_gamma + tool)
      acquire_lock(station_gamma);
    wc_j1_tool:
      acquire_counter(tool_cabinet);
    wc_j1_work:
      release_counter(tool_cabinet);
      release_lock(station_gamma);
      send(wC_to_insp, "inspect");
    wc_j1_result:
      receive(insp_to_wC, msg);
    wc_j1_check:
      if (msg = "pass") {
        job1_passed := TRUE;
        did_first := TRUE;
      } else {
      wc_j1_rework:
        receive(disp_to_wC, msg);
        goto wc_choose;
      };
    } or {
      \* Do job2 first (station_alpha, no tool)
      acquire_lock(station_alpha);
    wc_j2_work:
      release_lock(station_alpha);
      send(wC_to_insp, "inspect");
    wc_j2_result:
      receive(insp_to_wC, msg);
    wc_j2_check:
      if (msg = "pass") {
        job2_passed := TRUE;
        did_first := TRUE;
      } else {
      wc_j2_rework:
        receive(disp_to_wC, msg);
        goto wc_choose;
      };
    };

  wc_second:
    if (job1_passed /\ ~job2_passed) {
      acquire_lock(station_alpha);
    wc_s2_work:
      release_lock(station_alpha);
      send(wC_to_insp, "inspect");
    wc_s2_result:
      receive(insp_to_wC, msg);
    wc_s2_check:
      if (msg = "pass") {
        job2_passed := TRUE;
      } else {
      wc_s2_rework:
        receive(disp_to_wC, msg);
        goto wc_second;
      };
    } else {
      acquire_lock(station_gamma);
    wc_s1_tool:
      acquire_counter(tool_cabinet);
    wc_s1_work:
      release_counter(tool_cabinet);
      release_lock(station_gamma);
      send(wC_to_insp, "inspect");
    wc_s1_result:
      receive(insp_to_wC, msg);
    wc_s1_check:
      if (msg = "pass") {
        job1_passed := TRUE;
      } else {
      wc_s1_rework:
        receive(disp_to_wC, msg);
        goto wc_second;
      };
    };
  wc_done:
    skip;
}

fair process (inspector_proc \in {Inspector})
variables msg = "", passed = 0, src = "";
{
  \* Inspector: receive inspect requests, send pass/fail, track passed count
  in_loop:
    while (passed < 6) {
      in_recv:
        either {
          receive(wA_to_insp, msg);
          src := "A";
        } or {
          receive(wB_to_insp, msg);
          src := "B";
        } or {
          receive(wC_to_insp, msg);
          src := "C";
        };
      in_decide:
        either {
          \* Pass
          if (src = "A") {
            send(insp_to_wA, "pass");
          } else if (src = "B") {
            send(insp_to_wB, "pass");
          } else {
            send(insp_to_wC, "pass");
          };
          passed := passed + 1;
        } or {
          \* Fail
          if (src = "A") {
            send(insp_to_wA, "fail");
            send(insp_to_disp, "fail_A");
          } else if (src = "B") {
            send(insp_to_wB, "fail");
            send(insp_to_disp, "fail_B");
          } else {
            send(insp_to_wC, "fail");
            send(insp_to_disp, "fail_C");
          };
        };
    };
  in_finish:
    send(insp_to_disp, "all_done");
  in_done:
    skip;
}

fair process (dispatcher_proc \in {Dispatcher})
variables msg = "";
{
  \* Dispatcher: receive fail_reports, send rework orders; wait for all_done
  di_loop:
    while (TRUE) {
      di_recv:
        receive(insp_to_disp, msg);
      di_check:
        if (msg = "all_done") {
          goto di_done;
        } else if (msg = "fail_A") {
          send(disp_to_wA, "rework");
        } else if (msg = "fail_B") {
          send(disp_to_wB, "rework");
        } else {
          \* fail_C
          send(disp_to_wC, "rework");
        };
    };
  di_done:
    skip;
}

} *)
\* BEGIN TRANSLATION (chksum(pcal) = "e6cf2386" /\ chksum(tla) = "51f120dd")
\* Process variable msg of process workerA_proc at line 52 col 11 changed to msg_
\* Process variable did_first of process workerA_proc at line 52 col 21 changed to did_first_
\* Process variable job1_passed of process workerA_proc at line 52 col 40 changed to job1_passed_
\* Process variable job2_passed of process workerA_proc at line 52 col 61 changed to job2_passed_
\* Process variable msg of process workerB_proc at line 140 col 11 changed to msg_w
\* Process variable did_first of process workerB_proc at line 140 col 21 changed to did_first_w
\* Process variable job1_passed of process workerB_proc at line 140 col 40 changed to job1_passed_w
\* Process variable job2_passed of process workerB_proc at line 140 col 61 changed to job2_passed_w
\* Process variable msg of process workerC_proc at line 223 col 11 changed to msg_wo
\* Process variable msg of process inspector_proc at line 306 col 11 changed to msg_i
VARIABLES pc, wA_to_insp, wB_to_insp, wC_to_insp, insp_to_wA, insp_to_wB, 
          insp_to_wC, insp_to_disp, disp_to_wA, disp_to_wB, disp_to_wC, 
          station_alpha, station_beta, station_gamma, tool_cabinet, msg_, 
          did_first_, job1_passed_, job2_passed_, msg_w, did_first_w, 
          job1_passed_w, job2_passed_w, msg_wo, did_first, job1_passed, 
          job2_passed, msg_i, passed, src, msg

vars == << pc, wA_to_insp, wB_to_insp, wC_to_insp, insp_to_wA, insp_to_wB, 
           insp_to_wC, insp_to_disp, disp_to_wA, disp_to_wB, disp_to_wC, 
           station_alpha, station_beta, station_gamma, tool_cabinet, msg_, 
           did_first_, job1_passed_, job2_passed_, msg_w, did_first_w, 
           job1_passed_w, job2_passed_w, msg_wo, did_first, job1_passed, 
           job2_passed, msg_i, passed, src, msg >>

ProcSet == ({WorkerA}) \cup ({WorkerB}) \cup ({WorkerC}) \cup ({Inspector}) \cup ({Dispatcher})

Init == (* Global variables *)
        /\ wA_to_insp = <<>>
        /\ wB_to_insp = <<>>
        /\ wC_to_insp = <<>>
        /\ insp_to_wA = <<>>
        /\ insp_to_wB = <<>>
        /\ insp_to_wC = <<>>
        /\ insp_to_disp = <<>>
        /\ disp_to_wA = <<>>
        /\ disp_to_wB = <<>>
        /\ disp_to_wC = <<>>
        /\ station_alpha = "FREE"
        /\ station_beta = "FREE"
        /\ station_gamma = "FREE"
        /\ tool_cabinet = 2
        (* Process workerA_proc *)
        /\ msg_ = [self \in {WorkerA} |-> ""]
        /\ did_first_ = [self \in {WorkerA} |-> FALSE]
        /\ job1_passed_ = [self \in {WorkerA} |-> FALSE]
        /\ job2_passed_ = [self \in {WorkerA} |-> FALSE]
        (* Process workerB_proc *)
        /\ msg_w = [self \in {WorkerB} |-> ""]
        /\ did_first_w = [self \in {WorkerB} |-> FALSE]
        /\ job1_passed_w = [self \in {WorkerB} |-> FALSE]
        /\ job2_passed_w = [self \in {WorkerB} |-> FALSE]
        (* Process workerC_proc *)
        /\ msg_wo = [self \in {WorkerC} |-> ""]
        /\ did_first = [self \in {WorkerC} |-> FALSE]
        /\ job1_passed = [self \in {WorkerC} |-> FALSE]
        /\ job2_passed = [self \in {WorkerC} |-> FALSE]
        (* Process inspector_proc *)
        /\ msg_i = [self \in {Inspector} |-> ""]
        /\ passed = [self \in {Inspector} |-> 0]
        /\ src = [self \in {Inspector} |-> ""]
        (* Process dispatcher_proc *)
        /\ msg = [self \in {Dispatcher} |-> ""]
        /\ pc = [self \in ProcSet |-> CASE self \in {WorkerA} -> "wa_choose"
                                        [] self \in {WorkerB} -> "wb_choose"
                                        [] self \in {WorkerC} -> "wc_choose"
                                        [] self \in {Inspector} -> "in_loop"
                                        [] self \in {Dispatcher} -> "di_loop"]

wa_choose(self) == /\ pc[self] = "wa_choose"
                   /\ \/ /\ station_alpha = "FREE"
                         /\ station_alpha' = self
                         /\ pc' = [pc EXCEPT ![self] = "wa_j1_tool"]
                         /\ UNCHANGED station_beta
                      \/ /\ station_beta = "FREE"
                         /\ station_beta' = self
                         /\ pc' = [pc EXCEPT ![self] = "wa_j2_work"]
                         /\ UNCHANGED station_alpha
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   insp_to_wA, insp_to_wB, insp_to_wC, 
                                   insp_to_disp, disp_to_wA, disp_to_wB, 
                                   disp_to_wC, station_gamma, tool_cabinet, 
                                   msg_, did_first_, job1_passed_, 
                                   job2_passed_, msg_w, did_first_w, 
                                   job1_passed_w, job2_passed_w, msg_wo, 
                                   did_first, job1_passed, job2_passed, msg_i, 
                                   passed, src, msg >>

wa_j1_tool(self) == /\ pc[self] = "wa_j1_tool"
                    /\ tool_cabinet > 0
                    /\ tool_cabinet' = tool_cabinet - 1
                    /\ pc' = [pc EXCEPT ![self] = "wa_j1_work"]
                    /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                    insp_to_wA, insp_to_wB, insp_to_wC, 
                                    insp_to_disp, disp_to_wA, disp_to_wB, 
                                    disp_to_wC, station_alpha, station_beta, 
                                    station_gamma, msg_, did_first_, 
                                    job1_passed_, job2_passed_, msg_w, 
                                    did_first_w, job1_passed_w, job2_passed_w, 
                                    msg_wo, did_first, job1_passed, 
                                    job2_passed, msg_i, passed, src, msg >>

wa_j1_work(self) == /\ pc[self] = "wa_j1_work"
                    /\ tool_cabinet' = tool_cabinet + 1
                    /\ station_alpha' = "FREE"
                    /\ wA_to_insp' = Append(wA_to_insp, "inspect")
                    /\ pc' = [pc EXCEPT ![self] = "wa_j1_result"]
                    /\ UNCHANGED << wB_to_insp, wC_to_insp, insp_to_wA, 
                                    insp_to_wB, insp_to_wC, insp_to_disp, 
                                    disp_to_wA, disp_to_wB, disp_to_wC, 
                                    station_beta, station_gamma, msg_, 
                                    did_first_, job1_passed_, job2_passed_, 
                                    msg_w, did_first_w, job1_passed_w, 
                                    job2_passed_w, msg_wo, did_first, 
                                    job1_passed, job2_passed, msg_i, passed, 
                                    src, msg >>

wa_j1_result(self) == /\ pc[self] = "wa_j1_result"
                      /\ Len(insp_to_wA) > 0
                      /\ msg_' = [msg_ EXCEPT ![self] = Head(insp_to_wA)]
                      /\ insp_to_wA' = Tail(insp_to_wA)
                      /\ pc' = [pc EXCEPT ![self] = "wa_j1_check"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wB, insp_to_wC, insp_to_disp, 
                                      disp_to_wA, disp_to_wB, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, did_first_, 
                                      job1_passed_, job2_passed_, msg_w, 
                                      did_first_w, job1_passed_w, 
                                      job2_passed_w, msg_wo, did_first, 
                                      job1_passed, job2_passed, msg_i, passed, 
                                      src, msg >>

wa_j1_check(self) == /\ pc[self] = "wa_j1_check"
                     /\ IF msg_[self] = "pass"
                           THEN /\ job1_passed_' = [job1_passed_ EXCEPT ![self] = TRUE]
                                /\ did_first_' = [did_first_ EXCEPT ![self] = TRUE]
                                /\ pc' = [pc EXCEPT ![self] = "wa_second"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "wa_j1_rework"]
                                /\ UNCHANGED << did_first_, job1_passed_ >>
                     /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                     insp_to_wA, insp_to_wB, insp_to_wC, 
                                     insp_to_disp, disp_to_wA, disp_to_wB, 
                                     disp_to_wC, station_alpha, station_beta, 
                                     station_gamma, tool_cabinet, msg_, 
                                     job2_passed_, msg_w, did_first_w, 
                                     job1_passed_w, job2_passed_w, msg_wo, 
                                     did_first, job1_passed, job2_passed, 
                                     msg_i, passed, src, msg >>

wa_j1_rework(self) == /\ pc[self] = "wa_j1_rework"
                      /\ Len(disp_to_wA) > 0
                      /\ msg_' = [msg_ EXCEPT ![self] = Head(disp_to_wA)]
                      /\ disp_to_wA' = Tail(disp_to_wA)
                      /\ pc' = [pc EXCEPT ![self] = "wa_choose"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_disp, disp_to_wB, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, did_first_, 
                                      job1_passed_, job2_passed_, msg_w, 
                                      did_first_w, job1_passed_w, 
                                      job2_passed_w, msg_wo, did_first, 
                                      job1_passed, job2_passed, msg_i, passed, 
                                      src, msg >>

wa_j2_work(self) == /\ pc[self] = "wa_j2_work"
                    /\ station_beta' = "FREE"
                    /\ wA_to_insp' = Append(wA_to_insp, "inspect")
                    /\ pc' = [pc EXCEPT ![self] = "wa_j2_result"]
                    /\ UNCHANGED << wB_to_insp, wC_to_insp, insp_to_wA, 
                                    insp_to_wB, insp_to_wC, insp_to_disp, 
                                    disp_to_wA, disp_to_wB, disp_to_wC, 
                                    station_alpha, station_gamma, tool_cabinet, 
                                    msg_, did_first_, job1_passed_, 
                                    job2_passed_, msg_w, did_first_w, 
                                    job1_passed_w, job2_passed_w, msg_wo, 
                                    did_first, job1_passed, job2_passed, msg_i, 
                                    passed, src, msg >>

wa_j2_result(self) == /\ pc[self] = "wa_j2_result"
                      /\ Len(insp_to_wA) > 0
                      /\ msg_' = [msg_ EXCEPT ![self] = Head(insp_to_wA)]
                      /\ insp_to_wA' = Tail(insp_to_wA)
                      /\ pc' = [pc EXCEPT ![self] = "wa_j2_check"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wB, insp_to_wC, insp_to_disp, 
                                      disp_to_wA, disp_to_wB, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, did_first_, 
                                      job1_passed_, job2_passed_, msg_w, 
                                      did_first_w, job1_passed_w, 
                                      job2_passed_w, msg_wo, did_first, 
                                      job1_passed, job2_passed, msg_i, passed, 
                                      src, msg >>

wa_j2_check(self) == /\ pc[self] = "wa_j2_check"
                     /\ IF msg_[self] = "pass"
                           THEN /\ job2_passed_' = [job2_passed_ EXCEPT ![self] = TRUE]
                                /\ did_first_' = [did_first_ EXCEPT ![self] = TRUE]
                                /\ pc' = [pc EXCEPT ![self] = "wa_second"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "wa_j2_rework"]
                                /\ UNCHANGED << did_first_, job2_passed_ >>
                     /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                     insp_to_wA, insp_to_wB, insp_to_wC, 
                                     insp_to_disp, disp_to_wA, disp_to_wB, 
                                     disp_to_wC, station_alpha, station_beta, 
                                     station_gamma, tool_cabinet, msg_, 
                                     job1_passed_, msg_w, did_first_w, 
                                     job1_passed_w, job2_passed_w, msg_wo, 
                                     did_first, job1_passed, job2_passed, 
                                     msg_i, passed, src, msg >>

wa_j2_rework(self) == /\ pc[self] = "wa_j2_rework"
                      /\ Len(disp_to_wA) > 0
                      /\ msg_' = [msg_ EXCEPT ![self] = Head(disp_to_wA)]
                      /\ disp_to_wA' = Tail(disp_to_wA)
                      /\ pc' = [pc EXCEPT ![self] = "wa_choose"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_disp, disp_to_wB, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, did_first_, 
                                      job1_passed_, job2_passed_, msg_w, 
                                      did_first_w, job1_passed_w, 
                                      job2_passed_w, msg_wo, did_first, 
                                      job1_passed, job2_passed, msg_i, passed, 
                                      src, msg >>

wa_second(self) == /\ pc[self] = "wa_second"
                   /\ IF job1_passed_[self] /\ ~job2_passed_[self]
                         THEN /\ station_beta = "FREE"
                              /\ station_beta' = self
                              /\ pc' = [pc EXCEPT ![self] = "wa_s2_work"]
                              /\ UNCHANGED station_alpha
                         ELSE /\ station_alpha = "FREE"
                              /\ station_alpha' = self
                              /\ pc' = [pc EXCEPT ![self] = "wa_s1_tool"]
                              /\ UNCHANGED station_beta
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   insp_to_wA, insp_to_wB, insp_to_wC, 
                                   insp_to_disp, disp_to_wA, disp_to_wB, 
                                   disp_to_wC, station_gamma, tool_cabinet, 
                                   msg_, did_first_, job1_passed_, 
                                   job2_passed_, msg_w, did_first_w, 
                                   job1_passed_w, job2_passed_w, msg_wo, 
                                   did_first, job1_passed, job2_passed, msg_i, 
                                   passed, src, msg >>

wa_s2_work(self) == /\ pc[self] = "wa_s2_work"
                    /\ station_beta' = "FREE"
                    /\ wA_to_insp' = Append(wA_to_insp, "inspect")
                    /\ pc' = [pc EXCEPT ![self] = "wa_s2_result"]
                    /\ UNCHANGED << wB_to_insp, wC_to_insp, insp_to_wA, 
                                    insp_to_wB, insp_to_wC, insp_to_disp, 
                                    disp_to_wA, disp_to_wB, disp_to_wC, 
                                    station_alpha, station_gamma, tool_cabinet, 
                                    msg_, did_first_, job1_passed_, 
                                    job2_passed_, msg_w, did_first_w, 
                                    job1_passed_w, job2_passed_w, msg_wo, 
                                    did_first, job1_passed, job2_passed, msg_i, 
                                    passed, src, msg >>

wa_s2_result(self) == /\ pc[self] = "wa_s2_result"
                      /\ Len(insp_to_wA) > 0
                      /\ msg_' = [msg_ EXCEPT ![self] = Head(insp_to_wA)]
                      /\ insp_to_wA' = Tail(insp_to_wA)
                      /\ pc' = [pc EXCEPT ![self] = "wa_s2_check"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wB, insp_to_wC, insp_to_disp, 
                                      disp_to_wA, disp_to_wB, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, did_first_, 
                                      job1_passed_, job2_passed_, msg_w, 
                                      did_first_w, job1_passed_w, 
                                      job2_passed_w, msg_wo, did_first, 
                                      job1_passed, job2_passed, msg_i, passed, 
                                      src, msg >>

wa_s2_check(self) == /\ pc[self] = "wa_s2_check"
                     /\ IF msg_[self] = "pass"
                           THEN /\ job2_passed_' = [job2_passed_ EXCEPT ![self] = TRUE]
                                /\ pc' = [pc EXCEPT ![self] = "wa_done"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "wa_s2_rework"]
                                /\ UNCHANGED job2_passed_
                     /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                     insp_to_wA, insp_to_wB, insp_to_wC, 
                                     insp_to_disp, disp_to_wA, disp_to_wB, 
                                     disp_to_wC, station_alpha, station_beta, 
                                     station_gamma, tool_cabinet, msg_, 
                                     did_first_, job1_passed_, msg_w, 
                                     did_first_w, job1_passed_w, job2_passed_w, 
                                     msg_wo, did_first, job1_passed, 
                                     job2_passed, msg_i, passed, src, msg >>

wa_s2_rework(self) == /\ pc[self] = "wa_s2_rework"
                      /\ Len(disp_to_wA) > 0
                      /\ msg_' = [msg_ EXCEPT ![self] = Head(disp_to_wA)]
                      /\ disp_to_wA' = Tail(disp_to_wA)
                      /\ pc' = [pc EXCEPT ![self] = "wa_second"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_disp, disp_to_wB, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, did_first_, 
                                      job1_passed_, job2_passed_, msg_w, 
                                      did_first_w, job1_passed_w, 
                                      job2_passed_w, msg_wo, did_first, 
                                      job1_passed, job2_passed, msg_i, passed, 
                                      src, msg >>

wa_s1_tool(self) == /\ pc[self] = "wa_s1_tool"
                    /\ tool_cabinet > 0
                    /\ tool_cabinet' = tool_cabinet - 1
                    /\ pc' = [pc EXCEPT ![self] = "wa_s1_work"]
                    /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                    insp_to_wA, insp_to_wB, insp_to_wC, 
                                    insp_to_disp, disp_to_wA, disp_to_wB, 
                                    disp_to_wC, station_alpha, station_beta, 
                                    station_gamma, msg_, did_first_, 
                                    job1_passed_, job2_passed_, msg_w, 
                                    did_first_w, job1_passed_w, job2_passed_w, 
                                    msg_wo, did_first, job1_passed, 
                                    job2_passed, msg_i, passed, src, msg >>

wa_s1_work(self) == /\ pc[self] = "wa_s1_work"
                    /\ tool_cabinet' = tool_cabinet + 1
                    /\ station_alpha' = "FREE"
                    /\ wA_to_insp' = Append(wA_to_insp, "inspect")
                    /\ pc' = [pc EXCEPT ![self] = "wa_s1_result"]
                    /\ UNCHANGED << wB_to_insp, wC_to_insp, insp_to_wA, 
                                    insp_to_wB, insp_to_wC, insp_to_disp, 
                                    disp_to_wA, disp_to_wB, disp_to_wC, 
                                    station_beta, station_gamma, msg_, 
                                    did_first_, job1_passed_, job2_passed_, 
                                    msg_w, did_first_w, job1_passed_w, 
                                    job2_passed_w, msg_wo, did_first, 
                                    job1_passed, job2_passed, msg_i, passed, 
                                    src, msg >>

wa_s1_result(self) == /\ pc[self] = "wa_s1_result"
                      /\ Len(insp_to_wA) > 0
                      /\ msg_' = [msg_ EXCEPT ![self] = Head(insp_to_wA)]
                      /\ insp_to_wA' = Tail(insp_to_wA)
                      /\ pc' = [pc EXCEPT ![self] = "wa_s1_check"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wB, insp_to_wC, insp_to_disp, 
                                      disp_to_wA, disp_to_wB, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, did_first_, 
                                      job1_passed_, job2_passed_, msg_w, 
                                      did_first_w, job1_passed_w, 
                                      job2_passed_w, msg_wo, did_first, 
                                      job1_passed, job2_passed, msg_i, passed, 
                                      src, msg >>

wa_s1_check(self) == /\ pc[self] = "wa_s1_check"
                     /\ IF msg_[self] = "pass"
                           THEN /\ job1_passed_' = [job1_passed_ EXCEPT ![self] = TRUE]
                                /\ pc' = [pc EXCEPT ![self] = "wa_done"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "wa_s1_rework"]
                                /\ UNCHANGED job1_passed_
                     /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                     insp_to_wA, insp_to_wB, insp_to_wC, 
                                     insp_to_disp, disp_to_wA, disp_to_wB, 
                                     disp_to_wC, station_alpha, station_beta, 
                                     station_gamma, tool_cabinet, msg_, 
                                     did_first_, job2_passed_, msg_w, 
                                     did_first_w, job1_passed_w, job2_passed_w, 
                                     msg_wo, did_first, job1_passed, 
                                     job2_passed, msg_i, passed, src, msg >>

wa_s1_rework(self) == /\ pc[self] = "wa_s1_rework"
                      /\ Len(disp_to_wA) > 0
                      /\ msg_' = [msg_ EXCEPT ![self] = Head(disp_to_wA)]
                      /\ disp_to_wA' = Tail(disp_to_wA)
                      /\ pc' = [pc EXCEPT ![self] = "wa_second"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_disp, disp_to_wB, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, did_first_, 
                                      job1_passed_, job2_passed_, msg_w, 
                                      did_first_w, job1_passed_w, 
                                      job2_passed_w, msg_wo, did_first, 
                                      job1_passed, job2_passed, msg_i, passed, 
                                      src, msg >>

wa_done(self) == /\ pc[self] = "wa_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                 insp_to_wA, insp_to_wB, insp_to_wC, 
                                 insp_to_disp, disp_to_wA, disp_to_wB, 
                                 disp_to_wC, station_alpha, station_beta, 
                                 station_gamma, tool_cabinet, msg_, did_first_, 
                                 job1_passed_, job2_passed_, msg_w, 
                                 did_first_w, job1_passed_w, job2_passed_w, 
                                 msg_wo, did_first, job1_passed, job2_passed, 
                                 msg_i, passed, src, msg >>

workerA_proc(self) == wa_choose(self) \/ wa_j1_tool(self)
                         \/ wa_j1_work(self) \/ wa_j1_result(self)
                         \/ wa_j1_check(self) \/ wa_j1_rework(self)
                         \/ wa_j2_work(self) \/ wa_j2_result(self)
                         \/ wa_j2_check(self) \/ wa_j2_rework(self)
                         \/ wa_second(self) \/ wa_s2_work(self)
                         \/ wa_s2_result(self) \/ wa_s2_check(self)
                         \/ wa_s2_rework(self) \/ wa_s1_tool(self)
                         \/ wa_s1_work(self) \/ wa_s1_result(self)
                         \/ wa_s1_check(self) \/ wa_s1_rework(self)
                         \/ wa_done(self)

wb_choose(self) == /\ pc[self] = "wb_choose"
                   /\ \/ /\ station_beta = "FREE"
                         /\ station_beta' = self
                         /\ pc' = [pc EXCEPT ![self] = "wb_j1_tool"]
                         /\ UNCHANGED station_gamma
                      \/ /\ station_gamma = "FREE"
                         /\ station_gamma' = self
                         /\ pc' = [pc EXCEPT ![self] = "wb_j2_work"]
                         /\ UNCHANGED station_beta
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   insp_to_wA, insp_to_wB, insp_to_wC, 
                                   insp_to_disp, disp_to_wA, disp_to_wB, 
                                   disp_to_wC, station_alpha, tool_cabinet, 
                                   msg_, did_first_, job1_passed_, 
                                   job2_passed_, msg_w, did_first_w, 
                                   job1_passed_w, job2_passed_w, msg_wo, 
                                   did_first, job1_passed, job2_passed, msg_i, 
                                   passed, src, msg >>

wb_j1_tool(self) == /\ pc[self] = "wb_j1_tool"
                    /\ tool_cabinet > 0
                    /\ tool_cabinet' = tool_cabinet - 1
                    /\ pc' = [pc EXCEPT ![self] = "wb_j1_work"]
                    /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                    insp_to_wA, insp_to_wB, insp_to_wC, 
                                    insp_to_disp, disp_to_wA, disp_to_wB, 
                                    disp_to_wC, station_alpha, station_beta, 
                                    station_gamma, msg_, did_first_, 
                                    job1_passed_, job2_passed_, msg_w, 
                                    did_first_w, job1_passed_w, job2_passed_w, 
                                    msg_wo, did_first, job1_passed, 
                                    job2_passed, msg_i, passed, src, msg >>

wb_j1_work(self) == /\ pc[self] = "wb_j1_work"
                    /\ tool_cabinet' = tool_cabinet + 1
                    /\ station_beta' = "FREE"
                    /\ wB_to_insp' = Append(wB_to_insp, "inspect")
                    /\ pc' = [pc EXCEPT ![self] = "wb_j1_result"]
                    /\ UNCHANGED << wA_to_insp, wC_to_insp, insp_to_wA, 
                                    insp_to_wB, insp_to_wC, insp_to_disp, 
                                    disp_to_wA, disp_to_wB, disp_to_wC, 
                                    station_alpha, station_gamma, msg_, 
                                    did_first_, job1_passed_, job2_passed_, 
                                    msg_w, did_first_w, job1_passed_w, 
                                    job2_passed_w, msg_wo, did_first, 
                                    job1_passed, job2_passed, msg_i, passed, 
                                    src, msg >>

wb_j1_result(self) == /\ pc[self] = "wb_j1_result"
                      /\ Len(insp_to_wB) > 0
                      /\ msg_w' = [msg_w EXCEPT ![self] = Head(insp_to_wB)]
                      /\ insp_to_wB' = Tail(insp_to_wB)
                      /\ pc' = [pc EXCEPT ![self] = "wb_j1_check"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wC, insp_to_disp, 
                                      disp_to_wA, disp_to_wB, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, msg_, 
                                      did_first_, job1_passed_, job2_passed_, 
                                      did_first_w, job1_passed_w, 
                                      job2_passed_w, msg_wo, did_first, 
                                      job1_passed, job2_passed, msg_i, passed, 
                                      src, msg >>

wb_j1_check(self) == /\ pc[self] = "wb_j1_check"
                     /\ IF msg_w[self] = "pass"
                           THEN /\ job1_passed_w' = [job1_passed_w EXCEPT ![self] = TRUE]
                                /\ did_first_w' = [did_first_w EXCEPT ![self] = TRUE]
                                /\ pc' = [pc EXCEPT ![self] = "wb_second"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "wb_j1_rework"]
                                /\ UNCHANGED << did_first_w, job1_passed_w >>
                     /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                     insp_to_wA, insp_to_wB, insp_to_wC, 
                                     insp_to_disp, disp_to_wA, disp_to_wB, 
                                     disp_to_wC, station_alpha, station_beta, 
                                     station_gamma, tool_cabinet, msg_, 
                                     did_first_, job1_passed_, job2_passed_, 
                                     msg_w, job2_passed_w, msg_wo, did_first, 
                                     job1_passed, job2_passed, msg_i, passed, 
                                     src, msg >>

wb_j1_rework(self) == /\ pc[self] = "wb_j1_rework"
                      /\ Len(disp_to_wB) > 0
                      /\ msg_w' = [msg_w EXCEPT ![self] = Head(disp_to_wB)]
                      /\ disp_to_wB' = Tail(disp_to_wB)
                      /\ pc' = [pc EXCEPT ![self] = "wb_choose"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_disp, disp_to_wA, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, msg_, 
                                      did_first_, job1_passed_, job2_passed_, 
                                      did_first_w, job1_passed_w, 
                                      job2_passed_w, msg_wo, did_first, 
                                      job1_passed, job2_passed, msg_i, passed, 
                                      src, msg >>

wb_j2_work(self) == /\ pc[self] = "wb_j2_work"
                    /\ station_gamma' = "FREE"
                    /\ wB_to_insp' = Append(wB_to_insp, "inspect")
                    /\ pc' = [pc EXCEPT ![self] = "wb_j2_result"]
                    /\ UNCHANGED << wA_to_insp, wC_to_insp, insp_to_wA, 
                                    insp_to_wB, insp_to_wC, insp_to_disp, 
                                    disp_to_wA, disp_to_wB, disp_to_wC, 
                                    station_alpha, station_beta, tool_cabinet, 
                                    msg_, did_first_, job1_passed_, 
                                    job2_passed_, msg_w, did_first_w, 
                                    job1_passed_w, job2_passed_w, msg_wo, 
                                    did_first, job1_passed, job2_passed, msg_i, 
                                    passed, src, msg >>

wb_j2_result(self) == /\ pc[self] = "wb_j2_result"
                      /\ Len(insp_to_wB) > 0
                      /\ msg_w' = [msg_w EXCEPT ![self] = Head(insp_to_wB)]
                      /\ insp_to_wB' = Tail(insp_to_wB)
                      /\ pc' = [pc EXCEPT ![self] = "wb_j2_check"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wC, insp_to_disp, 
                                      disp_to_wA, disp_to_wB, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, msg_, 
                                      did_first_, job1_passed_, job2_passed_, 
                                      did_first_w, job1_passed_w, 
                                      job2_passed_w, msg_wo, did_first, 
                                      job1_passed, job2_passed, msg_i, passed, 
                                      src, msg >>

wb_j2_check(self) == /\ pc[self] = "wb_j2_check"
                     /\ IF msg_w[self] = "pass"
                           THEN /\ job2_passed_w' = [job2_passed_w EXCEPT ![self] = TRUE]
                                /\ did_first_w' = [did_first_w EXCEPT ![self] = TRUE]
                                /\ pc' = [pc EXCEPT ![self] = "wb_second"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "wb_j2_rework"]
                                /\ UNCHANGED << did_first_w, job2_passed_w >>
                     /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                     insp_to_wA, insp_to_wB, insp_to_wC, 
                                     insp_to_disp, disp_to_wA, disp_to_wB, 
                                     disp_to_wC, station_alpha, station_beta, 
                                     station_gamma, tool_cabinet, msg_, 
                                     did_first_, job1_passed_, job2_passed_, 
                                     msg_w, job1_passed_w, msg_wo, did_first, 
                                     job1_passed, job2_passed, msg_i, passed, 
                                     src, msg >>

wb_j2_rework(self) == /\ pc[self] = "wb_j2_rework"
                      /\ Len(disp_to_wB) > 0
                      /\ msg_w' = [msg_w EXCEPT ![self] = Head(disp_to_wB)]
                      /\ disp_to_wB' = Tail(disp_to_wB)
                      /\ pc' = [pc EXCEPT ![self] = "wb_choose"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_disp, disp_to_wA, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, msg_, 
                                      did_first_, job1_passed_, job2_passed_, 
                                      did_first_w, job1_passed_w, 
                                      job2_passed_w, msg_wo, did_first, 
                                      job1_passed, job2_passed, msg_i, passed, 
                                      src, msg >>

wb_second(self) == /\ pc[self] = "wb_second"
                   /\ IF job1_passed_w[self] /\ ~job2_passed_w[self]
                         THEN /\ station_gamma = "FREE"
                              /\ station_gamma' = self
                              /\ pc' = [pc EXCEPT ![self] = "wb_s2_work"]
                              /\ UNCHANGED station_beta
                         ELSE /\ station_beta = "FREE"
                              /\ station_beta' = self
                              /\ pc' = [pc EXCEPT ![self] = "wb_s1_tool"]
                              /\ UNCHANGED station_gamma
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   insp_to_wA, insp_to_wB, insp_to_wC, 
                                   insp_to_disp, disp_to_wA, disp_to_wB, 
                                   disp_to_wC, station_alpha, tool_cabinet, 
                                   msg_, did_first_, job1_passed_, 
                                   job2_passed_, msg_w, did_first_w, 
                                   job1_passed_w, job2_passed_w, msg_wo, 
                                   did_first, job1_passed, job2_passed, msg_i, 
                                   passed, src, msg >>

wb_s2_work(self) == /\ pc[self] = "wb_s2_work"
                    /\ station_gamma' = "FREE"
                    /\ wB_to_insp' = Append(wB_to_insp, "inspect")
                    /\ pc' = [pc EXCEPT ![self] = "wb_s2_result"]
                    /\ UNCHANGED << wA_to_insp, wC_to_insp, insp_to_wA, 
                                    insp_to_wB, insp_to_wC, insp_to_disp, 
                                    disp_to_wA, disp_to_wB, disp_to_wC, 
                                    station_alpha, station_beta, tool_cabinet, 
                                    msg_, did_first_, job1_passed_, 
                                    job2_passed_, msg_w, did_first_w, 
                                    job1_passed_w, job2_passed_w, msg_wo, 
                                    did_first, job1_passed, job2_passed, msg_i, 
                                    passed, src, msg >>

wb_s2_result(self) == /\ pc[self] = "wb_s2_result"
                      /\ Len(insp_to_wB) > 0
                      /\ msg_w' = [msg_w EXCEPT ![self] = Head(insp_to_wB)]
                      /\ insp_to_wB' = Tail(insp_to_wB)
                      /\ pc' = [pc EXCEPT ![self] = "wb_s2_check"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wC, insp_to_disp, 
                                      disp_to_wA, disp_to_wB, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, msg_, 
                                      did_first_, job1_passed_, job2_passed_, 
                                      did_first_w, job1_passed_w, 
                                      job2_passed_w, msg_wo, did_first, 
                                      job1_passed, job2_passed, msg_i, passed, 
                                      src, msg >>

wb_s2_check(self) == /\ pc[self] = "wb_s2_check"
                     /\ IF msg_w[self] = "pass"
                           THEN /\ job2_passed_w' = [job2_passed_w EXCEPT ![self] = TRUE]
                                /\ pc' = [pc EXCEPT ![self] = "wb_done"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "wb_s2_rework"]
                                /\ UNCHANGED job2_passed_w
                     /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                     insp_to_wA, insp_to_wB, insp_to_wC, 
                                     insp_to_disp, disp_to_wA, disp_to_wB, 
                                     disp_to_wC, station_alpha, station_beta, 
                                     station_gamma, tool_cabinet, msg_, 
                                     did_first_, job1_passed_, job2_passed_, 
                                     msg_w, did_first_w, job1_passed_w, msg_wo, 
                                     did_first, job1_passed, job2_passed, 
                                     msg_i, passed, src, msg >>

wb_s2_rework(self) == /\ pc[self] = "wb_s2_rework"
                      /\ Len(disp_to_wB) > 0
                      /\ msg_w' = [msg_w EXCEPT ![self] = Head(disp_to_wB)]
                      /\ disp_to_wB' = Tail(disp_to_wB)
                      /\ pc' = [pc EXCEPT ![self] = "wb_second"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_disp, disp_to_wA, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, msg_, 
                                      did_first_, job1_passed_, job2_passed_, 
                                      did_first_w, job1_passed_w, 
                                      job2_passed_w, msg_wo, did_first, 
                                      job1_passed, job2_passed, msg_i, passed, 
                                      src, msg >>

wb_s1_tool(self) == /\ pc[self] = "wb_s1_tool"
                    /\ tool_cabinet > 0
                    /\ tool_cabinet' = tool_cabinet - 1
                    /\ pc' = [pc EXCEPT ![self] = "wb_s1_work"]
                    /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                    insp_to_wA, insp_to_wB, insp_to_wC, 
                                    insp_to_disp, disp_to_wA, disp_to_wB, 
                                    disp_to_wC, station_alpha, station_beta, 
                                    station_gamma, msg_, did_first_, 
                                    job1_passed_, job2_passed_, msg_w, 
                                    did_first_w, job1_passed_w, job2_passed_w, 
                                    msg_wo, did_first, job1_passed, 
                                    job2_passed, msg_i, passed, src, msg >>

wb_s1_work(self) == /\ pc[self] = "wb_s1_work"
                    /\ tool_cabinet' = tool_cabinet + 1
                    /\ station_beta' = "FREE"
                    /\ wB_to_insp' = Append(wB_to_insp, "inspect")
                    /\ pc' = [pc EXCEPT ![self] = "wb_s1_result"]
                    /\ UNCHANGED << wA_to_insp, wC_to_insp, insp_to_wA, 
                                    insp_to_wB, insp_to_wC, insp_to_disp, 
                                    disp_to_wA, disp_to_wB, disp_to_wC, 
                                    station_alpha, station_gamma, msg_, 
                                    did_first_, job1_passed_, job2_passed_, 
                                    msg_w, did_first_w, job1_passed_w, 
                                    job2_passed_w, msg_wo, did_first, 
                                    job1_passed, job2_passed, msg_i, passed, 
                                    src, msg >>

wb_s1_result(self) == /\ pc[self] = "wb_s1_result"
                      /\ Len(insp_to_wB) > 0
                      /\ msg_w' = [msg_w EXCEPT ![self] = Head(insp_to_wB)]
                      /\ insp_to_wB' = Tail(insp_to_wB)
                      /\ pc' = [pc EXCEPT ![self] = "wb_s1_check"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wC, insp_to_disp, 
                                      disp_to_wA, disp_to_wB, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, msg_, 
                                      did_first_, job1_passed_, job2_passed_, 
                                      did_first_w, job1_passed_w, 
                                      job2_passed_w, msg_wo, did_first, 
                                      job1_passed, job2_passed, msg_i, passed, 
                                      src, msg >>

wb_s1_check(self) == /\ pc[self] = "wb_s1_check"
                     /\ IF msg_w[self] = "pass"
                           THEN /\ job1_passed_w' = [job1_passed_w EXCEPT ![self] = TRUE]
                                /\ pc' = [pc EXCEPT ![self] = "wb_done"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "wb_s1_rework"]
                                /\ UNCHANGED job1_passed_w
                     /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                     insp_to_wA, insp_to_wB, insp_to_wC, 
                                     insp_to_disp, disp_to_wA, disp_to_wB, 
                                     disp_to_wC, station_alpha, station_beta, 
                                     station_gamma, tool_cabinet, msg_, 
                                     did_first_, job1_passed_, job2_passed_, 
                                     msg_w, did_first_w, job2_passed_w, msg_wo, 
                                     did_first, job1_passed, job2_passed, 
                                     msg_i, passed, src, msg >>

wb_s1_rework(self) == /\ pc[self] = "wb_s1_rework"
                      /\ Len(disp_to_wB) > 0
                      /\ msg_w' = [msg_w EXCEPT ![self] = Head(disp_to_wB)]
                      /\ disp_to_wB' = Tail(disp_to_wB)
                      /\ pc' = [pc EXCEPT ![self] = "wb_second"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_disp, disp_to_wA, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, msg_, 
                                      did_first_, job1_passed_, job2_passed_, 
                                      did_first_w, job1_passed_w, 
                                      job2_passed_w, msg_wo, did_first, 
                                      job1_passed, job2_passed, msg_i, passed, 
                                      src, msg >>

wb_done(self) == /\ pc[self] = "wb_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                 insp_to_wA, insp_to_wB, insp_to_wC, 
                                 insp_to_disp, disp_to_wA, disp_to_wB, 
                                 disp_to_wC, station_alpha, station_beta, 
                                 station_gamma, tool_cabinet, msg_, did_first_, 
                                 job1_passed_, job2_passed_, msg_w, 
                                 did_first_w, job1_passed_w, job2_passed_w, 
                                 msg_wo, did_first, job1_passed, job2_passed, 
                                 msg_i, passed, src, msg >>

workerB_proc(self) == wb_choose(self) \/ wb_j1_tool(self)
                         \/ wb_j1_work(self) \/ wb_j1_result(self)
                         \/ wb_j1_check(self) \/ wb_j1_rework(self)
                         \/ wb_j2_work(self) \/ wb_j2_result(self)
                         \/ wb_j2_check(self) \/ wb_j2_rework(self)
                         \/ wb_second(self) \/ wb_s2_work(self)
                         \/ wb_s2_result(self) \/ wb_s2_check(self)
                         \/ wb_s2_rework(self) \/ wb_s1_tool(self)
                         \/ wb_s1_work(self) \/ wb_s1_result(self)
                         \/ wb_s1_check(self) \/ wb_s1_rework(self)
                         \/ wb_done(self)

wc_choose(self) == /\ pc[self] = "wc_choose"
                   /\ \/ /\ station_gamma = "FREE"
                         /\ station_gamma' = self
                         /\ pc' = [pc EXCEPT ![self] = "wc_j1_tool"]
                         /\ UNCHANGED station_alpha
                      \/ /\ station_alpha = "FREE"
                         /\ station_alpha' = self
                         /\ pc' = [pc EXCEPT ![self] = "wc_j2_work"]
                         /\ UNCHANGED station_gamma
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   insp_to_wA, insp_to_wB, insp_to_wC, 
                                   insp_to_disp, disp_to_wA, disp_to_wB, 
                                   disp_to_wC, station_beta, tool_cabinet, 
                                   msg_, did_first_, job1_passed_, 
                                   job2_passed_, msg_w, did_first_w, 
                                   job1_passed_w, job2_passed_w, msg_wo, 
                                   did_first, job1_passed, job2_passed, msg_i, 
                                   passed, src, msg >>

wc_j1_tool(self) == /\ pc[self] = "wc_j1_tool"
                    /\ tool_cabinet > 0
                    /\ tool_cabinet' = tool_cabinet - 1
                    /\ pc' = [pc EXCEPT ![self] = "wc_j1_work"]
                    /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                    insp_to_wA, insp_to_wB, insp_to_wC, 
                                    insp_to_disp, disp_to_wA, disp_to_wB, 
                                    disp_to_wC, station_alpha, station_beta, 
                                    station_gamma, msg_, did_first_, 
                                    job1_passed_, job2_passed_, msg_w, 
                                    did_first_w, job1_passed_w, job2_passed_w, 
                                    msg_wo, did_first, job1_passed, 
                                    job2_passed, msg_i, passed, src, msg >>

wc_j1_work(self) == /\ pc[self] = "wc_j1_work"
                    /\ tool_cabinet' = tool_cabinet + 1
                    /\ station_gamma' = "FREE"
                    /\ wC_to_insp' = Append(wC_to_insp, "inspect")
                    /\ pc' = [pc EXCEPT ![self] = "wc_j1_result"]
                    /\ UNCHANGED << wA_to_insp, wB_to_insp, insp_to_wA, 
                                    insp_to_wB, insp_to_wC, insp_to_disp, 
                                    disp_to_wA, disp_to_wB, disp_to_wC, 
                                    station_alpha, station_beta, msg_, 
                                    did_first_, job1_passed_, job2_passed_, 
                                    msg_w, did_first_w, job1_passed_w, 
                                    job2_passed_w, msg_wo, did_first, 
                                    job1_passed, job2_passed, msg_i, passed, 
                                    src, msg >>

wc_j1_result(self) == /\ pc[self] = "wc_j1_result"
                      /\ Len(insp_to_wC) > 0
                      /\ msg_wo' = [msg_wo EXCEPT ![self] = Head(insp_to_wC)]
                      /\ insp_to_wC' = Tail(insp_to_wC)
                      /\ pc' = [pc EXCEPT ![self] = "wc_j1_check"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_disp, 
                                      disp_to_wA, disp_to_wB, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, msg_, 
                                      did_first_, job1_passed_, job2_passed_, 
                                      msg_w, did_first_w, job1_passed_w, 
                                      job2_passed_w, did_first, job1_passed, 
                                      job2_passed, msg_i, passed, src, msg >>

wc_j1_check(self) == /\ pc[self] = "wc_j1_check"
                     /\ IF msg_wo[self] = "pass"
                           THEN /\ job1_passed' = [job1_passed EXCEPT ![self] = TRUE]
                                /\ did_first' = [did_first EXCEPT ![self] = TRUE]
                                /\ pc' = [pc EXCEPT ![self] = "wc_second"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "wc_j1_rework"]
                                /\ UNCHANGED << did_first, job1_passed >>
                     /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                     insp_to_wA, insp_to_wB, insp_to_wC, 
                                     insp_to_disp, disp_to_wA, disp_to_wB, 
                                     disp_to_wC, station_alpha, station_beta, 
                                     station_gamma, tool_cabinet, msg_, 
                                     did_first_, job1_passed_, job2_passed_, 
                                     msg_w, did_first_w, job1_passed_w, 
                                     job2_passed_w, msg_wo, job2_passed, msg_i, 
                                     passed, src, msg >>

wc_j1_rework(self) == /\ pc[self] = "wc_j1_rework"
                      /\ Len(disp_to_wC) > 0
                      /\ msg_wo' = [msg_wo EXCEPT ![self] = Head(disp_to_wC)]
                      /\ disp_to_wC' = Tail(disp_to_wC)
                      /\ pc' = [pc EXCEPT ![self] = "wc_choose"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_disp, disp_to_wA, disp_to_wB, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, msg_, 
                                      did_first_, job1_passed_, job2_passed_, 
                                      msg_w, did_first_w, job1_passed_w, 
                                      job2_passed_w, did_first, job1_passed, 
                                      job2_passed, msg_i, passed, src, msg >>

wc_j2_work(self) == /\ pc[self] = "wc_j2_work"
                    /\ station_alpha' = "FREE"
                    /\ wC_to_insp' = Append(wC_to_insp, "inspect")
                    /\ pc' = [pc EXCEPT ![self] = "wc_j2_result"]
                    /\ UNCHANGED << wA_to_insp, wB_to_insp, insp_to_wA, 
                                    insp_to_wB, insp_to_wC, insp_to_disp, 
                                    disp_to_wA, disp_to_wB, disp_to_wC, 
                                    station_beta, station_gamma, tool_cabinet, 
                                    msg_, did_first_, job1_passed_, 
                                    job2_passed_, msg_w, did_first_w, 
                                    job1_passed_w, job2_passed_w, msg_wo, 
                                    did_first, job1_passed, job2_passed, msg_i, 
                                    passed, src, msg >>

wc_j2_result(self) == /\ pc[self] = "wc_j2_result"
                      /\ Len(insp_to_wC) > 0
                      /\ msg_wo' = [msg_wo EXCEPT ![self] = Head(insp_to_wC)]
                      /\ insp_to_wC' = Tail(insp_to_wC)
                      /\ pc' = [pc EXCEPT ![self] = "wc_j2_check"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_disp, 
                                      disp_to_wA, disp_to_wB, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, msg_, 
                                      did_first_, job1_passed_, job2_passed_, 
                                      msg_w, did_first_w, job1_passed_w, 
                                      job2_passed_w, did_first, job1_passed, 
                                      job2_passed, msg_i, passed, src, msg >>

wc_j2_check(self) == /\ pc[self] = "wc_j2_check"
                     /\ IF msg_wo[self] = "pass"
                           THEN /\ job2_passed' = [job2_passed EXCEPT ![self] = TRUE]
                                /\ did_first' = [did_first EXCEPT ![self] = TRUE]
                                /\ pc' = [pc EXCEPT ![self] = "wc_second"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "wc_j2_rework"]
                                /\ UNCHANGED << did_first, job2_passed >>
                     /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                     insp_to_wA, insp_to_wB, insp_to_wC, 
                                     insp_to_disp, disp_to_wA, disp_to_wB, 
                                     disp_to_wC, station_alpha, station_beta, 
                                     station_gamma, tool_cabinet, msg_, 
                                     did_first_, job1_passed_, job2_passed_, 
                                     msg_w, did_first_w, job1_passed_w, 
                                     job2_passed_w, msg_wo, job1_passed, msg_i, 
                                     passed, src, msg >>

wc_j2_rework(self) == /\ pc[self] = "wc_j2_rework"
                      /\ Len(disp_to_wC) > 0
                      /\ msg_wo' = [msg_wo EXCEPT ![self] = Head(disp_to_wC)]
                      /\ disp_to_wC' = Tail(disp_to_wC)
                      /\ pc' = [pc EXCEPT ![self] = "wc_choose"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_disp, disp_to_wA, disp_to_wB, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, msg_, 
                                      did_first_, job1_passed_, job2_passed_, 
                                      msg_w, did_first_w, job1_passed_w, 
                                      job2_passed_w, did_first, job1_passed, 
                                      job2_passed, msg_i, passed, src, msg >>

wc_second(self) == /\ pc[self] = "wc_second"
                   /\ IF job1_passed[self] /\ ~job2_passed[self]
                         THEN /\ station_alpha = "FREE"
                              /\ station_alpha' = self
                              /\ pc' = [pc EXCEPT ![self] = "wc_s2_work"]
                              /\ UNCHANGED station_gamma
                         ELSE /\ station_gamma = "FREE"
                              /\ station_gamma' = self
                              /\ pc' = [pc EXCEPT ![self] = "wc_s1_tool"]
                              /\ UNCHANGED station_alpha
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   insp_to_wA, insp_to_wB, insp_to_wC, 
                                   insp_to_disp, disp_to_wA, disp_to_wB, 
                                   disp_to_wC, station_beta, tool_cabinet, 
                                   msg_, did_first_, job1_passed_, 
                                   job2_passed_, msg_w, did_first_w, 
                                   job1_passed_w, job2_passed_w, msg_wo, 
                                   did_first, job1_passed, job2_passed, msg_i, 
                                   passed, src, msg >>

wc_s2_work(self) == /\ pc[self] = "wc_s2_work"
                    /\ station_alpha' = "FREE"
                    /\ wC_to_insp' = Append(wC_to_insp, "inspect")
                    /\ pc' = [pc EXCEPT ![self] = "wc_s2_result"]
                    /\ UNCHANGED << wA_to_insp, wB_to_insp, insp_to_wA, 
                                    insp_to_wB, insp_to_wC, insp_to_disp, 
                                    disp_to_wA, disp_to_wB, disp_to_wC, 
                                    station_beta, station_gamma, tool_cabinet, 
                                    msg_, did_first_, job1_passed_, 
                                    job2_passed_, msg_w, did_first_w, 
                                    job1_passed_w, job2_passed_w, msg_wo, 
                                    did_first, job1_passed, job2_passed, msg_i, 
                                    passed, src, msg >>

wc_s2_result(self) == /\ pc[self] = "wc_s2_result"
                      /\ Len(insp_to_wC) > 0
                      /\ msg_wo' = [msg_wo EXCEPT ![self] = Head(insp_to_wC)]
                      /\ insp_to_wC' = Tail(insp_to_wC)
                      /\ pc' = [pc EXCEPT ![self] = "wc_s2_check"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_disp, 
                                      disp_to_wA, disp_to_wB, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, msg_, 
                                      did_first_, job1_passed_, job2_passed_, 
                                      msg_w, did_first_w, job1_passed_w, 
                                      job2_passed_w, did_first, job1_passed, 
                                      job2_passed, msg_i, passed, src, msg >>

wc_s2_check(self) == /\ pc[self] = "wc_s2_check"
                     /\ IF msg_wo[self] = "pass"
                           THEN /\ job2_passed' = [job2_passed EXCEPT ![self] = TRUE]
                                /\ pc' = [pc EXCEPT ![self] = "wc_done"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "wc_s2_rework"]
                                /\ UNCHANGED job2_passed
                     /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                     insp_to_wA, insp_to_wB, insp_to_wC, 
                                     insp_to_disp, disp_to_wA, disp_to_wB, 
                                     disp_to_wC, station_alpha, station_beta, 
                                     station_gamma, tool_cabinet, msg_, 
                                     did_first_, job1_passed_, job2_passed_, 
                                     msg_w, did_first_w, job1_passed_w, 
                                     job2_passed_w, msg_wo, did_first, 
                                     job1_passed, msg_i, passed, src, msg >>

wc_s2_rework(self) == /\ pc[self] = "wc_s2_rework"
                      /\ Len(disp_to_wC) > 0
                      /\ msg_wo' = [msg_wo EXCEPT ![self] = Head(disp_to_wC)]
                      /\ disp_to_wC' = Tail(disp_to_wC)
                      /\ pc' = [pc EXCEPT ![self] = "wc_second"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_disp, disp_to_wA, disp_to_wB, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, msg_, 
                                      did_first_, job1_passed_, job2_passed_, 
                                      msg_w, did_first_w, job1_passed_w, 
                                      job2_passed_w, did_first, job1_passed, 
                                      job2_passed, msg_i, passed, src, msg >>

wc_s1_tool(self) == /\ pc[self] = "wc_s1_tool"
                    /\ tool_cabinet > 0
                    /\ tool_cabinet' = tool_cabinet - 1
                    /\ pc' = [pc EXCEPT ![self] = "wc_s1_work"]
                    /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                    insp_to_wA, insp_to_wB, insp_to_wC, 
                                    insp_to_disp, disp_to_wA, disp_to_wB, 
                                    disp_to_wC, station_alpha, station_beta, 
                                    station_gamma, msg_, did_first_, 
                                    job1_passed_, job2_passed_, msg_w, 
                                    did_first_w, job1_passed_w, job2_passed_w, 
                                    msg_wo, did_first, job1_passed, 
                                    job2_passed, msg_i, passed, src, msg >>

wc_s1_work(self) == /\ pc[self] = "wc_s1_work"
                    /\ tool_cabinet' = tool_cabinet + 1
                    /\ station_gamma' = "FREE"
                    /\ wC_to_insp' = Append(wC_to_insp, "inspect")
                    /\ pc' = [pc EXCEPT ![self] = "wc_s1_result"]
                    /\ UNCHANGED << wA_to_insp, wB_to_insp, insp_to_wA, 
                                    insp_to_wB, insp_to_wC, insp_to_disp, 
                                    disp_to_wA, disp_to_wB, disp_to_wC, 
                                    station_alpha, station_beta, msg_, 
                                    did_first_, job1_passed_, job2_passed_, 
                                    msg_w, did_first_w, job1_passed_w, 
                                    job2_passed_w, msg_wo, did_first, 
                                    job1_passed, job2_passed, msg_i, passed, 
                                    src, msg >>

wc_s1_result(self) == /\ pc[self] = "wc_s1_result"
                      /\ Len(insp_to_wC) > 0
                      /\ msg_wo' = [msg_wo EXCEPT ![self] = Head(insp_to_wC)]
                      /\ insp_to_wC' = Tail(insp_to_wC)
                      /\ pc' = [pc EXCEPT ![self] = "wc_s1_check"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_disp, 
                                      disp_to_wA, disp_to_wB, disp_to_wC, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, msg_, 
                                      did_first_, job1_passed_, job2_passed_, 
                                      msg_w, did_first_w, job1_passed_w, 
                                      job2_passed_w, did_first, job1_passed, 
                                      job2_passed, msg_i, passed, src, msg >>

wc_s1_check(self) == /\ pc[self] = "wc_s1_check"
                     /\ IF msg_wo[self] = "pass"
                           THEN /\ job1_passed' = [job1_passed EXCEPT ![self] = TRUE]
                                /\ pc' = [pc EXCEPT ![self] = "wc_done"]
                           ELSE /\ pc' = [pc EXCEPT ![self] = "wc_s1_rework"]
                                /\ UNCHANGED job1_passed
                     /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                     insp_to_wA, insp_to_wB, insp_to_wC, 
                                     insp_to_disp, disp_to_wA, disp_to_wB, 
                                     disp_to_wC, station_alpha, station_beta, 
                                     station_gamma, tool_cabinet, msg_, 
                                     did_first_, job1_passed_, job2_passed_, 
                                     msg_w, did_first_w, job1_passed_w, 
                                     job2_passed_w, msg_wo, did_first, 
                                     job2_passed, msg_i, passed, src, msg >>

wc_s1_rework(self) == /\ pc[self] = "wc_s1_rework"
                      /\ Len(disp_to_wC) > 0
                      /\ msg_wo' = [msg_wo EXCEPT ![self] = Head(disp_to_wC)]
                      /\ disp_to_wC' = Tail(disp_to_wC)
                      /\ pc' = [pc EXCEPT ![self] = "wc_second"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_disp, disp_to_wA, disp_to_wB, 
                                      station_alpha, station_beta, 
                                      station_gamma, tool_cabinet, msg_, 
                                      did_first_, job1_passed_, job2_passed_, 
                                      msg_w, did_first_w, job1_passed_w, 
                                      job2_passed_w, did_first, job1_passed, 
                                      job2_passed, msg_i, passed, src, msg >>

wc_done(self) == /\ pc[self] = "wc_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                 insp_to_wA, insp_to_wB, insp_to_wC, 
                                 insp_to_disp, disp_to_wA, disp_to_wB, 
                                 disp_to_wC, station_alpha, station_beta, 
                                 station_gamma, tool_cabinet, msg_, did_first_, 
                                 job1_passed_, job2_passed_, msg_w, 
                                 did_first_w, job1_passed_w, job2_passed_w, 
                                 msg_wo, did_first, job1_passed, job2_passed, 
                                 msg_i, passed, src, msg >>

workerC_proc(self) == wc_choose(self) \/ wc_j1_tool(self)
                         \/ wc_j1_work(self) \/ wc_j1_result(self)
                         \/ wc_j1_check(self) \/ wc_j1_rework(self)
                         \/ wc_j2_work(self) \/ wc_j2_result(self)
                         \/ wc_j2_check(self) \/ wc_j2_rework(self)
                         \/ wc_second(self) \/ wc_s2_work(self)
                         \/ wc_s2_result(self) \/ wc_s2_check(self)
                         \/ wc_s2_rework(self) \/ wc_s1_tool(self)
                         \/ wc_s1_work(self) \/ wc_s1_result(self)
                         \/ wc_s1_check(self) \/ wc_s1_rework(self)
                         \/ wc_done(self)

in_loop(self) == /\ pc[self] = "in_loop"
                 /\ IF passed[self] < 6
                       THEN /\ pc' = [pc EXCEPT ![self] = "in_recv"]
                       ELSE /\ pc' = [pc EXCEPT ![self] = "in_finish"]
                 /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                 insp_to_wA, insp_to_wB, insp_to_wC, 
                                 insp_to_disp, disp_to_wA, disp_to_wB, 
                                 disp_to_wC, station_alpha, station_beta, 
                                 station_gamma, tool_cabinet, msg_, did_first_, 
                                 job1_passed_, job2_passed_, msg_w, 
                                 did_first_w, job1_passed_w, job2_passed_w, 
                                 msg_wo, did_first, job1_passed, job2_passed, 
                                 msg_i, passed, src, msg >>

in_recv(self) == /\ pc[self] = "in_recv"
                 /\ \/ /\ Len(wA_to_insp) > 0
                       /\ msg_i' = [msg_i EXCEPT ![self] = Head(wA_to_insp)]
                       /\ wA_to_insp' = Tail(wA_to_insp)
                       /\ src' = [src EXCEPT ![self] = "A"]
                       /\ UNCHANGED <<wB_to_insp, wC_to_insp>>
                    \/ /\ Len(wB_to_insp) > 0
                       /\ msg_i' = [msg_i EXCEPT ![self] = Head(wB_to_insp)]
                       /\ wB_to_insp' = Tail(wB_to_insp)
                       /\ src' = [src EXCEPT ![self] = "B"]
                       /\ UNCHANGED <<wA_to_insp, wC_to_insp>>
                    \/ /\ Len(wC_to_insp) > 0
                       /\ msg_i' = [msg_i EXCEPT ![self] = Head(wC_to_insp)]
                       /\ wC_to_insp' = Tail(wC_to_insp)
                       /\ src' = [src EXCEPT ![self] = "C"]
                       /\ UNCHANGED <<wA_to_insp, wB_to_insp>>
                 /\ pc' = [pc EXCEPT ![self] = "in_decide"]
                 /\ UNCHANGED << insp_to_wA, insp_to_wB, insp_to_wC, 
                                 insp_to_disp, disp_to_wA, disp_to_wB, 
                                 disp_to_wC, station_alpha, station_beta, 
                                 station_gamma, tool_cabinet, msg_, did_first_, 
                                 job1_passed_, job2_passed_, msg_w, 
                                 did_first_w, job1_passed_w, job2_passed_w, 
                                 msg_wo, did_first, job1_passed, job2_passed, 
                                 passed, msg >>

in_decide(self) == /\ pc[self] = "in_decide"
                   /\ \/ /\ IF src[self] = "A"
                               THEN /\ insp_to_wA' = Append(insp_to_wA, "pass")
                                    /\ UNCHANGED << insp_to_wB, insp_to_wC >>
                               ELSE /\ IF src[self] = "B"
                                          THEN /\ insp_to_wB' = Append(insp_to_wB, "pass")
                                               /\ UNCHANGED insp_to_wC
                                          ELSE /\ insp_to_wC' = Append(insp_to_wC, "pass")
                                               /\ UNCHANGED insp_to_wB
                                    /\ UNCHANGED insp_to_wA
                         /\ passed' = [passed EXCEPT ![self] = passed[self] + 1]
                         /\ UNCHANGED insp_to_disp
                      \/ /\ IF src[self] = "A"
                               THEN /\ insp_to_wA' = Append(insp_to_wA, "fail")
                                    /\ insp_to_disp' = Append(insp_to_disp, "fail_A")
                                    /\ UNCHANGED << insp_to_wB, insp_to_wC >>
                               ELSE /\ IF src[self] = "B"
                                          THEN /\ insp_to_wB' = Append(insp_to_wB, "fail")
                                               /\ insp_to_disp' = Append(insp_to_disp, "fail_B")
                                               /\ UNCHANGED insp_to_wC
                                          ELSE /\ insp_to_wC' = Append(insp_to_wC, "fail")
                                               /\ insp_to_disp' = Append(insp_to_disp, "fail_C")
                                               /\ UNCHANGED insp_to_wB
                                    /\ UNCHANGED insp_to_wA
                         /\ UNCHANGED passed
                   /\ pc' = [pc EXCEPT ![self] = "in_loop"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   disp_to_wA, disp_to_wB, disp_to_wC, 
                                   station_alpha, station_beta, station_gamma, 
                                   tool_cabinet, msg_, did_first_, 
                                   job1_passed_, job2_passed_, msg_w, 
                                   did_first_w, job1_passed_w, job2_passed_w, 
                                   msg_wo, did_first, job1_passed, job2_passed, 
                                   msg_i, src, msg >>

in_finish(self) == /\ pc[self] = "in_finish"
                   /\ insp_to_disp' = Append(insp_to_disp, "all_done")
                   /\ pc' = [pc EXCEPT ![self] = "in_done"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   insp_to_wA, insp_to_wB, insp_to_wC, 
                                   disp_to_wA, disp_to_wB, disp_to_wC, 
                                   station_alpha, station_beta, station_gamma, 
                                   tool_cabinet, msg_, did_first_, 
                                   job1_passed_, job2_passed_, msg_w, 
                                   did_first_w, job1_passed_w, job2_passed_w, 
                                   msg_wo, did_first, job1_passed, job2_passed, 
                                   msg_i, passed, src, msg >>

in_done(self) == /\ pc[self] = "in_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                 insp_to_wA, insp_to_wB, insp_to_wC, 
                                 insp_to_disp, disp_to_wA, disp_to_wB, 
                                 disp_to_wC, station_alpha, station_beta, 
                                 station_gamma, tool_cabinet, msg_, did_first_, 
                                 job1_passed_, job2_passed_, msg_w, 
                                 did_first_w, job1_passed_w, job2_passed_w, 
                                 msg_wo, did_first, job1_passed, job2_passed, 
                                 msg_i, passed, src, msg >>

inspector_proc(self) == in_loop(self) \/ in_recv(self) \/ in_decide(self)
                           \/ in_finish(self) \/ in_done(self)

di_loop(self) == /\ pc[self] = "di_loop"
                 /\ pc' = [pc EXCEPT ![self] = "di_recv"]
                 /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                 insp_to_wA, insp_to_wB, insp_to_wC, 
                                 insp_to_disp, disp_to_wA, disp_to_wB, 
                                 disp_to_wC, station_alpha, station_beta, 
                                 station_gamma, tool_cabinet, msg_, did_first_, 
                                 job1_passed_, job2_passed_, msg_w, 
                                 did_first_w, job1_passed_w, job2_passed_w, 
                                 msg_wo, did_first, job1_passed, job2_passed, 
                                 msg_i, passed, src, msg >>

di_recv(self) == /\ pc[self] = "di_recv"
                 /\ Len(insp_to_disp) > 0
                 /\ msg' = [msg EXCEPT ![self] = Head(insp_to_disp)]
                 /\ insp_to_disp' = Tail(insp_to_disp)
                 /\ pc' = [pc EXCEPT ![self] = "di_check"]
                 /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                 insp_to_wA, insp_to_wB, insp_to_wC, 
                                 disp_to_wA, disp_to_wB, disp_to_wC, 
                                 station_alpha, station_beta, station_gamma, 
                                 tool_cabinet, msg_, did_first_, job1_passed_, 
                                 job2_passed_, msg_w, did_first_w, 
                                 job1_passed_w, job2_passed_w, msg_wo, 
                                 did_first, job1_passed, job2_passed, msg_i, 
                                 passed, src >>

di_check(self) == /\ pc[self] = "di_check"
                  /\ IF msg[self] = "all_done"
                        THEN /\ pc' = [pc EXCEPT ![self] = "di_done"]
                             /\ UNCHANGED << disp_to_wA, disp_to_wB, 
                                             disp_to_wC >>
                        ELSE /\ IF msg[self] = "fail_A"
                                   THEN /\ disp_to_wA' = Append(disp_to_wA, "rework")
                                        /\ UNCHANGED << disp_to_wB, disp_to_wC >>
                                   ELSE /\ IF msg[self] = "fail_B"
                                              THEN /\ disp_to_wB' = Append(disp_to_wB, "rework")
                                                   /\ UNCHANGED disp_to_wC
                                              ELSE /\ disp_to_wC' = Append(disp_to_wC, "rework")
                                                   /\ UNCHANGED disp_to_wB
                                        /\ UNCHANGED disp_to_wA
                             /\ pc' = [pc EXCEPT ![self] = "di_loop"]
                  /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                  insp_to_wA, insp_to_wB, insp_to_wC, 
                                  insp_to_disp, station_alpha, station_beta, 
                                  station_gamma, tool_cabinet, msg_, 
                                  did_first_, job1_passed_, job2_passed_, 
                                  msg_w, did_first_w, job1_passed_w, 
                                  job2_passed_w, msg_wo, did_first, 
                                  job1_passed, job2_passed, msg_i, passed, src, 
                                  msg >>

di_done(self) == /\ pc[self] = "di_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                 insp_to_wA, insp_to_wB, insp_to_wC, 
                                 insp_to_disp, disp_to_wA, disp_to_wB, 
                                 disp_to_wC, station_alpha, station_beta, 
                                 station_gamma, tool_cabinet, msg_, did_first_, 
                                 job1_passed_, job2_passed_, msg_w, 
                                 did_first_w, job1_passed_w, job2_passed_w, 
                                 msg_wo, did_first, job1_passed, job2_passed, 
                                 msg_i, passed, src, msg >>

dispatcher_proc(self) == di_loop(self) \/ di_recv(self) \/ di_check(self)
                            \/ di_done(self)

(* Allow infinite stuttering to prevent deadlock on termination. *)
Terminating == /\ \A self \in ProcSet: pc[self] = "Done"
               /\ UNCHANGED vars

Next == (\E self \in {WorkerA}: workerA_proc(self))
           \/ (\E self \in {WorkerB}: workerB_proc(self))
           \/ (\E self \in {WorkerC}: workerC_proc(self))
           \/ (\E self \in {Inspector}: inspector_proc(self))
           \/ (\E self \in {Dispatcher}: dispatcher_proc(self))
           \/ Terminating

Spec == /\ Init /\ [][Next]_vars
        /\ \A self \in {WorkerA} : WF_vars(workerA_proc(self))
        /\ \A self \in {WorkerB} : WF_vars(workerB_proc(self))
        /\ \A self \in {WorkerC} : WF_vars(workerC_proc(self))
        /\ \A self \in {Inspector} : WF_vars(inspector_proc(self))
        /\ \A self \in {Dispatcher} : WF_vars(dispatcher_proc(self))

Termination == <>(\A self \in ProcSet: pc[self] = "Done")

\* END TRANSLATION 

AllDone == \A p \in {WorkerA, WorkerB, WorkerC, Inspector, Dispatcher}: pc[p] = "Done"

TypeInvariant ==
  /\ \A p \in {WorkerA, WorkerB, WorkerC, Inspector, Dispatcher}: pc[p] \in STRING
  /\ station_alpha \in {WorkerA, WorkerB, WorkerC, Inspector, Dispatcher, "FREE"}
  /\ station_beta \in {WorkerA, WorkerB, WorkerC, Inspector, Dispatcher, "FREE"}
  /\ station_gamma \in {WorkerA, WorkerB, WorkerC, Inspector, Dispatcher, "FREE"}
  /\ tool_cabinet \in Nat
  /\ wA_to_insp \in Seq(STRING)
  /\ wB_to_insp \in Seq(STRING)
  /\ wC_to_insp \in Seq(STRING)
  /\ insp_to_wA \in Seq(STRING)
  /\ insp_to_wB \in Seq(STRING)
  /\ insp_to_wC \in Seq(STRING)
  /\ insp_to_disp \in Seq(STRING)
  /\ disp_to_wA \in Seq(STRING)
  /\ disp_to_wB \in Seq(STRING)
  /\ disp_to_wC \in Seq(STRING)

NoOrphanLocks ==
  AllDone => (station_alpha = "FREE" /\ station_beta = "FREE" /\ station_gamma = "FREE")

ChannelsDrained ==
  AllDone => (Len(wA_to_insp) = 0 /\ Len(wB_to_insp) = 0 /\ Len(wC_to_insp) = 0 /\ Len(insp_to_wA) = 0 /\ Len(insp_to_wB) = 0 /\ Len(insp_to_wC) = 0 /\ Len(insp_to_disp) = 0 /\ Len(disp_to_wA) = 0 /\ Len(disp_to_wB) = 0 /\ Len(disp_to_wC) = 0)

ChannelBound ==
  Len(wA_to_insp) <= 3 /\ Len(wB_to_insp) <= 3 /\ Len(wC_to_insp) <= 3 /\ Len(insp_to_wA) <= 3 /\ Len(insp_to_wB) <= 3 /\ Len(insp_to_wC) <= 3 /\ Len(insp_to_disp) <= 3 /\ Len(disp_to_wA) <= 3 /\ Len(disp_to_wB) <= 3 /\ Len(disp_to_wC) <= 3

====
