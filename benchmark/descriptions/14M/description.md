# Drug Discovery Pipeline with Regulatory Review

Five scientists collaborate on evaluating a drug candidate compound. They share three expensive laboratory instruments. A regulatory specialist reviews the lead scientist's decision and can send the process back for additional evaluation. Assays can fail, requiring redo.

## Agents
- **CHEMIST**: synthesizes the compound and performs final documentation
- **BIOLOGIST**: evaluates biological activity of the compound
- **TOXICOLOGIST**: assesses compound safety and toxicity
- **LEAD_SCIENTIST**: reviews all results and makes the go/no-go decision
- **REGULATORY_SPECIALIST**: reviews the lead scientist's decision for regulatory compliance; can reject, requiring re-evaluation

## Shared Resources
- **HPLC**: chromatography system for compound analysis and purification QC
- **MASS_SPEC**: mass spectrometry system for molecular identification
- **CELL_LAB**: cell culture laboratory for biological and toxicity assays

## Workflow

### CHEMIST
The **CHEMIST** begins by running a synthesis quality-control check on the **HPLC** to verify compound purity, then confirms the molecular identity on the **MASS_SPEC**. Once both checks pass, the **CHEMIST** sends compound samples to the **BIOLOGIST** and the **TOXICOLOGIST** for independent evaluation. The **CHEMIST** then waits for the **REGULATORY_SPECIALIST**'s final compliance approval before performing a final **HPLC** documentation analysis to archive the compound's chromatographic profile.

### BIOLOGIST
The **BIOLOGIST** first prepares and qualifies cell lines in the **CELL_LAB**. After receiving the compound from the **CHEMIST**, the **BIOLOGIST** runs the primary bioassay on the prepared cells in the **CELL_LAB** — the bioassay can fail, requiring the **BIOLOGIST** to redo the cell assay. While the assay cultures are still incubating in the **CELL_LAB**, the **BIOLOGIST** uses the **HPLC** to verify that the compound has not degraded in the cell culture medium — the **HPLC** analysis can fail, requiring a redo. Once stability is confirmed, the **BIOLOGIST** sends the bioactivity report to the **LEAD_SCIENTIST**.

### TOXICOLOGIST
The **TOXICOLOGIST** begins by establishing baseline toxicity markers on the **MASS_SPEC**. After receiving the compound from the **CHEMIST**, the **TOXICOLOGIST** immediately checks compound purity on the **HPLC** to ensure the sample is suitable for safety testing. The **TOXICOLOGIST** then runs a cytotoxicity dose-response assay in the **CELL_LAB** — the cell assay can fail, requiring a redo. The **TOXICOLOGIST** sends the completed toxicity report to the **LEAD_SCIENTIST**.

### LEAD_SCIENTIST
The **LEAD_SCIENTIST** first sets up reference analytical methods on the **MASS_SPEC**. The **LEAD_SCIENTIST** then waits for both the bioactivity report from the **BIOLOGIST** and the toxicity report from the **TOXICOLOGIST**. After receiving both reports, the **LEAD_SCIENTIST** runs a structural confirmation analysis on the **HPLC** and a comprehensive characterization on the **MASS_SPEC**. Based on all data, the **LEAD_SCIENTIST** makes a go/no-go decision and sends it to the **REGULATORY_SPECIALIST**.

If the **REGULATORY_SPECIALIST** rejects the decision, the **LEAD_SCIENTIST** may request additional assays from the **BIOLOGIST** or **TOXICOLOGIST**. The **LEAD_SCIENTIST** re-collects the new report(s), performs another **HPLC** confirmation, and sends an updated decision to the **REGULATORY_SPECIALIST**. (For modeling purposes, at most one regulatory revision cycle occurs.)

### REGULATORY_SPECIALIST
The **REGULATORY_SPECIALIST** receives the **LEAD_SCIENTIST**'s go/no-go decision. The **REGULATORY_SPECIALIST** reviews the decision for regulatory compliance — this review can result in approval or rejection. If rejected, the **REGULATORY_SPECIALIST** sends a rejection notice to the **LEAD_SCIENTIST** and waits for a revised decision.

After final approval, the **REGULATORY_SPECIALIST** sends the compliance approval to the **CHEMIST** and is done.

## Goal
All five scientists complete their work: the **CHEMIST** archives the compound profile after regulatory approval, the **BIOLOGIST** delivers the bioactivity report, the **TOXICOLOGIST** delivers the toxicity report, the **LEAD_SCIENTIST** communicates the final decision, and the **REGULATORY_SPECIALIST** issues the compliance approval.
