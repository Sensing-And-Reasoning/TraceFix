# Pharmaceutical Lab with QC Review

Four scientists collaborate on synthesizing and testing a new pharmaceutical compound. They share three expensive instruments that only one scientist can use at a time. A QC controller verifies all results and can reject work, requiring re-analysis.

## Agents
- **CHEMIST**: synthesizes and purifies the compound
- **BIOLOGIST**: tests biological activity of the compound
- **ANALYST**: runs quality analytics
- **QC_CONTROLLER**: verifies each result and can reject, requiring the scientist to redo work

## Shared Resources
- **SPECTROMETER**: molecular analysis instrument (one scientist at a time)
- **CENTRIFUGE**: separation/purification instrument (one scientist at a time)
- **FUME_HOOD**: chemical synthesis and reaction environment (one scientist at a time)

## Workflow

### CHEMIST
1. Use the **FUME_HOOD** to synthesize the compound
2. Use the **SPECTROMETER** to analyze the synthesized compound
3. Use the **CENTRIFUGE** to purify the compound
4. Send the purified compound sample to the **BIOLOGIST** for testing
5. Send the purification data to the **QC_CONTROLLER** for verification
6. Wait for the **QC_CONTROLLER**'s verification result — if rejected, redo the **SPECTROMETER** analysis and resend data to **QC_CONTROLLER**
7. Once approved, wait for the quality report from the **ANALYST**
8. Use the **SPECTROMETER** for final compound validation
9. Done

### BIOLOGIST
1. Use the **CENTRIFUGE** to prepare cell cultures
2. Use the **SPECTROMETER** to calibrate fluorescence measurements
3. Receive the compound sample from the **CHEMIST**
4. Run bioassay — test compound on cell cultures (no instrument needed)
5. Send test results to the **ANALYST**
6. Send bioassay data to the **QC_CONTROLLER** for verification
7. Wait for the **QC_CONTROLLER**'s verification result — if rejected, redo the bioassay and resend data to **QC_CONTROLLER**
8. Once approved, done

### ANALYST
1. Receive test results from the **BIOLOGIST**
2. Use the **SPECTROMETER** for detailed molecular analysis
3. Use the **CENTRIFUGE** for additional separation verification
4. Send the quality report to the **CHEMIST**
5. Done

### QC_CONTROLLER
The **QC_CONTROLLER** receives verification requests from the **CHEMIST** and the **BIOLOGIST** in whatever order they arrive. For each request:
1. Use the **FUME_HOOD** to inspect the sample environment conditions
2. Use the **SPECTROMETER** to run a verification analysis
3. Send a verification result (approve or reject) back to the requesting scientist

The **QC_CONTROLLER** is done after verifying both the **CHEMIST**'s and the **BIOLOGIST**'s work (each may require multiple rounds if rejected).

## Goal
All four scientists complete their work: the **CHEMIST** validates the compound, the **BIOLOGIST** completes the approved bioassay, the **ANALYST** delivers the quality report, and the **QC_CONTROLLER** has approved all results.
