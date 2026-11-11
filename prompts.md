# Coding Agent Prompts Log

**Platform used:** Claude (via chat interface), used alongside VS Code for execution and testing.
All commands were run manually in the VS Code integrated terminal / WSL Ubuntu terminal based on
the assistant's guidance; the assistant also generated the ingestion scripts, query engine logic,
and Streamlit app code shown in this project, including the later reranking and agentic
calculation additions.

---

## Project setup and environment
1. "give steps to complete this project" (initial scoping)
2. "forget the beginner friendly part, ive used everything qdrant/postgres/supabase etc and we have to do what professor want"
3. "so ubuntu is already installed in our system... i want to tell you how professor want codes in vs code to look in our project"
4. "lets just begin the project, one step at a time and after successfully executing this step we will move further"
5. Requests to create a private, non-shared project folder (`~/rag_project`) separate from the shared course folder, with permissions locked to a single user account.

## Document preparation
6. "Generate sample documents for me" (for a fictional healthcare organization, Meridian Health Systems)
7. "so how can we improve? ... want to make the project look like it should be answering to each and every question that a user will be asking"
8. "Give me a support Faq to be uploaded in customer service"
9. Requests to review uploaded documents against a "golden Q&A" evaluation set and identify content gaps (e.g., dress code, resignation policy, new-hire laptop assignment).

## Parsing
10. Guidance requested on installing Docling in the correct virtual environment and troubleshooting a stray `.venv` created by VS Code.
11. "we have to do this project likewise [notebook style]... give me the codes line by line what needs to be run where"
12. Confirmation and troubleshooting of the parsing notebook converting all department PDFs/DOCX/XLSX files into Markdown.

## Embeddings, vector store, and RAG pipeline
13. "what embedding models are we using?"
14. Guidance on building a LlamaIndex + Ollama + Chroma ingestion pipeline (`ingestion/ingest.py`), including department metadata tagging.
15. Debugging a retrieval completeness issue where a multi-row leave-policy table was only partially retrieved; diagnosed as a chunking issue and fixed by switching from the default `SentenceSplitter` to `MarkdownNodeParser`.
16. Requested a comparative analysis between Chroma and Qdrant vector stores (ingestion time and query latency) to satisfy the assignment's requirement to justify the vector store choice.

## Testing (early)
17. Built a 43-question "golden Q&A" evaluation set covering all five departments, cross-department queries, and out-of-scope queries.
18. Ran and evaluated sample questions against the deployed app, including a leave-policy question, a cross-department device-loss question, and an out-of-scope CEO-contact question.

## Web interface and dashboard
19. Requested a mobile-friendly Streamlit Q&A interface with department filtering, source citations, and response-time display.
20. "It should answer questions of all profit loss and everything going forward. All the finance terms. So I want it should have everything in details answering everything like whether to invest or not as well. It should cover everything" \u2014 led to building a 22-term Finance glossary document and adding an investment-advice guardrail to the system prompt.
21. Requested real usage data (query log, feedback log, response-time metrics) to replace hardcoded sample data on the Analytics dashboard tab.
22. "Sir wants ki our model should be able to answer each and every questions vry precisely and nicely" \u2014 discussed adding a reranker, improving system-prompt formatting instructions, and increasing retrieval depth.

## Finance department overhaul
23. Provided a real, cross-verified 5-year financial workbook for a real healthcare company (P&L, Balance Sheet, and Cash Flow/Ratios across three sheets), later converted by the student to a single `.docx` and renamed to fit the project's naming convention.
24. "Also keep the IT department handbook in the IT and remove all other documents except the xl file. also remove all the HR documents from the file and only keep the HR document" \u2014 cleaned HR and IT folders down to one document each.
25. Added real annual-report PDFs (100+ pages each) for a second real company to the Finance folder, replacing the old synthetic KPI dashboard spreadsheet.
26. "Now Meridian Health System this should come as the name" \u2014 discussed the tradeoff between renaming a file containing real third-party company data versus rewriting its actual content, and kept the filename convention-matching while flagging the content-attribution question.

## Model selection
27. "what should be done? use granite or have to use some more powerful engines?" \u2014 discussed local model limitations (small parameter count, weak tool-calling) versus the assignment's explicit requirement to use an Ollama Cloud model.
28. Pulled and switched the primary LLM from local `granite4.1:3b` to `gpt-oss:20b-cloud` (Ollama Cloud), satisfying the assignment's cloud-model requirement and improving reasoning/calculation quality.

## Retrieval precision debugging
29. Ran a graduated, company-agnostic set of finance calculation test questions (simple lookup through investment-advice guardrail) to evaluate answer quality after the model switch.
30. Debugged a stale-vector-store issue: newly added/edited Finance documents were not reflected in answers until `parsed/` and `chroma_db/` were explicitly cleared and rebuilt.
31. Diagnosed a specific retrieval failure ("What is the current EBITDA margin?" returning "not available" despite a confirmed intact source table) as a retrieval-volume imbalance \u2014 a 7-chunk reference document competing against 400\u2013600+ chunk real annual reports in the same department.
32. Implemented a `SentenceTransformerRerank` cross-encoder reranker and widened initial retrieval from top_k=10 to top_k=40, to keep small high-value documents from being crowded out of the candidate pool.
33. Debugged an `IndentationError` introduced while manually editing the query-engine block in `app.py`.

## Agentic RAG: calculation and statistics support
34. "I want it should be able to do any statistical functions or any of the most difficult calculations or anything in between" \u2014 discussed why plain-text-generation RAG is unreliable for arithmetic and proposed an agentic architecture with a real calculation tool.
35. Built a four-way intent router (`classify_intent`) splitting questions into CALCULATION (pure arithmetic), DERIVED (a metric requiring lookup + calculation, e.g. growth rate or ROCE), DATA (spreadsheet aggregation), and DOCUMENT (plain lookup), each handled by a dedicated code path.
36. Implemented a restricted, sandboxed AST-based arithmetic evaluator (no `eval()`, no attribute/function-call access) for the CALCULATION and DERIVED paths, and a `PandasQueryEngine` (via `llama-index-experimental`) for the DATA path, so numeric answers come from real computation rather than LLM-estimated text generation.
37. Added a second, system-prompt-free "utility" LLM handle for the narrow routing and figure-extraction prompts, to keep the main assistant's persona/guardrails from interfering with those steps.

## Final packaging
38. "So this is the final app file that is running... pls read through all these, Give me the report, prompts file and code files" \u2014 requested a full review of the final running application against the existing report and assignment requirements, and an updated report, prompts log, and code bundle reflecting the final architecture (cloud model, reranker, agentic calculation routing).

---

*(This file reflects all prompts used with the coding agent through final submission packaging. If any
further changes are made after this point, add them here before the final zip is created.)*
