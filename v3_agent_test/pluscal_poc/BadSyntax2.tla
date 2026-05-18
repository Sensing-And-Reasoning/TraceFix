--------------------------- MODULE BadSyntax2 ---------------------------
EXTENDS Integers, Sequences

CONSTANTS WorkerA, WorkerB

(* --algorithm BadSyntax2

variables ch = <<>>;

fair process worker1 = WorkerA
variables x = 0;
begin
  s1:
    x := x + 1;
    goto nonexistent;
  s2:
    skip;
end process;

end algorithm; *)

=============================================================================
