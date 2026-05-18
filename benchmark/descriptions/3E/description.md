# Task 3E: Two-Author Research Report

Two researchers are collaborating on a report. Each researcher is responsible for a different subtopic. An **EDITOR** reviews both sections and combines them into the final report.

## Agents

- **RESEARCHER_A**: investigates subtopic A, writes section A, and updates the shared reference database
- **RESEARCHER_B**: investigates subtopic B, writes section B, and updates the shared reference database
- **EDITOR**: reviews both sections for consistency; if inconsistencies are found, asks the relevant researcher to revise; once both sections pass review, combines them into the final report

## Shared Resources

- **DOCUMENT**: shared draft document — only one agent can write to it at a time
- **DATABASE**: shared reference database — only one agent can update it at a time

## Workflow

Each researcher first investigates their subtopic, then writes their section into the shared document and updates the reference database. Once a researcher's work is ready, they submit it to the **EDITOR**. The **EDITOR** reviews the submitted sections; if revisions are needed, the researcher revises and resubmits. Once all sections pass review, the **EDITOR** combines them into the final report.

## Goal

All agents complete their work (research, write, update references, review, combine) without conflicts over the shared document or reference database.
