# Semiconductor Fabrication with Rework and Yield Halt

Six engineers coordinate to fabricate and qualify a batch of semiconductor wafers. They share five pieces of capital equipment and a limited number of wafer processing slots. Only one engineer may use each instrument at a time. Metrology failures require rework, integration requires a contamination check with simultaneous control of three chambers, and the **PROCESS_CONTROLLER** can issue a yield halt that blocks all fabrication.

## Agents
- **LITHOGRAPHER**: patterns wafer layers using the **STEPPER** and etch chamber
- **DEPOSITOR**: deposits thin films using the CVD deposition chamber
- **ETCHER**: performs precision reactive ion etching in the etch chamber
- **METROLOGY_ENGINEER**: measures critical dimensions at the metrology station
- **PROCESS_CONTROLLER**: validates process data via the monitoring system; can issue a yield halt
- **INTEGRATION_ENGINEER**: performs final cross-tool qualification including a contamination check

## Shared Resources
- **STEPPER**: photolithography stepper for wafer exposure
- **DEP_CHAMBER**: CVD deposition chamber for thin-film growth
- **ETCH_CHAMBER**: reactive ion etch chamber for pattern transfer
- **METROLOGY_STATION**: critical-dimension measurement station
- **MONITOR**: in-situ process monitoring system for real-time data collection

## Shared Resource Pool
- **WAFER_SLOTS**: 2 slots available — only 2 wafers can be processed simultaneously across the entire fab line. Each fab agent (**LITHOGRAPHER**, **DEPOSITOR**, **ETCHER**) must claim a wafer slot before starting their process and return it when done.

## Communication Channels

- Fab-ready channel (**LITHOGRAPHER** → **METROLOGY_ENGINEER**): pattern-ready notification
- Fab-ready channel (**DEPOSITOR** → **METROLOGY_ENGINEER**): film-ready notification
- Fab-ready channel (**ETCHER** → **METROLOGY_ENGINEER**): etch-ready notification
- Measurement report channel (**METROLOGY_ENGINEER** → **PROCESS_CONTROLLER**): dimensional measurement results (×3)
- Measurement failure channel (**METROLOGY_ENGINEER** → fab agents): measurement failure notification, triggering rework
- Rework notification channel (fab agents → **METROLOGY_ENGINEER**): rework complete, ready for re-measurement
- Validation confirmation channel (**PROCESS_CONTROLLER** → **LITHOGRAPHER**): process validated
- Validation confirmation channel (**PROCESS_CONTROLLER** → **DEPOSITOR**): process validated
- Validation confirmation channel (**PROCESS_CONTROLLER** → **ETCHER**): process validated
- All-validated channel (**PROCESS_CONTROLLER** → **INTEGRATION_ENGINEER**): all processes validated
- Yield halt channel (**PROCESS_CONTROLLER** → **LITHOGRAPHER**, **DEPOSITOR**, **ETCHER**): halt signal, stop all instrument use
- Clearance channel (**PROCESS_CONTROLLER** → **LITHOGRAPHER**, **DEPOSITOR**, **ETCHER**): clearance to resume after investigation
- Lot disposition channel (**INTEGRATION_ENGINEER** → **LITHOGRAPHER**): final lot disposition
- Lot disposition channel (**INTEGRATION_ENGINEER** → **DEPOSITOR**): final lot disposition
- Lot disposition channel (**INTEGRATION_ENGINEER** → **ETCHER**): final lot disposition

## Workflow

### LITHOGRAPHER
The **LITHOGRAPHER** claims a wafer slot, then loads a wafer into the **STEPPER** and runs the photolithography exposure sequence. While the wafer remains on the **STEPPER**, the **LITHOGRAPHER** uses the monitoring system to verify exposure parameters. After verification, the **LITHOGRAPHER** steps away from the **MONITOR**.

While still using the **STEPPER**, the **LITHOGRAPHER** must perform an OPC cross-calibration by reading etch profile sensors from the **ETCH_CHAMBER**. After cross-calibration, the **LITHOGRAPHER** steps away from the **ETCH_CHAMBER** and then the **STEPPER**.

The **LITHOGRAPHER** transfers the wafer to the **ETCH_CHAMBER** for pattern transfer etching. While the etch is in progress, the **LITHOGRAPHER** uses the **MONITOR** to verify the etch endpoint. After verification, the **LITHOGRAPHER** steps away from the **MONITOR**, then the **ETCH_CHAMBER**, and returns the wafer slot. The **LITHOGRAPHER** sends a pattern-ready notification to the **METROLOGY_ENGINEER**.

After receiving a validation confirmation from the **PROCESS_CONTROLLER**, the **LITHOGRAPHER** uses the **STEPPER** for a final alignment check. While the wafer is on the **STEPPER**, the **LITHOGRAPHER** uses the **METROLOGY_STATION** for in-situ CD measurement. After measurement, the **LITHOGRAPHER** steps away from the **METROLOGY_STATION**, then the **STEPPER**. The **LITHOGRAPHER** waits for lot disposition from the **INTEGRATION_ENGINEER**.

If the **METROLOGY_ENGINEER** reports a measurement failure for the **LITHOGRAPHER**'s process, the **LITHOGRAPHER** must rework: claim a new wafer slot, re-use the **STEPPER** for re-exposure, and re-send to metrology.

### DEPOSITOR
The **DEPOSITOR** claims a wafer slot, then loads wafers into the CVD deposition chamber. While the chamber is sealed, the **DEPOSITOR** uses the **MONITOR** to track deposition parameters. After verification, the **DEPOSITOR** steps away from the **MONITOR**.

While still using the **DEP_CHAMBER**, the **DEPOSITOR** must perform an alignment cross-calibration by reading stage sensors from the **STEPPER**. After cross-calibration, the **DEPOSITOR** steps away from the **STEPPER**, then the **DEP_CHAMBER**, and returns the wafer slot. The **DEPOSITOR** sends a film-ready notification to the **METROLOGY_ENGINEER**.

After receiving validation, the **DEPOSITOR** uses the **METROLOGY_STATION** for film-thickness verification. While measuring, the **DEPOSITOR** must use the **STEPPER** to read a reference alignment datum. After reading, the **DEPOSITOR** steps away from the **STEPPER**, then the **METROLOGY_STATION**. The **DEPOSITOR** waits for lot disposition.

If metrology reports a measurement failure, the **DEPOSITOR** must rework: claim a new wafer slot, re-use the **DEP_CHAMBER**, and redo deposition.

### ETCHER
The **ETCHER** claims a wafer slot, then loads wafers into the **ETCH_CHAMBER**. While the plasma etch is running, the **ETCHER** uses the **MONITOR** to check etch rate. After verification, the **ETCHER** steps away from the **MONITOR**.

While still using the **ETCH_CHAMBER**, the **ETCHER** must perform an endpoint cross-calibration by reading film stress sensors from the **DEP_CHAMBER**. After cross-calibration, the **ETCHER** steps away from the **DEP_CHAMBER**, then the **ETCH_CHAMBER**, and returns the wafer slot. The **ETCHER** sends an etch-ready notification to the **METROLOGY_ENGINEER**.

After receiving validation, the **ETCHER** waits for lot disposition.

If metrology reports a measurement failure, the **ETCHER** must rework: claim a new wafer slot, re-use the **ETCH_CHAMBER**, and redo etching.

### METROLOGY_ENGINEER
The **METROLOGY_ENGINEER** receives process-completion notifications from the **LITHOGRAPHER**, **DEPOSITOR**, and **ETCHER** in whatever order they arrive. For each notification, the **METROLOGY_ENGINEER** uses the **METROLOGY_STATION** to perform the measurement — the measurement can fail, requiring the **METROLOGY_ENGINEER** to notify the originating fab agent of the failure and wait for a rework notification. On success, the **METROLOGY_ENGINEER** steps away from the **METROLOGY_STATION** and sends a measurement report to the **PROCESS_CONTROLLER**.

### PROCESS_CONTROLLER
The **PROCESS_CONTROLLER** receives three measurement reports from the **METROLOGY_ENGINEER** in whatever order they arrive. After collecting all three, the **PROCESS_CONTROLLER** uses the **MONITOR** to cross-reference metrology data.

The **PROCESS_CONTROLLER** can issue a yield halt: uses the **MONITOR** and the **METROLOGY_STATION** simultaneously, broadcasts a halt signal to the **LITHOGRAPHER**, **DEPOSITOR**, and **ETCHER**. All three fab agents must stop using any instruments currently in use and wait for clearance. After investigation, the **PROCESS_CONTROLLER** steps away from the **METROLOGY_STATION** and **MONITOR**, and sends clearance to all three fab agents.

After validation (with or without halt), the **PROCESS_CONTROLLER** sends individual validation confirmations to the **LITHOGRAPHER**, **DEPOSITOR**, and **ETCHER**, and sends an all-validated signal to the **INTEGRATION_ENGINEER**.

### INTEGRATION_ENGINEER
The **INTEGRATION_ENGINEER** receives the all-validated signal. Before performing qualification checks, the **INTEGRATION_ENGINEER** must run a contamination scan: simultaneously use the **DEP_CHAMBER**, **ETCH_CHAMBER**, and **STEPPER** (all three chambers must be free) to verify no cross-contamination. After the scan, the **INTEGRATION_ENGINEER** steps away from all three.

The **INTEGRATION_ENGINEER** then performs individual qualification checks: uses the **STEPPER** and **METROLOGY_STATION** for overlay alignment, steps away from both; uses the **DEP_CHAMBER** for film integrity, steps away; uses the **ETCH_CHAMBER** for etch uniformity, steps away.

Finally, the **INTEGRATION_ENGINEER** sends lot disposition to the **LITHOGRAPHER**, **DEPOSITOR**, and **ETCHER**.

## Goal
All six engineers complete their work: fab agents finish post-validation checks, the **METROLOGY_ENGINEER** delivers all reports, the **PROCESS_CONTROLLER** communicates validations, and the **INTEGRATION_ENGINEER** sends lot dispositions.
