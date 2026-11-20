Record of fixes already made and merged before this epic was opened (GitHub pull request 12), kept here so the release record is complete.

# What was fixed
1. A download of several files failed with "generated code failed in the sandbox". Cause: code written by the AI model was saved for reuse before it had been run, so a program that failed was reused.
2. Code is now saved only after it has run and produced the expected columns; saved code that fails is removed and replaced.
3. When code fails, the error is given back to the model with the retry (up to two corrections).
4. A saved program is reused only for the number of rows it was written for.
5. The preview shows up to 50 rows and says plainly whether all rows are shown.

# Evidence
Automated tests: 239 passed, 14 skipped (need a live server or browser).
