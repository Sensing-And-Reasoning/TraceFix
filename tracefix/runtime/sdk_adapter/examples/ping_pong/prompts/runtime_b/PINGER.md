# Agent: PINGER

You are **PINGER** in a two-agent ping-pong coordination protocol. Follow these
steps in order, using the tools available to you. Do not skip steps.

## Your protocol

1. Use the **Write** tool to create the file `/tmp/tracefix_pingpong/pinger_note.txt`
   containing exactly: `PINGER did real work`.
2. Call **send_message** with `channel_id="ping_ch"` and `label="ping"`.
3. Call **receive_message** with `channel_id="pong_ch"` and wait for PONGER's reply.
4. Once you receive the `pong` reply, call **signal_done**.

Keep going until you have completed every step. Do not stop before calling signal_done.
