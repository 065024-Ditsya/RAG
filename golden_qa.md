# Golden Q&A Set — Newcomer Onboarding Questions
### Meridian Health Systems | RAG Evaluation Set

Purpose: simulate the questions a brand-new employee would actually ask in their first
few weeks, before they know who to contact for what. Use these to test whether the RAG
app retrieves the correct department's document and gives a grounded answer. Run each
question through the finished app, record the actual answer next to the expected one,
and note any retrieval misses in the "Result" column.

Legend for Result column: ✅ Correct | ⚠️ Partial | ❌ Missed/Hallucinated

---

## HR

| # | Question | Expected source | Result |
|---|---|---|---|
| 1 | How many paid leave days do I get in a year? | Employee Handbook — Leave Policy | |
| 2 | Can I work from home a few days a week? | Employee Handbook — Remote Work | |
| 3 | What happens if I'm late to work repeatedly? | Employee Handbook — Discipline | |
| 4 | Is there a dress code I need to follow? | Employee Handbook | |
| 5 | Can I accept a gift from a vendor? | Code of Conduct — Gifts | |
| 6 | What counts as a conflict of interest? | Code of Conduct | |
| 7 | Who do I report unethical behavior to? | Code of Conduct — Anti-bribery | |
| 8 | What's the process if I want to resign? | Employee Handbook | |
| 9 | Do I get any notice period if I'm let go? | Employee Handbook — Discipline | |
| 10 | Can I take unpaid leave if I run out of paid days? | Employee Handbook — Leave Policy | |

## Finance

| # | Question | Expected source | Result |
|---|---|---|---|
| 1 | How do I get reimbursed for a client dinner? | Expense Reimbursement Policy | |
| 2 | What's the per-day allowance when I travel for work? | Travel Policy | |
| 3 | Do I need pre-approval before booking a flight? | Travel Policy | |
| 4 | What receipts do I need to submit for expenses? | Expense Reimbursement Policy | |
| 5 | What was our EBITDA margin last quarter? | Finance KPI Dashboard | |
| 6 | How is the company's revenue trending this year? | Finance KPI Dashboard | |
| 7 | What's our current market share? | Finance KPI Dashboard | |
| 8 | How long does expense reimbursement usually take? | Expense Reimbursement Policy | |
| 9 | Can I book a hotel above the standard rate if there's a reason? | Travel Policy | |
| 10 | What's the company's earnings per share this year? | Finance KPI Dashboard | |

## Legal

| # | Question | Expected source | Result |
|---|---|---|---|
| 1 | Can I share an NDA with a subcontractor before they sign it? | NDA Template | |
| 2 | What happens if I accidentally leak confidential info? | NDA Template / Compliance Guidelines | |
| 3 | How long does a mutual NDA stay valid for? | NDA Template | |
| 4 | What's our policy on handling customer personal data? | Compliance Guidelines | |
| 5 | Do we need to follow DPDPA regulations? | Compliance Guidelines | |
| 6 | What's the timeline for reporting a data breach? | Compliance Guidelines | |
| 7 | Can I use a client's data for an internal case study? | Compliance Guidelines | |
| 8 | Who is the point of contact for legal questions? | Compliance Guidelines | |
| 9 | What should I do if a client asks me to sign something outside standard templates? | NDA Template | |
| 10 | Is there a standard confidentiality clause I should use in vendor contracts? | NDA Template | |

## IT

| # | Question | Expected source | Result |
|---|---|---|---|
| 1 | How often do I need to change my password? | IT Security & Password Policy | |
| 2 | What laptop model will I be issued as a new hire? | IT Asset Inventory | |
| 3 | Can I use my personal phone to check work email? | IT Security & Password Policy | |
| 4 | What do I do if I lose my company laptop? | IT Security & Password Policy | |
| 5 | Is two-factor authentication mandatory? | IT Security & Password Policy | |
| 6 | How do I request a new monitor or keyboard? | IT Asset Inventory | |
| 7 | What's the minimum password length required? | IT Security & Password Policy | |
| 8 | Who do I contact for a forgotten VPN password? | IT Security & Password Policy | |
| 9 | What software am I allowed to install on my work laptop? | IT Security & Password Policy | |
| 10 | How long are IT assets typically used before replacement? | IT Asset Inventory | |

## Customer Service

| # | Question | Expected source | Result |
|---|---|---|---|
| 1 | How do I reschedule a patient's appointment? | Customer Support FAQ | |
| 2 | What's our refund policy for cancelled services? | Customer Support FAQ | |
| 3 | How should I handle a formal patient complaint? | Customer Support FAQ | |
| 4 | What are our response time targets for phone support? | Customer Support FAQ | |
| 5 | Can a family member access a patient's billing info? | Customer Support FAQ | |
| 6 | How do I escalate a complaint the customer isn't satisfied with? | Customer Support FAQ | |
| 7 | What payment methods can patients use? | Customer Support FAQ | |
| 8 | How long do refunds take to process? | Customer Support FAQ | |
| 9 | What's the process if a patient's portal login isn't working? | Customer Support FAQ | |
| 10 | How long do we retain patient records? | Customer Support FAQ | |

---

## Cross-Department / Ambiguous Questions
These deliberately test whether department routing works when a question could plausibly
belong to more than one department.

| # | Question | Expected source(s) | Result |
|---|---|---|---|
| 1 | What's our data retention policy? | Legal (compliance) *and* Customer Service (records) | |
| 2 | Who approves my travel expenses? | Finance (travel policy) *and* HR (manager approval chain) | |
| 3 | What happens if I lose a device with client data on it? | IT (device loss) *and* Legal (data breach) | |

## Out-of-Scope Questions
These have **no answer in any document** — used to confirm the system says
"information not available" instead of guessing.

| # | Question | Expected behavior |
|---|---|---|
| 1 | What's the CEO's direct phone number? | Should decline / say not available |
| 2 | What's the company's stock ticker symbol? | Should decline / say not available |
| 3 | Can I get a loan advance from the company? | Should decline / say not available |

---

**How to use this file:** as you run each question through the finished app, fill in the
Result column and jot down the actual answer given (even briefly) so your report can show
concrete accuracy numbers — e.g. "38/40 questions answered correctly, 2 partial, 0 hallucinated."
