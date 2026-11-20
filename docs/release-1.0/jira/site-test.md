Test the whole site before release, and keep the tests and their results on record.

# Acceptance criteria
1. Automated tests cover every route the site offers and every user path on the page: upload a file, upload a dictionary, preview, download one file, download several files as a zip, the About page, the JSON API, errors.
2. A browser test runs the main paths against the deployed site.
3. Each test is described in plain words (objective, precondition, steps, expected result) and recorded in Zephyr with a result, linked to the story it checks.
4. Failures are raised as Jira issues, fixed, and re-run until the run is clean.
5. Results are counted honestly: tests that did not run are shown as not run.
