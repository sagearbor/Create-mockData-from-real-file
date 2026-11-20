As a developer, I want the About page to show blocks I can copy and paste so that I can call the tool from my own code without reading the source.

# Acceptance criteria
1. The About page has a section "Use it from code" with at least: a curl example, a Python example, and a JavaScript example for generating data from a JSON request.
2. Each block has a Copy button that puts the exact text on the clipboard.
3. The examples use the address of the site the page is being viewed on, so they work as pasted on any deployment.
4. The examples show how to send the API key header when the server requires one, and never contain a real key.
5. The page lists the request fields, the limits and the error shape, and links to the interactive API reference.
6. A pasted curl example, run unchanged against the deployed site, returns generated rows.
