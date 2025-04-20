# filepath: c:\Users\dngoi\source\repos\github\dngoins\ai-skills-fest-davie\CleanUpEvent.py
## This script is responsible for cleaning up events in the system.

import csv
import asyncio
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from azure.identity import ClientSecretCredential
from msgraph import GraphServiceClient
import os
from dotenv import load_dotenv


async def get_group_members(tenant_id, client_id, client_secret, group_id):
    """
    Get members of a specified Microsoft Entra ID group
    
    Args:
        tenant_id (str): Microsoft Entra ID tenant ID
        client_id (str): Application ID for authentication
        client_secret (str): Application secret for authentication
        group_id (str): ID of the group to get members from
        
    Returns:
        list: List of members in the group
    """
    # Initialize Microsoft Graph client
    credentials = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    graph_client = GraphServiceClient(credentials=credentials)
    
    # Get members of the group
    members = await graph_client.groups.by_group_id(group_id).members.get()
    return members

async def save_members_to_csv(members, csv_file_path="./data/Participants.csv"):
    """
    Save group members' information to a CSV file
    
    Args:
        members (list): List of group members
        csv_file_path (str): Path to save the CSV file
    """
    # Check if the CSV file already exists
    file_exists = os.path.isfile(csv_file_path)
    
    # Create a set of existing emails to avoid duplicates
    existing_emails = set()
    if file_exists:
        try:
            with open(csv_file_path, 'r', newline='') as csv_file:
                reader = csv.DictReader(csv_file)
                for row in reader:
                    if 'Email' in row and row['Email']:
                        existing_emails.add(row['Email'].lower())
        except Exception as e:
            print(f"Error reading existing CSV file: {str(e)}")
    
    # Open file in append mode if it exists, otherwise create a new one
    mode = 'a' if file_exists else 'w'
    with open(csv_file_path, mode, newline='') as csv_file:
        fieldnames = ['First Name', 'Email']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        
        # Write header only if creating a new file
        if not file_exists:
            writer.writeheader()
        
        # Track count of new entries
        new_entries_count = 0
        for member in members.value:
            # Use default values if attributes are not available
            display_name = member.display_name if hasattr(member, 'display_name') and member.display_name else "Unknown User"
            email = member.mail if hasattr(member, 'mail') and member.mail else ""
            
            # Extract first name and last name
            name_parts = display_name.split()
            first_name = name_parts[0] if name_parts else ""
                        
            # Skip if no email available
            if not email:
                print(f"Skipping member with no email: {display_name}")
                continue
            
            # Check if this email is already in the CSV (case insensitive)
            if email.lower() in existing_emails:
                print(f"Skipping existing member: {display_name} ({email})")
                continue
                
            # Write to CSV
            writer.writerow({
                'First Name': first_name, 
                'Email': email
            })
            
            # Add to tracking
            new_entries_count += 1
            existing_emails.add(email.lower())
            print(f"Added new member: {display_name} ({email})")
    
    print(f"Member information saved to {csv_file_path} ({new_entries_count} new entries added)")
    return csv_file_path


async def sendEmail(sender_email, sender_password, smtp_server, smtp_port, email, first_name,results):
    
    try:
        # Create email message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = email
        msg['Cc'] = "admins@aiskillsfest.net"
        msg['Subject'] = "Thank You for Attending AI Skills Fest!"
        
        # Email body
        body = f"""
        <html>
        <body>
            <p>Dear {first_name},</p>
            <p>Thank you for registering and attending the AI Skills Fest event! We hope you enjoyed the sessions and found them valuable.</p>
            <p>We're looking forward to seeing you at future events. If you have any feedback or questions, please don't hesitate to reach out, please contact our <a href="mailto:admins@aiskillsfest.net?subject=Inquiry&body=Hello,%20I%20have%20a%20question%20about..." >support team</a> about upcoming events or just saying hi!</p>                        
            <p>Best regards,<br><a href="https://aiskillsfest.com">The AI Skills Fest Team</a></p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        # Set up SMTP server and send email
        cc_emails = ["admins@aiskillsfest.net"]
        recipients = [email] + cc_emails
        
        # Send email
        # Connect to SMTP server if email info provided
        if all([smtp_server, smtp_port, sender_email, sender_password]):
            try:
                with smtplib.SMTP(smtp_server, smtp_port) as server:
                    server.starttls()  # Secure the connection
                    server.login(sender_email, sender_password)
                    server.sendmail(sender_email, recipients, msg.as_string())
                    server.quit()
                    print("Connected to SMTP server for sending thank you emails")
            except Exception as e:
                print(f"Failed to connect to SMTP server: {str(e)}")
        
        results['sent_emails'] += 1
        print(f"Thank you email sent to {email} ({first_name})")
    except Exception as e:
        print(f"Failed to send thank you email to {email}: {str(e)}")
 

async def send_thank_you_emails(csv_file_path, smtp_server, smtp_port, sender_email, sender_password):
    """
    Send thank you emails to event participants
    
    Args:
        csv_file_path (str): Path to the CSV file with participant information
        smtp_server (str): SMTP server for sending emails
        smtp_port (int): SMTP server port
        sender_email (str): Email address to send emails from
        sender_password (str): Password for sender email account
    """
    # Read participant information from CSV
    participants = []
    with open(csv_file_path, 'r') as csv_file:
        csv_reader = csv.DictReader(csv_file)
        for row in csv_reader:
            participants.append(row)
    
    # Send thank you emails
    for participant in participants:
        first_name = participant.get('First Name', '')
        email = participant.get('Email', '')
        
        if not email:
            continue
        
    results = {'sent_emails': 0}
    await sendEmail(sender_email, sender_password, smtp_server, smtp_port, email, first_name, results)

    print("All thank you emails sent successfully!")

async def remove_exgroup_members_from_tenant(tenant_id, client_id, client_secret, members):
    """
    Remove members from the Microsoft Entra ID tenant
    
    Args:
        tenant_id (str): Microsoft Entra ID tenant ID
        client_id (str): Application ID for authentication
        client_secret (str): Application secret for authentication
        members (list): List of members to remove
        
    Returns:
        int: Number of members successfully removed
    """

    # Initialize Microsoft Graph client
    credentials = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    graph_client = GraphServiceClient(credentials=credentials)
    
    removed_count = 0
    
    # Remove each member from the tenant, but first check if they're actually users
    for member in members.value:
        if hasattr(member, 'id') and member.id:
            try:
                # Check if the member is a user by getting their odata_type
                is_user = False
                if hasattr(member, 'odata_type') and member.odata_type:
                    is_user = "#microsoft.graph.user" in member.odata_type
                else:
                    # Get the full user object to check if it's a user
                    try:
                        user_details = await graph_client.users.by_user_id(member.id).get()
                        is_user = True
                    except Exception:
                        is_user = False
                
                if not is_user:
                    print(f"Skipping member {member.id} - not a user object")
                    continue
                
                # Remove user from tenant
                await graph_client.users.by_user_id(member.id).delete()
                
                # Print name and email if available
                name = member.display_name if hasattr(member, 'display_name') and member.display_name else "Unknown"
                email = member.mail if hasattr(member, 'mail') and member.mail else "Unknown"
                print(f"Removed user from tenant: {name} ({email})")
                
                removed_count += 1
            except Exception as e:
                print(f"Failed to remove user {member.id} from tenant: {str(e)}")
    
    return removed_count


async def remove_members_from_group(tenant_id, client_id, client_secret, group_id, members):
    """
    Remove members from a specified Microsoft Entra ID group
    
    Args:
        tenant_id (str): Microsoft Entra ID tenant ID
        client_id (str): Application ID for authentication
        client_secret (str): Application secret for authentication
        group_id (str): ID of the group to remove members from
        members (list): List of members to remove
        
    Returns:
        int: Number of members successfully removed
    """
    # Initialize Microsoft Graph client
    credentials = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    graph_client = GraphServiceClient(credentials=credentials)
    
    removed_count = 0
    
    # Remove each member from the group
    for member in members.value:
        if hasattr(member, 'id') and member.id:
            try:
                # Remove member from group
                await graph_client.groups.by_group_id(group_id).members.by_directory_object_id(member.id).ref.delete()
                
                # Print name and email if available
                name = member.display_name if hasattr(member, 'display_name') and member.display_name else "Unknown"
                email = member.mail if hasattr(member, 'mail') and member.mail else "Unknown"
                print(f"Removed member: {name} ({email})")
                
                removed_count += 1
            except Exception as e:
                print(f"Failed to remove member {member.id}: {str(e)}")
    
    return removed_count

async def remove_participants_from_tenant(tenant_id, client_id, client_secret, csv_file_path="./data/Participants.csv"):
    """
    Read participant emails from CSV, get their member IDs, and remove them from the tenant
    
    Args:
        tenant_id (str): Microsoft Entra ID tenant ID
        client_id (str): Application ID for authentication
        client_secret (str): Application secret for authentication
        csv_file_path (str): Path to the CSV file with participant information
        
    Returns:
        int: Number of users successfully removed from the tenant
    """
    # Initialize Microsoft Graph client
    credentials = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    graph_client = GraphServiceClient(credentials=credentials)
    
    # Read participant emails from CSV
    participant_emails = []
    try:
        with open(csv_file_path, 'r', newline='') as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                if 'Email' in row and row['Email']:
                    participant_emails.append(row['Email'].lower())
    except Exception as e:
        print(f"Error reading CSV file: {str(e)}")
        return 0
    
    print(f"Found {len(participant_emails)} participant emails in the CSV file")
    
    # Track removal count
    removed_count = 0
    
    # Process each participant email
    for email in participant_emails:
        try:            # Extract email handle (part before the @ symbol)
            email_handle = email.split('@')[0] if '@' in email else email
            
            # Create the expected user principal name in the format "handle@aiskillsfest.net"
            user_principal_name = f"{email_handle}@aiskillsfest.net"
            
            # Find the user by email or user principal name
            from msgraph.generated.users.users_request_builder import UsersRequestBuilder
            request_configuration = UsersRequestBuilder.UsersRequestBuilderGetRequestConfiguration(
                query_parameters=UsersRequestBuilder.UsersRequestBuilderGetQueryParameters(
                    filter=f"mail eq '{email}' or userPrincipalName eq '{user_principal_name}'"
                )
            )
            users = await graph_client.users.get(request_configuration=request_configuration)
            
            if not users.value or len(users.value) == 0:
                print(f"No user found with email: {email} or UPN: {user_principal_name}")
                continue
            
            # Process each matching user (should typically be just one)
            for user in users.value:
                if hasattr(user, 'id') and user.id:
                    try:
                        # Remove user from tenant
                        await graph_client.users.by_user_id(user.id).delete()
                        
                        # Get user display name if available
                        name = user.display_name if hasattr(user, 'display_name') and user.display_name else "Unknown"
                        upn = user.user_principal_name if hasattr(user, 'user_principal_name') else "Unknown UPN"
                        print(f"Removed user from tenant: {name} ({email}, UPN: {upn})")
                        
                        removed_count += 1
                    except Exception as e:
                        print(f"Failed to remove user with email {email}: {str(e)}")
        except Exception as e:
            print(f"Error processing email {email}: {str(e)}")
    
    return removed_count
           

async def process_additional_subscribers(tenant_id, client_id, client_secret, group_id, csv_file_path="./data/postRegistration.csv", participants_csv="./data/participants.csv", smtp_server=None, smtp_port=None, sender_email=None, sender_password=None):
    """
    Process additional subscribers from a separate CSV file:
    1. Check if they exist in the group
    2. Add them to Participants.csv if they're not already there
    3. Send thank you emails
    4. Remove them from the group and tenant
    
    Args:
        tenant_id (str): Microsoft Entra ID tenant ID
        client_id (str): Application ID for authentication
        client_secret (str): Application secret for authentication
        group_id (str): ID of the group to check and remove members from
        csv_file_path (str): Path to the CSV file with additional subscribers
        participants_csv (str): Path to the main participants CSV file
        smtp_server (str): SMTP server for sending emails
        smtp_port (int): SMTP server port
        sender_email (str): Email address to send emails from
        sender_password (str): Password for sender email account
        
    Returns:
        dict: Results with counts of processed subscribers
    """
    # Initialize Microsoft Graph client
    credentials = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    graph_client = GraphServiceClient(credentials=credentials)
    
    # Load existing participants to avoid duplicates
    existing_emails = set()
    if os.path.isfile(participants_csv):
        try:
            with open(participants_csv, 'r', newline='') as csv_file:
                reader = csv.DictReader(csv_file)
                for row in reader:
                    if 'Email' in row and row['Email']:
                        existing_emails.add(row['Email'].lower())
        except Exception as e:
            print(f"Error reading existing participants CSV file: {str(e)}")
    
    # Read subscribers from CSV
    subscribers = []
    try:
        with open(csv_file_path, 'r', newline='') as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                if 'Email' in row and row['Email'] and 'First Name' in row:
                    subscribers.append({
                        'first_name': row['First Name'],
                        'email': row['Email'].lower()
                    })
    except Exception as e:
        print(f"Error reading subscribers CSV file: {str(e)}")
        return {'added_to_participants': 0, 'sent_emails': 0, 'removed_from_group': 0, 'removed_from_tenant': 0}
    
    print(f"Found {len(subscribers)} subscribers in {csv_file_path}")
    
    # Get current group members
    members = await graph_client.groups.by_group_id(group_id).members.get()
    
    # Create dictionary of member emails for quick lookup
    member_emails = {}
    for member in members.value:
        if hasattr(member, 'mail') and member.mail:
            member_emails[member.mail.lower()] = member
    
    # Track progress
    results = {
        'added_to_participants': 0,
        'sent_emails': 0,
        'removed_from_group': 0,
        'removed_from_tenant': 0
    }
    
    # Open participants CSV in append mode
    with open(participants_csv, 'a', newline='') as csv_file:
        fieldnames = ['First Name', 'Email']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                
        # Process each subscriber
        for subscriber in subscribers:
            email = subscriber['email']
            first_name = subscriber['first_name']
            
            # Check if already in participants.csv
            if email in existing_emails:
                print(f"Subscriber {email} already in participants CSV")
                continue
            
            # Add to participants.csv
            writer.writerow({'First Name': first_name, 'Email': email})
            existing_emails.add(email)
            results['added_to_participants'] += 1
            print(f"Added subscriber to participants CSV: {first_name} ({email})")
            
            # Send thank you email if SMTP connection available
            await sendEmail(sender_email, sender_password, smtp_server, smtp_port, email, first_name, results)

            # Remove from group if member exists
            if email in member_emails:
                member = member_emails[email]
                if hasattr(member, 'id') and member.id:
                    try:
                        # Remove member from group
                        await graph_client.groups.by_group_id(group_id).members.by_directory_object_id(member.id).ref.delete()
                        results['removed_from_group'] += 1
                        print(f"Removed member from group: {first_name} ({email})")
                    except Exception as e:
                        print(f"Failed to remove member {email} from group: {str(e)}")
            
            # Try to remove from tenant using email and handle@aiskillsfest.net
            try:
                # Extract email handle (part before the @ symbol)
                email_handle = email.split('@')[0] if '@' in email else email
                
                # Create the expected user principal name in the format "handle@aiskillsfest.net"
                user_principal_name = f"{email_handle}@aiskillsfest.net"
                
                # Find the user by email or user principal name
                from msgraph.generated.users.users_request_builder import UsersRequestBuilder
                request_configuration = UsersRequestBuilder.UsersRequestBuilderGetRequestConfiguration(
                    query_parameters=UsersRequestBuilder.UsersRequestBuilderGetQueryParameters(
                        filter=f"mail eq '{email}' or userPrincipalName eq '{user_principal_name}'"
                    )
                )
                users = await graph_client.users.get(request_configuration=request_configuration)
                
                if users.value and len(users.value) > 0:
                    # Process each matching user (should typically be just one)
                    for user in users.value:
                        if hasattr(user, 'id') and user.id:
                            try:
                                # Remove user from tenant
                                await graph_client.users.by_user_id(user.id).delete()
                                
                                # Get user display name and UPN if available
                                name = user.display_name if hasattr(user, 'display_name') and user.display_name else "Unknown"
                                upn = user.user_principal_name if hasattr(user, 'user_principal_name') else "Unknown UPN"
                                print(f"Removed user from tenant: {name} ({email}, UPN: {upn})")
                                
                                results['removed_from_tenant'] += 1
                            except Exception as e:
                                print(f"Failed to remove user with email {email}: {str(e)}")
                else:
                    print(f"No user found in tenant with email: {email} or UPN: {user_principal_name}")
            except Exception as e:
                print(f"Error processing email {email} for tenant removal: {str(e)}")
        
       
    print(f"Results of processing {csv_file_path}:")
    print(f"- Added to participants CSV: {results['added_to_participants']}")
    print(f"- Thank you emails sent: {results['sent_emails']}")
    print(f"- Removed from group: {results['removed_from_group']}")
    print(f"- Removed from tenant: {results['removed_from_tenant']}")
    
    return results

async def main():
    """
    Main function to execute the cleanup process
    """
    # Get Azure settings from environment variables
    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    group_id = os.getenv("AISKILLSFEST_LEARNERS_GROUP_ID")
    sp_group_id = os.getenv("AISKILLSFEST_SHAREPOINT_GROUP_ID")
    
    # Get SMTP settings from environment variables
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    sender_email = os.getenv("SMTP_EMAIL")
    sender_password = os.getenv("SMTP_PASSWORD")
   
    try:
        # Get members of the AISkillsFestLearners group
        print(f"Getting members of the AISkillsFestLearners group (ID: {group_id})...")
        members = await get_group_members(tenant_id, client_id, client_secret, group_id)
        print(f"Found {len(members.value) if hasattr(members, 'value') else 0} members in the group")
        
        # Save member information to CSV
        print("Saving member information to CSV...")
        csv_file_path = await save_members_to_csv(members)
        
        # Send thank you emails
        print("Sending thank you emails...")
        await send_thank_you_emails(csv_file_path, smtp_server, smtp_port, sender_email, sender_password)
        
        # Remove members from the group                
        print("Removing members from the group...")
        removed_count = await remove_members_from_group(tenant_id, client_id, client_secret, group_id, members)
        print(f"Successfully removed {removed_count} members from the group")
        
        print("Removing members from AISkillsFest Tenant...")
        removed_count = await remove_exgroup_members_from_tenant(tenant_id, client_id, client_secret, members)
        print(f"Successfully removed {removed_count} members from the tenant")
        
        print("Removing participants from AISkillsFest Tenant using CSV data...")
        removed_count = await remove_participants_from_tenant(tenant_id, client_id, client_secret, csv_file_path)
        print(f"Successfully removed {removed_count} participants from the tenant")
        
         # Process additional subscribers from subscriberShorts.csv
        print("\nProcessing additional subscribers from subscriberShorts.csv...")
        subscriber_results = await process_additional_subscribers(
            tenant_id, 
            client_id, 
            client_secret, 
            group_id, 
            "./data/subscriberShorts.csv", 
            csv_file_path,
            smtp_server, 
            smtp_port, 
            sender_email, 
            sender_password
        )
        
        print("Cleanup process completed successfully!")
    
    except Exception as e:
        print(f"An error occurred during the cleanup process: {str(e)}")

# Run the script
if __name__ == "__main__":
    # Load environment variables from .env file
    load_dotenv()

    asyncio.run(main())

