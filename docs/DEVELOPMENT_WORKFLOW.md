# Development Workflow Guide

## Quick Start for Developers

This guide explains the git workflow and branching strategy. The repository is on GitHub and changes reach `main` through pull requests. No pipeline deploys this service automatically, and there is no production environment yet.

## 🌳 Branch Strategy

```
main
  └── feature/your-feature-name
```

- **`main`**: Changes arrive by pull request
- **`feature/*`**, **`fix/*`**, **`release/*`**: Working branches

The command examples below use a `dev` branch between `main` and the feature branches. Where the repository has no `dev` branch, read `dev` as `main`.

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

1. Go to the repository on GitHub > Pull requests
2. Click "New Pull Request"
3. Select: `feature/add-user-authentication` → `dev`
4. Fill in:
   - Title: Clear description of changes
   - Description: What, why, and how
   - Reviewers: Add team members
   - The Jira key of the related task
5. Click "Create"

### 4. After PR Approval

```bash
# Once merged, clean up locally
git checkout dev
git pull origin dev
git branch -d feature/add-user-authentication
```

## 🚀 Deployment Process

Merging to `main` does not deploy anything. The service is deployed by hand as a container on Azure Container Apps, through the organisation's guarded procedure (`Dockerfile.aca`, `deploy/aca/containerapp.yaml`). See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).

As deployed, the service is reachable only on the organisation network (VPN). There is no production environment yet.

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

## 📊 Checks on a Pull Request

Run the tests before you push (`pytest`). The only GitHub Actions workflow in this repository is `.github/workflows/deploy-cloudrun.yml`, which is started by hand and kept for reference only.

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

# Create a pull request on GitHub

# After PR merged
git checkout dev
git pull origin dev
```

## 🚨 If a Deployment Goes Wrong

Follow the organisation's Container Apps procedure. Then fix the code on a branch and open a pull request as usual.

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
- **Merge conflicts**: Ask for help, don't force push
- **Azure issues**: Ask the platform team

---

*Last Updated: 2025-09-21*
*For questions, contact the DevOps team*