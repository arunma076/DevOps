import boto3
import dns.resolver
import json
import mysql.connector
import smtplib
import os
from botocore.exceptions import ClientError
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Define MySQL connection parameters
mysql_host = os.getenv('MYSQL_HOST')  # Replace with your MySQL host
mysql_user = os.getenv('MYSQL_USER')# Replace with your MySQL username
mysql_password = os.getenv('MYSQL_PASS') # Replace with your MySQL password
mysql_database = os.getenv('MYSQL_DB') # Replace with your MySQL database name

# Initialize S3 client for logging
s3 = boto3.client('s3')
log_bucket = 'dns-change-logs'

# Fetch environment variables
DOMAIN_NAMES = os.getenv('DOMAIN_NAMES', '').split(',')
SENDER = os.getenv('SENDER_EMAIL')
RECIPIENT = os.getenv('RECIPIENT_EMAIL')
SMTP_USERNAME = os.getenv('SMTP_USERNAME')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
SMTP_SERVER = os.getenv('SMTP_SERVER', 'email-smtp.us-east-1.amazonaws.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))

def query_dns(domain):
    resolver = dns.resolver.Resolver()
    result = {}
    for record_type in ['A', 'AAAA', 'MX', 'NS', 'TXT', 'CNAME', 'NS', 'PTR', 'SOA']:
        try:
            answers = resolver.resolve(domain, record_type)
            result[record_type] = [rdata.to_text() for rdata in answers]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            result[record_type] = []
    return result

def get_previous_records(domain, cursor):
    try:
        query = "SELECT records FROM DNSRecords WHERE domain = %s"
        cursor.execute(query, (domain,))
        record = cursor.fetchone()
        if record:
            return json.loads(record[0])
        else:
            print(f"No item found in MySQL for domain: {domain}")
            return None  # Return None if no item found
    except mysql.connector.Error as e:
        print(f"Error retrieving item from MySQL: {e}")
        return None  # Return None on error
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None  # Return None on unexpected error

def store_current_records(domain, records, cursor, connection):
    try:
        records_json = json.dumps(records)
        query = "INSERT INTO DNSRecords (domain, records) VALUES (%s, %s) ON DUPLICATE KEY UPDATE records = %s"
        cursor.execute(query, (domain, records_json, records_json))
        connection.commit()
        print(f"Successfully stored records for domain: {domain}")
    except mysql.connector.Error as e:
        print(f"Error storing item in MySQL: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

def log_changes(domain, changes):
    log_key = f"{domain}-changes.log"
    try:
        # Retrieve existing log or initialize empty
        try:
            existing_log = s3.get_object(Bucket=log_bucket, Key=log_key)['Body'].read().decode('utf-8')
        except s3.exceptions.NoSuchKey:
            existing_log = ""

        # Append new log entry
        new_log_entry = json.dumps(changes, indent=2) + "\n"
        updated_log = existing_log + new_log_entry

        # Store updated log in S3
        s3.put_object(Bucket=log_bucket, Key=log_key, Body=updated_log)
        print(f"Successfully logged changes for domain: {domain}")
    except ClientError as e:
        print(f"Error storing log in S3: {e.response['Error']['Message']}")
    except Exception as e:
        print(f"Unexpected error: {e}")

def send_email(subject, body):
    # Create a multipart message
    msg = MIMEMultipart()
    msg['From'] = SENDER
    msg['To'] = RECIPIENT
    msg['Subject'] = subject

    # Attach the body with the msg instance
    msg.attach(MIMEText(body, 'plain'))

    try:
        # Connect to the server
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        text = msg.as_string()
        server.sendmail(SENDER, RECIPIENT, text)
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")

def lambda_handler(event, context):
    connection = None
    cursor = None
    try:
        # Connect to MySQL database
        connection = mysql.connector.connect(
            host=mysql_host,
            user=mysql_user,
            password=mysql_password,
            database=mysql_database
        )
        cursor = connection.cursor()

        for domain in DOMAIN_NAMES:
            current_records = query_dns(domain)
            previous_records = get_previous_records(domain, cursor)
            
            if previous_records is None:
                # First time checking this domain, store current records
                store_current_records(domain, current_records, cursor, connection)
                print(f"No previous records found for domain: {domain}. Storing current records.")
                continue

            if not compare_records(current_records, previous_records):
                changes = {
                    'domain': domain,
                    'previous': previous_records,
                    'current': current_records
                }
                log_changes(domain, changes)  # Log the detected changes
                store_current_records(domain, current_records, cursor, connection)  # Update MySQL with current records
                
                # Send an email notification
                email_body = f"DNS records changed for domain: {domain}\n\nChanges:\n{json.dumps(changes, indent=2)}"
                send_email(f"ALERT: DNS records changed for {domain}", email_body)
                
                print(f"Alert: DNS records changed for domain: {domain}")

        return {
            'statusCode': 200,
            'body': json.dumps('DNS check complete')
        }

    except Exception as e:
        print(f"Error in lambda_handler: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps('Error in lambda_handler')
        }

    finally:
        # Close MySQL connection
        if cursor:
            cursor.close()
        if connection:
            connection.close()
            print("MySQL connection closed")

def compare_records(current_records, previous_records):
    """
    Compare DNS records, ignoring order of lists.
    """
    for record_type in current_records.keys():
        if set(current_records.get(record_type, [])) != set(previous_records.get(record_type, [])):
            return False
    return True
