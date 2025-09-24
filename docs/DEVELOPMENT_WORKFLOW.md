# Development Workflow Guide for Azure DevOps

## Quick Start for Developers

This guide explains our git workflow, branching strategy, and how to safely develop and deploy code using Azure DevOps.

## 🌳 Branch Strategy

```
main
  └── dev
       └── feature/your-feature-name
```

- **`main`**: Production branch (protected, PR only)
- **`dev`**: Development branch (active development)
- **`feature/*`**: Feature branches (individual work)

## 📋 Development Workflow

### 1. Starting Your Day

```bash
# Always start by getting the latest code
git checkout dev
git pull origin dev

# Check you're up to date
git status
```

### 2. Working on a New Feature

```bash
# Create a feature branch from dev
git checkout -b feature/add-user-authentication

# Make your changes
code .  # Open VS Code or your editor

# Check what files you've changed
git status

# See the actual changes
git diff

# Stage all changes
git add .

# Or stage specific files
git add src/main.py src/config.py

# Commit with a clear message
git commit -m "feat: Add user authentication with Azure AD"

# Push your feature branch
git push origin feature/add-user-authentication
```

### 3. Creating a Pull Request

1. Go to Azure DevOps > Repos > Pull Requests
2. Click "New Pull Request"
3. Select: `feature/add-user-authentication` → `dev`
4. Fill in:
   - Title: Clear description of changes
   - Description: What, why, and how
   - Reviewers: Add team members
   - Work Items: Link related tasks
5. Click "Create"

### 4. After PR Approval

```bash
# Once merged, clean up locally
git checkout dev
git pull origin dev
git branch -d feature/add-user-authentication
```

## 🚀 Deployment Process

### To Development Environment

1. Merge PR to `dev` branch
2. Pipeline automatically:
   - Builds Docker image
   - Runs tests
   - Deploys to dev environment
3. Verify at: `https://your-app-dev.azurewebsites.net`

### To Production Environment

1. Create PR: `dev` → `main`
2. Get approval from senior developer
3. Merge PR
4. Pipeline automatically deploys to production
5. Verify at: `https://your-app.azurewebsites.net`

## 📝 Commit Message Standards

Use conventional commits for clear history:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation only
- `style:` Formatting, no code change
- `refactor:` Code restructuring
- `test:` Adding tests
- `chore:` Maintenance

Examples:
```bash
git commit -m "feat: Add CSV export functionality"
git commit -m "fix: Resolve CORS issue in production"
git commit -m "docs: Update API documentation"
git commit -m "refactor: Simplify data processing logic"
```

## ⚠️ Common Scenarios

### Scenario 1: Made changes to wrong branch

```bash
# If you accidentally made changes to main or dev directly
git stash                          # Save your changes
git checkout -b feature/my-feature # Create feature branch
git stash pop                      # Apply your changes
```

### Scenario 2: Need to update feature branch with latest dev

```bash
git checkout dev
git pull origin dev
git checkout feature/my-feature
git merge dev  # or git rebase dev for cleaner history
```

### Scenario 3: Undo last commit (not pushed)

```bash
git reset HEAD~1  # Undo commit, keep changes
# or
git reset --hard HEAD~1  # Undo commit and changes (careful!)
```

### Scenario 4: Fix commit message

```bash
git commit --amend -m "New correct message"
```

## 🔒 Security Checklist Before Push

- [ ] No hardcoded passwords or API keys
- [ ] No sensitive data in comments
- [ ] CORS settings appropriate for environment
- [ ] Environment variables used for configuration
- [ ] No `console.log` with sensitive data
- [ ] No test data with real user information

## 🛠️ Local Testing Before Push

```bash
# Run the application locally
python main.py

# Run tests (if available)
pytest tests/

# Build Docker image locally
docker build -t myapp:test .
docker run -p 8201:8201 myapp:test

# Check for security issues
# Review your changes for any hardcoded secrets
git diff --staged
```

## 📊 Pipeline Status Monitoring

### Check Pipeline Status
1. Go to Azure DevOps > Pipelines
2. Click on your pipeline
3. View recent runs

### If Pipeline Fails
1. Click on failed run
2. Check error messages
3. Common fixes:
   - Missing environment variables
   - Failed tests
   - Docker build issues
   - Azure connection problems

## 🔄 Daily Workflow Summary

```bash
# Morning
git checkout dev
git pull origin dev

# Start feature
git checkout -b feature/new-feature

# Work and commit
git add .
git commit -m "feat: Description"
git push origin feature/new-feature

# Create PR in Azure DevOps

# After PR merged
git checkout dev
git pull origin dev
```

## 🚨 Emergency Procedures

### Rollback Production

```bash
# If production deployment causes issues
git checkout main
git pull origin main
git log --oneline -5  # Find last good commit
git revert HEAD      # Create revert commit
git push origin main  # Triggers rollback deployment
```

### Hotfix Process

```bash
# For urgent production fixes
git checkout main
git pull origin main
git checkout -b hotfix/critical-bug-fix

# Make minimal fix
git add .
git commit -m "hotfix: Fix critical production bug"
git push origin hotfix/critical-bug-fix

# Create PR directly to main (with approval)
# After merge, sync back to dev
git checkout dev
git pull origin main
git push origin dev
```

## 📚 Git Command Reference

| Command | Purpose |
|---------|---------|
| `git status` | Check current state |
| `git diff` | See uncommitted changes |
| `git log --oneline -10` | View recent commits |
| `git branch` | List branches |
| `git checkout -b name` | Create new branch |
| `git add .` | Stage all changes |
| `git commit -m "msg"` | Commit changes |
| `git push origin branch` | Push to remote |
| `git pull origin branch` | Get latest changes |
| `git merge branch` | Merge branch |
| `git stash` | Temporarily save changes |
| `git stash pop` | Restore saved changes |

## 🎯 Best Practices

1. **Pull before push** - Always get latest changes
2. **Small commits** - One logical change per commit
3. **Clear messages** - Explain what and why
4. **Test locally** - Run app before pushing
5. **Review changes** - Use `git diff` before committing
6. **Clean branches** - Delete merged feature branches
7. **No secrets** - Never commit passwords or keys

## 🤝 Getting Help

- **Git issues**: Ask team lead or check this guide
- **Pipeline failures**: Check Azure DevOps logs
- **Merge conflicts**: Ask for help, don't force push
- **Azure issues**: Contact DevOps team

Remember: It's better to ask questions than to break production!

---

*Last Updated: 2025-09-21*
*For questions, contact the DevOps team*