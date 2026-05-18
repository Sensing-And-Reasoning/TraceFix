# Task 7H: Large Collaborative Document with Cross-Dependencies

Three writers are co-authoring a **DOCUMENT** with four chapters grouped into two parts: Part I (chapters 1--2: introduction and background) and Part II (chapter 3: core contribution, chapter 4: evaluation). A **FIGURE_CREATOR** handles visual content, a **FACT_CHECKER** verifies claims, a **REVIEWER** provides quality assessment, and an **EDITOR_IN_CHIEF** coordinates the entire process.

## Agents

### WRITER_A
Writes Part I (chapter 1: introduction, chapter 2: background).

### WRITER_B
Writes chapter 3 (core contribution).

### WRITER_C
Writes chapter 4 (evaluation and discussion).

### FIGURE_CREATOR
Produces figures, charts, and tables; inserts them into appropriate chapters.

### FACT_CHECKER
Verifies factual claims and data consistency across chapters.

### REVIEWER
Provides quality review on completed chapters, may request major or minor revisions.

### EDITOR_IN_CHIEF
Coordinates review assignments, resolves cross-chapter conflicts, makes final editorial decisions.

## Shared Resources

- **DOCUMENT**: shared document for collaborative writing
- **FIGURE_STORE**: shared figure repository

## Workflow

1. **WRITER_A** writes Part I; **WRITER_B** writes chapter 3; **WRITER_C** writes chapter 4 concurrently.
2. Chapter 3 references evaluation data from chapter 4 (**WRITER_B** depends on **WRITER_C**'s results). **WRITER_B** must wait for **WRITER_C** to publish stable results before finalizing chapter 3's references.
3. Part I (chapters 1--2) must frame the contribution described in chapters 3 and 4. **WRITER_A** waits for stable drafts from **WRITER_B** and **WRITER_C** before finalizing Part I.
4. **FIGURE_CREATOR** creates figures and inserts them into multiple chapters. Writers may still be editing when figures need to be inserted.
5. **FACT_CHECKER** verifies that data cited in one chapter matches data presented in another.
6. **REVIEWER** can only review complete chapters. Major revisions require re-review; minor revisions do not.
7. **EDITOR_IN_CHIEF** makes final editorial decisions (terminology changes, structural adjustments). Affected writers must update their chapters accordingly.
8. **EDITOR_IN_CHIEF** combines the final sections into the completed **DOCUMENT**.

## Goal

All writers complete their chapters, figures are inserted, facts are verified, chapters pass review, editorial decisions are finalized, and the complete document is assembled.
