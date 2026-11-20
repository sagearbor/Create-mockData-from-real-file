As a user, I want to choose a stronger AI model when the default one gives poor results, so that difficult files still produce usable data.

# Acceptance criteria
1. The page shows a model choice with the server's default selected.
2. The list comes from the server and holds only models the server allows; the server refuses any other name with a clear 400 error.
3. The choice applies to the web page routes and to the JSON API.
4. Each model offered has been shown to work with one real call; a model that returns empty or cut-off answers is not offered.
5. Code written by one model is not served from the cache for a request that chose another model.
6. The response says which model was used.
7. Reasoning models keep an output budget of at least 40,000 tokens.
