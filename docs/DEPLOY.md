# Deploying to AWS

The target layout is two containers and one database. Both images are built in CI.

```
Route 53 ─► ALB ─┬─► ECS Fargate: web  (Next.js, :3000)
                 └─► ECS Fargate: api  (FastAPI, :8000) ─► RDS PostgreSQL 16
                                          │
                                          └─► Anthropic API (ANTHROPIC_API_KEY from Secrets Manager)
```

| Piece | AWS service | Notes |
|---|---|---|
| Images | ECR | `pbm-api` from `./Dockerfile`; `pbm-web` from `web/Dockerfile` with `--build-arg NEXT_PUBLIC_API_URL=https://api.<domain>` |
| Compute | ECS Fargate, one service per image | App Runner also works and needs less setup. Fargate is the default once you need VPC-private RDS and an ALB. |
| Database | RDS for PostgreSQL 16 | Turn on encryption at rest (KMS). The app creates its tables on first connect. Add `CREATE EXTENSION vector` when RAG lands. |
| Secrets | Secrets Manager → ECS task secrets | `DATABASE_URL`, `ANTHROPIC_API_KEY`. Never baked into images. |
| Config | Task environment | `LLM_PROVIDER=anthropic`, `CORS_ORIGINS=https://<web domain>` |
| Health | ALB target group | API: `GET /health`. Web: `GET /`. |
| Logs | CloudWatch Logs (awslogs driver) | |

## Steps

```bash
# 1. Push images (after `aws ecr get-login-password | docker login ...`)
docker build -t $ECR/pbm-api:$GIT_SHA . && docker push $ECR/pbm-api:$GIT_SHA
docker build -t $ECR/pbm-web:$GIT_SHA --build-arg NEXT_PUBLIC_API_URL=https://api.$DOMAIN web \
  && docker push $ECR/pbm-web:$GIT_SHA

# 2. RDS: create a Postgres 16 instance in private subnets and store its URL in Secrets Manager
#    as postgresql://USER:PASS@HOST:5432/pbm

# 3. ECS: one task definition per image (secrets from step 2), services behind one ALB
#    (host-based routing: api.$DOMAIN -> api, $DOMAIN -> web)
```

Before real traffic:
- A live-model eval must pass the crisis ship gate (`crisis_recall_holdout = 1.00`, evals/README.md).
- Set a retention policy for the `turns` table and the checkpoint tables.
- The CI deploy step (GitHub OIDC → ECR push → `aws ecs update-service`) isn't written yet, because there's no AWS account wired up.

## Useful audit queries

```sql
-- Escalation and crisis rate per day
SELECT date_trunc('day', created_at) AS day,
       avg(escalated::int) AS escalation_rate,
       avg(crisis::int)    AS crisis_rate,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_ms
FROM turns GROUP BY 1 ORDER BY 1;

-- Containment: sessions that never reached a human
SELECT avg(contained::int) AS containment_rate
FROM (SELECT NOT bool_or(escalated) AS contained FROM turns GROUP BY session_id) s;
```
