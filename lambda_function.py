"""
AWS Lambda version of the Idle Resource Cleaner
"""

import json
import boto3
from datetime import datetime, timedelta
from typing import Dict, Any, List
import logging

# Configure logging for Lambda
logger = logging.getLogger()
logger.setLevel(logging.INFO)


class LambdaResourceCleaner:
    """Lambda-optimized version of AWS Resource Cleaner."""
    
    def __init__(self, region: str = None):
        self.region = region or boto3.Session().region_name
        self.ec2_client = boto3.client('ec2', region_name=self.region)
    
    def find_unused_elastic_ips(self) -> List[Dict[str, Any]]:
        """Find unattached Elastic IP addresses."""
        try:
            response = self.ec2_client.describe_addresses()
            unused_eips = []
            
            for eip in response['Addresses']:
                if 'InstanceId' not in eip and 'NetworkInterfaceId' not in eip:
                    unused_eips.append({
                        'AllocationId': eip.get('AllocationId'),
                        'PublicIp': eip.get('PublicIp'),
                        'Domain': eip.get('Domain', 'classic')
                    })
            
            return unused_eips
        except Exception as e:
            logger.error(f"Error finding unused EIPs: {e}")
            return []
    
    def find_old_snapshots(self, days: int = 30) -> List[Dict[str, Any]]:
        """Find EBS snapshots older than specified days."""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            response = self.ec2_client.describe_snapshots(OwnerIds=['self'])
            old_snapshots = []
            
            for snapshot in response['Snapshots']:
                start_time = snapshot['StartTime'].replace(tzinfo=None)
                if start_time < cutoff_date:
                    old_snapshots.append({
                        'SnapshotId': snapshot['SnapshotId'],
                        'Description': snapshot.get('Description', 'No description'),
                        'StartTime': snapshot['StartTime'].isoformat(),
                        'VolumeSize': snapshot['VolumeSize']
                    })
            
            return old_snapshots
        except Exception as e:
            logger.error(f"Error finding old snapshots: {e}")
            return []
    
    def find_stopped_instances(self, days: int = 7) -> List[Dict[str, Any]]:
        """Find EC2 instances that have been stopped for more than specified days."""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            response = self.ec2_client.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['stopped']}]
            )
            
            old_stopped_instances = []
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    launch_time = instance['LaunchTime'].replace(tzinfo=None)
                    if launch_time < cutoff_date:
                        old_stopped_instances.append({
                            'InstanceId': instance['InstanceId'],
                            'InstanceType': instance['InstanceType'],
                            'LaunchTime': instance['LaunchTime'].isoformat(),
                            'State': instance['State']['Name'],
                            'Name': self._get_instance_name(instance)
                        })
            
            return old_stopped_instances
        except Exception as e:
            logger.error(f"Error finding stopped instances: {e}")
            return []
    
    def _get_instance_name(self, instance: Dict) -> str:
        """Extract instance name from tags."""
        tags = instance.get('Tags', [])
        for tag in tags:
            if tag['Key'] == 'Name':
                return tag['Value']
        return 'No Name'
    
    def cleanup_resources(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Perform cleanup based on configuration."""
        results = {
            'region': self.region,
            'timestamp': datetime.now().isoformat(),
            'cleaned': {'eips': 0, 'snapshots': 0, 'instances': 0},
            'errors': []
        }
        
        dry_run = config.get('dry_run', True)
        
        # Clean Elastic IPs
        if config.get('clean_eips', False):
            try:
                unused_eips = self.find_unused_elastic_ips()
                logger.info(f"Found {len(unused_eips)} unused EIPs")
                
                for eip in unused_eips:
                    if not dry_run:
                        try:
                            if eip['Domain'] == 'vpc':
                                self.ec2_client.release_address(AllocationId=eip['AllocationId'])
                            else:
                                self.ec2_client.release_address(PublicIp=eip['PublicIp'])
                            logger.info(f"Released EIP: {eip['PublicIp']}")
                        except Exception as e:
                            error_msg = f"Error releasing EIP {eip['PublicIp']}: {e}"
                            logger.error(error_msg)
                            results['errors'].append(error_msg)
                            continue
                    
                    results['cleaned']['eips'] += 1
            except Exception as e:
                error_msg = f"Error in EIP cleanup: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        
        # Clean old snapshots
        if config.get('clean_snapshots', False):
            try:
                days = config.get('snapshot_days', 30)
                old_snapshots = self.find_old_snapshots(days)
                logger.info(f"Found {len(old_snapshots)} old snapshots")
                
                for snapshot in old_snapshots:
                    if not dry_run:
                        try:
                            self.ec2_client.delete_snapshot(SnapshotId=snapshot['SnapshotId'])
                            logger.info(f"Deleted snapshot: {snapshot['SnapshotId']}")
                        except Exception as e:
                            error_msg = f"Error deleting snapshot {snapshot['SnapshotId']}: {e}"
                            logger.error(error_msg)
                            results['errors'].append(error_msg)
                            continue
                    
                    results['cleaned']['snapshots'] += 1
            except Exception as e:
                error_msg = f"Error in snapshot cleanup: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        
        # Clean stopped instances
        if config.get('clean_instances', False):
            try:
                days = config.get('instance_days', 7)
                stopped_instances = self.find_stopped_instances(days)
                logger.info(f"Found {len(stopped_instances)} stopped instances")
                
                for instance in stopped_instances:
                    if not dry_run:
                        try:
                            self.ec2_client.terminate_instances(InstanceIds=[instance['InstanceId']])
                            logger.info(f"Terminated instance: {instance['InstanceId']}")
                        except Exception as e:
                            error_msg = f"Error terminating instance {instance['InstanceId']}: {e}"
                            logger.error(error_msg)
                            results['errors'].append(error_msg)
                            continue
                    
                    results['cleaned']['instances'] += 1
            except Exception as e:
                error_msg = f"Error in instance cleanup: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        
        return results


def lambda_handler(event, context):
    """
    Lambda entry point.
    
    Expected event format:
    {
        "regions": ["us-east-1", "us-west-2"],  # Optional, defaults to current region
        "dry_run": true,                        # Optional, defaults to true
        "clean_eips": true,                     # Optional, defaults to false
        "clean_snapshots": true,                # Optional, defaults to false
        "clean_instances": false,               # Optional, defaults to false
        "snapshot_days": 30,                    # Optional, defaults to 30
        "instance_days": 7                      # Optional, defaults to 7
    }
    """
    
    try:
        # Parse configuration from event
        config = {
            'dry_run': event.get('dry_run', True),
            'clean_eips': event.get('clean_eips', False),
            'clean_snapshots': event.get('clean_snapshots', False),
            'clean_instances': event.get('clean_instances', False),
            'snapshot_days': event.get('snapshot_days', 30),
            'instance_days': event.get('instance_days', 7)
        }
        
        regions = event.get('regions', [boto3.Session().region_name])
        all_results = []
        
        logger.info(f"Starting cleanup in regions: {regions}")
        logger.info(f"Configuration: {config}")
        
        # Process each region
        for region in regions:
            logger.info(f"Processing region: {region}")
            cleaner = LambdaResourceCleaner(region)
            result = cleaner.cleanup_resources(config)
            all_results.append(result)
        
        # Aggregate results
        total_cleaned = {'eips': 0, 'snapshots': 0, 'instances': 0}
        all_errors = []
        
        for result in all_results:
            for resource_type in total_cleaned:
                total_cleaned[resource_type] += result['cleaned'][resource_type]
            all_errors.extend(result['errors'])
        
        response = {
            'statusCode': 200,
            'body': {
                'message': 'Cleanup completed successfully',
                'total_cleaned': total_cleaned,
                'regions_processed': len(regions),
                'dry_run': config['dry_run'],
                'detailed_results': all_results,
                'errors': all_errors
            }
        }
        
        logger.info(f"Cleanup completed. Total cleaned: {total_cleaned}")
        return response
        
    except Exception as e:
        logger.error(f"Lambda execution failed: {e}")
        return {
            'statusCode': 500,
            'body': {
                'error': str(e),
                'message': 'Cleanup failed'
            }
        }