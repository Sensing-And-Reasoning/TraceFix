# Drug Discovery Pipeline with Multi-Round Trials

Seven scientists collaborate on evaluating a drug candidate through multiple trial rounds. They share four expensive laboratory instruments and a limited supply of biological samples. The project director can order additional rounds, and the regulatory specialist can issue clinical holds.

## Agents
- **CHEMIST**: synthesizes the compound using the HPLC and mass spectrometer
- **FORMULATION_SCIENTIST**: prepares drug formulations in the formulation suite
- **BIOLOGIST**: evaluates biological activity using cell-based assays
- **TOXICOLOGIST**: assesses compound safety and toxicity
- **REGULATORY_SPECIALIST**: reviews for compliance; can issue a clinical hold that blocks the clinical lead and project director
- **CLINICAL_LEAD**: reviews combined bio/tox results before regulatory submission
- **PROJECT_DIRECTOR**: makes the final continue/retry/abort decision; retry triggers a new round

## Shared Resources
- **HPLC**: chromatography system for compound analysis
- **MASS_SPEC**: mass spectrometry system for molecular identification
- **CELL_LAB**: cell culture laboratory for biological and toxicity assays
- **FORMULATION_SUITE**: formulation development laboratory

## Shared Resource Pool
- **BIOLOGICAL_SAMPLES**: 3 units available — each bioassay or toxicity study consumes one sample unit. If samples are exhausted, no more assays can be performed.

## Workflow

### CHEMIST
The **CHEMIST** runs a synthesis QC check on the **HPLC**, then confirms molecular identity on the **MASS_SPEC**. The **CHEMIST** sends the compound to the **FORMULATION_SCIENTIST** and waits for the **PROJECT_DIRECTOR**'s final decision. After receiving the decision, the **CHEMIST** runs a final **HPLC** documentation analysis and is done.

### FORMULATION_SCIENTIST
The **FORMULATION_SCIENTIST** receives the compound from the **CHEMIST**. The **FORMULATION_SCIENTIST** prepares the drug formulation in the **FORMULATION_SUITE** — this can fail, requiring a redo. After successful formulation, the **FORMULATION_SCIENTIST** sends the formulated compound to both the **BIOLOGIST** and the **TOXICOLOGIST**.

If the **PROJECT_DIRECTOR** orders a retry, the **FORMULATION_SCIENTIST** receives a new compound from the **CHEMIST** and repeats the formulation process. (For modeling purposes, at most one retry round occurs.)

### BIOLOGIST
The **BIOLOGIST** first prepares cell lines in the **CELL_LAB**. After receiving the formulated compound from the **FORMULATION_SCIENTIST**, the **BIOLOGIST** consumes one biological sample unit and runs the primary bioassay in the **CELL_LAB** — the assay can fail, requiring a redo (consuming another sample). The **BIOLOGIST** then verifies stability on the **HPLC** — this can also fail. The **BIOLOGIST** sends the bioactivity report to the **CLINICAL_LEAD**.

### TOXICOLOGIST
The **TOXICOLOGIST** begins by establishing baseline markers on the **MASS_SPEC**. After receiving the formulated compound from the **FORMULATION_SCIENTIST**, the **TOXICOLOGIST** consumes one biological sample unit and checks purity on the **HPLC**. The **TOXICOLOGIST** then runs a cytotoxicity assay in the **CELL_LAB** — the assay can fail, requiring a redo. The **TOXICOLOGIST** sends the toxicity report to the **CLINICAL_LEAD**.

### CLINICAL_LEAD
The **CLINICAL_LEAD** waits for both the bioactivity report from the **BIOLOGIST** and the toxicity report from the **TOXICOLOGIST** (in either order). The **CLINICAL_LEAD** then runs a comprehensive review using the **MASS_SPEC**. The **CLINICAL_LEAD** sends the combined clinical review to the **REGULATORY_SPECIALIST**.

If the **REGULATORY_SPECIALIST** issues a clinical hold, the **CLINICAL_LEAD** must wait for the hold to be lifted before proceeding.

### REGULATORY_SPECIALIST
The **REGULATORY_SPECIALIST** receives the clinical review from the **CLINICAL_LEAD**. The **REGULATORY_SPECIALIST** evaluates compliance — this can result in:
1. **Approval**: sends approval to the **PROJECT_DIRECTOR**
2. **Clinical hold**: the **REGULATORY_SPECIALIST** conducts an in-depth review using the **HPLC** and **MASS_SPEC**. After the review, the **REGULATORY_SPECIALIST** lifts the hold by sending a clearance to the **CLINICAL_LEAD**, then sends a conditional approval to the **PROJECT_DIRECTOR**.

### PROJECT_DIRECTOR
The **PROJECT_DIRECTOR** receives the regulatory decision. The **PROJECT_DIRECTOR** decides:
1. **Continue**: sends the final decision (approved) to the **CHEMIST** and is done
2. **Retry**: the **CHEMIST** must re-synthesize, the **FORMULATION_SCIENTIST** re-formulates, and bio/tox re-evaluate. The **PROJECT_DIRECTOR** sends retry signals to the **CHEMIST** and **FORMULATION_SCIENTIST**, then waits for a new regulatory decision
3. **Abort**: sends abort to the **CHEMIST** and is done

(For modeling purposes, at most one retry occurs.)

## Goal
All seven scientists complete their work: the **CHEMIST** archives the final profile, the **FORMULATION_SCIENTIST** delivers the formulation, the **BIOLOGIST** and **TOXICOLOGIST** deliver their reports, the **CLINICAL_LEAD** completes the review, the **REGULATORY_SPECIALIST** issues the compliance decision, and the **PROJECT_DIRECTOR** communicates the final outcome.
