# Development Task List - BYOD Synthetic Data Generator

## Phase 0: Local Development & Infrastructure as Code (IaC)
**Goal:** Create a fully functional local development environment and write automation scripts to define the cloud infrastructure.

### Task 0.1: Set up Local Environment
- [ ] 0.1.1: Initialize Git repository and define project structure
- [ ] 0.1.2: Create Python virtual environment and requirements.txt file  
- [ ] 0.1.3: Configure local development environment to use .env file for secrets
- [ ] 0.1.4: Set up local execution scripts (main.py using Flask or FastAPI)

### Task 0.2: Write Infrastructure as Code (IaC) Scripts
- [ ] 0.2.1: Choose an IaC tool (Terraform, Bicep)
- [ ] 0.2.2: Write scripts to define cloud resources (App Service, Function App, Cosmos DB)
- [ ] 0.2.3: Parameterize scripts for different environments (dev, prod)
- [ ] 0.2.4: Write scripts for security policies, networking, and managed identities

## Phase 1: The Metadata Engine (The "Autopsy" Script)
**Goal:** Build the core analysis Python script that can dissect various data file formats and produce a secure JSON metadata report.

### Task 1.0: Implement Format-Agnostic Data Loader
- [ ] 1.0.1: Develop logic to detect file type (CSV, JSON, etc.)
- [ ] 1.0.2: Create dispatcher to route files to correct pandas parser
- [ ] 1.0.3: Implement pd.json_normalize for flattening nested JSON
- [ ] 1.0.4: Ensure module returns standardized pandas DataFrame

### Task 1.1: Develop Metadata Extraction Module
- [ ] 1.1.1: Implement structural metadata extraction (column names, types)
- [ ] 1.1.2: Implement statistical properties (mean, std, min, max)
- [ ] 1.1.3: Implement string analysis (regex, categorical values)
- [ ] 1.1.4: Implement correlation matrix logic
- [ ] 1.1.5: Consolidate metadata into canonicalized JSON object

### Task 1.2: Integrate Metadata Engine into Local App
- [ ] 1.2.1: Modify main.py to call Metadata Engine and return metadata JSON

## Phase 2: LLM Integration & Dynamic Code Generation
**Goal:** Connect to the LLM, use metadata to generate Python script, and execute it to create synthetic file.

### Task 2.1: Develop Prompt Engineering & Code Execution
- [ ] 2.1.1: Create module to construct robust system prompt from metadata JSON
- [ ] 2.1.2: Implement Azure OpenAI Chat Completions API integration
- [ ] 2.1.3: Implement secure sandbox for executing LLM-returned Python code
- [ ] 2.1.4: Return generated synthetic file as final output

## Phase 3: Caching & Similarity Search (The "Smart" Layer)
**Goal:** Implement advanced caching strategy with sliding similarity scale.

### Task 3.1: Develop Hashing & Vectorization Module
- [ ] 3.1.1: Create "Format Hash" function (structural metadata)
- [ ] 3.1.2: Create "Full Hash" function (entire metadata JSON)
- [ ] 3.1.3: Create function to call embedding model for metadata vectorization

### Task 3.2: Implement Program Catalog & Search Logic
- [ ] 3.2.1: Create data access functions to store/retrieve scripts/vectors
- [ ] 3.2.2: Implement caching workflow based on match_threshold parameter
- [ ] 3.2.3: Store Anonymized Organizational Metadata alongside scripts

### Task 3.3: Implement Versioning
- [ ] 3.3.1: Add GENERATOR_VERSION constant to app settings
- [ ] 3.3.2: Append version to all hash keys and metadata in DB

## Phase 4: API & Frontend Development
**Goal:** Expose service through user-friendly webpage, REST API, and MCP tool call.

### Task 4.1: Finalize the Local REST API
- [ ] 4.1.1: Refine web framework endpoints to be production-ready
- [ ] 4.1.2: Implement request validation, error handling, status codes
- [ ] 4.1.3: Document API using OpenAPI/Swagger specs

### Task 4.2: Develop the Web Frontend
- [ ] 4.2.1: Build HTML/JS frontend communicating with local API
- [ ] 4.2.2: Create file upload control and "Match Strictness" slider
- [ ] 4.2.3: Implement Demo Mode with local sample files

### Task 4.3: Develop MCP Tool Definition
- [ ] 4.3.1: Create JSON or YAML definition for MCP tool call

## Phase 5: Testing & Quality Assurance
**Goal:** Ensure reliability and robustness through comprehensive local testing.

### Task 5.1: Implement Unit Tests
- [ ] 5.1.1: Write pytest tests for Data Loader module (Task 1.0)
- [ ] 5.1.2: Write pytest tests for Metadata Extraction module (Task 1.1)
- [ ] 5.1.3: Write pytest tests for Caching & Hashing module (Task 3.1)

### Task 5.2: Implement Integration Tests
- [ ] 5.2.1: Write end-to-end tests calling local API and validating returned files
- [ ] 5.2.2: Create tests for all match_threshold scenarios

## Phase 6: Cloud Deployment & Automation
**Goal:** Deploy fully developed and tested application to Azure using IaC scripts.

### Task 6.1: Deploy Azure Resources via IaC
- [ ] 6.1.1: Set up CI/CD pipeline to run IaC scripts
- [ ] 6.1.2: Execute scripts to provision all Azure resources

### Task 6.2: Deploy Application Code
- [ ] 6.2.1: Create build and release pipeline in Azure Pipelines
- [ ] 6.2.2: Configure pipeline to deploy code to Azure Function App/App Service

### Task 6.3: Final Cloud Integration Test
- [ ] 6.3.1: Run integration tests against live cloud endpoints

## Phase 7: Future-Proofing (Direct Synthesis Stub)
**Goal:** Create placeholders for future Direct Synthesis approach.

### Task 7.1: Stub API Endpoint & UI
- [ ] 7.1.1: Create placeholder endpoints for future direct synthesis functionality

## Progress Tracking

### Current Phase: Phase 0
### Completed Tasks: 0
### Total Tasks: 38