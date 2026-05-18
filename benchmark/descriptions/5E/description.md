# Task 5E: Dual-Specialist Consultation

A patient arrives at the emergency room with chest pain. The ER doctor needs to determine whether the cause is cardiac or pulmonary, potentially requiring a cardiology consultation and CT imaging.

## Agents

- **ER_DOCTOR**: performs initial assessment, orders basic tests, coordinates overall patient care
- **CARDIOLOGIST**: evaluates cardiac-specific findings, may order specialized cardiac tests
- **PHARMACIST**: reviews all prescribed medications for interactions and contraindications

## Shared Resources

- **CT_SCANNER**: the hospital's CT scanner (only one patient can be scanned at a time)

## Communication Channels

- Referral channel (**ER_DOCTOR** -> **CARDIOLOGIST**)
- Test results channel (bidirectional findings sharing between doctors)
- Prescription review channel (Doctors -> **PHARMACIST**, **PHARMACIST** -> Doctors)

## Workflow

### ER_DOCTOR
1. Performs initial patient assessment (vitals, basic labs)
2. Orders basic diagnostic tests
3. Determines whether cause is cardiac or pulmonary
4. If cardiac: refers patient to **CARDIOLOGIST** via referral channel
5. Orders CT imaging using the **CT_SCANNER**
6. Shares findings with **CARDIOLOGIST**
7. Sends prescriptions to **PHARMACIST** for review

### CARDIOLOGIST
1. Receives referral from **ER_DOCTOR**
2. Orders specialized cardiac tests (ECG, cardiac enzymes)
3. Evaluates cardiac-specific findings
4. Makes cardiac diagnosis
5. Shares findings with **ER_DOCTOR**
6. Sends prescriptions to **PHARMACIST** for review

### PHARMACIST
1. Receives prescription review requests from doctors
2. Reviews all prescribed medications for interactions and contraindications
3. Approves or flags medication issues
4. Returns review results to prescribing doctors

## Constraints

- The CT scanner can only serve one patient at a time (shared hospital resource).
- Each specialist can only see test results from their own domain -- the **ER_DOCTOR** sees general vitals and basic labs, the **CARDIOLOGIST** sees cardiac-specific results (ECG, cardiac enzymes). Findings must be explicitly shared.
- Any medication prescription must be reviewed by the **PHARMACIST** before administration.

## Properties (verified by TLC)

- Safety: **CT_SCANNER** never used by more than one patient simultaneously.
- Liveness: All agents eventually terminate (diagnosis reached, treatment plan established).
