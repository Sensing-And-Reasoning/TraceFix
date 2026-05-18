---- MODULE Protocol ----
EXTENDS Integers, Sequences, TLC

CONSTANTS BackendDev, DbAdmin, Tester

(* --algorithm Protocol {
variables
  dbAdmin_to_backend = <<>>; \* dbAdmin -> backendDev, labels: ['migration_done']
  backend_to_tester = <<>>; \* backendDev -> tester, labels: ['deploy']
  tester_to_backend = <<>>; \* tester -> backendDev, labels: ['pass', 'fail']
  backend_to_dbAdmin = <<>>; \* backendDev -> dbAdmin, labels: ['adjust', 'done']
  migration_lock = "FREE"; \* Lock
  test_env_lock = "FREE"; \* Lock

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

fair process (dbAdmin_proc \in {DbAdmin})
variables msg = "";
{
  \* Execute initial database migration
  da_migrate:
    acquire_lock(migration_lock);
  da_migrate_done:
    release_lock(migration_lock);
    send(dbAdmin_to_backend, "migration_done");

  \* Wait for backend to signal done or adjustment needed
  da_wait:
    receive(backend_to_dbAdmin, msg);
  da_check:
    if (msg = "adjust") {
      \* Adjust migration and re-notify
    da_adjust:
      acquire_lock(migration_lock);
    da_adjust_done:
      release_lock(migration_lock);
      send(dbAdmin_to_backend, "migration_done");
    da_wait2:
      receive(backend_to_dbAdmin, msg);
    };

  da_done:
    skip;
}

fair process (backendDev_proc \in {BackendDev})
variables msg = "";
{
  \* Wait for DB migration to complete before implementing
  bd_wait_migration:
    receive(dbAdmin_to_backend, msg);

  \* Implement backend code and deploy for testing
  bd_deploy:
    send(backend_to_tester, "deploy");

  \* Wait for test results
  bd_test_wait:
    receive(tester_to_backend, msg);
  bd_test_check:
    if (msg = "pass") {
      \* Tests passed - signal done to dbAdmin
      send(backend_to_dbAdmin, "done");
      goto bd_done;
    } else {
      \* Tests failed - fix needed
      either {
        \* Fix only requires backend code change - no DB adjustment
        skip;
      } or {
        \* Fix requires DB admin to adjust migration
        send(backend_to_dbAdmin, "adjust");
      bd_wait_adjust:
        receive(dbAdmin_to_backend, msg);
      };
    };

  \* Redeploy after fix
  bd_redeploy:
    send(backend_to_tester, "deploy");
  bd_retest_wait:
    receive(tester_to_backend, msg);
  bd_retest_done:
    \* Signal done to dbAdmin (only "done" sent on this path)
    send(backend_to_dbAdmin, "done");

  bd_done:
    skip;
}

fair process (tester_proc \in {Tester})
variables msg = "";
{
  \* Wait for backend deployment
  t_wait:
    receive(backend_to_tester, msg);

  \* Run tests (exclusive test environment)
  t_test:
    acquire_lock(test_env_lock);
  t_test_done:
    release_lock(test_env_lock);

  \* Send test results (nondeterministic pass/fail)
  t_result:
    either {
      send(tester_to_backend, "pass");
    } or {
      send(tester_to_backend, "fail");

    \* If fail, wait for redeployment and retest
    t_rewait:
      receive(backend_to_tester, msg);
    t_retest:
      acquire_lock(test_env_lock);
    t_retest_done:
      release_lock(test_env_lock);
      send(tester_to_backend, "pass");
    };
}

} *)
\* BEGIN TRANSLATION (chksum(pcal) = "743b5716" /\ chksum(tla) = "4ab3d508")
\* Process variable msg of process dbAdmin_proc at line 35 col 11 changed to msg_
\* Process variable msg of process backendDev_proc at line 64 col 11 changed to msg_b
VARIABLES pc, dbAdmin_to_backend, backend_to_tester, tester_to_backend, 
          backend_to_dbAdmin, migration_lock, test_env_lock, msg_, msg_b, msg

vars == << pc, dbAdmin_to_backend, backend_to_tester, tester_to_backend, 
           backend_to_dbAdmin, migration_lock, test_env_lock, msg_, msg_b, 
           msg >>

ProcSet == ({DbAdmin}) \cup ({BackendDev}) \cup ({Tester})

Init == (* Global variables *)
        /\ dbAdmin_to_backend = <<>>
        /\ backend_to_tester = <<>>
        /\ tester_to_backend = <<>>
        /\ backend_to_dbAdmin = <<>>
        /\ migration_lock = "FREE"
        /\ test_env_lock = "FREE"
        (* Process dbAdmin_proc *)
        /\ msg_ = [self \in {DbAdmin} |-> ""]
        (* Process backendDev_proc *)
        /\ msg_b = [self \in {BackendDev} |-> ""]
        (* Process tester_proc *)
        /\ msg = [self \in {Tester} |-> ""]
        /\ pc = [self \in ProcSet |-> CASE self \in {DbAdmin} -> "da_migrate"
                                        [] self \in {BackendDev} -> "bd_wait_migration"
                                        [] self \in {Tester} -> "t_wait"]

da_migrate(self) == /\ pc[self] = "da_migrate"
                    /\ migration_lock = "FREE"
                    /\ migration_lock' = self
                    /\ pc' = [pc EXCEPT ![self] = "da_migrate_done"]
                    /\ UNCHANGED << dbAdmin_to_backend, backend_to_tester, 
                                    tester_to_backend, backend_to_dbAdmin, 
                                    test_env_lock, msg_, msg_b, msg >>

da_migrate_done(self) == /\ pc[self] = "da_migrate_done"
                         /\ migration_lock' = "FREE"
                         /\ dbAdmin_to_backend' = Append(dbAdmin_to_backend, "migration_done")
                         /\ pc' = [pc EXCEPT ![self] = "da_wait"]
                         /\ UNCHANGED << backend_to_tester, tester_to_backend, 
                                         backend_to_dbAdmin, test_env_lock, 
                                         msg_, msg_b, msg >>

da_wait(self) == /\ pc[self] = "da_wait"
                 /\ Len(backend_to_dbAdmin) > 0
                 /\ msg_' = [msg_ EXCEPT ![self] = Head(backend_to_dbAdmin)]
                 /\ backend_to_dbAdmin' = Tail(backend_to_dbAdmin)
                 /\ pc' = [pc EXCEPT ![self] = "da_check"]
                 /\ UNCHANGED << dbAdmin_to_backend, backend_to_tester, 
                                 tester_to_backend, migration_lock, 
                                 test_env_lock, msg_b, msg >>

da_check(self) == /\ pc[self] = "da_check"
                  /\ IF msg_[self] = "adjust"
                        THEN /\ pc' = [pc EXCEPT ![self] = "da_adjust"]
                        ELSE /\ pc' = [pc EXCEPT ![self] = "da_done"]
                  /\ UNCHANGED << dbAdmin_to_backend, backend_to_tester, 
                                  tester_to_backend, backend_to_dbAdmin, 
                                  migration_lock, test_env_lock, msg_, msg_b, 
                                  msg >>

da_adjust(self) == /\ pc[self] = "da_adjust"
                   /\ migration_lock = "FREE"
                   /\ migration_lock' = self
                   /\ pc' = [pc EXCEPT ![self] = "da_adjust_done"]
                   /\ UNCHANGED << dbAdmin_to_backend, backend_to_tester, 
                                   tester_to_backend, backend_to_dbAdmin, 
                                   test_env_lock, msg_, msg_b, msg >>

da_adjust_done(self) == /\ pc[self] = "da_adjust_done"
                        /\ migration_lock' = "FREE"
                        /\ dbAdmin_to_backend' = Append(dbAdmin_to_backend, "migration_done")
                        /\ pc' = [pc EXCEPT ![self] = "da_wait2"]
                        /\ UNCHANGED << backend_to_tester, tester_to_backend, 
                                        backend_to_dbAdmin, test_env_lock, 
                                        msg_, msg_b, msg >>

da_wait2(self) == /\ pc[self] = "da_wait2"
                  /\ Len(backend_to_dbAdmin) > 0
                  /\ msg_' = [msg_ EXCEPT ![self] = Head(backend_to_dbAdmin)]
                  /\ backend_to_dbAdmin' = Tail(backend_to_dbAdmin)
                  /\ pc' = [pc EXCEPT ![self] = "da_done"]
                  /\ UNCHANGED << dbAdmin_to_backend, backend_to_tester, 
                                  tester_to_backend, migration_lock, 
                                  test_env_lock, msg_b, msg >>

da_done(self) == /\ pc[self] = "da_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << dbAdmin_to_backend, backend_to_tester, 
                                 tester_to_backend, backend_to_dbAdmin, 
                                 migration_lock, test_env_lock, msg_, msg_b, 
                                 msg >>

dbAdmin_proc(self) == da_migrate(self) \/ da_migrate_done(self)
                         \/ da_wait(self) \/ da_check(self)
                         \/ da_adjust(self) \/ da_adjust_done(self)
                         \/ da_wait2(self) \/ da_done(self)

bd_wait_migration(self) == /\ pc[self] = "bd_wait_migration"
                           /\ Len(dbAdmin_to_backend) > 0
                           /\ msg_b' = [msg_b EXCEPT ![self] = Head(dbAdmin_to_backend)]
                           /\ dbAdmin_to_backend' = Tail(dbAdmin_to_backend)
                           /\ pc' = [pc EXCEPT ![self] = "bd_deploy"]
                           /\ UNCHANGED << backend_to_tester, 
                                           tester_to_backend, 
                                           backend_to_dbAdmin, migration_lock, 
                                           test_env_lock, msg_, msg >>

bd_deploy(self) == /\ pc[self] = "bd_deploy"
                   /\ backend_to_tester' = Append(backend_to_tester, "deploy")
                   /\ pc' = [pc EXCEPT ![self] = "bd_test_wait"]
                   /\ UNCHANGED << dbAdmin_to_backend, tester_to_backend, 
                                   backend_to_dbAdmin, migration_lock, 
                                   test_env_lock, msg_, msg_b, msg >>

bd_test_wait(self) == /\ pc[self] = "bd_test_wait"
                      /\ Len(tester_to_backend) > 0
                      /\ msg_b' = [msg_b EXCEPT ![self] = Head(tester_to_backend)]
                      /\ tester_to_backend' = Tail(tester_to_backend)
                      /\ pc' = [pc EXCEPT ![self] = "bd_test_check"]
                      /\ UNCHANGED << dbAdmin_to_backend, backend_to_tester, 
                                      backend_to_dbAdmin, migration_lock, 
                                      test_env_lock, msg_, msg >>

bd_test_check(self) == /\ pc[self] = "bd_test_check"
                       /\ IF msg_b[self] = "pass"
                             THEN /\ backend_to_dbAdmin' = Append(backend_to_dbAdmin, "done")
                                  /\ pc' = [pc EXCEPT ![self] = "bd_done"]
                             ELSE /\ \/ /\ TRUE
                                        /\ pc' = [pc EXCEPT ![self] = "bd_redeploy"]
                                        /\ UNCHANGED backend_to_dbAdmin
                                     \/ /\ backend_to_dbAdmin' = Append(backend_to_dbAdmin, "adjust")
                                        /\ pc' = [pc EXCEPT ![self] = "bd_wait_adjust"]
                       /\ UNCHANGED << dbAdmin_to_backend, backend_to_tester, 
                                       tester_to_backend, migration_lock, 
                                       test_env_lock, msg_, msg_b, msg >>

bd_wait_adjust(self) == /\ pc[self] = "bd_wait_adjust"
                        /\ Len(dbAdmin_to_backend) > 0
                        /\ msg_b' = [msg_b EXCEPT ![self] = Head(dbAdmin_to_backend)]
                        /\ dbAdmin_to_backend' = Tail(dbAdmin_to_backend)
                        /\ pc' = [pc EXCEPT ![self] = "bd_redeploy"]
                        /\ UNCHANGED << backend_to_tester, tester_to_backend, 
                                        backend_to_dbAdmin, migration_lock, 
                                        test_env_lock, msg_, msg >>

bd_redeploy(self) == /\ pc[self] = "bd_redeploy"
                     /\ backend_to_tester' = Append(backend_to_tester, "deploy")
                     /\ pc' = [pc EXCEPT ![self] = "bd_retest_wait"]
                     /\ UNCHANGED << dbAdmin_to_backend, tester_to_backend, 
                                     backend_to_dbAdmin, migration_lock, 
                                     test_env_lock, msg_, msg_b, msg >>

bd_retest_wait(self) == /\ pc[self] = "bd_retest_wait"
                        /\ Len(tester_to_backend) > 0
                        /\ msg_b' = [msg_b EXCEPT ![self] = Head(tester_to_backend)]
                        /\ tester_to_backend' = Tail(tester_to_backend)
                        /\ pc' = [pc EXCEPT ![self] = "bd_retest_done"]
                        /\ UNCHANGED << dbAdmin_to_backend, backend_to_tester, 
                                        backend_to_dbAdmin, migration_lock, 
                                        test_env_lock, msg_, msg >>

bd_retest_done(self) == /\ pc[self] = "bd_retest_done"
                        /\ backend_to_dbAdmin' = Append(backend_to_dbAdmin, "done")
                        /\ pc' = [pc EXCEPT ![self] = "bd_done"]
                        /\ UNCHANGED << dbAdmin_to_backend, backend_to_tester, 
                                        tester_to_backend, migration_lock, 
                                        test_env_lock, msg_, msg_b, msg >>

bd_done(self) == /\ pc[self] = "bd_done"
                 /\ TRUE
                 /\ pc' = [pc EXCEPT ![self] = "Done"]
                 /\ UNCHANGED << dbAdmin_to_backend, backend_to_tester, 
                                 tester_to_backend, backend_to_dbAdmin, 
                                 migration_lock, test_env_lock, msg_, msg_b, 
                                 msg >>

backendDev_proc(self) == bd_wait_migration(self) \/ bd_deploy(self)
                            \/ bd_test_wait(self) \/ bd_test_check(self)
                            \/ bd_wait_adjust(self) \/ bd_redeploy(self)
                            \/ bd_retest_wait(self) \/ bd_retest_done(self)
                            \/ bd_done(self)

t_wait(self) == /\ pc[self] = "t_wait"
                /\ Len(backend_to_tester) > 0
                /\ msg' = [msg EXCEPT ![self] = Head(backend_to_tester)]
                /\ backend_to_tester' = Tail(backend_to_tester)
                /\ pc' = [pc EXCEPT ![self] = "t_test"]
                /\ UNCHANGED << dbAdmin_to_backend, tester_to_backend, 
                                backend_to_dbAdmin, migration_lock, 
                                test_env_lock, msg_, msg_b >>

t_test(self) == /\ pc[self] = "t_test"
                /\ test_env_lock = "FREE"
                /\ test_env_lock' = self
                /\ pc' = [pc EXCEPT ![self] = "t_test_done"]
                /\ UNCHANGED << dbAdmin_to_backend, backend_to_tester, 
                                tester_to_backend, backend_to_dbAdmin, 
                                migration_lock, msg_, msg_b, msg >>

t_test_done(self) == /\ pc[self] = "t_test_done"
                     /\ test_env_lock' = "FREE"
                     /\ pc' = [pc EXCEPT ![self] = "t_result"]
                     /\ UNCHANGED << dbAdmin_to_backend, backend_to_tester, 
                                     tester_to_backend, backend_to_dbAdmin, 
                                     migration_lock, msg_, msg_b, msg >>

t_result(self) == /\ pc[self] = "t_result"
                  /\ \/ /\ tester_to_backend' = Append(tester_to_backend, "pass")
                        /\ pc' = [pc EXCEPT ![self] = "Done"]
                     \/ /\ tester_to_backend' = Append(tester_to_backend, "fail")
                        /\ pc' = [pc EXCEPT ![self] = "t_rewait"]
                  /\ UNCHANGED << dbAdmin_to_backend, backend_to_tester, 
                                  backend_to_dbAdmin, migration_lock, 
                                  test_env_lock, msg_, msg_b, msg >>

t_rewait(self) == /\ pc[self] = "t_rewait"
                  /\ Len(backend_to_tester) > 0
                  /\ msg' = [msg EXCEPT ![self] = Head(backend_to_tester)]
                  /\ backend_to_tester' = Tail(backend_to_tester)
                  /\ pc' = [pc EXCEPT ![self] = "t_retest"]
                  /\ UNCHANGED << dbAdmin_to_backend, tester_to_backend, 
                                  backend_to_dbAdmin, migration_lock, 
                                  test_env_lock, msg_, msg_b >>

t_retest(self) == /\ pc[self] = "t_retest"
                  /\ test_env_lock = "FREE"
                  /\ test_env_lock' = self
                  /\ pc' = [pc EXCEPT ![self] = "t_retest_done"]
                  /\ UNCHANGED << dbAdmin_to_backend, backend_to_tester, 
                                  tester_to_backend, backend_to_dbAdmin, 
                                  migration_lock, msg_, msg_b, msg >>

t_retest_done(self) == /\ pc[self] = "t_retest_done"
                       /\ test_env_lock' = "FREE"
                       /\ tester_to_backend' = Append(tester_to_backend, "pass")
                       /\ pc' = [pc EXCEPT ![self] = "Done"]
                       /\ UNCHANGED << dbAdmin_to_backend, backend_to_tester, 
                                       backend_to_dbAdmin, migration_lock, 
                                       msg_, msg_b, msg >>

tester_proc(self) == t_wait(self) \/ t_test(self) \/ t_test_done(self)
                        \/ t_result(self) \/ t_rewait(self)
                        \/ t_retest(self) \/ t_retest_done(self)

(* Allow infinite stuttering to prevent deadlock on termination. *)
Terminating == /\ \A self \in ProcSet: pc[self] = "Done"
               /\ UNCHANGED vars

Next == (\E self \in {DbAdmin}: dbAdmin_proc(self))
           \/ (\E self \in {BackendDev}: backendDev_proc(self))
           \/ (\E self \in {Tester}: tester_proc(self))
           \/ Terminating

Spec == /\ Init /\ [][Next]_vars
        /\ \A self \in {DbAdmin} : WF_vars(dbAdmin_proc(self))
        /\ \A self \in {BackendDev} : WF_vars(backendDev_proc(self))
        /\ \A self \in {Tester} : WF_vars(tester_proc(self))

Termination == <>(\A self \in ProcSet: pc[self] = "Done")

\* END TRANSLATION 

AllDone == \A p \in {BackendDev, DbAdmin, Tester}: pc[p] = "Done"

TypeInvariant ==
  /\ \A p \in {BackendDev, DbAdmin, Tester}: pc[p] \in STRING
  /\ migration_lock \in {BackendDev, DbAdmin, Tester, "FREE"}
  /\ test_env_lock \in {BackendDev, DbAdmin, Tester, "FREE"}
  /\ dbAdmin_to_backend \in Seq(STRING)
  /\ backend_to_tester \in Seq(STRING)
  /\ tester_to_backend \in Seq(STRING)
  /\ backend_to_dbAdmin \in Seq(STRING)

NoOrphanLocks ==
  AllDone => (migration_lock = "FREE" /\ test_env_lock = "FREE")

ChannelsDrained ==
  AllDone => (Len(dbAdmin_to_backend) = 0 /\ Len(backend_to_tester) = 0 /\ Len(tester_to_backend) = 0 /\ Len(backend_to_dbAdmin) = 0)

ChannelBound ==
  Len(dbAdmin_to_backend) <= 3 /\ Len(backend_to_tester) <= 3 /\ Len(tester_to_backend) <= 3 /\ Len(backend_to_dbAdmin) <= 3

====
