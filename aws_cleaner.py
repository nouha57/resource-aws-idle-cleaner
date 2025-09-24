#!/usr/bin/env python3
"""
AWS Idle Resource Cleaner
A cost optimization tool for cleaning up unused AWS resources.
"""

import boto3
import click
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any
from colorama import init, Fore, Style
import logging

# Initialize colorama for cross-platform colored output
init()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AWSResourceCleaner:
    """Main class for AWS resource cleanup operations."""
    
    def __init__(self, region: str = 'us-east-1', dry_run: bool = True):
        self.region = region
        self.dry_run = dry_run
        self.ec2_client = boto3.client('ec2', region_name=region)
        self.session = boto3.Session()
        
    def get_all_regions(self) -> List[str]:
        """Get list of all available AWS regions."""
        try:
            regions = self.ec2_client.describe_regions()
            return [region['RegionName'] for region in regions['Regions']]
        except Exception as e:
            logger.error(f"Error getting regions: {e}")
            return [self.region]
    
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
                        'StartTime': snapshot['StartTime'],
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
                    # Check state transition time
                    for transition in instance.get('StateTransitionReason', ''):
                        if 'stopped' in transition.lower():
                            # Parse the transition time if available
                            state_reason = instance.get('StateReason', {})
                            # For simplicity, we'll use launch time as approximation
                            launch_time = instance['LaunchTime'].replace(tzinfo=None)
                            if launch_time < cutoff_date:
                                old_stopped_instances.append({
                                    'InstanceId': instance['InstanceId'],
                                    'InstanceType': instance['InstanceType'],
                                    'LaunchTime': instance['LaunchTime'],
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
    
    def clean_elastic_ips(self, eips: List[Dict[str, Any]]) -> int:
        """Release unused Elastic IP addresses."""
        cleaned_count = 0
        
        for eip in eips:
            try:
                if self.dry_run:
                    print(f"{Fore.YELLOW}[DRY RUN] Would release EIP: {eip['PublicIp']}{Style.RESET_ALL}")
                else:
                    if eip['Domain'] == 'vpc':
                        self.ec2_client.release_address(AllocationId=eip['AllocationId'])
                    else:
                        self.ec2_client.release_address(PublicIp=eip['PublicIp'])
                    
                    print(f"{Fore.GREEN}Released EIP: {eip['PublicIp']}{Style.RESET_ALL}")
                    logger.info(f"Released EIP: {eip['PublicIp']}")
                
                cleaned_count += 1
            except Exception as e:
                print(f"{Fore.RED}Error releasing EIP {eip['PublicIp']}: {e}{Style.RESET_ALL}")
                logger.error(f"Error releasing EIP {eip['PublicIp']}: {e}")
        
        return cleaned_count
    
    def clean_snapshots(self, snapshots: List[Dict[str, Any]]) -> int:
        """Delete old EBS snapshots."""
        cleaned_count = 0
        
        for snapshot in snapshots:
            try:
                if self.dry_run:
                    print(f"{Fore.YELLOW}[DRY RUN] Would delete snapshot: {snapshot['SnapshotId']} "
                          f"({snapshot['VolumeSize']}GB){Style.RESET_ALL}")
                else:
                    self.ec2_client.delete_snapshot(SnapshotId=snapshot['SnapshotId'])
                    print(f"{Fore.GREEN}Deleted snapshot: {snapshot['SnapshotId']} "
                          f"({snapshot['VolumeSize']}GB){Style.RESET_ALL}")
                    logger.info(f"Deleted snapshot: {snapshot['SnapshotId']}")
                
                cleaned_count += 1
            except Exception as e:
                print(f"{Fore.RED}Error deleting snapshot {snapshot['SnapshotId']}: {e}{Style.RESET_ALL}")
                logger.error(f"Error deleting snapshot {snapshot['SnapshotId']}: {e}")
        
        return cleaned_count
    
    def clean_stopped_instances(self, instances: List[Dict[str, Any]]) -> int:
        """Terminate long-stopped EC2 instances."""
        cleaned_count = 0
        
        for instance in instances:
            try:
                if self.dry_run:
                    print(f"{Fore.YELLOW}[DRY RUN] Would terminate instance: {instance['InstanceId']} "
                          f"({instance['Name']}){Style.RESET_ALL}")
                else:
                    # Add extra confirmation for instance termination
                    if click.confirm(f"Are you sure you want to terminate {instance['InstanceId']} ({instance['Name']})?"):
                        self.ec2_client.terminate_instances(InstanceIds=[instance['InstanceId']])
                        print(f"{Fore.GREEN}Terminated instance: {instance['InstanceId']} "
                              f"({instance['Name']}){Style.RESET_ALL}")
                        logger.info(f"Terminated instance: {instance['InstanceId']}")
                        cleaned_count += 1
                    else:
                        print(f"{Fore.BLUE}Skipped instance: {instance['InstanceId']}{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}Error terminating instance {instance['InstanceId']}: {e}{Style.RESET_ALL}")
                logger.error(f"Error terminating instance {instance['InstanceId']}: {e}")
        
        return cleaned_count


@click.command()
@click.option('--region', default='us-east-1', help='AWS region to scan')
@click.option('--all-regions', is_flag=True, help='Scan all AWS regions')
@click.option('--dry-run/--no-dry-run', default=True, help='Preview changes without applying them')
@click.option('--clean-eips', is_flag=True, help='Clean unused Elastic IPs')
@click.option('--clean-snapshots', is_flag=True, help='Clean old EBS snapshots')
@click.option('--clean-instances', is_flag=True, help='Clean stopped EC2 instances')
@click.option('--days', default=30, help='Age threshold in days for snapshots/instances')
@click.option('--force', is_flag=True, help='Skip confirmation prompts')
def main(region, all_regions, dry_run, clean_eips, clean_snapshots, clean_instances, days, force):
    """AWS Idle Resource Cleaner - Optimize your AWS costs by cleaning unused resources."""
    
    print(f"{Fore.CYAN}AWS Idle Resource Cleaner{Style.RESET_ALL}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE CLEANUP'}")
    print("-" * 50)
    
    regions_to_scan = []
    if all_regions:
        cleaner = AWSResourceCleaner(region, dry_run)
        regions_to_scan = cleaner.get_all_regions()
        print(f"Scanning {len(regions_to_scan)} regions...")
    else:
        regions_to_scan = [region]
        print(f"Scanning region: {region}")
    
    total_cleaned = {'eips': 0, 'snapshots': 0, 'instances': 0}
    
    for current_region in regions_to_scan:
        print(f"\n{Fore.BLUE}Region: {current_region}{Style.RESET_ALL}")
        cleaner = AWSResourceCleaner(current_region, dry_run)
        
        # Clean Elastic IPs
        if clean_eips:
            print(f"\n{Fore.MAGENTA}Finding unused Elastic IPs...{Style.RESET_ALL}")
            unused_eips = cleaner.find_unused_elastic_ips()
            if unused_eips:
                print(f"Found {len(unused_eips)} unused Elastic IPs")
                if not dry_run and not force:
                    if not click.confirm("Proceed with EIP cleanup?"):
                        continue
                cleaned = cleaner.clean_elastic_ips(unused_eips)
                total_cleaned['eips'] += cleaned
            else:
                print("No unused Elastic IPs found")
        
        # Clean old snapshots
        if clean_snapshots:
            print(f"\n{Fore.MAGENTA}Finding old snapshots (>{days} days)...{Style.RESET_ALL}")
            old_snapshots = cleaner.find_old_snapshots(days)
            if old_snapshots:
                print(f"Found {len(old_snapshots)} old snapshots")
                if not dry_run and not force:
                    if not click.confirm("Proceed with snapshot cleanup?"):
                        continue
                cleaned = cleaner.clean_snapshots(old_snapshots)
                total_cleaned['snapshots'] += cleaned
            else:
                print("No old snapshots found")
        
        # Clean stopped instances
        if clean_instances:
            print(f"\n{Fore.MAGENTA}Finding stopped instances (>{days} days)...{Style.RESET_ALL}")
            stopped_instances = cleaner.find_stopped_instances(days)
            if stopped_instances:
                print(f"Found {len(stopped_instances)} long-stopped instances")
                if not dry_run and not force:
                    if not click.confirm("Proceed with instance cleanup?"):
                        continue
                cleaned = cleaner.clean_stopped_instances(stopped_instances)
                total_cleaned['instances'] += cleaned
            else:
                print("No long-stopped instances found")
    
    # Summary
    print(f"\n{Fore.GREEN}Cleanup Summary:{Style.RESET_ALL}")
    print(f"Elastic IPs: {total_cleaned['eips']}")
    print(f"Snapshots: {total_cleaned['snapshots']}")
    print(f"Instances: {total_cleaned['instances']}")
    
    if dry_run:
        print(f"\n{Fore.YELLOW}This was a dry run. Use --no-dry-run to apply changes.{Style.RESET_ALL}")


if __name__ == '__main__':
    main()