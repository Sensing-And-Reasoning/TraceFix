# Task 5M: Multi-Specialty Case Conference

A patient presents with complex, multi-system symptoms: chest pain, persistent headache, and limb numbness. The emergency room doctor determines that multiple specialists need to collaborate to reach a diagnosis.

## Agents

- **ER_DOCTOR**: performs initial assessment, coordinates the overall diagnostic process, makes referrals
- **CARDIOLOGIST**: evaluates cardiac-related symptoms and tests
- **NEUROLOGIST**: evaluates neurological symptoms and tests
- **RADIOLOGIST**: operates imaging equipment (CT, MRI), interprets imaging results for all specialists
- **PHARMACIST**: reviews all prescriptions across specialists before administration

## Shared Resources

- **MRI**: the hospital's MRI machine (only one patient can be scanned at a time)
- **CT_SCANNER**: the hospital's CT scanner (only one patient can be scanned at a time)
- **CONSULTATION_ROOM**: the dedicated case conference room (only one conference at a time)

## Communication Channels

- Referral channel (**ER_DOCTOR** -> Specialists)
- Imaging request channel (Specialists -> **RADIOLOGIST**)
- Findings sharing channel (bidirectional among all doctors)
- Prescription review channel (Specialists -> **PHARMACIST**, **PHARMACIST** -> Specialists)
- Case conference channel (all doctors -- for scheduling and conducting conferences)

## Workflow

### ER_DOCTOR
1. Performs initial patient assessment (vitals, basic labs)
2. Orders basic diagnostic tests
3. Makes referrals to **CARDIOLOGIST** and **NEUROLOGIST** via referral channel
4. Coordinates overall diagnostic process
5. If specialists disagree, schedules case conference in the **CONSULTATION_ROOM**
6. Sends prescriptions to **PHARMACIST** for review

### CARDIOLOGIST
1. Receives referral from **ER_DOCTOR**
2. Orders cardiac-specific tests (ECG, cardiac enzymes)
3. Requests imaging from **RADIOLOGIST** via imaging request channel
4. Evaluates cardiac-specific findings
5. Makes preliminary cardiac diagnosis
6. Shares findings with other doctors
7. Participates in case conference if needed
8. Sends prescriptions to **PHARMACIST** for review

### NEUROLOGIST
1. Receives referral from **ER_DOCTOR**
2. Orders neurological tests (neuro exam, nerve conduction)
3. Requests imaging from **RADIOLOGIST** via imaging request channel
4. Evaluates neurological findings
5. Makes preliminary neurological diagnosis
6. Shares findings with other doctors
7. Participates in case conference if needed
8. Sends prescriptions to **PHARMACIST** for review

### RADIOLOGIST
1. Receives imaging requests from specialists
2. Performs CT imaging using the **CT_SCANNER**
3. Performs MRI imaging using the **MRI**
4. Interprets imaging results
5. Shares imaging findings with requesting specialists

### PHARMACIST
1. Receives prescription review requests from all specialists
2. Reviews all prescribed medications for interactions across specialists
3. Approves or flags medication issues
4. Returns review results to prescribing doctors

## Constraints

- The MRI machine can only scan one patient at a time.
- The CT scanner can only scan one patient at a time.
- Each specialist can only directly observe test results from their own domain. Cross-domain findings must be explicitly shared.
- The **RADIOLOGIST** is a shared resource -- all imaging requests go through them, creating a potential bottleneck.
- If two specialists reach different preliminary diagnoses, a formal case conference must be held (requires the **CONSULTATION_ROOM**) to resolve the disagreement.
- All medication prescriptions from any specialist must pass through **PHARMACIST** review before administration.

## Properties (verified by TLC)

- Safety: **MRI** never double-booked. **CT_SCANNER** never used by more than one patient simultaneously. **CONSULTATION_ROOM** never used by more than one conference at a time.
- Liveness: All agents eventually terminate (consensus reached, treatment plan established).
