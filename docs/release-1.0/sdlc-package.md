# Mock Data Generator 1.0: SDLC document package

> **Correction, 20 Nov 2026.** The seven pages listed below were started from the DS-S-001
> template family by mistake. This tool falls under TS-S-001 v2.0 (to be confirmed by the
> Quality Manager). The TS-S-001 drafts are under the Confluence page "DRAFT Mock Data Generator
> 1.0 - TS-S-001 SDLC Package" (page id 6259474575); their page ids are in `tracking.json` under
> the `ts-*` entries. The DS-S-001 drafts below are kept unchanged for reference only.


Index of the release documents in Confluence (space ADP). Jira: ADP-45, epic ADP-40.
The URL paths below follow the address of the organisation's Confluence site, which is not written here because this repository is public.

All seven pages are **Draft**: prepared by Claude Code for Sage Arbor on 20 Nov 2026, not reviewed, not
approved, nothing released. Signature and approval blocks are empty. The preliminary risk level (Medium: Impact Low, Complexity High; release request ADP-92) and the solution
type (Integrations) are assumptions for the Release Advisory Board (RAB) to confirm.

Until the open security items are closed and a person signs off, the tool must not be used with real study
data or patient identifiers. It is suitable for made-up or already de-identified sample files.

| Page | Title | URL path | Page id | Status | Still PENDING or TBD | Who supplies it |
| --- | --- | --- | --- | --- | --- | --- |
| Parent | DRAFT Mock Data Generator 1.0 - SDLC Documentation Parent Page | `/wiki/spaces/ADP/pages/6259540055` | 6259540055 | Draft | Nothing of its own; lists the six pages below | - |
| VP | DRAFT Mock Data Generator 1.0_VP | `/wiki/spaces/ADP/pages/6258524277` | 6258524277 | Draft | Risk level and solution type; EPM code; D1 plan id; Jira fix version; stakeholder titles and names; Zephyr cycle key | RAB; Release Manager; test run (ADP-44) |
| RS | DRAFT Mock Data Generator 1.0_RS | `/wiki/spaces/ADP/pages/6260064372` | 6260064372 | Draft | Verification of all 56 requirements (MDG-REQ-001 to MDG-REQ-056); model choice (ADP-43); privacy fix (ADP-58); retention periods; EPM code; D1 plan id | Developers and test run (ADP-41 to ADP-44); Release Manager |
| CRUT | DRAFT Mock Data Generator 1.0_CRUT | `/wiki/spaces/ADP/pages/6259146872` | 6259146872 | Draft | Final commit; final test counts; pass or fail; human reviewer; completion date; approval method; signer names | Test run on the final commit; a human reviewer; Development Manager |
| IQC | DRAFT Mock Data Generator 1.0_IQC | `/wiki/spaces/ADP/pages/6258589767` | 6258589767 | Draft | Every execution result; implementer; Release to Val task number | Deployment to the development environment (ADP-46) |
| PQ | DRAFT Mock Data Generator 1.0_PQ | `/wiki/spaces/ADP/pages/6258393290` | 6258393290 | Draft | Execution of test case 001; evidence; tester; overall status | Tester, after deployment (ADP-46) |
| VRRAF | DRAFT Mock Data Generator 1.0_VRRAF | `/wiki/spaces/ADP/pages/6260031544` | 6260031544 | Draft | All test results; closure of the open issues (ADP-56 to ADP-68, including ADP-56 isolation of the code runner and ADP-60 sign-in); release decision; all signatures | Test run; developers; IT (ADP-60); RAB |

## Notes

- The pages are copies of the current DS-S-001 templates, filled in place. Tables, checkboxes and signature
  blocks are as copied.
- The answers used for each page are kept outside git in `docs/release-1.0/private.local/sdlc/`, with the scripts
  that apply them, so a fill can be repeated.
- The environment is development only (VPN only). There is no production environment, so the production
  installation check cannot be done.
- Baseline before the release work: 239 automated tests passed and 14 were skipped on main at commit
  4c0930c. Final counts are PENDING.
- The requirement numbers MDG-REQ-001 to MDG-REQ-056 are defined in section 1.4 of the RS page.
