--------------------------- MODULE BadSyntax3 ---------------------------
EXTENDS Integers, Sequences

CONSTANTS A, B

(* --algorithm BadSyntax3

variables ch = <<>>;

\* Error: label inside macro (PlusCal forbids this)
macro bad_macro() begin
  lbl:
    ch := Append(ch, "x");
end macro;

fair process p1 = A
begin
  start:
    bad_macro();
end process;

end algorithm; *)

=============================================================================
