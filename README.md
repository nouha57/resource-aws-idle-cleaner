# AWS Idle Resource Cleaner

A Python-based cost optimization tool that identifies and cleans up unused AWS resources to reduce your cloud spending.

## Features

- **Unused Elastic IPs**: Finds and releases unattached Elastic IP addresses
- **Old EBS Snapshots**: Identifies and deletes snapshots older than specified days
- **Stopped EC2 Instances**: Finds long-running stopped instances for cleanup
- **Dual Deployment**: Works as both CLI tool and AWS Lambda function
- **Dry Run Mode**: Preview changes before applying them
- **Multi-Region Support**: Scan resources across multiple AWS regions

## Quick Start

### CLI Usage
```bash
# Install dependencies
pip install -r requirements.txt

# Dry run to see what would be cleaned
python aws_cleaner.py --dry-run

# Clean unused Elastic IPs
python aws_cleaner.py --clean-eips

# Clean old snapshots (older than 30 days)
python aws_cleaner.py --clean-snapshots --days 30

# Clean stopped instances (stopped for more than 7 days)
python aws_cleaner.py --clean-instances --days 7
```

### Lambda Deployment
```bash
# Package for Lambda
./deploy_lambda.sh

# Or use AWS CLI
aws lambda create-function --function-name aws-idle-cleaner \
  --runtime python3.9 --role arn:aws:iam::ACCOUNT:role/lambda-role \
  --handler lambda_function.lambda_handler --zip-file fileb://deployment.zip
```

## Configuration

Set AWS credentials via:
- AWS CLI (`aws configure`)
- Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
- IAM roles (recommended for Lambda)

## Required IAM Permissions

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeAddresses",
                "ec2:ReleaseAddress",
                "ec2:DescribeSnapshots",
                "ec2:DeleteSnapshot",
                "ec2:DescribeInstances",
                "ec2:TerminateInstances"
            ],
            "Resource": "*"
        }
    ]
}
```

## Safety Features

- Dry run mode by default
- Configurable retention periods
- Detailed logging of all actions
- Confirmation prompts for destructive operations

## Examples

### CLI Examples
```bash
# Dry run to preview cleanup
python aws_cleaner.py --dry-run --clean-eips --clean-snapshots

# Clean unused EIPs in production
python aws_cleaner.py --no-dry-run --clean-eips --force

# Clean old snapshots across all regions
python aws_cleaner.py --no-dry-run --clean-snapshots --days 60 --all-regions

# Comprehensive cleanup with prompts
python aws_cleaner.py --no-dry-run --clean-eips --clean-snapshots --clean-instances
```

### Lambda Examples
```json
{
  "regions": ["us-east-1", "us-west-2"],
  "dry_run": false,
  "clean_eips": true,
  "clean_snapshots": true,
  "snapshot_days": 30
}
```

### Estimated Cost Savings
- **Unused EIPs**: $3.60/month per EIP
- **Old Snapshots**: $0.05/GB-month
- **Stopped Instances**: Varies by instance type

## Scheduling

### Lambda with EventBridge
```bash
# Weekly cleanup schedule
aws events put-rule --name weekly-cleanup --schedule-expression "rate(7 days)"
aws events put-targets --rule weekly-cleanup --targets "Id"="1","Arn"="arn:aws:lambda:region:account:function:aws-idle-cleaner"
```

### Cron Job
```bash
# Daily dry run at 2 AM
0 2 * * * /usr/bin/python3 /path/to/aws_cleaner.py --dry-run --clean-eips --clean-snapshots
```