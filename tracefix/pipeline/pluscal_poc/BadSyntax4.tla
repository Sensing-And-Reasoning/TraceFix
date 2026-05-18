--------------------------- MODULE BadSyntax4 ---------------------------
EXTENDS Integers, Sequences

CONSTANTS A, B

(* --algorithm BadSyntax4

variables ch = <<>>;

macro send(c, m) begin
  c := Append(c, m);
end macro;

\* Error: two statements with await in same label (need separate labels)
fair process p1 = A
variables x = "", y = "";
begin
  start:
    await Len(ch) > 0;
    x := Head(ch);
    ch := Tail(ch);
    await Len(ch) > 0;
    y := Head(ch);
    ch := Tail(ch);
end process;

end algorithm; *)

=============================================================================
