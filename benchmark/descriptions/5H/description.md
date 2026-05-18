# Task 5H: Multi-Patient Emergency Triage

Two critical patients arrive at the emergency department in quick succession. Patient A is a trauma victim who likely needs surgery. Patient B is a stroke patient who needs urgent imaging and ICU admission. The medical team must manage both patients simultaneously with limited shared resources.

## Agents

- **ER_DOCTOR_A**: leads care for Patient A (trauma)
- **ER_DOCTOR_B**: leads care for Patient B (stroke)
- **SURGEON**: performs surgical procedures; uses the **OPERATING_ROOM** for each surgery
- **ANESTHESIOLOGIST**: prepares anesthesia before surgery and monitors during; coordinates with **SURGEON** via channels
- **RADIOLOGIST**: operates imaging equipment (CT, MRI) and interprets results
- **ICU_COORDINATOR**: manages ICU bed allocation (limited to 2 beds) and ICU-level monitoring
- **PHARMACIST**: manages medication orders for all patients, checks for interactions

## Shared Resources

- **OPERATING_ROOM**: the hospital's operating room (only one surgery at a time)
- **CT_SCANNER**: the hospital's CT scanner (only one patient can be scanned at a time)
- **MRI**: the hospital's MRI machine (only one patient can be scanned at a time)
- **ICU_BEDS**: the hospital's ICU capacity (initial=2, shared across all patients)
- **VENTILATOR**: the hospital's ventilator (only one patient at a time)

## Communication Channels

- Triage alert channel (**ER_DOCTOR_A**/**ER_DOCTOR_B** -> all, priority announcements)
- Surgical request channel (**ER_DOCTOR_A**/**ER_DOCTOR_B** -> **SURGEON**, requesting surgery)
- Anesthesia ready channel (**ANESTHESIOLOGIST** -> **SURGEON**, confirming readiness before surgery)
- ICU admission channel (**ER_DOCTOR_A**/**ER_DOCTOR_B** -> **ICU_COORDINATOR**)
- Imaging queue channel (**ER_DOCTOR_A**/**ER_DOCTOR_B** -> **RADIOLOGIST**)
- Drug order channel (all Doctors -> **PHARMACIST**, **PHARMACIST** -> Doctors)
- Status update channel (all agents -> **ER_DOCTOR_A**/**ER_DOCTOR_B**, patient condition updates)

## Workflow

### ER_DOCTOR_A
1. Assesses trauma patient (Patient A)
2. Orders trauma panel, blood type, coagulation tests
3. Requests imaging from **RADIOLOGIST** via imaging queue channel
4. Decides treatment plan (surgery vs conservative)
5. If surgery needed: sends surgical request to **SURGEON**
6. Sends drug orders to **PHARMACIST** for review
7. Receives status updates from other agents

### ER_DOCTOR_B
1. Assesses stroke patient (Patient B)
2. Orders stroke panel, CT angiography
3. Requests imaging from **RADIOLOGIST** via imaging queue channel
4. Decides imaging type and ICU admission needs
5. Sends ICU admission request to **ICU_COORDINATOR**
6. Sends drug orders to **PHARMACIST** for review
7. Receives status updates from other agents

### SURGEON
1. Receives surgical request from **ER_DOCTOR_A**
2. Waits for anesthesia readiness confirmation from **ANESTHESIOLOGIST**
3. Uses the **OPERATING_ROOM** to perform surgery on Patient A
4. Sends status update to **ER_DOCTOR_A**

### ANESTHESIOLOGIST
1. Prepares anesthesia for Patient A
2. Confirms readiness to **SURGEON** via anesthesia ready channel
3. Monitors patient during surgery

### RADIOLOGIST
1. Receives imaging requests from ER doctors
2. Performs CT imaging using the **CT_SCANNER** for Patient A
3. Performs CT and MRI imaging using the **CT_SCANNER** and **MRI** for Patient B
4. Interprets imaging results
5. Sends imaging findings back to requesting doctors

### ICU_COORDINATOR
1. Receives ICU admission requests from ER doctors
2. Manages ICU bed allocation (decrements **ICU_BEDS** counter)
3. Monitors ICU patients
4. Discharges patients when stable (increments **ICU_BEDS** counter)

### PHARMACIST
1. Receives drug order review requests from all doctors
2. Reviews medications for interactions across both patients
3. Approves or flags medication issues
4. Returns review results to prescribing doctors

## Constraints

- The operating room can only serve one patient at a time. Before surgery can begin, the **ANESTHESIOLOGIST** must confirm readiness via the anesthesia ready channel.
- The CT scanner and MRI can each only serve one patient at a time.
- There are only 2 ICU beds available (**ICU_BEDS** counter with initial=2). Admission decrements the counter; discharge increments it. If the counter reaches 0, no more admissions until a bed is freed.
- There is only one ventilator. If both patients need mechanical ventilation, only one can use the **VENTILATOR** at a time.
- Each patient's medication prescriptions must pass through **PHARMACIST** review before administration.
- When both patients need the same equipment simultaneously, only one can proceed at a time.

## Properties (verified by TLC)

- Safety: **OPERATING_ROOM** never used for more than one surgery at a time. **CT_SCANNER** never used by more than one patient simultaneously. **MRI** never used by more than one patient simultaneously. **VENTILATOR** never used by more than one patient at a time. **ICU_BEDS** counter never goes negative.
- Liveness: All agents eventually terminate (both patients treated, all procedures completed). ICU beds freed before agents finish.
