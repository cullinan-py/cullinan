# GitHub Pages Deployment - Environment Branch Policy

> Governance record of the `github-pages` environment deployment branch policy.
> Updated: 2026-07-19

## Context

The `mkdocs-build.yml` workflow's `deploy` job references the `github-pages`
environment. GitHub enforces a deployment branch policy on this environment;
only branches listed in the policy may deploy to it. Any branch that triggers
the workflow but is absent from the policy will see its `deploy` job rejected
at the environment gate (the job shows `failure` with zero steps executed).

## Allowed Branches

| Branch Pattern | Added | Reason |
|----------------|-------|--------|
| `gh-pages`     | historical | Legacy Pages source branch |
| `master`       | historical | Stable release channel |
| `release/*`    | historical | Release tag/branch channel |
| `preview`      | 2026-07-19 (S4, v0.95a1) | Pre-release channel authoritative source. Per S4 spec, `preview` is the single authoritative source for the `pre` documentation channel. |

## Maintenance Rule

When a new documentation channel is introduced (or an existing channel's
authoritative source branch changes), the `github-pages` environment's
deployment branch policy MUST be updated to include the branch. This is a
GitHub repository setting, modified via the GitHub API or repo settings UI -
it is NOT a code change and cannot be delivered via a pull request.

API reference:
```
GET  /repos/{owner}/{repo}/environments/github-pages/deployment-branch-policies
POST /repos/{owner}/{repo}/environments/github-pages/deployment-branch-policies  -f name=<branch>
DELETE /repos/{owner}/{repo}/environments/github-pages/deployment-branch-policies/{policy_id}
```

## Related

- S4 spec (channel mapping): `preview` -> `pre` channel
- Workflow file: `.github/workflows/mkdocs-build.yml` (`deploy` job, `environment: github-pages`)
