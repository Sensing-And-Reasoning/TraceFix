# Task 3M: Multi-Author Paper with Fact Checking

Three researchers are writing a paper, each responsible for a different section. A **FACT_CHECKER** verifies factual claims before sections proceed to the **EDITOR**, who ensures overall consistency and finalizes the paper.

## Agents

- **RESEARCHER_A**: investigates subtopic A, writes section A, and updates the shared reference database
- **RESEARCHER_B**: investigates subtopic B, writes section B, and updates the shared reference database
- **RESEARCHER_C**: investigates subtopic C, writes section C, and updates the shared reference database
- **FACT_CHECKER**: verifies factual claims in submitted sections; if a claim cannot be verified, the researcher must revise and resubmit
- **EDITOR**: reviews fact-checked sections for cross-section consistency and quality; if revisions are needed, the relevant researcher revises and resubmits; once all sections pass review, combines them into the final paper

## Shared Resources

- **DOCUMENT**: shared draft document — only one agent can write to it at a time
- **DATABASE**: shared reference database — only one agent can update it at a time

## Workflow

Each researcher investigates their subtopic, then writes their section into the shared document and updates the reference database. Sections are then submitted for fact checking. The **FACT_CHECKER** works on sections as they arrive and does not wait for all sections before starting. Once a section passes fact checking, it goes to the **EDITOR** for review. If revisions are needed at any stage, the researcher revises and resubmits. Once all sections pass both fact checking and editorial review, the **EDITOR** combines them into the final paper.

## Goal

All agents complete their work (research, write, update references, fact check, review, combine) without conflicts over the shared document or reference database.
