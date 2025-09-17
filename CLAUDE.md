# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## IMPORTANT: Task Management Protocol

When working on this project, follow these rules:

1. **Check `developer_tasklist.md`** - This is the single source of truth for pending work
2. **Update task status** - Mark tasks as completed when done
3. **Move completed tasks** - Transfer finished items to `archived/developer_tasklist_ARCHIVED.md`
4. **Update documentation** - Keep README.md and architecture diagrams current
5. **Test your changes** - Run the application and verify functionality

### Task Workflow
```
1. Read developer_tasklist.md → Pick a HIGH PRIORITY task
2. Implement the solution → Test thoroughly
3. Update developer_tasklist.md → Mark as completed
4. Move to archived/developer_tasklist_ARCHIVED.md
5. Update README.md and docs/ if needed
```

## Project Overview

This is the BYOD (Bring Your Own Data) Synthetic Data Generation Service - a tool designed to generate synthetic/mock data that preserves the structure and statistical properties of real data while ensuring privacy. The service allows developers to work with realistic test data without PHI or sensitive information exposure.

## Key Architecture Components

- **Local-First Development**: Designed to run entirely on local machines during development
- **Secure by Design**: Uses metadata extraction approach - LLMs never see sensitive data directly
- **Intelligent Caching**: Leverages hashing and vector similarity search to reuse previously generated scripts
- **Multi-Interface**: Supports web UI, RESTful API, and MCP tool calls

## Azure Services Used

When deployed to cloud:
- **Azure App Service**: Hosts web UI
- **Azure Function App**: Main orchestration engine
- **Azure OpenAI**: Provides LLM and embedding models
- **Azure Blob Storage**: Temporary file staging
- **Azure Cosmos DB**: Stores Program Catalog
- **Azure AI Search**: Vector database capabilities
- **Azure Key Vault**: Secrets management

## Development Setup

1. **Environment Configuration**:
   - Copy `.env.example` to `.env`
   - For local development, minimally configure:
     - `AZURE_OPENAI_ENDPOINT`
     - `AZURE_OPENAI_API_KEY`
     - `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`
     - `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME`

2. **Python Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Run Locally**:
   ```bash
   python main.py
   ```

## Common Commands

```bash
# Setup virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run application locally
python main.py

# Run tests (when implemented)
pytest tests/

# Format code (when setup)
black .
isort .

# Lint code (when setup)
pylint src/
flake8 src/
```

## Project Structure

The project follows a modular architecture designed for both local development and cloud deployment:

- **Infrastructure as Code**: Cloud infrastructure defined in scripts for automated deployment
- **Format Agnostic**: Supports CSV and JSON initially, extensible to other formats
- **Statistical Preservation**: Maintains distributions and correlations from original data
- **Tunable Quality**: Adjustable strictness for statistical matching

## Key Implementation Notes

- The service never exposes raw sensitive data to LLMs - it works with statistical metadata
- Supports both file uploads and programmatic API access
- Implements caching to reduce costs and improve performance
- Designed for enterprise use with compliance and security in mind

## Development Workflow

1. Develop and test locally using minimal Azure services
2. Use Infrastructure as Code scripts for cloud deployment
3. Refer to Development_tasklist.rtf for detailed development plan and phases