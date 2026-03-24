#!/usr/bin/env bash
set -euo pipefail

# Deploy the remote MCP server to AWS ECS Fargate.
#
# Uses the existing ECS cluster and ALB from the cited backend infrastructure.
# Creates its own ECR repo, target group, listener rule, task definition, and
# ECS service — all via AWS CLI (no CDK dependency).
#
# Usage:
#   ./scripts/deploy-mcp.sh dev              # Deploy to dev (mcpdev.youcited.com)
#   ./scripts/deploy-mcp.sh prod             # Deploy to prod (mcp.youcited.com) — requires prod AWS account
#   ./scripts/deploy-mcp.sh prod --dev-infra  # Deploy prod MCP on dev AWS infra (prod API suspended)
#
# The --dev-infra flag deploys the prod MCP service (pointing at api.youcited.com)
# onto the dev AWS account's infrastructure. Useful when the prod AWS account is
# suspended. The MCP server is stateless — it just relays authenticated requests.
#
# Prerequisites:
#   - AWS SSO session: aws sso login --profile advgeo-<env>
#   - Docker running locally
#   - SSM params from the cited backend CDK (VPC, cluster, ALB, etc.)
#   - For --dev-infra: JWT secret at cited-mcp-prod/jwt-secret in dev account

ENV="${1:-}"
DEV_INFRA=false
if [[ "${2:-}" == "--dev-infra" ]]; then
    DEV_INFRA=true
fi

if [[ -z "$ENV" || ! "$ENV" =~ ^(dev|prod)$ ]]; then
    echo "Usage: $0 <dev|prod> [--dev-infra]"
    exit 1
fi

if [[ "$DEV_INFRA" == true && "$ENV" != "prod" ]]; then
    echo "Error: --dev-infra is only valid with prod environment"
    exit 1
fi

# Infrastructure profile: which AWS account to deploy to
if [[ "$DEV_INFRA" == true ]]; then
    INFRA_ENV="dev"
    PROFILE="advgeo-dev"
    echo "*** Cross-account deploy: prod MCP service on dev AWS infrastructure ***"
else
    INFRA_ENV="$ENV"
    PROFILE="advgeo-${ENV}"
fi

REGION="us-east-1"
SERVICE_NAME="cited-mcp-${ENV}"
CONTAINER_NAME="cited-mcp"
CONTAINER_PORT=8080
CPU=256
MEMORY=512

# Environment-specific config (always based on target ENV, not infra)
if [[ "$ENV" == "dev" ]]; then
    MCP_URL="https://mcpdev.youcited.com"
    API_URL="https://dev.youcited.com"
    MCP_HOST="mcpdev.youcited.com"
else
    MCP_URL="https://mcp.youcited.com"
    API_URL="https://api.youcited.com"
    MCP_HOST="mcp.youcited.com"
fi

echo "==> Deploying MCP server to ${ENV} (${MCP_HOST}) [infra: ${INFRA_ENV}]"

# ── Resolve SSM parameters from existing infra ──────────────────────────────
echo "    Resolving infrastructure parameters from ${INFRA_ENV} account..."
ssm() { aws --profile "$PROFILE" --region "$REGION" ssm get-parameter --name "$1" --query Parameter.Value --output text; }

VPC_ID=$(ssm "/advgeo/${INFRA_ENV}/vpc-id")
SUBNET_IDS=$(ssm "/advgeo/${INFRA_ENV}/private-subnet-ids")
ECS_CLUSTER=$(ssm "/advgeo/${INFRA_ENV}/ecs-cluster-arn")
ECS_SG=$(ssm "/advgeo/${INFRA_ENV}/ecs-security-group-id")
HTTPS_LISTENER=$(ssm "/advgeo/${INFRA_ENV}/https-listener-arn")
ACCOUNT_ID=$(aws --profile "$PROFILE" sts get-caller-identity --query Account --output text)

echo "    VPC: ${VPC_ID}"
echo "    Cluster: ${ECS_CLUSTER}"

# ── ECR repository ──────────────────────────────────────────────────────────
ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${SERVICE_NAME}"

if ! aws --profile "$PROFILE" --region "$REGION" ecr describe-repositories --repository-names "$SERVICE_NAME" &>/dev/null; then
    echo "    Creating ECR repository: ${SERVICE_NAME}"
    aws --profile "$PROFILE" --region "$REGION" ecr create-repository \
        --repository-name "$SERVICE_NAME" \
        --image-scanning-configuration scanOnPush=true \
        --query 'repository.repositoryUri' --output text
else
    echo "    ECR repository exists: ${SERVICE_NAME}"
fi

# ── Build and push Docker image ─────────────────────────────────────────────
echo "==> Building Docker image..."
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Build from repo root so COPY paths work
docker build --platform linux/amd64 -t "${SERVICE_NAME}:latest" \
    -f "${REPO_ROOT}/packages/mcp/Dockerfile" \
    "${REPO_ROOT}"

echo "==> Pushing to ECR..."
aws --profile "$PROFILE" --region "$REGION" ecr get-login-password | \
    docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

docker tag "${SERVICE_NAME}:latest" "${ECR_REPO}:latest"
docker push "${ECR_REPO}:latest"
IMAGE_DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' "${ECR_REPO}:latest" 2>/dev/null || echo "${ECR_REPO}:latest")

# ── Target group ────────────────────────────────────────────────────────────
TG_NAME="${SERVICE_NAME}-tg"
TG_ARN=$(aws --profile "$PROFILE" --region "$REGION" elbv2 describe-target-groups \
    --names "$TG_NAME" --query "TargetGroups[0].TargetGroupArn" --output text 2>/dev/null || echo "None")

if [[ "$TG_ARN" == "None" || -z "$TG_ARN" ]]; then
    echo "    Creating target group: ${TG_NAME}"
    TG_ARN=$(aws --profile "$PROFILE" --region "$REGION" elbv2 create-target-group \
        --name "$TG_NAME" \
        --protocol HTTP \
        --port "$CONTAINER_PORT" \
        --vpc-id "$VPC_ID" \
        --target-type ip \
        --health-check-path "/health" \
        --health-check-interval-seconds 30 \
        --healthy-threshold-count 2 \
        --unhealthy-threshold-count 3 \
        --query "TargetGroups[0].TargetGroupArn" --output text)
else
    echo "    Target group exists: ${TG_NAME}"
fi

# ── ALB listener rule (host-header based) ───────────────────────────────────
RULE_EXISTS=$(aws --profile "$PROFILE" --region "$REGION" elbv2 describe-rules \
    --listener-arn "$HTTPS_LISTENER" \
    --query "Rules[?Conditions[?Field=='host-header' && Values[?contains(@,'${MCP_HOST}')]]]|[0].RuleArn" \
    --output text 2>/dev/null || echo "None")

# Assign different priorities so dev and prod rules can coexist on the same ALB
if [[ "$ENV" == "dev" ]]; then RULE_PRIORITY=1; else RULE_PRIORITY=2; fi

if [[ "$RULE_EXISTS" == "None" || -z "$RULE_EXISTS" ]]; then
    echo "    Creating listener rule for ${MCP_HOST} (priority ${RULE_PRIORITY})"
    aws --profile "$PROFILE" --region "$REGION" elbv2 create-rule \
        --listener-arn "$HTTPS_LISTENER" \
        --priority "$RULE_PRIORITY" \
        --conditions "Field=host-header,Values=${MCP_HOST}" \
        --actions "Type=forward,TargetGroupArn=${TG_ARN}" \
        --query "Rules[0].RuleArn" --output text
else
    echo "    Listener rule exists for ${MCP_HOST}"
fi

# ── Resolve JWT secret ARN ──────────────────────────────────────────────────
if [[ "$DEV_INFRA" == true ]]; then
    # Cross-account: use dedicated prod JWT secret stored in dev account
    JWT_SECRET_ARN=$(aws --profile "$PROFILE" --region "$REGION" secretsmanager list-secrets \
        --filters "Key=name,Values=cited-mcp-prod/jwt-secret" \
        --query "SecretList[0].ARN" --output text)
else
    JWT_SECRET_ARN=$(aws --profile "$PROFILE" --region "$REGION" secretsmanager list-secrets \
        --filters "Key=name,Values=advgeo/${ENV}/jwt-secret" \
        --query "SecretList[0].ARN" --output text)
fi
if [[ -z "$JWT_SECRET_ARN" || "$JWT_SECRET_ARN" == "None" ]]; then
    echo "Error: JWT secret not found. For --dev-infra, create it first:"
    echo "  aws --profile advgeo-dev --region us-east-1 secretsmanager create-secret \\"
    echo "    --name cited-mcp-prod/jwt-secret --secret-string \"\$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')\""
    exit 1
fi
echo "    JWT secret: ${JWT_SECRET_ARN}"

# ── IAM roles (reuse existing execution role, create minimal task role) ─────
# Get execution role from existing API task definition
API_TASKDEF=$(aws --profile "$PROFILE" --region "$REGION" ecs describe-services \
    --cluster advgeo-${INFRA_ENV} --services advgeo-${INFRA_ENV}-api \
    --query "services[0].taskDefinition" --output text)
EXEC_ROLE=$(aws --profile "$PROFILE" --region "$REGION" ecs describe-task-definition \
    --task-definition "$API_TASKDEF" \
    --query "taskDefinition.executionRoleArn" --output text)
TASK_ROLE=$(aws --profile "$PROFILE" --region "$REGION" ecs describe-task-definition \
    --task-definition "$API_TASKDEF" \
    --query "taskDefinition.taskRoleArn" --output text)

# ── ECS task definition ─────────────────────────────────────────────────────
echo "==> Registering task definition..."
TASKDEF_FILE=$(mktemp)
cat > "$TASKDEF_FILE" <<EOF
{
    "family": "${SERVICE_NAME}",
    "networkMode": "awsvpc",
    "requiresCompatibilities": ["FARGATE"],
    "cpu": "${CPU}",
    "memory": "${MEMORY}",
    "executionRoleArn": "${EXEC_ROLE}",
    "taskRoleArn": "${TASK_ROLE}",
    "containerDefinitions": [
        {
            "name": "${CONTAINER_NAME}",
            "image": "${ECR_REPO}:latest",
            "essential": true,
            "portMappings": [
                {
                    "containerPort": ${CONTAINER_PORT},
                    "protocol": "tcp"
                }
            ],
            "environment": [
                {"name": "CITED_API_URL", "value": "${API_URL}"},
                {"name": "MCP_URL", "value": "${MCP_URL}"},
                {"name": "CITED_ENV", "value": "${ENV}"},
                {"name": "HOST", "value": "0.0.0.0"},
                {"name": "PORT", "value": "${CONTAINER_PORT}"}
            ],
            "secrets": [
                {"name": "JWT_SECRET", "valueFrom": "${JWT_SECRET_ARN}"}
            ],
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group": "/ecs/advgeo-${INFRA_ENV}",
                    "awslogs-region": "${REGION}",
                    "awslogs-stream-prefix": "mcp"
                }
            }
        }
    ]
}
EOF

TASKDEF_ARN=$(aws --profile "$PROFILE" --region "$REGION" ecs register-task-definition \
    --cli-input-json "file://${TASKDEF_FILE}" \
    --query "taskDefinition.taskDefinitionArn" --output text)
rm -f "$TASKDEF_FILE"
echo "    Task definition: ${TASKDEF_ARN}"

# ── ECS service ─────────────────────────────────────────────────────────────
SERVICE_EXISTS=$(aws --profile "$PROFILE" --region "$REGION" ecs describe-services \
    --cluster "advgeo-${INFRA_ENV}" --services "$SERVICE_NAME" \
    --query "services[?status=='ACTIVE']|[0].serviceName" --output text 2>/dev/null || echo "None")

# Format subnet IDs for JSON array
IFS=',' read -ra SUBNET_ARR <<< "$SUBNET_IDS"
SUBNET_JSON=$(printf '"%s",' "${SUBNET_ARR[@]}" | sed 's/,$//')

if [[ "$SERVICE_EXISTS" == "None" || -z "$SERVICE_EXISTS" ]]; then
    echo "==> Creating ECS service: ${SERVICE_NAME}"
    aws --profile "$PROFILE" --region "$REGION" ecs create-service \
        --cluster "advgeo-${INFRA_ENV}" \
        --service-name "$SERVICE_NAME" \
        --task-definition "$TASKDEF_ARN" \
        --desired-count 1 \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[${SUBNET_JSON}],securityGroups=[\"${ECS_SG}\"],assignPublicIp=DISABLED}" \
        --load-balancers "targetGroupArn=${TG_ARN},containerName=${CONTAINER_NAME},containerPort=${CONTAINER_PORT}" \
        --deployment-configuration "maximumPercent=200,minimumHealthyPercent=100,deploymentCircuitBreaker={enable=true,rollback=true}" \
        --query "service.serviceName" --output text
else
    echo "==> Updating ECS service: ${SERVICE_NAME}"
    aws --profile "$PROFILE" --region "$REGION" ecs update-service \
        --cluster "advgeo-${INFRA_ENV}" \
        --service "$SERVICE_NAME" \
        --task-definition "$TASKDEF_ARN" \
        --force-new-deployment \
        --query "service.serviceName" --output text
fi

echo ""
echo "==> Deployment initiated!"
echo "    Service: ${SERVICE_NAME}"
echo "    URL: ${MCP_URL}"
echo ""
echo "    Waiting for service to stabilize..."
aws --profile "$PROFILE" --region "$REGION" ecs wait services-stable \
    --cluster "advgeo-${INFRA_ENV}" --services "$SERVICE_NAME" && \
    echo "    ✓ Service is stable!" || \
    echo "    ⚠ Service did not stabilize within timeout. Check ECS console."

echo ""
echo "    Next steps:"
echo "    1. Add DNS CNAME: ${MCP_HOST} → ALB DNS name"
echo "    2. Test: curl https://${MCP_HOST}/health"
echo "    3. Claude Desktop config: {\"type\": \"http\", \"url\": \"${MCP_URL}\"}"
