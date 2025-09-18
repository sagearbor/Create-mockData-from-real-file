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
- [ ] **6.1.1**: API documentation with examples
- [ ] **6.1.2**: Data dictionary format specification
- [ ] **6.1.3**: Deployment guide for Azure

### Task 6.2: Production Readiness
- [ ] **6.2.1**: Add rate limiting and quotas
- [ ] **6.2.2**: Implement file size limits and validation
- [ ] **6.2.3**: Add monitoring and alerting
- [ ] **6.2.4**: Security hardening and penetration testing

## Known Issues & Technical Debt

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