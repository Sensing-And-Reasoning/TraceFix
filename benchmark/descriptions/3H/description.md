# Task 3H: Large Survey Paper Production

A team of seven is producing a comprehensive survey paper. Four researchers each cover a different subtopic, a **DATA_ANALYST** produces figures and tables, a **REVIEWER** provides academic peer review, and an **EDITOR_IN_CHIEF** makes final editorial decisions and assembles the complete paper.

## Agents

- **RESEARCHER_A**: investigates subtopic A, writes section A, updates the reference database, and coordinates with the **DATA_ANALYST** on figures
- **RESEARCHER_B**: investigates subtopic B, writes section B, updates the reference database, and coordinates with the **DATA_ANALYST** on figures
- **RESEARCHER_C**: investigates subtopic C, writes section C, updates the reference database, and coordinates with the **DATA_ANALYST** on figures
- **RESEARCHER_D**: investigates subtopic D, writes section D, updates the reference database, and coordinates with the **DATA_ANALYST** on figures
- **DATA_ANALYST**: creates figures, tables, and statistical analyses from researcher data; updates the figure repository; inserts figures into the appropriate section drafts
- **REVIEWER**: conducts peer review on each completed section; if major revisions are needed, the section returns to the researcher and must be re-reviewed after revision; forwards accepted sections to the **EDITOR_IN_CHIEF**
- **EDITOR_IN_CHIEF**: reviews cross-section consistency, resolves conflicts, makes final editorial decisions, and assembles the complete paper once all sections are accepted

## Shared Resources

- **SECTION_A**: section A draft — only one agent can write to it at a time
- **SECTION_B**: section B draft — only one agent can write to it at a time
- **SECTION_C**: section C draft — only one agent can write to it at a time
- **SECTION_D**: section D draft — only one agent can write to it at a time
- **FIGURE_REPOSITORY**: shared figure repository — only one agent can update it at a time
- **DATABASE**: shared reference database — only one agent can update it at a time

## Workflow

Each researcher investigates their subtopic, writes their section draft, and updates the shared reference database. Researchers also send their raw data to the **DATA_ANALYST**, who creates figures and inserts them into the relevant section drafts. Researchers may need figures from the **DATA_ANALYST** before their sections are complete, while the **DATA_ANALYST** needs researcher data before producing figures. Once a section is ready, it is submitted for peer review. The **REVIEWER** reviews each section independently; if major revisions are requested, the researcher revises and resubmits for re-review. Accepted sections go to the **EDITOR_IN_CHIEF**, who reviews cross-section consistency, resolves any conflicts, and assembles the final paper.

## Goal

All agents complete their work (research, write, update references, produce figures, peer review, editorial review, assemble) without conflicts over the section drafts, figure repository, or reference database.
