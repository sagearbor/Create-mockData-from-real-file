Get the Mock Data Generator (BYOD Synthetic Data Generator) to its first production release, with the work, the tests and the release documents all on record.

# What the tool does
A person uploads a data file, a data dictionary, or both. The tool describes the data (column names, types, value ranges), asks an AI model to write a small program from that description, runs the program, and returns made-up data with the same shape. The uploaded rows themselves are never sent to the AI model.

# Scope of release 1.0
- Security review (two independent reviews) and fixes for what they find
- About page with ready-to-copy blocks so developers can call the tool from code
- A choice of AI model on the page, limited to models the server allows
- A full test of the site, recorded as test cases with results
- The SDLC release documents, in Confluence
- Deployment and a check of the deployed site

# Where things are
- Code: GitHub repository sagearbor/Create-mockData-from-real-file, branch release/1.0-sdlc
- Documents: Confluence space ADP, under Projects
- Tests: Zephyr (waiting for Zephyr to be switched on for this Jira project)

# Notes
- Work is being done with Claude Code on behalf of Sage Arbor. A person reviews and approves; nothing here is signed or approved by the AI.
- The only environment today is the development one. There is no production environment yet; standing one up is outside this epic unless added.
