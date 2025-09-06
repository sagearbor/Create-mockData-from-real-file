# Create-mockData-from-real-file
Upload a real file, even something that has egphi, and have a similar mock file data created. You do not have to worry about privacy.

BYOD - Synthetic Data Generation Service
1. Overview
The "Bring Your Own Data" (BYOD) service is an enterprise tool designed to accelerate development and testing by providing high-quality, structurally identical, and statistically representative synthetic data. It allows developers, data scientists, and QA engineers to work with realistic data formats without the security risks or compliance delays associated with using production files containing Protected Health Information (PHI) or other sensitive data.
This service ingests a sample data file (e.g., CSV, JSON) and, without exposing the raw data to an LLM, generates a brand new file with the same schema and similar statistical properties but populated entirely with mock data.
2. The Problem
Development cycles are often blocked by the lack of safe, realistic test data. Using production PHI is a major compliance risk, and manually creating mock data is time-consuming, error-prone, and often fails to capture the statistical nuances of the real dataset. This bottleneck slows down feature development, integration testing, and bug fixing.
3. Core Features
Portable & Local-First: Designed to be developed and run entirely on a local machine, ensuring rapid development cycles without cloud dependencies or permission blockers.
Infrastructure as Code (IaC): The entire cloud infrastructure is defined in scripts (e.g., Terraform, Bicep) for automated, repeatable deployments to any cloud.
Format Agnostic: Accepts various file formats (starting with CSV and JSON) and generates synthetic data in the same format.
High-Fidelity Synthesis: Preserves not only column types and formats but also statistical distributions and inter-column correlations.
Tunable Match Strictness: Users can control the desired quality of the statistical match via a sliding scale.
Secure by Design (Metadata Approach): The core generation logic is architected to be secure. An internal script produces an anonymous statistical metadata report, ensuring the LLM never sees sensitive data.
Intelligent Caching: Uses hashing and vector similarity search to reuse previously generated scripts, drastically reducing cost and latency.
Multi-Interface Access: Accessible via a web UI, a RESTful API, and an MCP tool call.
4. High-Level Architecture (Azure)
Frontend: An Azure App Service hosts the web UI. An Azure API Management gateway could be used to manage API access.
Processing: An Azure Function App serves as the main orchestration engine.
Intelligence: An Azure OpenAI service provides the code-generating LLM and embedding models.
Data & Caching:
Azure Blob Storage for temporary file staging.
Azure Cosmos DB stores the "Program Catalog".
Azure AI Search provides vector database capabilities.
Security: Azure Key Vault stores all secrets, and Managed Identities are used for secure communication.
5. Getting Started (Local-First Workflow)
Clone the Repository: git clone ... from your Azure DevOps project.
Set up Local Environment: Create a Python virtual environment and install dependencies from requirements.txt.
Configure Secrets: Copy .env.example to .env and fill in the necessary API keys for local development (e.g., your Azure OpenAI key).
Run Locally: Launch the application using the local execution script (e.g., python main.py). You can now develop and test the entire application against http://localhost.
Deploy to Cloud: Once development and testing are complete, run the Infrastructure as Code scripts (Phase 0) and CI/CD pipelines (Phase 6) to deploy the application to Azure.
Refer to TASK_LIST.md for the detailed development plan.
