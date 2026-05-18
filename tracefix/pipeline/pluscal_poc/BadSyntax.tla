--------------------------- MODULE BadSyntax ---------------------------
EXTENDS Integers, Sequences

CONSTANTS WorkerA, WorkerB

(* --algorithm BadSyntax

variables ch = <<>>;

macro send(c, m) begin
  c := Append(c, m);
end macro;

\* Error 1: missing "end if"
fair process worker1 = WorkerA
begin
  start:
    if TRUE then
      send(ch, "hello");
end process;

\* Error 2: label inside macro (not allowed)
\* (can't test directly, but let's test other errors)

fair process worker2 = WorkerB
variables x = 0;
begin
  s1:
    x := x + 1;
    \* Error: goto non-existent label
    goto nonexistent;
  s2:
    skip;
end process;

end algorithm; *)

=============================================================================
