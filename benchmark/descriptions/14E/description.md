# Drug Discovery Pipeline

Four scientists collaborate on evaluating a drug candidate compound. They share three expensive laboratory instruments that only one scientist can use at a time: an HPLC (High-Performance Liquid Chromatography) system, a mass spectrometer, and a cell culture laboratory.

## Agents
- **CHEMIST**: synthesizes the compound and performs final documentation
- **BIOLOGIST**: evaluates biological activity of the compound
- **TOXICOLOGIST**: assesses compound safety and toxicity
- **LEAD_SCIENTIST**: reviews all results and makes the go/no-go decision

## Shared Resources
- **HPLC**: chromatography system for compound analysis and purification QC
- **MASS_SPEC**: mass spectrometry system for molecular identification
- **CELL_LAB**: cell culture laboratory for biological and toxicity assays

## Workflow

### CHEMIST
The **CHEMIST** begins by running a synthesis quality-control check on the **HPLC** to verify compound purity, then confirms the molecular identity on the **MASS_SPEC**. Once both checks pass, the **CHEMIST** sends compound samples to the **BIOLOGIST** and the **TOXICOLOGIST** for independent evaluation. The **CHEMIST** then waits for the **LEAD_SCIENTIST**'s go/no-go decision before performing a final **HPLC** documentation analysis to archive the compound's chromatographic profile.

### BIOLOGIST
The **BIOLOGIST** first prepares and qualifies cell lines in the **CELL_LAB**. After receiving the compound from the **CHEMIST**, the **BIOLOGIST** runs the primary bioassay on the prepared cells in the **CELL_LAB**. While the assay cultures are still incubating in the **CELL_LAB**, the **BIOLOGIST** uses the **HPLC** to verify that the compound has not degraded in the cell culture medium. Once stability is confirmed, the **BIOLOGIST** sends the bioactivity report to the **LEAD_SCIENTIST**.

### TOXICOLOGIST
The **TOXICOLOGIST** begins by establishing baseline toxicity markers on the **MASS_SPEC**. After receiving the compound from the **CHEMIST**, the **TOXICOLOGIST** immediately checks compound purity on the **HPLC** to ensure the sample is suitable for safety testing. The **TOXICOLOGIST** then runs a cytotoxicity dose-response assay in the **CELL_LAB**. The **TOXICOLOGIST** sends the completed toxicity report to the **LEAD_SCIENTIST**.

### LEAD_SCIENTIST
The **LEAD_SCIENTIST** first sets up reference analytical methods on the **MASS_SPEC**. The **LEAD_SCIENTIST** then waits for both the bioactivity report from the **BIOLOGIST** and the toxicity report from the **TOXICOLOGIST**. After receiving both reports, the **LEAD_SCIENTIST** runs a structural confirmation analysis on the **HPLC** and a comprehensive characterization on the **MASS_SPEC**. Based on all data, the **LEAD_SCIENTIST** sends the final go/no-go decision to the **CHEMIST**.

## Goal
All four scientists complete their work: the **CHEMIST** archives the compound profile, the **BIOLOGIST** delivers the bioactivity report, the **TOXICOLOGIST** delivers the toxicity report, and the **LEAD_SCIENTIST** communicates the final decision.
