# Azure DevOps Secure Settings & Deployment Guide

## 🎯 Purpose
This guide documents the security fixes and deployment configuration for Azure DevOps pipelines, focusing on CORS security, environment-specific settings, and proper git workflows. This setup is designed to be **reusable across multiple repositories**.

## 📚 Table of Contents
1. [Security Issues Fixed](#security-issues-fixed)
2. [Understanding CORS Security](#understanding-cors-security)
3. [Environment Configuration](#environment-configuration)
4. [Azure Pipeline Setup](#azure-pipeline-setup)
5. [Git Workflow & Branch Strategy](#git-workflow--branch-strategy)
6. [How to Reuse This Setup](#how-to-reuse-this-setup)
7. [Security Checklist](#security-checklist)
8. [Troubleshooting](#troubleshooting)

---

## 🔒 Security Issues Fixed

### 1. **CORS Vulnerability (CRITICAL)**
**Before (INSECURE):**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 🚨 ALLOWS ANY WEBSITE TO ACCESS YOUR API
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**After (SECURE):**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),  # ✅ Only specified origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # ✅ Only minimal needed methods (no DELETE/PUT)
    allow_headers=["*"],
    max_age=3600,
)
```

**Note on HTTP Methods:**
- **GET**: For reading data and health checks
- **POST**: For file uploads and generating synthetic data (creates in-memory files/zips)
- **OPTIONS**: Required for CORS preflight requests
- **Removed PUT/DELETE**: Not needed for this app, reduces attack surface

### 2. **Pipeline Branch Mismatch**
- Fixed pipeline referencing `develop` instead of actual `dev` branch
- This was preventing deployments to the development environment

### 3. **Missing Environment-Specific Settings**
- Added environment-aware configuration
- Different CORS settings for local, dev, and production

---

## 🌐 Understanding CORS Security

### What is CORS?
**CORS (Cross-Origin Resource Sharing)** controls which websites can access your API.

### The Risk
When you set `allow_origins=["*"]`:
- **ANY website** on the internet can call your API
- Malicious sites can steal data or perform unauthorized actions
- Users' browsers will send cookies/credentials to your API from any site

### Real-World Attack Example
```javascript
// Evil website (evil-site.com) can do this:
fetch('https://your-api.azurewebsites.net/api/sensitive-data', {
    credentials: 'include',  // Sends user's cookies
    method: 'POST',
    body: JSON.stringify({ malicious: 'data' })
})
.then(response => response.json())
.then(stolen_data => {
    // Send stolen data to attacker
    sendToAttacker(stolen_data);
});
```

### The Fix
Only allow specific, trusted domains:
- **Local Development**: `http://localhost:3000`, `http://localhost:8201`
- **Development Environment**: `https://your-app-dev.azurewebsites.net`
- **Production**: `https://your-app.azurewebsites.net`, `https://yourdomain.com`

---

## ⚙️ Environment Configuration

### 1. Environment Variables Structure

#### `.env.example` (Template for all environments)
```bash
# ENVIRONMENT CONFIGURATION
ENVIRONMENT="local"  # Options: local, development, production

# CORS SECURITY SETTINGS
# For local development
ALLOWED_ORIGINS="http://localhost:8201,http://localhost:3000,http://127.0.0.1:8201"

# For development deployment
# ALLOWED_ORIGINS="https://byod-synthetic-data-service-dev.azurewebsites.net"

# For production deployment
# ALLOWED_ORIGINS="https://byod-synthetic-data-service.azurewebsites.net,https://yourdomain.com"

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT="https://your-aoai-resource.openai.azure.com/"
AZURE_OPENAI_API_KEY="your-api-key"
# ... other settings
```

### 2. Configuration in Code (`src/utils/config.py`)
```python
class Settings(BaseSettings):
    # Environment setting
    environment: str = Field(default="local", env="ENVIRONMENT")

    # CORS settings with secure defaults
    allowed_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:8201"],
        env="ALLOWED_ORIGINS"
    )

    def get_allowed_origins(self) -> List[str]:
        """Parse comma-separated origins from environment variable."""
        origins_str = os.getenv("ALLOWED_ORIGINS", "")
        if origins_str:
            return [origin.strip() for origin in origins_str.split(",")]

        # Default based on environment
        if self.environment == "production":
            return ["https://your-app.azurewebsites.net"]
        elif self.environment == "development":
            return ["https://your-app-dev.azurewebsites.net"]
        else:  # local
            return ["http://localhost:8201", "http://localhost:3000"]
```

### 3. Setting Environment Variables in Azure

#### In Azure App Service:
1. Go to your App Service in Azure Portal
2. Navigate to **Configuration** > **Application settings**
3. Add these settings:

| Name | Value (Development) | Value (Production) |
|------|-------------------|-------------------|
| `ENVIRONMENT` | `development` | `production` |
| `ALLOWED_ORIGINS` | `https://your-app-dev.azurewebsites.net` | `https://your-app.azurewebsites.net,https://yourdomain.com` |
| `AZURE_OPENAI_ENDPOINT` | `https://your-dev-openai.openai.azure.com/` | `https://your-prod-openai.openai.azure.com/` |
| `AZURE_OPENAI_API_KEY` | `[dev-api-key]` | `[prod-api-key]` |

---

## 🚀 Azure Pipeline Setup

### Pipeline File Structure (`azure-pipelines.yml`)

The pipeline has three key stages:

```yaml
stages:
  - stage: Build       # Builds Docker image, runs tests
  - stage: DeployDev   # Deploys to development (triggered by dev branch)
  - stage: DeployProd  # Deploys to production (triggered by main branch)
```

### Key Fixes Applied:

1. **Branch Detection Fix in IT's Pipeline (`pipelines/azure-pipelines.yml`):**
```yaml
# BEFORE (WRONG):
condition: and(succeeded(), or(..., eq(variables['Build.SourceBranch'], 'refs/heads/prod')))

# AFTER (CORRECT):
condition: and(succeeded(), or(..., eq(variables['Build.SourceBranch'], 'refs/heads/main')))
```

**Note:** We're using IT's parameterized pipeline which is better for reusability across projects.

2. **Environment-Specific Deployment:**
```yaml
- stage: DeployDev
  condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/dev'))
  jobs:
    - deployment: DeployToDev
      environment: 'development'  # Uses Azure DevOps environment

- stage: DeployProd
  condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
  jobs:
    - deployment: DeployToProd
      environment: 'production'  # Requires approval
```

### Pipeline Configuration (Using IT's Template):

The pipeline (`pipelines/azure-pipelines.yml`) uses IT's parameterized approach which:
- Automatically detects environment based on branch (dev→val→main)
- Uses a single Deploy stage with conditions
- Is easily reusable across projects
- Only requires updating the container registry service connection

---

## 🌳 Git Workflow & Branch Strategy

### Branch Structure
```
main (production)
  └── dev (development)
       └── feature/your-feature (feature branches)
```

### Workflow Steps

#### 1. **Daily Development Workflow**
```bash
# Start your day - get latest changes
git checkout dev
git pull origin dev

# Create a feature branch for your work
git checkout -b feature/my-new-feature

# Make your changes
# ... edit files ...

# Check what you changed
git status
git diff

# Stage and commit your changes
git add .
git commit -m "Add new feature for data processing"

# Push your feature branch
git push origin feature/my-new-feature
```

#### 2. **Creating a Pull Request**
1. Go to Azure DevOps Repos
2. Click "Create a pull request"
3. Source: `feature/my-new-feature`
4. Target: `dev`
5. Add description of changes
6. Request reviewers
7. Complete PR after approval

#### 3. **Deploying to Development**
```bash
# After PR is merged to dev
git checkout dev
git pull origin dev

# This automatically triggers the pipeline to deploy to dev environment
```

#### 4. **Deploying to Production**
```bash
# Create PR from dev to main
# After approval and merge, production deployment triggers automatically
```

### Important Git Commands for Beginners

```bash
# Check which branch you're on
git branch

# See status of your changes
git status

# See what changed
git diff

# Undo uncommitted changes
git checkout -- filename

# See commit history
git log --oneline -10

# Pull latest changes
git pull origin dev

# Push your changes
git push origin dev
```

---

## 🔄 How to Reuse This Setup

### For a New Repository:

#### Step 1: Copy Core Files
```bash
# From this repo, copy these files to your new repo:
cp .env.example /path/to/new-repo/
cp pipelines/azure-pipelines.yml /path/to/new-repo/pipelines/  # IT's template
cp docs/UNIVERSAL_CORS_SECURITY_TEMPLATE.md /path/to/new-repo/docs/
cp DEVELOPMENT_WORKFLOW.md /path/to/new-repo/

# For Python projects, also copy:
cp src/utils/config.py /path/to/new-repo/src/utils/
```

#### Step 2: Update CORS in Your Main Application

**See `/docs/UNIVERSAL_CORS_SECURITY_TEMPLATE.md` for code snippets in:**
- Python (FastAPI, Flask)
- Node.js (Express)
- C# (ASP.NET Core)
- Java (Spring Boot)
- Go (Gin)
- Ruby (Rails)
- PHP (Laravel)

Example for Python FastAPI:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # Minimal methods
    allow_headers=["*"],
)
```

#### Step 3: Configure Azure DevOps
1. Import repository to Azure DevOps
2. Create service connection to Azure
3. Set up pipeline variables
4. Create environments (development, production)
5. Set branch policies on main branch

#### Step 4: Update App-Specific Settings
```yaml
# In azure-pipelines.yml, update:
variables:
  azureContainerRegistry: 'your-registry.azurecr.io'
  imageName: 'your-app-name'
  webAppName: 'your-app-service-name'
```

### Quick Setup Script
Save this as `setup-secure-deployment.sh`:
```bash
#!/bin/bash
# Quick setup script for new repos

# Create necessary directories
mkdir -p docs
mkdir -p src/utils

# Create .env from template
cp .env.example .env

# Set up git branches
git checkout -b dev
git push -u origin dev

# Create initial commit
git add .
git commit -m "Initial secure setup with CORS protection"
git push origin dev

echo "✅ Secure setup complete!"
echo "Next steps:"
echo "1. Update .env with your Azure credentials"
echo "2. Configure Azure DevOps pipeline"
echo "3. Set branch policies in Azure DevOps"
```

---

## ✅ Security Checklist

Before each deployment, verify:

### Local Development
- [ ] `.env` file exists and is NOT committed to git
- [ ] `ENVIRONMENT=local` in .env
- [ ] `ALLOWED_ORIGINS` includes only localhost

### Development Deployment
- [ ] All changes committed to `dev` branch
- [ ] Pipeline runs successfully
- [ ] `ENVIRONMENT=development` set in Azure
- [ ] `ALLOWED_ORIGINS` set to dev URL only

### Production Deployment
- [ ] Code reviewed via Pull Request
- [ ] All tests passing
- [ ] `ENVIRONMENT=production` set in Azure
- [ ] `ALLOWED_ORIGINS` includes only production domains
- [ ] No sensitive data in logs

### CORS Security Check
```python
# Test script to verify CORS settings
import requests

# This should FAIL in production
response = requests.get(
    'https://your-api.azurewebsites.net/health',
    headers={'Origin': 'https://evil-site.com'}
)
print(f"Evil site access: {'BLOCKED' if response.status_code == 403 else 'ALLOWED - FIX THIS!'}")
```

---

## 🔧 Troubleshooting

### Common Issues and Solutions

#### 1. **Pipeline Not Triggering**
**Problem**: Push to dev branch doesn't trigger deployment

**Solution**:
```yaml
# Check azure-pipelines.yml has correct trigger:
trigger:
  branches:
    include:
      - main
      - dev  # Must match your branch name exactly
```

#### 2. **CORS Errors in Browser**
**Problem**: "Access to fetch at 'api-url' from origin 'website' has been blocked by CORS policy"

**Solution**:
1. Check Azure App Service configuration for `ALLOWED_ORIGINS`
2. Ensure your website URL is in the allowed list
3. Restart the App Service

#### 3. **401 Unauthorized Errors**
**Problem**: API returns 401 errors

**Solution**:
1. Check `AZURE_OPENAI_API_KEY` is set correctly
2. Verify service principal has correct permissions
3. Check Key Vault access policies if using Key Vault

#### 4. **Docker Build Fails**
**Problem**: Pipeline fails at Docker build step

**Solution**:
```bash
# Test locally first:
docker build -t test-image .
docker run -p 8201:8201 test-image

# Check for missing files in .dockerignore
```

#### 5. **Environment Variables Not Loading**
**Problem**: App doesn't read environment variables

**Solution**:
```python
# Debug in your app:
import os
print(f"Environment: {os.getenv('ENVIRONMENT', 'not set')}")
print(f"Allowed Origins: {os.getenv('ALLOWED_ORIGINS', 'not set')}")
```

### Getting Help

1. **Check Logs**:
   - Azure Portal > App Service > Log Stream
   - Azure DevOps > Pipelines > [Your Pipeline] > Runs

2. **Validate Configuration**:
   ```bash
   # In Azure Cloud Shell:
   az webapp config appsettings list --name your-app-name --resource-group your-rg
   ```

3. **Test Endpoints**:
   ```bash
   # Health check
   curl https://your-app.azurewebsites.net/health

   # With CORS headers
   curl -H "Origin: https://your-allowed-domain.com" \
        -I https://your-app.azurewebsites.net/health
   ```

---

## 📝 Summary

This secure setup provides:
1. **Protection against CORS attacks** by restricting origins
2. **Environment-specific configurations** for safe deployments
3. **Proper git workflow** with branch protection
4. **Reusable templates** for future projects
5. **Clear documentation** for team members

Remember: **Security is not optional** - it protects your data, your users, and your organization's reputation.

---

*Last Updated: 2025-09-21*
*Version: 1.0*
*Author: BYOD Development Team*