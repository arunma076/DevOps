import boto3
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import csv
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# List of regions to check
regions = ['ap-south-1', 'ap-southeast-1', 'me-south-1', 'me-central-1']

# Account IDs and corresponding names
account_names = {
    "538459208795": "Aurex",
    "540746789084": "Digital",
    "519366970446": "Invest-Bank",
    "606273301575": "DDA",
    "885358077472": "Amalak",
    "383575894474": "Tabreed",
    "329040483280": "Yelo"

}

def get_unused_volumes(region, account_id):
    if account_id == "538459208795":
        logger.info(f"Using default credentials for source account: {account_id}")
        ec2 = boto3.client('ec2', region_name=region)
    else:
        sts_client = boto3.client('sts')
        role_arn = f"arn:aws:iam::{account_id}:role/UnusedEBVolumeCrossAccount"
        try:
            logger.info(f"Assuming role {role_arn}")
            assumed_role = sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName="AssumeRoleSession"
            )
            credentials = assumed_role['Credentials']
            ec2 = boto3.client(
                'ec2',
                region_name=region,
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )
        except Exception as e:
            logger.error(f"Error assuming role for account {account_id} in region {region}: {e}")
            return []

    try:
        volumes = ec2.describe_volumes()['Volumes']
        unused_volumes = [
            {
                'VolumeId': vol['VolumeId'],
                'VolumeName': next((tag['Value'] for tag in vol.get('Tags', []) if tag['Key'] == 'Name'), "N/A"),
                'Region': region,
                'AccountId': account_id,
                'Name': account_names.get(account_id, ''),
                'CreationDate': vol['CreateTime'].strftime("%Y-%m-%d %H:%M:%S")
            }
            for vol in volumes if not vol['Attachments']
        ]
        return unused_volumes
    except Exception as e:
        logger.error(f"Error describing volumes for account {account_id} in region {region}: {e}")
        return []

def create_csv(volumes, file_path):
    with open(file_path, 'w', newline='') as csvfile:
        fieldnames = ["VolumeId", "VolumeName", "Region", "AccountId", "Name", "CreationDate"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for volume in volumes:
            writer.writerow(volume)

def send_email(file_path, smtp_config, sender, recipient, cc_recipient, subject, body):
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = recipient
    msg['Cc'] = cc_recipient
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    with open(file_path, "rb") as attachment:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="unused_volumes.csv"')
        msg.attach(part)
    with smtplib.SMTP(smtp_config['host'], smtp_config['port']) as server:
        server.starttls()
        server.login(smtp_config['user'], smtp_config['password'])
        recipients = [recipient] + [cc_recipient]
        server.sendmail(sender, recipients, msg.as_string())

def lambda_handler(event, context):
    all_unused_volumes = []
    for account_id, account_name in account_names.items():
        logger.info(f"Processing account: {account_name} ({account_id})")
        for region in regions:
            logger.info(f"Checking region: {region} for account: {account_id}")
            unused_volumes = get_unused_volumes(region, account_id)
            for volume in unused_volumes:
                volume['AccountId'] = account_id
                volume['Name'] = account_name
            all_unused_volumes.extend(unused_volumes)  # Add volumes to the combined list

    # Create the CSV file with combined volumes from all accounts
    file_path = "/tmp/unused_volumes.csv"
    try:
        create_csv(all_unused_volumes, file_path)
    except Exception as e:
        logger.error(f"Error writing report to file: {e}")

    smtp_config = {
        'host': 'email-smtp.ap-south-1.amazonaws.com',
        'port': 587,
        '#user': ,
        '#password':
    }
    send_email(file_path, smtp_config, 'devops@beinex.com', 'devops@beinex.com', 'Warning - Unused Volume List', 'This email is being sent to provide you with information regarding the details of unused EBS volumes in each account. Please review the attached file and take appropriate action as necessary.')
    return "success"
