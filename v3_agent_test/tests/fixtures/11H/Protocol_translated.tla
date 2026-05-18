---- MODULE Protocol ----
EXTENDS Integers, Sequences, TLC

CONSTANTS WorkerA, WorkerB, WorkerC, WorkerD, Inspector, Mat_handler, Packager

(* --algorithm Protocol {
variables
  wA_to_insp = <<>>; \* workerA -> inspector
  wB_to_insp = <<>>; \* workerB -> inspector
  wC_to_insp = <<>>; \* workerC -> inspector
  wD_to_insp = <<>>; \* workerD -> inspector
  insp_to_wA = <<>>; \* inspector -> workerA
  insp_to_wB = <<>>; \* inspector -> workerB
  insp_to_wC = <<>>; \* inspector -> workerC
  insp_to_wD = <<>>; \* inspector -> workerD
  wA_to_pack = <<>>; \* workerA -> packager
  wB_to_pack = <<>>; \* workerB -> packager
  wC_to_pack = <<>>; \* workerC -> packager
  wD_to_pack = <<>>; \* workerD -> packager
  insp_to_mat = <<>>; \* inspector -> mat_handler (all_done signal)
  station_1 = "FREE"; \* Lock
  station_2 = "FREE"; \* Lock
  station_3 = "FREE"; \* Lock
  station_4 = "FREE"; \* Lock
  tool_supply = 3; \* Counter (non-negative)
  raw_material = 4; \* Counter (non-negative)

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

\* Worker A: Job 1 on station_1 or station_2 (alt routing), Job 2 on station_3
\* Material acquired before station to prevent deadlock
fair process (workerA_proc \in {WorkerA})
variables msg = "";
{
  wa_j1_mat:
    acquire_counter(raw_material);
  wa_j1:
    either {
      acquire_lock(station_1);
    wa_j1s1_tool:
      acquire_counter(tool_supply);
    wa_j1s1_done:
      release_counter(tool_supply);
      release_lock(station_1);
      send(wA_to_insp, "inspect");
    } or {
      acquire_lock(station_2);
    wa_j1s2_tool:
      acquire_counter(tool_supply);
    wa_j1s2_done:
      release_counter(tool_supply);
      release_lock(station_2);
      send(wA_to_insp, "inspect");
    };
  wa_j1_res:
    receive(insp_to_wA, msg);
    send(wA_to_pack, "finished");

  wa_j2_mat:
    acquire_counter(raw_material);
  wa_j2:
    acquire_lock(station_3);
  wa_j2_tool:
    acquire_counter(tool_supply);
  wa_j2_done:
    release_counter(tool_supply);
    release_lock(station_3);
    send(wA_to_insp, "inspect");
  wa_j2_res:
    receive(insp_to_wA, msg);
    send(wA_to_pack, "finished");
  wa_end: skip;
}

\* Worker B: Job 1 on station_2 or station_3 (alt routing), Job 2 on station_4
fair process (workerB_proc \in {WorkerB})
variables msg = "";
{
  wb_j1_mat:
    acquire_counter(raw_material);
  wb_j1:
    either {
      acquire_lock(station_2);
    wb_j1s2_tool:
      acquire_counter(tool_supply);
    wb_j1s2_done:
      release_counter(tool_supply);
      release_lock(station_2);
      send(wB_to_insp, "inspect");
    } or {
      acquire_lock(station_3);
    wb_j1s3_tool:
      acquire_counter(tool_supply);
    wb_j1s3_done:
      release_counter(tool_supply);
      release_lock(station_3);
      send(wB_to_insp, "inspect");
    };
  wb_j1_res:
    receive(insp_to_wB, msg);
    send(wB_to_pack, "finished");

  wb_j2_mat:
    acquire_counter(raw_material);
  wb_j2:
    acquire_lock(station_4);
  wb_j2_tool:
    acquire_counter(tool_supply);
  wb_j2_done:
    release_counter(tool_supply);
    release_lock(station_4);
    send(wB_to_insp, "inspect");
  wb_j2_res:
    receive(insp_to_wB, msg);
    send(wB_to_pack, "finished");
  wb_end: skip;
}

\* Worker C: Job 1 on station_3 or station_4 (alt routing), Job 2 on station_1
fair process (workerC_proc \in {WorkerC})
variables msg = "";
{
  wc_j1_mat:
    acquire_counter(raw_material);
  wc_j1:
    either {
      acquire_lock(station_3);
    wc_j1s3_tool:
      acquire_counter(tool_supply);
    wc_j1s3_done:
      release_counter(tool_supply);
      release_lock(station_3);
      send(wC_to_insp, "inspect");
    } or {
      acquire_lock(station_4);
    wc_j1s4_tool:
      acquire_counter(tool_supply);
    wc_j1s4_done:
      release_counter(tool_supply);
      release_lock(station_4);
      send(wC_to_insp, "inspect");
    };
  wc_j1_res:
    receive(insp_to_wC, msg);
    send(wC_to_pack, "finished");

  wc_j2_mat:
    acquire_counter(raw_material);
  wc_j2:
    acquire_lock(station_1);
  wc_j2_tool:
    acquire_counter(tool_supply);
  wc_j2_done:
    release_counter(tool_supply);
    release_lock(station_1);
    send(wC_to_insp, "inspect");
  wc_j2_res:
    receive(insp_to_wC, msg);
    send(wC_to_pack, "finished");
  wc_end: skip;
}

\* Worker D: Job 1 on station_4 or station_1 (alt routing), Job 2 on station_2
fair process (workerD_proc \in {WorkerD})
variables msg = "";
{
  wd_j1_mat:
    acquire_counter(raw_material);
  wd_j1:
    either {
      acquire_lock(station_4);
    wd_j1s4_tool:
      acquire_counter(tool_supply);
    wd_j1s4_done:
      release_counter(tool_supply);
      release_lock(station_4);
      send(wD_to_insp, "inspect");
    } or {
      acquire_lock(station_1);
    wd_j1s1_tool:
      acquire_counter(tool_supply);
    wd_j1s1_done:
      release_counter(tool_supply);
      release_lock(station_1);
      send(wD_to_insp, "inspect");
    };
  wd_j1_res:
    receive(insp_to_wD, msg);
    send(wD_to_pack, "finished");

  wd_j2_mat:
    acquire_counter(raw_material);
  wd_j2:
    acquire_lock(station_2);
  wd_j2_tool:
    acquire_counter(tool_supply);
  wd_j2_done:
    release_counter(tool_supply);
    release_lock(station_2);
    send(wD_to_insp, "inspect");
  wd_j2_res:
    receive(insp_to_wD, msg);
    send(wD_to_pack, "finished");
  wd_end: skip;
}

\* Inspector: receives inspection requests, always passes, sends all_done to mat_handler
fair process (inspector_proc \in {Inspector})
variables msg = "", passed = 0, src = "";
{
  in_loop:
    while (passed < 8) {
      in_recv:
        either {
          receive(wA_to_insp, msg); src := "A";
        } or {
          receive(wB_to_insp, msg); src := "B";
        } or {
          receive(wC_to_insp, msg); src := "C";
        } or {
          receive(wD_to_insp, msg); src := "D";
        };
      in_pass:
        if (src = "A") { send(insp_to_wA, "pass"); }
        else if (src = "B") { send(insp_to_wB, "pass"); }
        else if (src = "C") { send(insp_to_wC, "pass"); }
        else { send(insp_to_wD, "pass"); };
        passed := passed + 1;
    };
  in_signal:
    send(insp_to_mat, "all_done");
  in_done: skip;
}

\* Material Handler: replenishes raw_material 4 times (bridging the deficit),
\* then waits for all_done signal from inspector
fair process (mat_handler_proc \in {Mat_handler})
variables msg = "", replenished = 0;
{
  mh_replenish:
    while (replenished < 4) {
      mh_add:
        release_counter(raw_material);
        replenished := replenished + 1;
    };
  mh_wait:
    receive(insp_to_mat, msg);
  mh_end: skip;
}

\* Packager: collects 8 finished goods
fair process (packager_proc \in {Packager})
variables msg = "", count = 0;
{
  pk_loop:
    while (count < 8) {
      pk_recv:
        either {
          receive(wA_to_pack, msg);
        } or {
          receive(wB_to_pack, msg);
        } or {
          receive(wC_to_pack, msg);
        } or {
          receive(wD_to_pack, msg);
        };
        count := count + 1;
    };
  pk_done: skip;
}

} *)
\* BEGIN TRANSLATION (chksum(pcal) = "d7e9f4fb" /\ chksum(tla) = "24a8c201")
\* Process variable msg of process workerA_proc at line 59 col 11 changed to msg_
\* Process variable msg of process workerB_proc at line 103 col 11 changed to msg_w
\* Process variable msg of process workerC_proc at line 147 col 11 changed to msg_wo
\* Process variable msg of process workerD_proc at line 191 col 11 changed to msg_wor
\* Process variable msg of process inspector_proc at line 235 col 11 changed to msg_i
\* Process variable msg of process mat_handler_proc at line 264 col 11 changed to msg_m
VARIABLES pc, wA_to_insp, wB_to_insp, wC_to_insp, wD_to_insp, insp_to_wA, 
          insp_to_wB, insp_to_wC, insp_to_wD, wA_to_pack, wB_to_pack, 
          wC_to_pack, wD_to_pack, insp_to_mat, station_1, station_2, 
          station_3, station_4, tool_supply, raw_material, msg_, msg_w, 
          msg_wo, msg_wor, msg_i, passed, src, msg_m, replenished, msg, count

vars == << pc, wA_to_insp, wB_to_insp, wC_to_insp, wD_to_insp, insp_to_wA, 
           insp_to_wB, insp_to_wC, insp_to_wD, wA_to_pack, wB_to_pack, 
           wC_to_pack, wD_to_pack, insp_to_mat, station_1, station_2, 
           station_3, station_4, tool_supply, raw_material, msg_, msg_w, 
           msg_wo, msg_wor, msg_i, passed, src, msg_m, replenished, msg, 
           count >>

ProcSet == ({WorkerA}) \cup ({WorkerB}) \cup ({WorkerC}) \cup ({WorkerD}) \cup ({Inspector}) \cup ({Mat_handler}) \cup ({Packager})

Init == (* Global variables *)
        /\ wA_to_insp = <<>>
        /\ wB_to_insp = <<>>
        /\ wC_to_insp = <<>>
        /\ wD_to_insp = <<>>
        /\ insp_to_wA = <<>>
        /\ insp_to_wB = <<>>
        /\ insp_to_wC = <<>>
        /\ insp_to_wD = <<>>
        /\ wA_to_pack = <<>>
        /\ wB_to_pack = <<>>
        /\ wC_to_pack = <<>>
        /\ wD_to_pack = <<>>
        /\ insp_to_mat = <<>>
        /\ station_1 = "FREE"
        /\ station_2 = "FREE"
        /\ station_3 = "FREE"
        /\ station_4 = "FREE"
        /\ tool_supply = 3
        /\ raw_material = 4
        (* Process workerA_proc *)
        /\ msg_ = [self \in {WorkerA} |-> ""]
        (* Process workerB_proc *)
        /\ msg_w = [self \in {WorkerB} |-> ""]
        (* Process workerC_proc *)
        /\ msg_wo = [self \in {WorkerC} |-> ""]
        (* Process workerD_proc *)
        /\ msg_wor = [self \in {WorkerD} |-> ""]
        (* Process inspector_proc *)
        /\ msg_i = [self \in {Inspector} |-> ""]
        /\ passed = [self \in {Inspector} |-> 0]
        /\ src = [self \in {Inspector} |-> ""]
        (* Process mat_handler_proc *)
        /\ msg_m = [self \in {Mat_handler} |-> ""]
        /\ replenished = [self \in {Mat_handler} |-> 0]
        (* Process packager_proc *)
        /\ msg = [self \in {Packager} |-> ""]
        /\ count = [self \in {Packager} |-> 0]
        /\ pc = [self \in ProcSet |-> CASE self \in {WorkerA} -> "wa_j1_mat"
                                        [] self \in {WorkerB} -> "wb_j1_mat"
                                        [] self \in {WorkerC} -> "wc_j1_mat"
                                        [] self \in {WorkerD} -> "wd_j1_mat"
                                        [] self \in {Inspector} -> "in_loop"
                                        [] self \in {Mat_handler} -> "mh_replenish"
                                        [] self \in {Packager} -> "pk_loop"]

wa_j1_mat(self) == /\ pc[self] = "wa_j1_mat"
                   /\ raw_material > 0
                   /\ raw_material' = raw_material - 1
                   /\ pc' = [pc EXCEPT ![self] = "wa_j1"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   wD_to_insp, insp_to_wA, insp_to_wB, 
                                   insp_to_wC, insp_to_wD, wA_to_pack, 
                                   wB_to_pack, wC_to_pack, wD_to_pack, 
                                   insp_to_mat, station_1, station_2, 
                                   station_3, station_4, tool_supply, msg_, 
                                   msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                   msg_m, replenished, msg, count >>

wa_j1(self) == /\ pc[self] = "wa_j1"
               /\ \/ /\ station_1 = "FREE"
                     /\ station_1' = self
                     /\ pc' = [pc EXCEPT ![self] = "wa_j1s1_tool"]
                     /\ UNCHANGED station_2
                  \/ /\ station_2 = "FREE"
                     /\ station_2' = self
                     /\ pc' = [pc EXCEPT ![self] = "wa_j1s2_tool"]
                     /\ UNCHANGED station_1
               /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, wD_to_insp, 
                               insp_to_wA, insp_to_wB, insp_to_wC, insp_to_wD, 
                               wA_to_pack, wB_to_pack, wC_to_pack, wD_to_pack, 
                               insp_to_mat, station_3, station_4, tool_supply, 
                               raw_material, msg_, msg_w, msg_wo, msg_wor, 
                               msg_i, passed, src, msg_m, replenished, msg, 
                               count >>

wa_j1s1_tool(self) == /\ pc[self] = "wa_j1s1_tool"
                      /\ tool_supply > 0
                      /\ tool_supply' = tool_supply - 1
                      /\ pc' = [pc EXCEPT ![self] = "wa_j1s1_done"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      wD_to_insp, insp_to_wA, insp_to_wB, 
                                      insp_to_wC, insp_to_wD, wA_to_pack, 
                                      wB_to_pack, wC_to_pack, wD_to_pack, 
                                      insp_to_mat, station_1, station_2, 
                                      station_3, station_4, raw_material, msg_, 
                                      msg_w, msg_wo, msg_wor, msg_i, passed, 
                                      src, msg_m, replenished, msg, count >>

wa_j1s1_done(self) == /\ pc[self] = "wa_j1s1_done"
                      /\ tool_supply' = tool_supply + 1
                      /\ station_1' = "FREE"
                      /\ wA_to_insp' = Append(wA_to_insp, "inspect")
                      /\ pc' = [pc EXCEPT ![self] = "wa_j1_res"]
                      /\ UNCHANGED << wB_to_insp, wC_to_insp, wD_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_wD, wA_to_pack, wB_to_pack, 
                                      wC_to_pack, wD_to_pack, insp_to_mat, 
                                      station_2, station_3, station_4, 
                                      raw_material, msg_, msg_w, msg_wo, 
                                      msg_wor, msg_i, passed, src, msg_m, 
                                      replenished, msg, count >>

wa_j1s2_tool(self) == /\ pc[self] = "wa_j1s2_tool"
                      /\ tool_supply > 0
                      /\ tool_supply' = tool_supply - 1
                      /\ pc' = [pc EXCEPT ![self] = "wa_j1s2_done"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      wD_to_insp, insp_to_wA, insp_to_wB, 
                                      insp_to_wC, insp_to_wD, wA_to_pack, 
                                      wB_to_pack, wC_to_pack, wD_to_pack, 
                                      insp_to_mat, station_1, station_2, 
                                      station_3, station_4, raw_material, msg_, 
                                      msg_w, msg_wo, msg_wor, msg_i, passed, 
                                      src, msg_m, replenished, msg, count >>

wa_j1s2_done(self) == /\ pc[self] = "wa_j1s2_done"
                      /\ tool_supply' = tool_supply + 1
                      /\ station_2' = "FREE"
                      /\ wA_to_insp' = Append(wA_to_insp, "inspect")
                      /\ pc' = [pc EXCEPT ![self] = "wa_j1_res"]
                      /\ UNCHANGED << wB_to_insp, wC_to_insp, wD_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_wD, wA_to_pack, wB_to_pack, 
                                      wC_to_pack, wD_to_pack, insp_to_mat, 
                                      station_1, station_3, station_4, 
                                      raw_material, msg_, msg_w, msg_wo, 
                                      msg_wor, msg_i, passed, src, msg_m, 
                                      replenished, msg, count >>

wa_j1_res(self) == /\ pc[self] = "wa_j1_res"
                   /\ Len(insp_to_wA) > 0
                   /\ msg_' = [msg_ EXCEPT ![self] = Head(insp_to_wA)]
                   /\ insp_to_wA' = Tail(insp_to_wA)
                   /\ wA_to_pack' = Append(wA_to_pack, "finished")
                   /\ pc' = [pc EXCEPT ![self] = "wa_j2_mat"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   wD_to_insp, insp_to_wB, insp_to_wC, 
                                   insp_to_wD, wB_to_pack, wC_to_pack, 
                                   wD_to_pack, insp_to_mat, station_1, 
                                   station_2, station_3, station_4, 
                                   tool_supply, raw_material, msg_w, msg_wo, 
                                   msg_wor, msg_i, passed, src, msg_m, 
                                   replenished, msg, count >>

wa_j2_mat(self) == /\ pc[self] = "wa_j2_mat"
                   /\ raw_material > 0
                   /\ raw_material' = raw_material - 1
                   /\ pc' = [pc EXCEPT ![self] = "wa_j2"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   wD_to_insp, insp_to_wA, insp_to_wB, 
                                   insp_to_wC, insp_to_wD, wA_to_pack, 
                                   wB_to_pack, wC_to_pack, wD_to_pack, 
                                   insp_to_mat, station_1, station_2, 
                                   station_3, station_4, tool_supply, msg_, 
                                   msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                   msg_m, replenished, msg, count >>

wa_j2(self) == /\ pc[self] = "wa_j2"
               /\ station_3 = "FREE"
               /\ station_3' = self
               /\ pc' = [pc EXCEPT ![self] = "wa_j2_tool"]
               /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, wD_to_insp, 
                               insp_to_wA, insp_to_wB, insp_to_wC, insp_to_wD, 
                               wA_to_pack, wB_to_pack, wC_to_pack, wD_to_pack, 
                               insp_to_mat, station_1, station_2, station_4, 
                               tool_supply, raw_material, msg_, msg_w, msg_wo, 
                               msg_wor, msg_i, passed, src, msg_m, replenished, 
                               msg, count >>

wa_j2_tool(self) == /\ pc[self] = "wa_j2_tool"
                    /\ tool_supply > 0
                    /\ tool_supply' = tool_supply - 1
                    /\ pc' = [pc EXCEPT ![self] = "wa_j2_done"]
                    /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                    wD_to_insp, insp_to_wA, insp_to_wB, 
                                    insp_to_wC, insp_to_wD, wA_to_pack, 
                                    wB_to_pack, wC_to_pack, wD_to_pack, 
                                    insp_to_mat, station_1, station_2, 
                                    station_3, station_4, raw_material, msg_, 
                                    msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                    msg_m, replenished, msg, count >>

wa_j2_done(self) == /\ pc[self] = "wa_j2_done"
                    /\ tool_supply' = tool_supply + 1
                    /\ station_3' = "FREE"
                    /\ wA_to_insp' = Append(wA_to_insp, "inspect")
                    /\ pc' = [pc EXCEPT ![self] = "wa_j2_res"]
                    /\ UNCHANGED << wB_to_insp, wC_to_insp, wD_to_insp, 
                                    insp_to_wA, insp_to_wB, insp_to_wC, 
                                    insp_to_wD, wA_to_pack, wB_to_pack, 
                                    wC_to_pack, wD_to_pack, insp_to_mat, 
                                    station_1, station_2, station_4, 
                                    raw_material, msg_, msg_w, msg_wo, msg_wor, 
                                    msg_i, passed, src, msg_m, replenished, 
                                    msg, count >>

wa_j2_res(self) == /\ pc[self] = "wa_j2_res"
                   /\ Len(insp_to_wA) > 0
                   /\ msg_' = [msg_ EXCEPT ![self] = Head(insp_to_wA)]
                   /\ insp_to_wA' = Tail(insp_to_wA)
                   /\ wA_to_pack' = Append(wA_to_pack, "finished")
                   /\ pc' = [pc EXCEPT ![self] = "wa_end"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   wD_to_insp, insp_to_wB, insp_to_wC, 
                                   insp_to_wD, wB_to_pack, wC_to_pack, 
                                   wD_to_pack, insp_to_mat, station_1, 
                                   station_2, station_3, station_4, 
                                   tool_supply, raw_material, msg_w, msg_wo, 
                                   msg_wor, msg_i, passed, src, msg_m, 
                                   replenished, msg, count >>

wa_end(self) == /\ pc[self] = "wa_end"
                /\ TRUE
                /\ pc' = [pc EXCEPT ![self] = "Done"]
                /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, wD_to_insp, 
                                insp_to_wA, insp_to_wB, insp_to_wC, insp_to_wD, 
                                wA_to_pack, wB_to_pack, wC_to_pack, wD_to_pack, 
                                insp_to_mat, station_1, station_2, station_3, 
                                station_4, tool_supply, raw_material, msg_, 
                                msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                msg_m, replenished, msg, count >>

workerA_proc(self) == wa_j1_mat(self) \/ wa_j1(self) \/ wa_j1s1_tool(self)
                         \/ wa_j1s1_done(self) \/ wa_j1s2_tool(self)
                         \/ wa_j1s2_done(self) \/ wa_j1_res(self)
                         \/ wa_j2_mat(self) \/ wa_j2(self)
                         \/ wa_j2_tool(self) \/ wa_j2_done(self)
                         \/ wa_j2_res(self) \/ wa_end(self)

wb_j1_mat(self) == /\ pc[self] = "wb_j1_mat"
                   /\ raw_material > 0
                   /\ raw_material' = raw_material - 1
                   /\ pc' = [pc EXCEPT ![self] = "wb_j1"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   wD_to_insp, insp_to_wA, insp_to_wB, 
                                   insp_to_wC, insp_to_wD, wA_to_pack, 
                                   wB_to_pack, wC_to_pack, wD_to_pack, 
                                   insp_to_mat, station_1, station_2, 
                                   station_3, station_4, tool_supply, msg_, 
                                   msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                   msg_m, replenished, msg, count >>

wb_j1(self) == /\ pc[self] = "wb_j1"
               /\ \/ /\ station_2 = "FREE"
                     /\ station_2' = self
                     /\ pc' = [pc EXCEPT ![self] = "wb_j1s2_tool"]
                     /\ UNCHANGED station_3
                  \/ /\ station_3 = "FREE"
                     /\ station_3' = self
                     /\ pc' = [pc EXCEPT ![self] = "wb_j1s3_tool"]
                     /\ UNCHANGED station_2
               /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, wD_to_insp, 
                               insp_to_wA, insp_to_wB, insp_to_wC, insp_to_wD, 
                               wA_to_pack, wB_to_pack, wC_to_pack, wD_to_pack, 
                               insp_to_mat, station_1, station_4, tool_supply, 
                               raw_material, msg_, msg_w, msg_wo, msg_wor, 
                               msg_i, passed, src, msg_m, replenished, msg, 
                               count >>

wb_j1s2_tool(self) == /\ pc[self] = "wb_j1s2_tool"
                      /\ tool_supply > 0
                      /\ tool_supply' = tool_supply - 1
                      /\ pc' = [pc EXCEPT ![self] = "wb_j1s2_done"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      wD_to_insp, insp_to_wA, insp_to_wB, 
                                      insp_to_wC, insp_to_wD, wA_to_pack, 
                                      wB_to_pack, wC_to_pack, wD_to_pack, 
                                      insp_to_mat, station_1, station_2, 
                                      station_3, station_4, raw_material, msg_, 
                                      msg_w, msg_wo, msg_wor, msg_i, passed, 
                                      src, msg_m, replenished, msg, count >>

wb_j1s2_done(self) == /\ pc[self] = "wb_j1s2_done"
                      /\ tool_supply' = tool_supply + 1
                      /\ station_2' = "FREE"
                      /\ wB_to_insp' = Append(wB_to_insp, "inspect")
                      /\ pc' = [pc EXCEPT ![self] = "wb_j1_res"]
                      /\ UNCHANGED << wA_to_insp, wC_to_insp, wD_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_wD, wA_to_pack, wB_to_pack, 
                                      wC_to_pack, wD_to_pack, insp_to_mat, 
                                      station_1, station_3, station_4, 
                                      raw_material, msg_, msg_w, msg_wo, 
                                      msg_wor, msg_i, passed, src, msg_m, 
                                      replenished, msg, count >>

wb_j1s3_tool(self) == /\ pc[self] = "wb_j1s3_tool"
                      /\ tool_supply > 0
                      /\ tool_supply' = tool_supply - 1
                      /\ pc' = [pc EXCEPT ![self] = "wb_j1s3_done"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      wD_to_insp, insp_to_wA, insp_to_wB, 
                                      insp_to_wC, insp_to_wD, wA_to_pack, 
                                      wB_to_pack, wC_to_pack, wD_to_pack, 
                                      insp_to_mat, station_1, station_2, 
                                      station_3, station_4, raw_material, msg_, 
                                      msg_w, msg_wo, msg_wor, msg_i, passed, 
                                      src, msg_m, replenished, msg, count >>

wb_j1s3_done(self) == /\ pc[self] = "wb_j1s3_done"
                      /\ tool_supply' = tool_supply + 1
                      /\ station_3' = "FREE"
                      /\ wB_to_insp' = Append(wB_to_insp, "inspect")
                      /\ pc' = [pc EXCEPT ![self] = "wb_j1_res"]
                      /\ UNCHANGED << wA_to_insp, wC_to_insp, wD_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_wD, wA_to_pack, wB_to_pack, 
                                      wC_to_pack, wD_to_pack, insp_to_mat, 
                                      station_1, station_2, station_4, 
                                      raw_material, msg_, msg_w, msg_wo, 
                                      msg_wor, msg_i, passed, src, msg_m, 
                                      replenished, msg, count >>

wb_j1_res(self) == /\ pc[self] = "wb_j1_res"
                   /\ Len(insp_to_wB) > 0
                   /\ msg_w' = [msg_w EXCEPT ![self] = Head(insp_to_wB)]
                   /\ insp_to_wB' = Tail(insp_to_wB)
                   /\ wB_to_pack' = Append(wB_to_pack, "finished")
                   /\ pc' = [pc EXCEPT ![self] = "wb_j2_mat"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   wD_to_insp, insp_to_wA, insp_to_wC, 
                                   insp_to_wD, wA_to_pack, wC_to_pack, 
                                   wD_to_pack, insp_to_mat, station_1, 
                                   station_2, station_3, station_4, 
                                   tool_supply, raw_material, msg_, msg_wo, 
                                   msg_wor, msg_i, passed, src, msg_m, 
                                   replenished, msg, count >>

wb_j2_mat(self) == /\ pc[self] = "wb_j2_mat"
                   /\ raw_material > 0
                   /\ raw_material' = raw_material - 1
                   /\ pc' = [pc EXCEPT ![self] = "wb_j2"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   wD_to_insp, insp_to_wA, insp_to_wB, 
                                   insp_to_wC, insp_to_wD, wA_to_pack, 
                                   wB_to_pack, wC_to_pack, wD_to_pack, 
                                   insp_to_mat, station_1, station_2, 
                                   station_3, station_4, tool_supply, msg_, 
                                   msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                   msg_m, replenished, msg, count >>

wb_j2(self) == /\ pc[self] = "wb_j2"
               /\ station_4 = "FREE"
               /\ station_4' = self
               /\ pc' = [pc EXCEPT ![self] = "wb_j2_tool"]
               /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, wD_to_insp, 
                               insp_to_wA, insp_to_wB, insp_to_wC, insp_to_wD, 
                               wA_to_pack, wB_to_pack, wC_to_pack, wD_to_pack, 
                               insp_to_mat, station_1, station_2, station_3, 
                               tool_supply, raw_material, msg_, msg_w, msg_wo, 
                               msg_wor, msg_i, passed, src, msg_m, replenished, 
                               msg, count >>

wb_j2_tool(self) == /\ pc[self] = "wb_j2_tool"
                    /\ tool_supply > 0
                    /\ tool_supply' = tool_supply - 1
                    /\ pc' = [pc EXCEPT ![self] = "wb_j2_done"]
                    /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                    wD_to_insp, insp_to_wA, insp_to_wB, 
                                    insp_to_wC, insp_to_wD, wA_to_pack, 
                                    wB_to_pack, wC_to_pack, wD_to_pack, 
                                    insp_to_mat, station_1, station_2, 
                                    station_3, station_4, raw_material, msg_, 
                                    msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                    msg_m, replenished, msg, count >>

wb_j2_done(self) == /\ pc[self] = "wb_j2_done"
                    /\ tool_supply' = tool_supply + 1
                    /\ station_4' = "FREE"
                    /\ wB_to_insp' = Append(wB_to_insp, "inspect")
                    /\ pc' = [pc EXCEPT ![self] = "wb_j2_res"]
                    /\ UNCHANGED << wA_to_insp, wC_to_insp, wD_to_insp, 
                                    insp_to_wA, insp_to_wB, insp_to_wC, 
                                    insp_to_wD, wA_to_pack, wB_to_pack, 
                                    wC_to_pack, wD_to_pack, insp_to_mat, 
                                    station_1, station_2, station_3, 
                                    raw_material, msg_, msg_w, msg_wo, msg_wor, 
                                    msg_i, passed, src, msg_m, replenished, 
                                    msg, count >>

wb_j2_res(self) == /\ pc[self] = "wb_j2_res"
                   /\ Len(insp_to_wB) > 0
                   /\ msg_w' = [msg_w EXCEPT ![self] = Head(insp_to_wB)]
                   /\ insp_to_wB' = Tail(insp_to_wB)
                   /\ wB_to_pack' = Append(wB_to_pack, "finished")
                   /\ pc' = [pc EXCEPT ![self] = "wb_end"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   wD_to_insp, insp_to_wA, insp_to_wC, 
                                   insp_to_wD, wA_to_pack, wC_to_pack, 
                                   wD_to_pack, insp_to_mat, station_1, 
                                   station_2, station_3, station_4, 
                                   tool_supply, raw_material, msg_, msg_wo, 
                                   msg_wor, msg_i, passed, src, msg_m, 
                                   replenished, msg, count >>

wb_end(self) == /\ pc[self] = "wb_end"
                /\ TRUE
                /\ pc' = [pc EXCEPT ![self] = "Done"]
                /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, wD_to_insp, 
                                insp_to_wA, insp_to_wB, insp_to_wC, insp_to_wD, 
                                wA_to_pack, wB_to_pack, wC_to_pack, wD_to_pack, 
                                insp_to_mat, station_1, station_2, station_3, 
                                station_4, tool_supply, raw_material, msg_, 
                                msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                msg_m, replenished, msg, count >>

workerB_proc(self) == wb_j1_mat(self) \/ wb_j1(self) \/ wb_j1s2_tool(self)
                         \/ wb_j1s2_done(self) \/ wb_j1s3_tool(self)
                         \/ wb_j1s3_done(self) \/ wb_j1_res(self)
                         \/ wb_j2_mat(self) \/ wb_j2(self)
                         \/ wb_j2_tool(self) \/ wb_j2_done(self)
                         \/ wb_j2_res(self) \/ wb_end(self)

wc_j1_mat(self) == /\ pc[self] = "wc_j1_mat"
                   /\ raw_material > 0
                   /\ raw_material' = raw_material - 1
                   /\ pc' = [pc EXCEPT ![self] = "wc_j1"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   wD_to_insp, insp_to_wA, insp_to_wB, 
                                   insp_to_wC, insp_to_wD, wA_to_pack, 
                                   wB_to_pack, wC_to_pack, wD_to_pack, 
                                   insp_to_mat, station_1, station_2, 
                                   station_3, station_4, tool_supply, msg_, 
                                   msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                   msg_m, replenished, msg, count >>

wc_j1(self) == /\ pc[self] = "wc_j1"
               /\ \/ /\ station_3 = "FREE"
                     /\ station_3' = self
                     /\ pc' = [pc EXCEPT ![self] = "wc_j1s3_tool"]
                     /\ UNCHANGED station_4
                  \/ /\ station_4 = "FREE"
                     /\ station_4' = self
                     /\ pc' = [pc EXCEPT ![self] = "wc_j1s4_tool"]
                     /\ UNCHANGED station_3
               /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, wD_to_insp, 
                               insp_to_wA, insp_to_wB, insp_to_wC, insp_to_wD, 
                               wA_to_pack, wB_to_pack, wC_to_pack, wD_to_pack, 
                               insp_to_mat, station_1, station_2, tool_supply, 
                               raw_material, msg_, msg_w, msg_wo, msg_wor, 
                               msg_i, passed, src, msg_m, replenished, msg, 
                               count >>

wc_j1s3_tool(self) == /\ pc[self] = "wc_j1s3_tool"
                      /\ tool_supply > 0
                      /\ tool_supply' = tool_supply - 1
                      /\ pc' = [pc EXCEPT ![self] = "wc_j1s3_done"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      wD_to_insp, insp_to_wA, insp_to_wB, 
                                      insp_to_wC, insp_to_wD, wA_to_pack, 
                                      wB_to_pack, wC_to_pack, wD_to_pack, 
                                      insp_to_mat, station_1, station_2, 
                                      station_3, station_4, raw_material, msg_, 
                                      msg_w, msg_wo, msg_wor, msg_i, passed, 
                                      src, msg_m, replenished, msg, count >>

wc_j1s3_done(self) == /\ pc[self] = "wc_j1s3_done"
                      /\ tool_supply' = tool_supply + 1
                      /\ station_3' = "FREE"
                      /\ wC_to_insp' = Append(wC_to_insp, "inspect")
                      /\ pc' = [pc EXCEPT ![self] = "wc_j1_res"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wD_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_wD, wA_to_pack, wB_to_pack, 
                                      wC_to_pack, wD_to_pack, insp_to_mat, 
                                      station_1, station_2, station_4, 
                                      raw_material, msg_, msg_w, msg_wo, 
                                      msg_wor, msg_i, passed, src, msg_m, 
                                      replenished, msg, count >>

wc_j1s4_tool(self) == /\ pc[self] = "wc_j1s4_tool"
                      /\ tool_supply > 0
                      /\ tool_supply' = tool_supply - 1
                      /\ pc' = [pc EXCEPT ![self] = "wc_j1s4_done"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      wD_to_insp, insp_to_wA, insp_to_wB, 
                                      insp_to_wC, insp_to_wD, wA_to_pack, 
                                      wB_to_pack, wC_to_pack, wD_to_pack, 
                                      insp_to_mat, station_1, station_2, 
                                      station_3, station_4, raw_material, msg_, 
                                      msg_w, msg_wo, msg_wor, msg_i, passed, 
                                      src, msg_m, replenished, msg, count >>

wc_j1s4_done(self) == /\ pc[self] = "wc_j1s4_done"
                      /\ tool_supply' = tool_supply + 1
                      /\ station_4' = "FREE"
                      /\ wC_to_insp' = Append(wC_to_insp, "inspect")
                      /\ pc' = [pc EXCEPT ![self] = "wc_j1_res"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wD_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_wD, wA_to_pack, wB_to_pack, 
                                      wC_to_pack, wD_to_pack, insp_to_mat, 
                                      station_1, station_2, station_3, 
                                      raw_material, msg_, msg_w, msg_wo, 
                                      msg_wor, msg_i, passed, src, msg_m, 
                                      replenished, msg, count >>

wc_j1_res(self) == /\ pc[self] = "wc_j1_res"
                   /\ Len(insp_to_wC) > 0
                   /\ msg_wo' = [msg_wo EXCEPT ![self] = Head(insp_to_wC)]
                   /\ insp_to_wC' = Tail(insp_to_wC)
                   /\ wC_to_pack' = Append(wC_to_pack, "finished")
                   /\ pc' = [pc EXCEPT ![self] = "wc_j2_mat"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   wD_to_insp, insp_to_wA, insp_to_wB, 
                                   insp_to_wD, wA_to_pack, wB_to_pack, 
                                   wD_to_pack, insp_to_mat, station_1, 
                                   station_2, station_3, station_4, 
                                   tool_supply, raw_material, msg_, msg_w, 
                                   msg_wor, msg_i, passed, src, msg_m, 
                                   replenished, msg, count >>

wc_j2_mat(self) == /\ pc[self] = "wc_j2_mat"
                   /\ raw_material > 0
                   /\ raw_material' = raw_material - 1
                   /\ pc' = [pc EXCEPT ![self] = "wc_j2"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   wD_to_insp, insp_to_wA, insp_to_wB, 
                                   insp_to_wC, insp_to_wD, wA_to_pack, 
                                   wB_to_pack, wC_to_pack, wD_to_pack, 
                                   insp_to_mat, station_1, station_2, 
                                   station_3, station_4, tool_supply, msg_, 
                                   msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                   msg_m, replenished, msg, count >>

wc_j2(self) == /\ pc[self] = "wc_j2"
               /\ station_1 = "FREE"
               /\ station_1' = self
               /\ pc' = [pc EXCEPT ![self] = "wc_j2_tool"]
               /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, wD_to_insp, 
                               insp_to_wA, insp_to_wB, insp_to_wC, insp_to_wD, 
                               wA_to_pack, wB_to_pack, wC_to_pack, wD_to_pack, 
                               insp_to_mat, station_2, station_3, station_4, 
                               tool_supply, raw_material, msg_, msg_w, msg_wo, 
                               msg_wor, msg_i, passed, src, msg_m, replenished, 
                               msg, count >>

wc_j2_tool(self) == /\ pc[self] = "wc_j2_tool"
                    /\ tool_supply > 0
                    /\ tool_supply' = tool_supply - 1
                    /\ pc' = [pc EXCEPT ![self] = "wc_j2_done"]
                    /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                    wD_to_insp, insp_to_wA, insp_to_wB, 
                                    insp_to_wC, insp_to_wD, wA_to_pack, 
                                    wB_to_pack, wC_to_pack, wD_to_pack, 
                                    insp_to_mat, station_1, station_2, 
                                    station_3, station_4, raw_material, msg_, 
                                    msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                    msg_m, replenished, msg, count >>

wc_j2_done(self) == /\ pc[self] = "wc_j2_done"
                    /\ tool_supply' = tool_supply + 1
                    /\ station_1' = "FREE"
                    /\ wC_to_insp' = Append(wC_to_insp, "inspect")
                    /\ pc' = [pc EXCEPT ![self] = "wc_j2_res"]
                    /\ UNCHANGED << wA_to_insp, wB_to_insp, wD_to_insp, 
                                    insp_to_wA, insp_to_wB, insp_to_wC, 
                                    insp_to_wD, wA_to_pack, wB_to_pack, 
                                    wC_to_pack, wD_to_pack, insp_to_mat, 
                                    station_2, station_3, station_4, 
                                    raw_material, msg_, msg_w, msg_wo, msg_wor, 
                                    msg_i, passed, src, msg_m, replenished, 
                                    msg, count >>

wc_j2_res(self) == /\ pc[self] = "wc_j2_res"
                   /\ Len(insp_to_wC) > 0
                   /\ msg_wo' = [msg_wo EXCEPT ![self] = Head(insp_to_wC)]
                   /\ insp_to_wC' = Tail(insp_to_wC)
                   /\ wC_to_pack' = Append(wC_to_pack, "finished")
                   /\ pc' = [pc EXCEPT ![self] = "wc_end"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   wD_to_insp, insp_to_wA, insp_to_wB, 
                                   insp_to_wD, wA_to_pack, wB_to_pack, 
                                   wD_to_pack, insp_to_mat, station_1, 
                                   station_2, station_3, station_4, 
                                   tool_supply, raw_material, msg_, msg_w, 
                                   msg_wor, msg_i, passed, src, msg_m, 
                                   replenished, msg, count >>

wc_end(self) == /\ pc[self] = "wc_end"
                /\ TRUE
                /\ pc' = [pc EXCEPT ![self] = "Done"]
                /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, wD_to_insp, 
                                insp_to_wA, insp_to_wB, insp_to_wC, insp_to_wD, 
                                wA_to_pack, wB_to_pack, wC_to_pack, wD_to_pack, 
                                insp_to_mat, station_1, station_2, station_3, 
                                station_4, tool_supply, raw_material, msg_, 
                                msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                msg_m, replenished, msg, count >>

workerC_proc(self) == wc_j1_mat(self) \/ wc_j1(self) \/ wc_j1s3_tool(self)
                         \/ wc_j1s3_done(self) \/ wc_j1s4_tool(self)
                         \/ wc_j1s4_done(self) \/ wc_j1_res(self)
                         \/ wc_j2_mat(self) \/ wc_j2(self)
                         \/ wc_j2_tool(self) \/ wc_j2_done(self)
                         \/ wc_j2_res(self) \/ wc_end(self)

wd_j1_mat(self) == /\ pc[self] = "wd_j1_mat"
                   /\ raw_material > 0
                   /\ raw_material' = raw_material - 1
                   /\ pc' = [pc EXCEPT ![self] = "wd_j1"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   wD_to_insp, insp_to_wA, insp_to_wB, 
                                   insp_to_wC, insp_to_wD, wA_to_pack, 
                                   wB_to_pack, wC_to_pack, wD_to_pack, 
                                   insp_to_mat, station_1, station_2, 
                                   station_3, station_4, tool_supply, msg_, 
                                   msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                   msg_m, replenished, msg, count >>

wd_j1(self) == /\ pc[self] = "wd_j1"
               /\ \/ /\ station_4 = "FREE"
                     /\ station_4' = self
                     /\ pc' = [pc EXCEPT ![self] = "wd_j1s4_tool"]
                     /\ UNCHANGED station_1
                  \/ /\ station_1 = "FREE"
                     /\ station_1' = self
                     /\ pc' = [pc EXCEPT ![self] = "wd_j1s1_tool"]
                     /\ UNCHANGED station_4
               /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, wD_to_insp, 
                               insp_to_wA, insp_to_wB, insp_to_wC, insp_to_wD, 
                               wA_to_pack, wB_to_pack, wC_to_pack, wD_to_pack, 
                               insp_to_mat, station_2, station_3, tool_supply, 
                               raw_material, msg_, msg_w, msg_wo, msg_wor, 
                               msg_i, passed, src, msg_m, replenished, msg, 
                               count >>

wd_j1s4_tool(self) == /\ pc[self] = "wd_j1s4_tool"
                      /\ tool_supply > 0
                      /\ tool_supply' = tool_supply - 1
                      /\ pc' = [pc EXCEPT ![self] = "wd_j1s4_done"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      wD_to_insp, insp_to_wA, insp_to_wB, 
                                      insp_to_wC, insp_to_wD, wA_to_pack, 
                                      wB_to_pack, wC_to_pack, wD_to_pack, 
                                      insp_to_mat, station_1, station_2, 
                                      station_3, station_4, raw_material, msg_, 
                                      msg_w, msg_wo, msg_wor, msg_i, passed, 
                                      src, msg_m, replenished, msg, count >>

wd_j1s4_done(self) == /\ pc[self] = "wd_j1s4_done"
                      /\ tool_supply' = tool_supply + 1
                      /\ station_4' = "FREE"
                      /\ wD_to_insp' = Append(wD_to_insp, "inspect")
                      /\ pc' = [pc EXCEPT ![self] = "wd_j1_res"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_wD, wA_to_pack, wB_to_pack, 
                                      wC_to_pack, wD_to_pack, insp_to_mat, 
                                      station_1, station_2, station_3, 
                                      raw_material, msg_, msg_w, msg_wo, 
                                      msg_wor, msg_i, passed, src, msg_m, 
                                      replenished, msg, count >>

wd_j1s1_tool(self) == /\ pc[self] = "wd_j1s1_tool"
                      /\ tool_supply > 0
                      /\ tool_supply' = tool_supply - 1
                      /\ pc' = [pc EXCEPT ![self] = "wd_j1s1_done"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      wD_to_insp, insp_to_wA, insp_to_wB, 
                                      insp_to_wC, insp_to_wD, wA_to_pack, 
                                      wB_to_pack, wC_to_pack, wD_to_pack, 
                                      insp_to_mat, station_1, station_2, 
                                      station_3, station_4, raw_material, msg_, 
                                      msg_w, msg_wo, msg_wor, msg_i, passed, 
                                      src, msg_m, replenished, msg, count >>

wd_j1s1_done(self) == /\ pc[self] = "wd_j1s1_done"
                      /\ tool_supply' = tool_supply + 1
                      /\ station_1' = "FREE"
                      /\ wD_to_insp' = Append(wD_to_insp, "inspect")
                      /\ pc' = [pc EXCEPT ![self] = "wd_j1_res"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      insp_to_wA, insp_to_wB, insp_to_wC, 
                                      insp_to_wD, wA_to_pack, wB_to_pack, 
                                      wC_to_pack, wD_to_pack, insp_to_mat, 
                                      station_2, station_3, station_4, 
                                      raw_material, msg_, msg_w, msg_wo, 
                                      msg_wor, msg_i, passed, src, msg_m, 
                                      replenished, msg, count >>

wd_j1_res(self) == /\ pc[self] = "wd_j1_res"
                   /\ Len(insp_to_wD) > 0
                   /\ msg_wor' = [msg_wor EXCEPT ![self] = Head(insp_to_wD)]
                   /\ insp_to_wD' = Tail(insp_to_wD)
                   /\ wD_to_pack' = Append(wD_to_pack, "finished")
                   /\ pc' = [pc EXCEPT ![self] = "wd_j2_mat"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   wD_to_insp, insp_to_wA, insp_to_wB, 
                                   insp_to_wC, wA_to_pack, wB_to_pack, 
                                   wC_to_pack, insp_to_mat, station_1, 
                                   station_2, station_3, station_4, 
                                   tool_supply, raw_material, msg_, msg_w, 
                                   msg_wo, msg_i, passed, src, msg_m, 
                                   replenished, msg, count >>

wd_j2_mat(self) == /\ pc[self] = "wd_j2_mat"
                   /\ raw_material > 0
                   /\ raw_material' = raw_material - 1
                   /\ pc' = [pc EXCEPT ![self] = "wd_j2"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   wD_to_insp, insp_to_wA, insp_to_wB, 
                                   insp_to_wC, insp_to_wD, wA_to_pack, 
                                   wB_to_pack, wC_to_pack, wD_to_pack, 
                                   insp_to_mat, station_1, station_2, 
                                   station_3, station_4, tool_supply, msg_, 
                                   msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                   msg_m, replenished, msg, count >>

wd_j2(self) == /\ pc[self] = "wd_j2"
               /\ station_2 = "FREE"
               /\ station_2' = self
               /\ pc' = [pc EXCEPT ![self] = "wd_j2_tool"]
               /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, wD_to_insp, 
                               insp_to_wA, insp_to_wB, insp_to_wC, insp_to_wD, 
                               wA_to_pack, wB_to_pack, wC_to_pack, wD_to_pack, 
                               insp_to_mat, station_1, station_3, station_4, 
                               tool_supply, raw_material, msg_, msg_w, msg_wo, 
                               msg_wor, msg_i, passed, src, msg_m, replenished, 
                               msg, count >>

wd_j2_tool(self) == /\ pc[self] = "wd_j2_tool"
                    /\ tool_supply > 0
                    /\ tool_supply' = tool_supply - 1
                    /\ pc' = [pc EXCEPT ![self] = "wd_j2_done"]
                    /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                    wD_to_insp, insp_to_wA, insp_to_wB, 
                                    insp_to_wC, insp_to_wD, wA_to_pack, 
                                    wB_to_pack, wC_to_pack, wD_to_pack, 
                                    insp_to_mat, station_1, station_2, 
                                    station_3, station_4, raw_material, msg_, 
                                    msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                    msg_m, replenished, msg, count >>

wd_j2_done(self) == /\ pc[self] = "wd_j2_done"
                    /\ tool_supply' = tool_supply + 1
                    /\ station_2' = "FREE"
                    /\ wD_to_insp' = Append(wD_to_insp, "inspect")
                    /\ pc' = [pc EXCEPT ![self] = "wd_j2_res"]
                    /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                    insp_to_wA, insp_to_wB, insp_to_wC, 
                                    insp_to_wD, wA_to_pack, wB_to_pack, 
                                    wC_to_pack, wD_to_pack, insp_to_mat, 
                                    station_1, station_3, station_4, 
                                    raw_material, msg_, msg_w, msg_wo, msg_wor, 
                                    msg_i, passed, src, msg_m, replenished, 
                                    msg, count >>

wd_j2_res(self) == /\ pc[self] = "wd_j2_res"
                   /\ Len(insp_to_wD) > 0
                   /\ msg_wor' = [msg_wor EXCEPT ![self] = Head(insp_to_wD)]
                   /\ insp_to_wD' = Tail(insp_to_wD)
                   /\ wD_to_pack' = Append(wD_to_pack, "finished")
                   /\ pc' = [pc EXCEPT ![self] = "wd_end"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   wD_to_insp, insp_to_wA, insp_to_wB, 
                                   insp_to_wC, wA_to_pack, wB_to_pack, 
                                   wC_to_pack, insp_to_mat, station_1, 
                                   station_2, station_3, station_4, 
                                   tool_supply, raw_material, msg_, msg_w, 
                                   msg_wo, msg_i, passed, src, msg_m, 
                                   replenished, msg, count >>

wd_end(self) == /\ pc[self] = "wd_end"
                /\ TRUE
                /\ pc' = [pc EXCEPT ![self] = "Done"]
                /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, wD_to_insp, 
                                insp_to_wA, insp_to_wB, insp_to_wC, insp_to_wD, 
                                wA_to_pack, wB_to_pack, wC_to_pack, wD_to_pack, 
                                insp_to_mat, station_1, station_2, station_3, 
                                station_4, tool_supply, raw_material, msg_, 
                                msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                msg_m, replenished, msg, count >>

workerD_proc(self) == wd_j1_mat(self) \/ wd_j1(self) \/ wd_j1s4_tool(self)
                         \/ wd_j1s4_done(self) \/ wd_j1s1_tool(self)
                         \/ wd_j1s1_done(self) \/ wd_j1_res(self)
                         \/ wd_j2_mat(self) \/ wd_j2(self)
                         \/ wd_j2_tool(self) \/ wd_j2_done(self)
                         \/ wd_j2_res(self) \/ wd_end(self)

in_loop(self) == /\ pc[self] = "in_loop"
                 /\ IF passed[self] < 8
                       THEN /\ pc' = [pc EXCEPT ![self] = "in_recv"]
                       ELSE /\ pc' = [pc EXCEPT ![self] = "in_signal"]
                 /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                 wD_to_insp, insp_to_wA, insp_to_wB, 
                                 insp_to_wC, insp_to_wD, wA_to_pack, 
                                 wB_to_pack, wC_to_pack, wD_to_pack, 
                                 insp_to_mat, station_1, station_2, station_3, 
                                 station_4, tool_supply, raw_material, msg_, 
                                 msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                 msg_m, replenished, msg, count >>

in_recv(self) == /\ pc[self] = "in_recv"
                 /\ \/ /\ Len(wA_to_insp) > 0
                       /\ msg_i' = [msg_i EXCEPT ![self] = Head(wA_to_insp)]
                       /\ wA_to_insp' = Tail(wA_to_insp)
                       /\ src' = [src EXCEPT ![self] = "A"]
                       /\ UNCHANGED <<wB_to_insp, wC_to_insp, wD_to_insp>>
                    \/ /\ Len(wB_to_insp) > 0
                       /\ msg_i' = [msg_i EXCEPT ![self] = Head(wB_to_insp)]
                       /\ wB_to_insp' = Tail(wB_to_insp)
                       /\ src' = [src EXCEPT ![self] = "B"]
                       /\ UNCHANGED <<wA_to_insp, wC_to_insp, wD_to_insp>>
                    \/ /\ Len(wC_to_insp) > 0
                       /\ msg_i' = [msg_i EXCEPT ![self] = Head(wC_to_insp)]
                       /\ wC_to_insp' = Tail(wC_to_insp)
                       /\ src' = [src EXCEPT ![self] = "C"]
                       /\ UNCHANGED <<wA_to_insp, wB_to_insp, wD_to_insp>>
                    \/ /\ Len(wD_to_insp) > 0
                       /\ msg_i' = [msg_i EXCEPT ![self] = Head(wD_to_insp)]
                       /\ wD_to_insp' = Tail(wD_to_insp)
                       /\ src' = [src EXCEPT ![self] = "D"]
                       /\ UNCHANGED <<wA_to_insp, wB_to_insp, wC_to_insp>>
                 /\ pc' = [pc EXCEPT ![self] = "in_pass"]
                 /\ UNCHANGED << insp_to_wA, insp_to_wB, insp_to_wC, 
                                 insp_to_wD, wA_to_pack, wB_to_pack, 
                                 wC_to_pack, wD_to_pack, insp_to_mat, 
                                 station_1, station_2, station_3, station_4, 
                                 tool_supply, raw_material, msg_, msg_w, 
                                 msg_wo, msg_wor, passed, msg_m, replenished, 
                                 msg, count >>

in_pass(self) == /\ pc[self] = "in_pass"
                 /\ IF src[self] = "A"
                       THEN /\ insp_to_wA' = Append(insp_to_wA, "pass")
                            /\ UNCHANGED << insp_to_wB, insp_to_wC, insp_to_wD >>
                       ELSE /\ IF src[self] = "B"
                                  THEN /\ insp_to_wB' = Append(insp_to_wB, "pass")
                                       /\ UNCHANGED << insp_to_wC, insp_to_wD >>
                                  ELSE /\ IF src[self] = "C"
                                             THEN /\ insp_to_wC' = Append(insp_to_wC, "pass")
                                                  /\ UNCHANGED insp_to_wD
                                             ELSE /\ insp_to_wD' = Append(insp_to_wD, "pass")
                                                  /\ UNCHANGED insp_to_wC
                                       /\ UNCHANGED insp_to_wB
                            /\ UNCHANGED insp_to_wA
                 /\ passed' = [passed EXCEPT ![self] = passed[self] + 1]
                 /\ pc' = [pc EXCEPT ![self] = "in_loop"]
                 /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                 wD_to_insp, wA_to_pack, wB_to_pack, 
                                 wC_to_pack, wD_to_pack, insp_to_mat, 
                                 station_1, station_2, station_3, station_4, 
                                 tool_supply, raw_material, msg_, msg_w, 
                                 msg_wo, msg_wor, msg_i, src, msg_m, 
                                 replenished, msg, count >>

in_signal(self) == /\ pc[self] = "in_signal"
                   /\ insp_to_mat' = Append(insp_to_mat, "all_done")
                   /\ pc' = [pc EXCEPT ![self] = "in_done"]
                   /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                   wD_to_insp, insp_to_wA, insp_to_wB, 
                                   insp_to_wC, insp_to_wD, wA_to_pack, 
                                   wB_to_pack, wC_to_pack, wD_to_pack, 
                                   station_1, station_2, station_3, station_4, 
                                   tool_supply, raw_material, msg_, msg_w, 
                                   msg_wo, msg_wor, msg_i, passed, src, msg_m, 
                                   replenished, msg, count >>

in_done(self) == /\ pc[self] = "in_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                 wD_to_insp, insp_to_wA, insp_to_wB, 
                                 insp_to_wC, insp_to_wD, wA_to_pack, 
                                 wB_to_pack, wC_to_pack, wD_to_pack, 
                                 insp_to_mat, station_1, station_2, station_3, 
                                 station_4, tool_supply, raw_material, msg_, 
                                 msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                 msg_m, replenished, msg, count >>

inspector_proc(self) == in_loop(self) \/ in_recv(self) \/ in_pass(self)
                           \/ in_signal(self) \/ in_done(self)

mh_replenish(self) == /\ pc[self] = "mh_replenish"
                      /\ IF replenished[self] < 4
                            THEN /\ pc' = [pc EXCEPT ![self] = "mh_add"]
                            ELSE /\ pc' = [pc EXCEPT ![self] = "mh_wait"]
                      /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                      wD_to_insp, insp_to_wA, insp_to_wB, 
                                      insp_to_wC, insp_to_wD, wA_to_pack, 
                                      wB_to_pack, wC_to_pack, wD_to_pack, 
                                      insp_to_mat, station_1, station_2, 
                                      station_3, station_4, tool_supply, 
                                      raw_material, msg_, msg_w, msg_wo, 
                                      msg_wor, msg_i, passed, src, msg_m, 
                                      replenished, msg, count >>

mh_add(self) == /\ pc[self] = "mh_add"
                /\ raw_material' = raw_material + 1
                /\ replenished' = [replenished EXCEPT ![self] = replenished[self] + 1]
                /\ pc' = [pc EXCEPT ![self] = "mh_replenish"]
                /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, wD_to_insp, 
                                insp_to_wA, insp_to_wB, insp_to_wC, insp_to_wD, 
                                wA_to_pack, wB_to_pack, wC_to_pack, wD_to_pack, 
                                insp_to_mat, station_1, station_2, station_3, 
                                station_4, tool_supply, msg_, msg_w, msg_wo, 
                                msg_wor, msg_i, passed, src, msg_m, msg, count >>

mh_wait(self) == /\ pc[self] = "mh_wait"
                 /\ Len(insp_to_mat) > 0
                 /\ msg_m' = [msg_m EXCEPT ![self] = Head(insp_to_mat)]
                 /\ insp_to_mat' = Tail(insp_to_mat)
                 /\ pc' = [pc EXCEPT ![self] = "mh_end"]
                 /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                 wD_to_insp, insp_to_wA, insp_to_wB, 
                                 insp_to_wC, insp_to_wD, wA_to_pack, 
                                 wB_to_pack, wC_to_pack, wD_to_pack, station_1, 
                                 station_2, station_3, station_4, tool_supply, 
                                 raw_material, msg_, msg_w, msg_wo, msg_wor, 
                                 msg_i, passed, src, replenished, msg, count >>

mh_end(self) == /\ pc[self] = "mh_end"
                /\ TRUE
                /\ pc' = [pc EXCEPT ![self] = "Done"]
                /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, wD_to_insp, 
                                insp_to_wA, insp_to_wB, insp_to_wC, insp_to_wD, 
                                wA_to_pack, wB_to_pack, wC_to_pack, wD_to_pack, 
                                insp_to_mat, station_1, station_2, station_3, 
                                station_4, tool_supply, raw_material, msg_, 
                                msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                msg_m, replenished, msg, count >>

mat_handler_proc(self) == mh_replenish(self) \/ mh_add(self)
                             \/ mh_wait(self) \/ mh_end(self)

pk_loop(self) == /\ pc[self] = "pk_loop"
                 /\ IF count[self] < 8
                       THEN /\ pc' = [pc EXCEPT ![self] = "pk_recv"]
                       ELSE /\ pc' = [pc EXCEPT ![self] = "pk_done"]
                 /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                 wD_to_insp, insp_to_wA, insp_to_wB, 
                                 insp_to_wC, insp_to_wD, wA_to_pack, 
                                 wB_to_pack, wC_to_pack, wD_to_pack, 
                                 insp_to_mat, station_1, station_2, station_3, 
                                 station_4, tool_supply, raw_material, msg_, 
                                 msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                 msg_m, replenished, msg, count >>

pk_recv(self) == /\ pc[self] = "pk_recv"
                 /\ \/ /\ Len(wA_to_pack) > 0
                       /\ msg' = [msg EXCEPT ![self] = Head(wA_to_pack)]
                       /\ wA_to_pack' = Tail(wA_to_pack)
                       /\ UNCHANGED <<wB_to_pack, wC_to_pack, wD_to_pack>>
                    \/ /\ Len(wB_to_pack) > 0
                       /\ msg' = [msg EXCEPT ![self] = Head(wB_to_pack)]
                       /\ wB_to_pack' = Tail(wB_to_pack)
                       /\ UNCHANGED <<wA_to_pack, wC_to_pack, wD_to_pack>>
                    \/ /\ Len(wC_to_pack) > 0
                       /\ msg' = [msg EXCEPT ![self] = Head(wC_to_pack)]
                       /\ wC_to_pack' = Tail(wC_to_pack)
                       /\ UNCHANGED <<wA_to_pack, wB_to_pack, wD_to_pack>>
                    \/ /\ Len(wD_to_pack) > 0
                       /\ msg' = [msg EXCEPT ![self] = Head(wD_to_pack)]
                       /\ wD_to_pack' = Tail(wD_to_pack)
                       /\ UNCHANGED <<wA_to_pack, wB_to_pack, wC_to_pack>>
                 /\ count' = [count EXCEPT ![self] = count[self] + 1]
                 /\ pc' = [pc EXCEPT ![self] = "pk_loop"]
                 /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                 wD_to_insp, insp_to_wA, insp_to_wB, 
                                 insp_to_wC, insp_to_wD, insp_to_mat, 
                                 station_1, station_2, station_3, station_4, 
                                 tool_supply, raw_material, msg_, msg_w, 
                                 msg_wo, msg_wor, msg_i, passed, src, msg_m, 
                                 replenished >>

pk_done(self) == /\ pc[self] = "pk_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << wA_to_insp, wB_to_insp, wC_to_insp, 
                                 wD_to_insp, insp_to_wA, insp_to_wB, 
                                 insp_to_wC, insp_to_wD, wA_to_pack, 
                                 wB_to_pack, wC_to_pack, wD_to_pack, 
                                 insp_to_mat, station_1, station_2, station_3, 
                                 station_4, tool_supply, raw_material, msg_, 
                                 msg_w, msg_wo, msg_wor, msg_i, passed, src, 
                                 msg_m, replenished, msg, count >>

packager_proc(self) == pk_loop(self) \/ pk_recv(self) \/ pk_done(self)

(* Allow infinite stuttering to prevent deadlock on termination. *)
Terminating == /\ \A self \in ProcSet: pc[self] = "Done"
               /\ UNCHANGED vars

Next == (\E self \in {WorkerA}: workerA_proc(self))
           \/ (\E self \in {WorkerB}: workerB_proc(self))
           \/ (\E self \in {WorkerC}: workerC_proc(self))
           \/ (\E self \in {WorkerD}: workerD_proc(self))
           \/ (\E self \in {Inspector}: inspector_proc(self))
           \/ (\E self \in {Mat_handler}: mat_handler_proc(self))
           \/ (\E self \in {Packager}: packager_proc(self))
           \/ Terminating

Spec == /\ Init /\ [][Next]_vars
        /\ \A self \in {WorkerA} : WF_vars(workerA_proc(self))
        /\ \A self \in {WorkerB} : WF_vars(workerB_proc(self))
        /\ \A self \in {WorkerC} : WF_vars(workerC_proc(self))
        /\ \A self \in {WorkerD} : WF_vars(workerD_proc(self))
        /\ \A self \in {Inspector} : WF_vars(inspector_proc(self))
        /\ \A self \in {Mat_handler} : WF_vars(mat_handler_proc(self))
        /\ \A self \in {Packager} : WF_vars(packager_proc(self))

Termination == <>(\A self \in ProcSet: pc[self] = "Done")

\* END TRANSLATION 

AllDone == \A p \in {WorkerA, WorkerB, WorkerC, WorkerD, Inspector, Mat_handler, Packager}: pc[p] = "Done"

TypeInvariant ==
  /\ \A p \in {WorkerA, WorkerB, WorkerC, WorkerD, Inspector, Mat_handler, Packager}: pc[p] \in STRING
  /\ station_1 \in {WorkerA, WorkerB, WorkerC, WorkerD, Inspector, Mat_handler, Packager, "FREE"}
  /\ station_2 \in {WorkerA, WorkerB, WorkerC, WorkerD, Inspector, Mat_handler, Packager, "FREE"}
  /\ station_3 \in {WorkerA, WorkerB, WorkerC, WorkerD, Inspector, Mat_handler, Packager, "FREE"}
  /\ station_4 \in {WorkerA, WorkerB, WorkerC, WorkerD, Inspector, Mat_handler, Packager, "FREE"}
  /\ tool_supply \in Nat
  /\ raw_material \in Nat
  /\ wA_to_insp \in Seq(STRING)
  /\ wB_to_insp \in Seq(STRING)
  /\ wC_to_insp \in Seq(STRING)
  /\ wD_to_insp \in Seq(STRING)
  /\ insp_to_wA \in Seq(STRING)
  /\ insp_to_wB \in Seq(STRING)
  /\ insp_to_wC \in Seq(STRING)
  /\ insp_to_wD \in Seq(STRING)
  /\ wA_to_pack \in Seq(STRING)
  /\ wB_to_pack \in Seq(STRING)
  /\ wC_to_pack \in Seq(STRING)
  /\ wD_to_pack \in Seq(STRING)
  /\ insp_to_mat \in Seq(STRING)

NoOrphanLocks ==
  AllDone => (station_1 = "FREE" /\ station_2 = "FREE" /\ station_3 = "FREE" /\ station_4 = "FREE")

ChannelsDrained ==
  AllDone => (Len(wA_to_insp) = 0 /\ Len(wB_to_insp) = 0 /\ Len(wC_to_insp) = 0 /\ Len(wD_to_insp) = 0 /\ Len(insp_to_wA) = 0 /\ Len(insp_to_wB) = 0 /\ Len(insp_to_wC) = 0 /\ Len(insp_to_wD) = 0 /\ Len(wA_to_pack) = 0 /\ Len(wB_to_pack) = 0 /\ Len(wC_to_pack) = 0 /\ Len(wD_to_pack) = 0 /\ Len(insp_to_mat) = 0)

ChannelBound ==
  Len(wA_to_insp) <= 2 /\ Len(wB_to_insp) <= 2 /\ Len(wC_to_insp) <= 2 /\ Len(wD_to_insp) <= 2
  /\ Len(insp_to_wA) <= 2 /\ Len(insp_to_wB) <= 2 /\ Len(insp_to_wC) <= 2 /\ Len(insp_to_wD) <= 2
  /\ Len(wA_to_pack) <= 2 /\ Len(wB_to_pack) <= 2 /\ Len(wC_to_pack) <= 2 /\ Len(wD_to_pack) <= 2
  /\ Len(insp_to_mat) <= 2

====
