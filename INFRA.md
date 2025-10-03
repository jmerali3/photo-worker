# Infrastructure Setup Guide

This document outlines all the AWS infrastructure components that need to be configured to run the photo-worker service.

## Overview

The photo-worker requires the following AWS services:
- **S3**: For storing raw images, OCR results, and manifests
- **Textract**: For OCR processing of recipe images
- **IAM**: For service permissions
- **Optional**: RDS for managed PostgreSQL (or self-managed EC2/container)

## AWS Services Configuration

### 1. S3 Bucket Setup

#### Create Primary S3 Bucket
```bash
# Replace 'your-org-photo-worker' with your desired bucket name
BUCKET_NAME="your-org-photo-worker-prod"
AWS_REGION="us-west-2"

# Create bucket
aws s3 mb s3://$BUCKET_NAME --region $AWS_REGION

# Enable versioning (recommended)
aws s3api put-bucket-versioning \
  --bucket $BUCKET_NAME \
  --versioning-configuration Status=Enabled
```

#### Configure Bucket Structure
The worker expects this folder structure:
```
s3://your-bucket/
├── raw/              # Original uploaded images
├── artifacts/        # OCR results and manifests
│   └── {job_id}/
│       ├── textract.json
│       └── manifest.json
└── tags/             # Future: LLM-generated tags
    └── {job_id}/
        └── v{version}.json
```

#### S3 Bucket Policy (Optional - for cross-account access)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PhotoWorkerAccess",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::YOUR-ACCOUNT-ID:role/PhotoWorkerRole"
      },
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-org-photo-worker-prod",
        "arn:aws:s3:::your-org-photo-worker-prod/*"
      ]
    }
  ]
}
```

#### S3 Lifecycle Policy (Cost Optimization)
```json
{
  "Rules": [
    {
      "ID": "TransitionOldOCRResults",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "artifacts/"
      },
      "Transitions": [
        {
          "Days": 30,
          "StorageClass": "STANDARD_IA"
        },
        {
          "Days": 90,
          "StorageClass": "GLACIER"
        }
      ]
    }
  ]
}
```

### 2. IAM Configuration

#### Create IAM Role for Photo Worker
```bash
# Create trust policy for the worker (EC2/ECS/Lambda)
cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": [
          "ec2.amazonaws.com",
          "ecs-tasks.amazonaws.com"
        ]
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create the role
aws iam create-role \
  --role-name PhotoWorkerRole \
  --assume-role-policy-document file://trust-policy.json
```

#### Create IAM Policy for Photo Worker
```bash
cat > photo-worker-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:HeadObject"
      ],
      "Resource": "arn:aws:s3:::your-org-photo-worker-prod/*"
    },
    {
      "Sid": "S3ListAccess",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::your-org-photo-worker-prod"
    },
    {
      "Sid": "TextractAccess",
      "Effect": "Allow",
      "Action": [
        "textract:DetectDocumentText",
        "textract:AnalyzeDocument"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
EOF

# Create policy
aws iam create-policy \
  --policy-name PhotoWorkerPolicy \
  --policy-document file://photo-worker-policy.json

# Attach policy to role
aws iam attach-role-policy \
  --role-name PhotoWorkerRole \
  --policy-arn arn:aws:iam::YOUR-ACCOUNT-ID:policy/PhotoWorkerPolicy
```

#### Create Instance Profile (for EC2 deployment)
```bash
# Create instance profile
aws iam create-instance-profile --instance-profile-name photo-dev-dev-worker-instance-profile

# Add role to instance profile
aws iam add-role-to-instance-profile \
  --instance-profile-name photo-dev-dev-worker-instance-profile \
  --role-name PhotoWorkerRole
```

### 3. Textract Service Limits

#### Check Current Limits
```bash
# Check Textract service limits
aws service-quotas get-service-quota \
  --service-code textract \
  --quota-code L-D3DB0C0D  # DetectDocumentText synchronous requests per second

# List all Textract quotas
aws service-quotas list-service-quotas --service-code textract
```

#### Request Limit Increases (if needed)
- **DetectDocumentText (Sync)**: Default 2 TPS, can request up to 50 TPS
- **Document size**: Max 10MB for sync operations
- **Pages**: Max 3000 pages per document

Submit requests through AWS Support Console if you need higher limits.

### 4. Database Setup Options

#### Option A: Amazon RDS PostgreSQL (Recommended)
```bash
# Create RDS PostgreSQL instance
aws rds create-db-instance \
  --db-instance-identifier photo-dev-dev-pg \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --engine-version 15.4 \
  --master-username appuser \
  --master-user-password "<sensitive>" \
  --allocated-storage 20 \
  --storage-type gp2 \
  --vpc-security-group-ids sg-0c8205f5e517d263d \
  --db-subnet-group-name your-db-subnet-group \
  --backup-retention-period 7 \
  --storage-encrypted \
  --multi-az false
```

#### Option B: Self-Managed PostgreSQL on EC2
- Launch EC2 instance with PostgreSQL
- Configure security groups for port 5432
- Set up regular backups
- Apply security patches regularly

### 5. Networking Configuration

#### VPC and Security Groups
```bash
# Create security group for photo worker
aws ec2 create-security-group \
  --group-name photo-worker-sg \
  --description "Security group for photo worker service" \
  --vpc-id vpc-xxxxxxxxx

# Add rules (adjust as needed)
# Allow outbound HTTPS for AWS APIs
aws ec2 authorize-security-group-egress \
  --group-id sg-0c6b18fb20c16059d \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0

# Allow database access (if using RDS)
aws ec2 authorize-security-group-egress \
  --group-id sg-0c6b18fb20c16059d \
  --protocol tcp \
  --port 5432 \
  --source-group sg-0c8205f5e517d263d  # RDS security group
```

### 6. Monitoring and Logging

#### CloudWatch Log Groups
```bash
# Create log group for photo worker
aws logs create-log-group --log-group-name /aws/photo-worker/application

# Set retention policy (optional)
aws logs put-retention-policy \
  --log-group-name /aws/photo-worker/application \
  --retention-in-days 30
```

#### CloudWatch Alarms (Optional)
```bash
# Example: Alarm for high error rate
aws cloudwatch put-metric-alarm \
  --alarm-name "PhotoWorker-HighErrorRate" \
  --alarm-description "High error rate in photo worker" \
  --metric-name Errors \
  --namespace AWS/Logs \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1
```

## Environment-Specific Configurations

### Development Environment
```bash
# Smaller, cheaper resources
- S3: Standard storage class
- RDS: db.t3.micro, single-AZ
- Textract: Default limits
- Retention: 7 days
```

### Production Environment
```bash
# Production-ready resources
- S3: Standard + IA transition policies
- RDS: db.t3.small or larger, Multi-AZ
- Textract: Request higher limits if needed
- Retention: 30+ days
- Backup: Cross-region replication
```

## Security Considerations

### 1. Secrets Management
```bash
# Store database credentials in AWS Secrets Manager
aws secretsmanager create-secret \
  --name photo-worker/database \
  --description "Database credentials for photo worker" \
  --secret-string '{"username":"appuser","password":"<sensitive>","host":"photo-dev-dev-pg.cr8uowes62h6.us-west-2.rds.amazonaws.com","port":"5432","dbname":"photo_worker"}'
```

### 2. Encryption
- **S3**: Enable bucket encryption (AES-256 or KMS)
- **RDS**: Enable encryption at rest
- **Textract**: Uses encryption in transit by default
- **Logs**: Enable CloudWatch Logs encryption

### 3. Network Security
- Use VPC endpoints for S3 and other AWS services
- Restrict security group rules to minimum required
- Use private subnets for worker instances
- Consider AWS WAF if exposing any web interfaces

## Cost Optimization

### 1. S3 Storage Classes
- Use lifecycle policies to transition old artifacts to cheaper storage
- Consider Intelligent Tiering for unpredictable access patterns

### 2. Textract Pricing
- **DetectDocumentText**: $1.50 per 1,000 pages
- **AnalyzeDocument**: Higher cost but more features
- Monitor usage and consider batch processing

### 3. RDS Optimization
- Use Reserved Instances for predictable workloads
- Enable automated backups with appropriate retention
- Monitor CPU and memory usage for right-sizing

## Terraform Variables (for future automation)

```hcl
# variables.tf
variable "bucket_name" {
  description = "S3 bucket name for photo worker"
  type        = string
  default     = "my-ocr-processed-bucket-070703032025"
}

variable "environment" {
  description = "Environment (dev/staging/prod)"
  type        = string
  default     = "dev"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-west-2"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "vpc_id" {
  description = "VPC ID for resources"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for RDS"
  type        = list(string)
}
```

## Deployment Checklist

- [ ] Create S3 bucket with proper naming convention
- [ ] Configure S3 bucket policy and lifecycle rules
- [ ] Create IAM role and policy for photo worker
- [ ] Set up PostgreSQL database (RDS or self-managed)
- [ ] Configure security groups and networking
- [ ] Set up CloudWatch logging
- [ ] Store database credentials in Secrets Manager
- [ ] Test Textract permissions and limits
- [ ] Configure monitoring and alerting
- [ ] Document connection strings and ARNs for application deployment

## Required Information for Application Configuration

After completing the infrastructure setup, you'll need these values for your `.env.prod` file:

```bash
# From your infrastructure setup
S3_BUCKET="my-ocr-processed-bucket-070703032025"
AWS_REGION="us-west-2"
DB_HOST="photo-dev-dev-pg.cr8uowes62h6.us-west-2.rds.amazonaws.com"
DB_NAME="photo_worker"
DB_USERNAME="appuser"
DB_PASSWORD="<sensitive>"

# For EC2/ECS deployment rely on the instance or task role
# For local debugging, optionally choose an AWS CLI profile
# AWS_PROFILE="photo-worker-dev"
```
