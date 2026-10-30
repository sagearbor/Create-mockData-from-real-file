# Developer Task List - BYOD Synthetic Data Generator

> **Note**: Completed tasks are moved to `archived/developer_tasklist_ARCHIVED.md`

## Current Status
- **Current Phase**: Phase 2 (LLM Integration) - 80% Complete
- **Total Completed Tasks**: 15 (see archived list)
- **Active Tasks**: Focus on production readiness

## HIGH PRIORITY - Immediate Fixes Needed ✅ COMPLETED

### Data Type Detection Improvements

- [x] **FIX.2**: Implement domain-aware column detection ✅
  - ✅ Fallback code now detects date columns by name keywords
  - ✅ Maps columns with 'date', 'time', 'created', 'updated' to datetime type
  - ✅ Generates proper date formats instead of random text

### Clinical Data Dictionary Feature

- [x] **CLINICAL.2**: Implement data dictionary upload feature ✅
  - ✅ Created comprehensive DataDictionary class
  - ✅ Accepts JSON, YAML, CSV, Excel, and text formats
  - ✅ Auto-detects format and parses constraints
  - ✅ Validates uploaded data against dictionary rules
  - ✅ Generates mock data respecting dictionary constraints
  - ✅ Web UI section for dictionary upload/management
  - **No PHI risk**: Dictionary validation happens locally without data exposure

## Phase 2: LLM Integration & Dynamic Code Generation ⏳ 80% COMPLETE

### Task 2.1: Enhance LLM Integration
- [x] Basic Azure OpenAI integration ✅
- [x] **2.1.1**: ~~Improve prompt engineering for better column understanding~~ ✅
  - ✅ Column name semantics included in metadata
  - ✅ Clinical context passed to LLM
- [x] **2.1.2**: ~~Implement column-type suggestion system~~ ✅
  - ✅ Clinical reference library detects medical columns
  - ✅ Suggested values provided in metadata
- [x] **2.1.3**: ~~Add semantic data generation~~ ✅
  - ✅ Contextually appropriate values for medical data
  - ✅ Reference data libraries integrated

## Phase 3: Caching & Similarity Search ⏳ PLANNED

### Task 3.1: Smart Caching System
- [ ] **3.1.1**: Implement metadata-based caching
  - Hash metadata structure for cache keys
  - Store generation scripts with metadata signatures
  - Reuse scripts for similar data structures

### Task 3.2: Similarity Detection
- [ ] **3.2.1**: Add vector similarity search
  - Embed metadata using Azure OpenAI
  - Find similar previously processed files
  - Suggest generation parameters based on history

## Phase 4: Enhanced UI/UX Features ⏳ ACTIVE

### Task 4.1: Web Interface Improvements
- [x] Basic file upload and generation
- [x] Multi-file generation with count selector
- [x] About page with architecture diagram
- [ ] **4.1.1**: Add data dictionary upload interface
- [ ] **4.1.2**: Show detected vs actual column types with override option
- [ ] **4.1.3**: Add preview of first few generated rows before download
- [ ] **4.1.4**: Progress indicator for multi-file generation

### Task 4.2: API Enhancements
- [ ] **4.2.1**: Add endpoint for data dictionary validation
- [ ] **4.2.2**: Return detailed generation metadata in response
- [ ] **4.2.3**: Support batch processing with progress webhooks

## Phase 5: Testing & Quality Assurance ⏳ HIGH PRIORITY

### Task 5.1: Core Functionality Tests
- [ ] **5.1.1**: Test date detection with various formats
- [ ] **5.1.2**: Test multi-file ZIP generation (edge cases: 1, 20, errors)
- [ ] **5.1.3**: Test clinical data type detection

### Task 5.2: Integration Testing
- [ ] **5.2.1**: End-to-end test with medical data samples
- [ ] **5.2.2**: Test data dictionary validation flow
- [ ] **5.2.3**: Performance test with large files (>100MB)

## Phase 6: Documentation & Deployment

### Task 6.1: Documentation
- [x] Basic architecture documentation
- [x] **6.1.0**: Multi-interface transport layer (MCP + A2A) ✅ DONE
  - Added `src/core/generation_service.py` — single shared core for all transports
  - Added `src/mcp_server.py` — MCP stdio server (`python -m src.mcp_server`); tools:
    `generate_synthetic_data` and `extract_metadata`
  - Added `src/a2a_agent.py` — A2A agent (`MockDataAgent`, `build_card`, `register`)
    implementing `a2a_runtime.RunnableAgent`
  - Mounted A2A routes on FastAPI (`/.well-known/agent.json`, `POST /a2a/{agent_id}`),
    registered agent in lifespan, added `a2a_backend` to `/health`
  - `a2a_runtime/` ships a pure-stdlib shim; automatically uses `dcri-a2a-core`
    when installed
  - Tests: `tests/test_a2a_runtime.py` (stdlib-only), `tests/test_a2a_agent.py`,
    `tests/test_mcp_server.py`
  - Added `mcp>=0.4.0` to `requirements.txt`
  - Created `docs/INTEGRATION.md` and updated `README.md` with calling guide
- [ ] **6.1.1**: API documentation with examples
- [ ] **6.1.2**: Data dictionary format specification
- [ ] **6.1.3**: Deployment guide for Azure

### Task 6.2: Production Readiness
- [ ] **6.2.1**: Add rate limiting and quotas
- [ ] **6.2.2**: Implement file size limits and validation
- [ ] **6.2.3**: Add monitoring and alerting
- [ ] **6.2.4**: Security hardening and penetration testing
- [x] **SEC.1**: Fix code injection in the fallback generator ✅
  - ✅ Column names / cell values / detected formats are emitted as `repr()`
    literals (`py_literal()`), never interpolated as raw source
  - ✅ Generated helper variables are named by column index, so a column name
    can no longer become a Python identifier
  - ✅ Comments sanitized (`safe_comment()`) so a newline in a header cannot
    end the comment and start a statement
  - ✅ Exec subprocess now runs with a minimal environment, so generated code
    cannot read `AZURE_OPENAI_API_KEY` or cloud metadata tokens
  - ✅ `Dockerfile.api` runs as non-root `appuser` (matches `./Dockerfile`)
  - Regression tests: `tests/test_synthetic_generator_injection.py`,
    `tests/test_synthetic_generator_sandbox.py`

- [x] **COMPAT.1**: Make the suite green on pandas 2.x and 3.x ✅
  - ✅ `src/utils/pandas_compat.py` — `is_text_dtype()` / `is_categorical()` /
    `text_columns()` give identical answers on pandas 2 and 3. pandas 3 moved
    text columns to the `str` dtype, so every `is_object_dtype()` guard had
    silently stopped firing (date detection and pattern extraction were dead)
  - ✅ Dropped `infer_datetime_format=` (no-op since pandas 2.0, removed in 3.0)
  - ✅ Boolean columns cast to int before numeric stats — `quantile()` on a bool
    Series raises "numpy boolean subtract" on **both** version sets
  - ✅ Guarded divide-by-zero in categorical association for all-null columns
  - ✅ Clinical detection ordering: `medication_name` / `lab_test_name` /
    `diagnosis_name` / `procedure_name` resolved to *people's names* because the
    generic `name` keyword was checked before every clinical keyword
  - ✅ `is_clinical` now only true for genuinely clinical columns; other
    reference matches (names, cities, states) use `reference_context`
  - ✅ `CacheManager` writes the empty index on init, as its docstring claimed
  - ✅ Test fixtures flushed before yielding (three fixtures yielded from inside
    `open()`, so the loader read an empty file)
  - ✅ Server-dependent tests marked `requires_server` and skipped with a clear
    reason instead of failing (`tests/conftest.py`); playwright test skips when
    the package is absent
  - ✅ Pins widened to `pandas>=2.1.4,<4` / `numpy>=1.26.2,<3` so installs work
    on modern Python. **The deployed image now resolves to pandas 3.x.**
  - Regression tests: `tests/test_pandas_compat.py`

- [x] **LLM.1**: Keyless Azure OpenAI auth + per-call telemetry (dcri_llm) ✅
  - ✅ Vendored `src/dcri_llm.py` (v1.0.0, unmodified); one client builder
    `src/core/llm_client.py` used by the web app and the MCP/A2A service layer
  - ✅ Default auth is managed identity (`LLM_AUTH=identity`); API key only via
    `LLM_AUTH=key`. No endpoint or a failed call -> template fallback, and the
    reason is returned in `generation_info["llm_error"]`
  - ✅ `max_completion_tokens=40000` (was `max_tokens=4000`); `finish_reason=length`
    or empty output is treated as a failure, not success
  - ✅ PHI: usage logs no longer store column names; loader/dictionary/sandbox logs
    report counts instead of column names, sheet names or stderr text
  - [ ] **Open question (Sage):** the prompt still sends real `most_common_values`
    for categorical columns to the LLM — decide whether that is acceptable
  - Regression tests: `tests/test_dcri_llm_integration.py`

## Known Issues & Technical Debt

### Version Support

The suite must stay green on both ends of the supported range. Verify before
release:

```bash
pytest                                   # your local venv
docker run --rm -v "$PWD":/app -w /app python:3.11-slim bash -c \
  'pip install -q pandas==2.1.4 numpy==1.26.2 pydantic-settings python-dotenv \
     pytest pytest-asyncio requests fastapi "uvicorn[standard]" httpx \
     python-multipart aiofiles openai && pytest -q'
```

Prefer the helpers in `src/utils/pandas_compat.py` over `is_object_dtype()` and
`select_dtypes(include=['object'])`; on pandas 3 those quietly stop matching
ordinary text columns rather than raising.

### Security Notes
- **Public deployment**: `deploy/cloudrun.sh` intentionally deploys with
  `--allow-unauthenticated`. Anything reachable there is reachable by anyone,
  so the exec path must stay injection-free — see SEC.1 and its tests.
- **Generated code is still executed**: the LLM and cache paths produce Python
  that is run in a subprocess. The subprocess has a scrubbed environment and a
  30s timeout, but no CPU/memory/network sandbox. Untrusted *cache contents*
  would still be a code-execution vector.

### Current Bugs
1. **Date Detection**: Standard date formats (YYYY-MM-DD) not properly detected
2. **Domain Knowledge**: No semantic understanding of column names
3. **Memory Usage**: Large files may cause memory issues (no streaming)

### Technical Improvements Needed
1. **Streaming Processing**: Handle large files without loading entirely into memory
2. **Async Processing**: Multi-file generation should be truly parallel
3. **Error Recovery**: Better error handling and user feedback
4. **Logging**: Comprehensive logging for debugging and audit

## Developer Notes

### Quick Fixes for Common Issues
- **Date not detected**: Check `src/core/metadata_extractor.py` → `_infer_column_type()`
- **Multi-file not zipping**: Check `main.py` → `generate_synthetic_data()` file_count logic
- **LLM not using domain knowledge**: Enhance prompt in `src/core/synthetic_generator.py`

### Environment Variables Required
```bash
AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
AZURE_OPENAI_API_KEY="your-key"
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME="gpt-4"
```

### Testing Commands
```bash
# Full suite. Tests needing a live API server skip themselves cleanly;
# start the server first to run them too.
pytest

# Security regression tests for the code-generation path (must always pass)
pytest tests/test_synthetic_generator_injection.py \
       tests/test_synthetic_generator_sandbox.py

# pandas/numpy portability
pytest tests/test_pandas_compat.py

# Run local server
python main.py

# Test multi-file generation
curl -X POST http://localhost:8201/generate \
  -F "file=@test.csv" \
  -F "file_count=3" \
  -F "output_format=csv"
```

## Next Sprint Priorities (Recommended Order)
1. **FIX.1**: Fix date detection issue
2. **CLINICAL.1**: Implement clinical reference library
3. **2.1.2**: Add column-type suggestion system
4. **5.1.1-5.1.3**: Add comprehensive tests
5. **CLINICAL.2**: Data dictionary upload feature

---
**Last Updated**: September 2025
**Active Developer**: AI Assistant
**Project Phase**: MVP Enhancement