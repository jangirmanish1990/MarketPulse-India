---
description: Package and deploy MarketPulse India to AWS (lambdas + ECS service)
argument-hint: <env: dev|staging|prod>
---

# /deploy-aws — deploy to AWS

> **Confirmation required.** Do not run this command without explicit user
> approval. `prod` deploys additionally require a typed "yes deploy prod"
> from the user.

Target environment: `$1` (one of `dev`, `staging`, `prod`).

Steps (run in this order, stop on first failure):

1. Verify a clean working tree: `git status --porcelain` must be empty.
2. Verify CI is green on the current commit (GitHub Actions).
3. Run `make lint && make test` locally as a last-mile gate.
4. Build container image for the backend; push to ECR under tag
   `marketpulse-backend:$(git rev-parse --short HEAD)`.
5. Package each lambda under `lambdas/` (zip + deps) and upload to S3.
6. Apply Terraform in `infra/envs/$1/`:
   - `terraform init` (if needed)
   - `terraform plan -out plan.tfplan`
   - **Show the plan to the user before applying.**
   - `terraform apply plan.tfplan` only after user confirms.
7. Run smoke checks: hit the deployed `/health` endpoint and verify a
   signal endpoint returns the SEBI disclaimer.

Constraints:

- Never edit Terraform state files by hand.
- Never bypass the human confirmation step for `prod`.
- If a deploy fails partway, do not auto-rollback Terraform — surface the
  state and let the user decide.
