"""
tools/utils.py
--------------
Shared helpers for EC2 provisioning, SSH, and file transfer.
"""

from __future__ import annotations

import boto3
import gzip
import os
import paramiko
import shutil
import sys
import time


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def make_ec2_client(region: str) -> boto3.client:
    """
    Creates a boto3 EC2 client for the given region.
    """
    return boto3.client("ec2", region_name=region)


# # ---------------------------------------------------------------------------
# # Instance lifecycle
# # ---------------------------------------------------------------------------

def get_latest_amazon_linux_ami(region) -> str:
    """
    Fetches the latest Amazon Linux 2 AMI ID for the configured region.
    """
    ssm = boto3.client("ssm", region_name=region)
    param = ssm.get_parameter(
        Name="/aws/service/ami-amazon-linux-latest/amzn2-ami-hvm-x86_64-gp2"
    )
    ami_id = param["Parameter"]["Value"]
    print(f"    Resolved AMI: {ami_id}")
    return ami_id


# def create_instance(ec2, ami_id: str, instance_type: str,
#                     key_pair_name: str, security_group_id: str,
#                     tag_name: str = "fgv-cloud-lab") -> str:
#     """
#     Launches an EC2 instance and returns its instance ID.
#     """
#     print(f"  [create] {instance_type} | AMI {ami_id}")
#     instance_params = {
#         "ImageId": ami_id,
#         "InstanceType": instance_type,
#         "KeyName": key_pair_name,
#         "SecurityGroupIds": [security_group_id],
#         "MinCount": 1,
#         "MaxCount": 1,
#         "TagSpecifications": [{
#             "ResourceType": "instance",
#             "Tags": [{"Key": "Name", "Value": tag_name}]
#         }]
#     }
#     if instance_type.startswith(("t2.", "t3.", "t3a.", "t4g.")):
#         # noinspection PyTypeChecker
#         instance_params["CreditSpecification"] = {"CpuCredits": "standard"}
#     response = ec2.run_instances(**instance_params)

#     instance_id = response["Instances"][0]["InstanceId"]
#     print(f"  [create] Instance ID: {instance_id}")
#     return instance_id


# def wait_for_instance(ec2, instance_id: str,
#                       ssh_init_wait: int = 20) -> str:
#     """
#     Waits until the instance is in 'running' state and returns its public IP.

#     Parameters
#     ----------
#     ssh_init_wait : seconds to wait after 'running' for the SSH daemon to start
#     """
#     print(f"  [wait]   Waiting for 'running' state ...")
#     waiter = ec2.get_waiter("instance_running")
#     waiter.wait(InstanceIds=[instance_id])

#     description = ec2.describe_instances(InstanceIds=[instance_id])
#     public_ip   = description["Reservations"][0]["Instances"][0]["PublicIpAddress"]
#     print(f"  [wait]   Running. IP: {public_ip}. Waiting {ssh_init_wait}s for SSH ...")
#     time.sleep(ssh_init_wait)

#     return public_ip


# def terminate_instance(ec2, instance_id: str) -> None:
#     """
#     Terminates the EC2 instance.
#     """
#     print(f"  [terminate] {instance_id}")
#     ec2.terminate_instances(InstanceIds=[instance_id])


# # ---------------------------------------------------------------------------
# # SSH / SFTP
# # ---------------------------------------------------------------------------

# def connect_ssh(public_ip: str, ssh_user: str,
#                 private_key_path: str,
#                 retries: int = 5,
#                 retry_wait: int = 10) -> paramiko.SSHClient:
#     """
#     Opens an SSH connection and returns the connected Paramiko client.
#     Retries up to `retries` times to handle slow SSH daemon startup.
#     """
#     key_path = os.path.expanduser(private_key_path)
#     key = paramiko.RSAKey.from_private_key_file(key_path)

#     client = paramiko.SSHClient()
#     client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

#     for attempt in range(1, retries + 1):
#         try:
#             client.connect(hostname=public_ip, username=ssh_user,
#                            pkey=key, timeout=10)
#             print(f"  [ssh]    Connected to {public_ip}")
#             return client
#         except Exception as e:
#             print(f"  [ssh]    Attempt {attempt}/{retries} failed: {e}. "
#                   f"Retrying in {retry_wait}s ...")
#             time.sleep(retry_wait)

#     print("ERROR: Could not connect via SSH after all attempts.")
#     sys.exit(1)


# def compress(path: str) -> str:
#     """
#     Compresses a file with gzip and returns the .gz path.
#     """
#     gz_path = path + ".gz"
#     with open(path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
#         shutil.copyfileobj(f_in, f_out)
#     return gz_path


# def upload_files(ssh_client: paramiko.SSHClient,
#                  files: list[tuple[str, str]]) -> None:
#     """
#     Uploads files to the remote instance via SFTP.

#     Parameters
#     ----------
#     files : list of (local_path, remote_path) pairs
#     """
#     sftp = ssh_client.open_sftp()
#     sftp.get_channel().setblocking(True)
#     sftp.MAX_PACKET_SIZE = 32768
#     for local_path, remote_path in files:
#         if not os.path.isfile(local_path):
#             print(f"ERROR: Local file not found: '{local_path}'")
#             sftp.close()
#             sys.exit(1)
#         size_kb = os.path.getsize(local_path) / 1024
#         print(f"  [upload] {local_path} → {remote_path} ({size_kb:.1f} KB)")
#         sftp.put(local_path, remote_path)
#     sftp.close()


# def run_remote(ssh_client: paramiko.SSHClient, command: str) -> str:
#     """
#     Executes a command on the remote instance.
#     Prints stderr if non-empty, and returns stdout as a string.
#     """
#     print(f"  [run]    {command}")
#     _, stdout, stderr = ssh_client.exec_command(command)

#     output = stdout.read().decode("utf-8").strip()
#     errors = stderr.read().decode("utf-8").strip()

#     if errors:
#         print(f"  [stderr]\n{errors}")

#     return output
