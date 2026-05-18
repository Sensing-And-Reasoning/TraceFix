# Semiconductor Wafer Fabrication Line

Six engineers coordinate to fabricate and qualify a batch of semiconductor wafers. They share five pieces of capital equipment: a photolithography **STEPPER**, a chemical vapor deposition (CVD) chamber, a reactive ion etch (RIE) chamber, a metrology station, and a process monitoring system. Only one engineer may use each instrument at a time.

## Agents
- **LITHOGRAPHER**: patterns wafer layers using the **STEPPER** and etch chamber
- **DEPOSITOR**: deposits thin films using the CVD deposition chamber
- **ETCHER**: performs precision reactive ion etching in the etch chamber
- **METROLOGY_ENGINEER**: measures critical dimensions at the metrology station
- **PROCESS_CONTROLLER**: validates process data via the monitoring system and issues go/no-go decisions
- **INTEGRATION_ENGINEER**: performs final cross-tool qualification checks

## Shared Resources
- **STEPPER**: photolithography stepper for wafer exposure
- **DEP_CHAMBER**: CVD deposition chamber for thin-film growth
- **ETCH_CHAMBER**: reactive ion etch chamber for pattern transfer
- **METROLOGY_STATION**: critical-dimension measurement station
- **MONITOR**: in-situ process monitoring system for real-time data collection

## Communication Channels

- Fab-ready channel (**LITHOGRAPHER** → **METROLOGY_ENGINEER**): pattern-ready notification
- Fab-ready channel (**DEPOSITOR** → **METROLOGY_ENGINEER**): film-ready notification
- Fab-ready channel (**ETCHER** → **METROLOGY_ENGINEER**): etch-ready notification
- Measurement report channel (**METROLOGY_ENGINEER** → **PROCESS_CONTROLLER**): dimensional measurement results (×3)
- Validation confirmation channel (**PROCESS_CONTROLLER** → **LITHOGRAPHER**): process validated
- Validation confirmation channel (**PROCESS_CONTROLLER** → **DEPOSITOR**): process validated
- Validation confirmation channel (**PROCESS_CONTROLLER** → **ETCHER**): process validated
- All-validated channel (**PROCESS_CONTROLLER** → **INTEGRATION_ENGINEER**): all processes validated
- Lot disposition channel (**INTEGRATION_ENGINEER** → **LITHOGRAPHER**): final lot disposition
- Lot disposition channel (**INTEGRATION_ENGINEER** → **DEPOSITOR**): final lot disposition
- Lot disposition channel (**INTEGRATION_ENGINEER** → **ETCHER**): final lot disposition

## Workflow

### LITHOGRAPHER
The **LITHOGRAPHER** begins by loading a wafer lot into the **STEPPER** and running the photolithography exposure sequence. While the wafer remains loaded on the **STEPPER** stage, the **LITHOGRAPHER** accesses the process monitoring system to verify that exposure dose and focus are within specification — removing the wafer mid-exposure would destroy the partially exposed resist pattern. After confirming exposure parameters, the **LITHOGRAPHER** steps away from the monitoring system and then unloads the wafer from the **STEPPER**.

Next, the **LITHOGRAPHER** transfers the wafer to the etch chamber for pattern transfer etching. While the etch is in progress inside the sealed chamber, the **LITHOGRAPHER** again accesses the monitoring system to verify the etch endpoint signal — opening the chamber during the plasma etch would cause non-uniform material removal. After confirming the etch endpoint, the **LITHOGRAPHER** steps away from the monitoring system and then removes the wafer from the etch chamber. The **LITHOGRAPHER** sends a pattern-ready notification to the **METROLOGY_ENGINEER**.

After process validation, the **LITHOGRAPHER** receives a validation confirmation from the **PROCESS_CONTROLLER**. The **LITHOGRAPHER** then uses the **METROLOGY_STATION** for a final post-litho alignment check and waits for the lot disposition from the **INTEGRATION_ENGINEER**.

### DEPOSITOR
The **DEPOSITOR** loads wafers into the CVD deposition chamber and begins the thin-film growth process. While the chamber is sealed and deposition is underway, the **DEPOSITOR** accesses the monitoring system to track the deposition rate and film uniformity in real time — opening the chamber during CVD would introduce contaminants and ruin the film. After confirming the deposition parameters, the **DEPOSITOR** steps away from the monitoring system and then vents and unloads the deposition chamber. The **DEPOSITOR** sends a film-ready notification to the **METROLOGY_ENGINEER**.

After process validation, the **DEPOSITOR** receives a validation confirmation from the **PROCESS_CONTROLLER**. The **DEPOSITOR** uses the **METROLOGY_STATION** for a final film-thickness verification and waits for the lot disposition from the **INTEGRATION_ENGINEER**.

### ETCHER
The **ETCHER** loads wafers into the etch chamber and starts the reactive ion etch process. While the plasma etch is running in the sealed chamber, the **ETCHER** accesses the monitoring system to monitor the etch rate and selectivity — interrupting a plasma etch mid-process would leave non-uniform surface profiles. After confirming etch parameters, the **ETCHER** steps away from the monitoring system and then removes the wafer from the etch chamber. The **ETCHER** sends an etch-ready notification to the **METROLOGY_ENGINEER**.

After process validation, the **ETCHER** receives a validation confirmation from the **PROCESS_CONTROLLER** and waits for the lot disposition from the **INTEGRATION_ENGINEER**.

### METROLOGY_ENGINEER
The **METROLOGY_ENGINEER** receives process-completion notifications from the **LITHOGRAPHER**, **DEPOSITOR**, and **ETCHER** in whatever order they arrive. For each notification received, the **METROLOGY_ENGINEER** uses the **METROLOGY_STATION** to perform the appropriate dimensional measurement and sends a measurement report to the **PROCESS_CONTROLLER**. The **METROLOGY_ENGINEER** is done after sending all three reports.

### PROCESS_CONTROLLER
The **PROCESS_CONTROLLER** receives three measurement reports from the **METROLOGY_ENGINEER** in whatever order they arrive. After collecting all three reports, the **PROCESS_CONTROLLER** uses the monitoring system to cross-reference the metrology data against the in-situ process logs. After completing the cross-reference analysis, the **PROCESS_CONTROLLER** steps away from the monitoring system.

The **PROCESS_CONTROLLER** then sends individual validation confirmations to the **LITHOGRAPHER**, **DEPOSITOR**, and **ETCHER**, and sends an all-validated signal to the **INTEGRATION_ENGINEER**.

### INTEGRATION_ENGINEER
The **INTEGRATION_ENGINEER** receives the all-validated signal from the **PROCESS_CONTROLLER**. The **INTEGRATION_ENGINEER** then loads a reference wafer onto the **STEPPER** stage. While the wafer is on the **STEPPER**, the **INTEGRATION_ENGINEER** uses the **METROLOGY_STATION** to perform an in-situ overlay alignment measurement — the wafer must remain fixtured on the **STEPPER** stage during this measurement. After completing the measurement, the **INTEGRATION_ENGINEER** steps away from the **METROLOGY_STATION** and then unloads the wafer from the **STEPPER**.

The **INTEGRATION_ENGINEER** next uses the **DEP_CHAMBER** for a film-integrity spot check, then uses the **ETCH_CHAMBER** for an etch-uniformity spot check.

Finally, the **INTEGRATION_ENGINEER** sends the lot disposition to the **LITHOGRAPHER**, the **DEPOSITOR**, and the **ETCHER**.

## Goal
All six engineers complete their work: the **LITHOGRAPHER** and **DEPOSITOR** finish post-validation metrology, the **ETCHER** receives its disposition, the **METROLOGY_ENGINEER** delivers all three measurement reports, the **PROCESS_CONTROLLER** communicates all validation decisions, and the **INTEGRATION_ENGINEER** sends lot dispositions to all three fabrication agents.
