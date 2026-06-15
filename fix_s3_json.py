import boto3
import json
import re

s3 = boto3.client('s3', region_name='us-east-1')
import os
# get bucket name using python so we dont need hardcoded
import boto3
import json

bucket = os.environ['DATALAKE_BUCKET']

paginator = s3.get_paginator('list_objects_v2')
pages = paginator.paginate(Bucket=bucket, Prefix='events/')

for page in pages:
    if 'Contents' not in page: continue
    for obj in page['Contents']:
        key = obj['Key']
        if key.endswith('/'): continue
        
        resp = s3.get_object(Bucket=bucket, Key=key)
        content = resp['Body'].read().decode('utf-8', errors='ignore')
        
        lines = content.split('\n')
        new_lines = []
        changed = False
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # Case 1: Old SQS envelope
            if line.startswith('{"messageId":'):
                try:
                    obj = json.loads(line)
                    body_str = obj.get('body', '{}')
                    # body_str is usually a JSON string
                    # Just append it as the line
                    new_lines.append(body_str)
                    changed = True
                    continue
                except Exception as e:
                    pass
                    
            # Case 2: Broken eventbridge object like {order_id:6,status:CONFIRMED,...}
            if line.startswith('{order_id:'):
                try:
                    # Fix keys and values
                    # It looks like: {order_id:6,status:CONFIRMED,restaurant_id:3,region_id:1,timestamp:2026-06-15T05:29:32.103292+00:00}
                    # We can use regex to wrap keys in quotes and string values in quotes
                    # But actually we know exactly the format!
                    # Let's just do simple regex replacements
                    line = re.sub(r'([{,])([a-z_]+):', r'\1"\2":', line)
                    # Values: CONFIRMED, 2026-... need quotes
                    line = line.replace(':CONFIRMED', ':"CONFIRMED"')
                    line = line.replace(':PREPARING', ':"PREPARING"')
                    line = line.replace(':READY_FOR_PICKUP', ':"READY_FOR_PICKUP"')
                    line = line.replace(':PICKED_UP', ':"PICKED_UP"')
                    line = line.replace(':IN_TRANSIT', ':"IN_TRANSIT"')
                    line = line.replace(':DELIVERED', ':"DELIVERED"')
                    line = line.replace(':CANCELLED', ':"CANCELLED"')
                    # Timestamp value
                    line = re.sub(r':(2026-[^}]+)}', r':"\1"}', line)
                    new_lines.append(line)
                    changed = True
                    continue
                except Exception as e:
                    pass
            
            # Case 3: Already valid JSON
            new_lines.append(line)
            
        if changed:
            new_content = '\n'.join(new_lines)
            s3.put_object(Bucket=bucket, Key=key, Body=new_content.encode('utf-8'))
            print(f"Fixed {key}")

