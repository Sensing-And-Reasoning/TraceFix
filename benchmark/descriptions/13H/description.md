# Pharmaceutical Lab with Cascading QC and Safety

Five scientists collaborate on synthesizing and testing a new pharmaceutical compound. They share four expensive instruments (each only one scientist can use at a time) and a limited reagent supply. A QC controller verifies all results (rejections cascade), and a safety officer periodically inspects all instruments.

## Agents
- **CHEMIST**: synthesizes compounds using reagents (each synthesis consumes one reagent unit)
- **BIOLOGIST**: tests biological activity of the compound
- **ANALYST**: runs quality analytics using the **CHROMATOGRAPH**
- **QC_CONTROLLER**: verifies each result; rejection of **BIOLOGIST**'s work cascades back to **CHEMIST** for re-synthesis
- **SAFETY_OFFICER**: performs a full safety inspection that requires occupying all instruments simultaneously for the duration of the inspection

## Shared Resources
- **SPECTROMETER**: molecular analysis instrument
- **CENTRIFUGE**: separation/purification instrument
- **FUME_HOOD**: chemical synthesis and reaction environment
- **CHROMATOGRAPH**: compound separation and identification instrument

## Shared Resource Pool
- **REAGENT_SUPPLY**: 3 units available — each synthesis by the **CHEMIST** consumes one unit. If reagents are exhausted, no more syntheses can occur.

## Workflow

### CHEMIST
1. Consume one reagent unit and use the **FUME_HOOD** to synthesize the compound
2. Use the **SPECTROMETER** to analyze the synthesized compound
3. Use the **CENTRIFUGE** to purify the compound
4. Send the purified compound to the **BIOLOGIST**
5. Wait for the **QC_CONTROLLER**'s final approval or a re-synthesis request
6. If re-synthesis is requested: consume another reagent unit, re-synthesize in the **FUME_HOOD**, re-analyze on the **SPECTROMETER**, re-purify on the **CENTRIFUGE**, and resend to the **BIOLOGIST**
7. Once approved, use the **SPECTROMETER** for final compound validation
8. Done

### BIOLOGIST
1. Use the **CENTRIFUGE** to prepare cell cultures
2. Use the **SPECTROMETER** to calibrate fluorescence measurements
3. Receive the compound from the **CHEMIST**
4. Run bioassay (no instrument needed)
5. Send test results to the **ANALYST**
6. Send bioassay data to the **QC_CONTROLLER**
7. Wait for QC verification — if rejected, the **BIOLOGIST** requests a new compound from the **CHEMIST** (cascading re-synthesis) and repeats from step 3
8. Once approved, done

### ANALYST
1. Receive test results from the **BIOLOGIST**
2. Use the **CHROMATOGRAPH** for compound separation analysis
3. Use the **SPECTROMETER** for detailed molecular analysis
4. Use the **CENTRIFUGE** for additional separation verification
5. Send the quality report to the **CHEMIST**
6. Done

### QC_CONTROLLER
The **QC_CONTROLLER** receives verification requests from the **BIOLOGIST**. For each request:
1. Use the **FUME_HOOD** to inspect sample environment conditions
2. Use the **SPECTROMETER** to run verification analysis
3. Send verification result to the **BIOLOGIST** (approve or reject)

If rejected, the cascading re-synthesis eventually produces a new bioassay submission.

The **QC_CONTROLLER** is done after a final approval.

### SAFETY_OFFICER
The **SAFETY_OFFICER** performs a safety inspection during the protocol:
1. Occupy all four instruments (**SPECTROMETER**, **CENTRIFUGE**, **FUME_HOOD**, **CHROMATOGRAPH**) simultaneously for the duration of the inspection
2. Perform the safety inspection
3. Return all four instruments when the inspection is complete
4. Done

## Goal
All five scientists complete their work: the **CHEMIST** validates the final compound, the **BIOLOGIST** has an approved bioassay, the **ANALYST** delivers the quality report, the **QC_CONTROLLER** has given final approval, and the **SAFETY_OFFICER** has completed the inspection.
