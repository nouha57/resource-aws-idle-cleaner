#!/usr/bin/env python3
"""
Test script for AWS Idle Resource Cleaner
Run this to verify your setup and AWS credentials work correctly.
"""

import boto3
from aws_cleaner import AWSResourceCleaner
from lambda_function import LambdaResourceCleaner
import json

def test_aws_connection():
    """Test basic AWS connectivity."""
    print("Testing AWS connection...")
    try:
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()
        print(f"Connected as: {identity.get('Arn', 'Unknown')}")
        print(f"   Account ID: {identity.get('Account', 'Unknown')}")
        return True
    except Exception as e:
        print(f"AWS connection failed: {e}")
        return False

def test_cli_cleaner():
    """Test the CLI cleaner class."""
    print("\nTesting CLI cleaner...")
    try:
        cleaner = AWSResourceCleaner(dry_run=True)
        
        # Test finding resources (dry run)
        eips = cleaner.find_unused_elastic_ips()
        snapshots = cleaner.find_old_snapshots(30)
        instances = cleaner.find_stopped_instances(7)
        
        print(f"Found {len(eips)} unused EIPs")
        print(f"Found {len(snapshots)} old snapshots")
        print(f"Found {len(instances)} stopped instances")
        
        return True
    except Exception as e:
        print(f"CLI cleaner test failed: {e}")
        return False

def test_lambda_cleaner():
    """Test the Lambda cleaner class."""
    print("\nTesting Lambda cleaner...")
    try:
        cleaner = LambdaResourceCleaner()
        
        # Test configuration
        config = {
            'dry_run': True,
            'clean_eips': True,
            'clean_snapshots': True,
            'clean_instances': False,
            'snapshot_days': 30,
            'instance_days': 7
        }
        
        result = cleaner.cleanup_resources(config)
        
        print(f"Lambda test completed")
        print(f"   Region: {result['region']}")
        print(f"   Cleaned: {result['cleaned']}")
        print(f"   Errors: {len(result['errors'])}")
        
        return True
    except Exception as e:
        print(f"Lambda cleaner test failed: {e}")
        return False

def test_permissions():
    """Test required AWS permissions."""
    print("\nTesting AWS permissions...")
    
    permissions_test = [
        ('ec2:DescribeAddresses', 'describe_addresses'),
        ('ec2:DescribeSnapshots', 'describe_snapshots'),
        ('ec2:DescribeInstances', 'describe_instances'),
        ('ec2:DescribeRegions', 'describe_regions')
    ]
    
    ec2 = boto3.client('ec2')
    passed = 0
    
    for permission, method in permissions_test:
        try:
            if method == 'describe_addresses':
                ec2.describe_addresses()
            elif method == 'describe_snapshots':
                ec2.describe_snapshots(OwnerIds=['self'], MaxResults=5)
            elif method == 'describe_instances':
                ec2.describe_instances(MaxResults=5)
            elif method == 'describe_regions':
                ec2.describe_regions()
            
            print(f"[OK] {permission}")
            passed += 1
        except Exception as e:
            print(f"[ERROR] {permission}: {e}")
    
    print(f"\nPermissions test: {passed}/{len(permissions_test)} passed")
    return passed == len(permissions_test)

def main():
    """Run all tests."""
    print("AWS Idle Resource Cleaner - Test Suite")
    print("=" * 50)
    
    tests = [
        ("AWS Connection", test_aws_connection),
        ("CLI Cleaner", test_cli_cleaner),
        ("Lambda Cleaner", test_lambda_cleaner),
        ("Permissions", test_permissions)
    ]
    
    passed = 0
    for test_name, test_func in tests:
        if test_func():
            passed += 1
    
    print(f"\nTest Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("All tests passed! Your setup is ready to use.")
        print("\nNext steps:")
        print("   1. Run: python aws_cleaner.py --dry-run --clean-eips")
        print("   2. Deploy Lambda: ./deploy_lambda.sh")
        print("   3. Check example_usage.py for more examples")
    else:
        print("Some tests failed. Please check your AWS configuration.")

if __name__ == '__main__':
    main()