# Branching Strategy & Git Workflow

## 1. Branch Topology

The repository follows a strict GitFlow-lite branching strategy for this milestone delivery:

- **`main`**: Represents production-ready releases. Direct commits are strictly prohibited. Releases are marked with annotated Git tags (`v1.0.0`, `v1.1.0`).
- **`develop`**: Integration branch for verified feature work. Serves as the base for new feature branches and the target for pull requests. Direct commits are strictly prohibited.
- **`feature/<name>`**: Dedicated short-lived branches created for each development phase or capability (e.g., `feature/setup`, `feature/app`, `feature/docker`, `feature/k8s`). All development occurs on these branches.

```
main ----------------------------------● [v1.0.0] -----------● [v1.1.0]
               \                      /                     /
develop --------●--------------------●---------------------●
                 \                  / \                   /
feature/setup ----●---●---●--------/   \                 /
                                        \               /
feature/docker --------------------------●---●---●-----/
```

## 2. Commit Standards

- **Atomic Commits**: Each commit must encapsulate exactly one logical intent (e.g., "add readiness probe to backend deployment").
- **No Generic Messages**: Commit messages such as "wip", "fix", "update", or "changes" are forbidden.
- **No Force-Pushes or Squashing**: Linear, verifiable history must be maintained. Do not backdate, squash, amend pushed commits, or force-push. Use merge commits for pull requests.
- **Staging Verification**: Never use `git add -A` blindly. Run `git status` and `git diff --staged` before every commit to inspect staged changes and prevent accidental secret leakage.

## 3. Pull Request and Release Flow

1. **Branch Creation**: Cut `feature/<phase-name>` from the latest `develop`.
2. **Local Development & Verification**: Implement atomic commits, verify changes locally against acceptance criteria.
3. **Pull Request**: Push branch to remote and open a Pull Request targeting `develop`.
4. **Merge**: Merge the PR into `develop` once verified (using merge commits, no squash).
5. **Milestone Promotion & Tagging**:
   - When Docker orchestration is fully verified: Merge `develop` into `main` and create annotated tag `v1.0.0`.
   - When Kubernetes deployment is fully verified: Merge `develop` into `main` and create annotated tag `v1.1.0`.

## 4. Team Recommendation (5 Engineers Shipping Daily)

While GitFlow-lite provides clear staged gatekeeping for phased academic or milestone deliverables, **for a team of 5 engineers shipping multiple times daily to production, Trunk-Based Development with short-lived feature branches (< 1 day) is recommended**.

- **Why**: Maintaining a long-lived `develop` branch creates merge overhead, delayed integration conflicts, and dual-merge complexity back into `main`.
- **Alternative**: Engineers branch directly from `main`, run automated CI test suites and ephemeral preview deployments, and merge back into `main` via PRs within 24 hours behind feature flags. Releases are driven continuously from `main`.
