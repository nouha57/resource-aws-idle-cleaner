#!/bin/bash

# AWS Lambda Deployment Script for Idle Resource Cleaner

set -e

echo "Deploying AWS Idle Resource Cleaner to Lambda..."

# Configuration
FUNCTION_NAME="aws-idle-cleaner"
RUNTIME="python3.9"
HANDLER="lambda_function.lambda_handler"
TIMEOUT=300
MEMORY=256

# Create deployment package
echo "Creating deployment package..."
rm -rf deployment/
mkdir -p deployment/

# Copy source files
cp lambda_function.py deployment/
cp requirements.txt deployment/

# Install dependencies
echo "Installing dependencies..."
cd deployment/
pip install -r requirements.txt -t .
rm requirements.txt

# Create zip file
echo "Creating zip archive..."
zip -r ../deployment.zip . -x "*.pyc" "__pycache__/*"
cd ..

echo "Deployment package created: deployment.zip"

# Check if AWS CLI is configured
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "ERROR: AWS CLI not configured. Please run 'aws configure' first."
    exit 1
fi

# Get AWS account ID and region
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=$(aws configure get region)

echo "Deploying to region: $REGION"
echo "Account ID: $ACCOUNT_ID"

# Create IAM role if it doesn't exist
ROLE_NAME="aws-idle-cleaner-role"
ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/$ROLE_NAME"

if ! aws iam get-role --role-name $ROLE_NAME > /dev/null 2>&1; then
    echo "Creating IAM role..."
    
    # Create trust policy
    cat > trust-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "lambda.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
EOF

    # Create execution policy
    cat > execution-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeAddresses",
                "ec2:ReleaseAddress",
                "ec2:DescribeSnapshots",
                "ec2:DeleteSnapshot",
                "ec2:DescribeInstances",
                "ec2:TerminateInstances",
                "ec2:DescribeRegions"
            ],
            "Resource": "*"
        }
    ]
}
EOF

    # Create role
    aws iam create-role --role-name $ROLE_NAME --assume-role-policy-document file://trust-policy.json
    
    # Attach policies
    aws iam put-role-policy --role-name $ROLE_NAME --policy-name "IdleCleanerPolicy" --policy-document file://execution-policy.json
    
    # Clean up policy files
    rm trust-policy.json execution-policy.json
    
    echo "Waiting for role to be ready..."
    sleep 10
else
    echo "IAM role already exists"
fi

# Deploy or update Lambda function
if aws lambda get-function --function-name $FUNCTION_NAME > /dev/null 2>&1; then
    echo "Updating existing Lambda function..."
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --zip-file fileb://deployment.zip
    
    aws lambda update-function-configuration \
        --function-name $FUNCTION_NAME \
        --timeout $TIMEOUT \
        --memory-size $MEMORY
else
    echo "Creating new Lambda function..."
    aws lambda create-function \
        --function-name $FUNCTION_NAME \
        --runtime $RUNTIME \
        --role $ROLE_ARN \
        --handler $HANDLER \
        --zip-file fileb://deployment.zip \
        --timeout $TIMEOUT \
        --memory-size $MEMORY \
        --description "AWS Idle Resource Cleaner for cost optimization"
fi

# Clean up
rm -rf deployment/
rm deployment.zip

echo "Deployment completed successfully!"
echo ""
echo "Function Details:"
echo "   Name: $FUNCTION_NAME"
echo "   Region: $REGION"
echo "   Role: $ROLE_ARN"
echo ""
echo "Test your function with:"
echo "   aws lambda invoke --function-name $FUNCTION_NAME --payload '{\"dry_run\": true, \"clean_eips\": true}' response.json"