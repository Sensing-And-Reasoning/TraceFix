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
