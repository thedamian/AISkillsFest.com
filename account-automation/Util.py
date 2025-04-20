import csv
import re
import smtplib
import asyncio
import string
import secrets
import requests
import json
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from azure.identity import ClientSecretCredential
from msgraph import GraphServiceClient
from msgraph.generated.models.user import User
from msgraph.generated.models.password_profile import PasswordProfile
from license_skuids import LICENSE_SKUIDS
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def get_email_handle(email):
    """
    Extract the handle part from an email address (before the @ symbol)
    """
    if not email:
        return None
    match = re.match(r'^([^@]+)@', email.lower())
    return match.group(1) if match else None

async def check_user_exists(user_principal_name, tenant_id, client_id, client_secret):
    """
    Check if a user with the given principal name already exists in the Entra ID tenant
    
    Args:
        user_principal_name (str): The user principal name to check
        tenant_id (str): Microsoft Entra ID tenant ID
        client_id (str): Application ID for authentication
        client_secret (str): Application secret for authentication
        
    Returns:
        tuple: (exists, user_id) where exists is a boolean and user_id is the ID if the user exists
    """
    # Initialize credentials
    credentials = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    
    try:
        # Get access token from credentials for direct API call
        # Use asyncio to ensure we're properly handling async operations
        token_obj = await asyncio.create_task(credentials.get_token("https://graph.microsoft.com/.default"))
        token = token_obj.token
        
        # Check if user exists using direct HTTP request
        # Use filter to search by userPrincipalName
        url = f"https://graph.microsoft.com/v1.0/users?$filter=userPrincipalName eq '{user_principal_name}'"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Use aiohttp for async HTTP requests but fall back to requests for compatibility
        try:
            import aiohttp
            # Use aiohttp for proper async HTTP handling
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    status_code = response.status
                    response_json = await response.json()
                    
                    if status_code == 200:
                        users = response_json.get('value', [])
                        
                        if users and len(users) > 0:
                            # User exists
                            return True, users[0].get('id')
                        else:
                            # User doesn't exist
                            return False, None
                    else:
                        print(f"Failed to check if user exists: HTTP {status_code}")
                        return False, None
        except ImportError:
            # Fall back to requests if aiohttp is not available
            print("Using synchronous requests. Consider installing aiohttp for better performance.")
            # Wrap the synchronous call in an async task to avoid blocking
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, lambda: requests.get(url, headers=headers))
            
            if response.status_code == 200:
                users = response.json().get('value', [])
                
                if users and len(users) > 0:
                    # User exists
                    return True, users[0].get('id')
                else:
                    # User doesn't exist
                    return False, None
            else:
                print(f"Failed to check if user exists: HTTP {response.status_code}")
                return False, None
                
    except Exception as e:
        print(f"Error checking if user exists: {str(e)}")
        return False, None

async def create_entra_users_from_csv(csv_file_path, tenant_id, client_id, client_secret, smtp_server=None, smtp_port=None, sender_email=None, sender_password=None):
    """
    Load CSV file with subscriber data and create Microsoft Entra ID users
    
    Args:
        csv_file_path (str): Path to the CSV file with subscriber data
        tenant_id (str): Microsoft Entra ID tenant ID
        client_id (str): Application ID for authentication
        client_secret (str): Application secret for authentication
        smtp_server (str, optional): SMTP server for sending welcome emails
        smtp_port (int, optional): SMTP server port
        sender_email (str, optional): Email address to send welcome emails from
        sender_password (str, optional): Password for sender email account
        
    Returns:
        list: List of dictionaries with results of user creation operations
    """
    # Initialize Microsoft Graph client
    credentials = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    graph_client = GraphServiceClient(credentials=credentials)
    
    results = []
    
    try:
        with open(csv_file_path, 'r') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            
            for row in csv_reader:
                email = row.get('Email Address', '')
                first_name = row.get('First Name', '')
                last_name = row.get('Last Name', '')
                
                # Skip empty rows or rows with missing essential data
                if not email or not first_name:
                    continue
                
                # Extract the handle from the email address
                handle = get_email_handle(email)
                if not handle:
                    continue
                
                # Create new user ID with the handle and aiskillsfest.net domain
                new_user_principal_name = f"{handle}@aiskillsfest.net"
                  
                # Check if user already exists
                print(f"Checking if user {new_user_principal_name} exists...")
                try:
                    # Add explicit await and wait for response before continuing
                    print(f"Waiting for existence check response...")
                    # Explicitly await the result to ensure we have it before proceeding
                    user_exists, existing_user_id = await check_user_exists(
                        new_user_principal_name,
                        tenant_id,
                        client_id,
                        client_secret
                    )
                    
                    print(f"Received check response: exists={user_exists}")
                    
                    # Make sure we got a valid response
                    if user_exists is None:
                        raise Exception("Failed to determine if user exists")
                    
                    if user_exists:
                        print(f"User {new_user_principal_name} already exists with ID: {existing_user_id}")
                        user_info = {
                            "email": email,
                            "new_user_id": new_user_principal_name,
                            "status": "skipped",
                            "reason": "User already exists",
                            "user_id": existing_user_id
                        }
                        results.append(user_info)
                        print(f"Skipping to next user...")
                        continue  # Skip to next user in CSV
                    else:
                        print(f"User {new_user_principal_name} does not exist. Will create new user.")
                except Exception as e:
                    print(f"Error checking if user exists: {str(e)}")
                    results.append({
                        "email": email,
                        "new_user_id": new_user_principal_name,
                        "status": "error",
                        "message": f"Error checking if user exists: {str(e)}"
                    })
                    continue  # Skip to next user if we can't check existence
                
                # Generate temporary password for the new user
                temp_password = generate_temporary_password()
                  
                # Create user in Entra ID
                try:
                    # Prepare user data
                    password_profile = PasswordProfile(
                        force_change_password_next_sign_in=True,
                        password=temp_password
                    )
                    
                    user = User(
                        account_enabled=True,
                        display_name=f"{first_name} {last_name or 'Student'}".strip(),
                        mail_nickname=handle,
                        user_principal_name=new_user_principal_name,
                        password_profile=password_profile,
                        given_name=first_name,
                        surname=last_name or "Student",
                        mail=email
                    )
                    
                    # Call Microsoft Graph API to create the user using GraphServiceClient
                    print(f"Creating user: {new_user_principal_name}...")
                    response = await graph_client.users.post(body=user)
                    
                    if response:
                        user_id = response.id
                        print(f"User created successfully with ID: {user_id}")
                        user_info = {
                            "email": email,
                            "new_user_id": new_user_principal_name,
                            "status": "created",
                            "user_id": user_id,
                            "temp_password": temp_password
                        }
                        results.append(user_info)
                        
                        # Assign licenses to the new user
                        print(f"Assigning licenses to user {new_user_principal_name}...")
                        licenses_to_assign = [
                            LICENSE_SKUIDS["MICROSOFT_COPILOT_STUDIO_VIRAL_TRIAL"],
                            LICENSE_SKUIDS["MICROSOFT_POWER_APPS_DEV"]
                        ]
                        license_result = await assign_licenses_to_user(
                            user_id,
                            licenses_to_assign,
                            tenant_id,
                            client_id,
                            client_secret
                        )
                        user_info["licenses_assigned"] = license_result["success"]
                        if license_result["success"]:
                            print(f"Successfully assigned licenses to {new_user_principal_name}")
                        else:
                            print(f"Failed to assign licenses to {new_user_principal_name}: {license_result.get('reason', 'Unknown error')}")
                        
                        # Send welcome email if SMTP details are provided
                        if all([smtp_server, smtp_port, sender_email, sender_password]):
                            print(f"Sending welcome email to {email}...")
                            email_sent = send_welcome_email(
                                to_email=email,
                                first_name=first_name,
                                last_name=last_name,
                                new_username=new_user_principal_name,
                                temp_password=temp_password,
                                smtp_server=smtp_server,
                                smtp_port=smtp_port,
                                sender_email=sender_email,
                                sender_password=sender_password
                            )
                            user_info["email_sent"] = email_sent
                            print(f"Email {'sent successfully' if email_sent else 'failed to send'}")
                        
                        print(f"User processing complete.")
                    else:
                        print(f"Failed to create user: No response received")
                        results.append({
                            "email": email,
                            "new_user_id": new_user_principal_name,
                            "status": "error",
                            "message": "Failed to create user: No response received"
                        })
                except Exception as e:
                    error_msg = str(e)
                    print(f"Error creating user {new_user_principal_name}: {error_msg}")
                    results.append({
                        "email": email,
                        "new_user_id": new_user_principal_name,
                        "status": "error",
                        "message": error_msg
                    })
    
    except Exception as e:
        print(f"Error processing CSV file: {str(e)}")
        return []
    
    return results

def generate_temporary_password(length=12):
    """
    Generate a secure temporary password for new users
    """
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(alphabet) for _ in range(length))

async def add_users_to_group(users, group_id, tenant_id, client_id, client_secret):
    """
    Add multiple users to an Entra ID group
    
    Args:
        users (list): List of user IDs to add to the group
        group_id (str): ID of the group to add users to
        tenant_id (str): Microsoft Entra ID tenant ID
        client_id (str): Application ID for authentication
        client_secret (str): Application secret for authentication
        
    Returns:
        dict: Results of group addition operations
    """
    # Initialize Microsoft Graph client
    credentials = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    graph_client = GraphServiceClient(credentials=credentials)
    
    results = {"success": [], "failed": []}
    for user_id in users:
        try:
            print(f"Adding user {user_id} to group...")
            
            # Get access token from credentials for direct API call
            token = credentials.get_token("https://graph.microsoft.com/.default").token
            
            # Create the request body to add a user to a group
            request_body = {
                "@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{user_id}"
            }
            
            # Add member to group using direct HTTP request
            url = f"https://graph.microsoft.com/v1.0/groups/{group_id}/members/$ref"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, headers=headers, json=request_body)
            
            # 204 No Content is success for this operation
            if response.status_code == 204:
                results["success"].append(user_id)
            else:
                results["failed"].append({
                    "user_id": user_id,
                    "reason": f"HTTP {response.status_code}: {response.text}"
                })
                
        except Exception as e:
            results["failed"].append({
                "user_id": user_id,
                "reason": str(e)
            })
    
    return results

async def remove_user_from_group(user_id, group_id, tenant_id, client_id, client_secret):
    """
    Remove a user from an Entra ID group
    
    Args:
        user_id (str): ID of the user to remove from the group
        group_id (str): ID of the group to remove the user from
        tenant_id (str): Microsoft Entra ID tenant ID
        client_id (str): Application ID for authentication
        client_secret (str): Application secret for authentication
        
    Returns:
        dict: Result of the operation
    """
    # Initialize credentials
    credentials = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    
    result = {"success": False}
    
    try:
        # Get access token from credentials for direct API call
        token = credentials.get_token("https://graph.microsoft.com/.default").token
        
        # Remove member from group using direct HTTP request
        url = f"https://graph.microsoft.com/v1.0/groups/{group_id}/members/{user_id}/$ref"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        response = requests.delete(url, headers=headers)
        
        # 204 No Content is success for this operation
        if response.status_code == 204:
            result["success"] = True
            print(f"User {user_id} removed from group {group_id} successfully")
        else:
            result["success"] = False
            result["reason"] = f"HTTP {response.status_code}: {response.text}"
            print(f"Failed to remove user from group: HTTP {response.status_code}")
                
    except Exception as e:
        result["success"] = False
        result["reason"] = str(e)
        print(f"Error removing user from group: {str(e)}")
    
    return result

async def remove_users_from_group(users, group_id, tenant_id, client_id, client_secret):
    """
    Remove multiple users from an Entra ID group
    
    Args:
        users (list): List of user IDs to remove from the group
        group_id (str): ID of the group to remove users from
        tenant_id (str): Microsoft Entra ID tenant ID
        client_id (str): Application ID for authentication
        client_secret (str): Application secret for authentication
        
    Returns:
        dict: Results of group removal operations
    """
    results = {"success": [], "failed": []}
    
    for user_id in users:
        result = await remove_user_from_group(
            user_id, 
            group_id, 
            tenant_id, 
            client_id, 
            client_secret
        )
        
        if result["success"]:
            results["success"].append(user_id)
        else:
            results["failed"].append({
                "user_id": user_id,
                "reason": result.get("reason", "Unknown error")
            })
    
    return results

async def delete_user_from_tenant(user_id, tenant_id, client_id, client_secret):
    """
    Delete a user from the Microsoft Entra ID tenant
    
    Args:
        user_id (str): ID of the user to delete
        tenant_id (str): Microsoft Entra ID tenant ID
        client_id (str): Application ID for authentication
        client_secret (str): Application secret for authentication
        
    Returns:
        dict: Result of the operation
    """
    # Initialize credentials
    credentials = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    
    result = {"success": False}
    
    try:
        # Get access token from credentials for direct API call
        token = credentials.get_token("https://graph.microsoft.com/.default").token
        
        # Delete user using direct HTTP request
        url = f"https://graph.microsoft.com/v1.0/users/{user_id}"
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        response = requests.delete(url, headers=headers)
        
        # 204 No Content is success for this operation
        if response.status_code == 204:
            result["success"] = True
            print(f"User {user_id} deleted successfully from the tenant")
        else:
            result["success"] = False
            result["reason"] = f"HTTP {response.status_code}: {response.text}"
            print(f"Failed to delete user: HTTP {response.status_code}")
                
    except Exception as e:
        result["success"] = False
        result["reason"] = str(e)
        print(f"Error deleting user: {str(e)}")
    
    return result

async def delete_users_from_tenant(users, tenant_id, client_id, client_secret):
    """
    Delete multiple users from the Microsoft Entra ID tenant
    
    Args:
        users (list): List of user IDs to delete
        tenant_id (str): Microsoft Entra ID tenant ID
        client_id (str): Application ID for authentication
        client_secret (str): Application secret for authentication
        
    Returns:
        dict: Results of user deletion operations
    """
    results = {"success": [], "failed": []}
    
    for user_id in users:
        result = await delete_user_from_tenant(
            user_id, 
            tenant_id, 
            client_id, 
            client_secret
        )
        
        if result["success"]:
            results["success"].append(user_id)
        else:
            results["failed"].append({
                "user_id": user_id,
                "reason": result.get("reason", "Unknown error")
            })
    
    return results

async def assign_licenses_to_user(user_id, license_skus, tenant_id, client_id, client_secret):
    """
    Assign multiple licenses to a user in Microsoft Entra ID
    
    Args:
        user_id (str): ID of the user to assign licenses to
        license_skus (list): List of license SKU IDs to assign
        tenant_id (str): Microsoft Entra ID tenant ID
        client_id (str): Application ID for authentication
        client_secret (str): Application secret for authentication
        
    Returns:
        dict: Result of the license assignment operation
    """
    # Initialize credentials
    credentials = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    
    result = {"success": False, "assigned_licenses": []}
    
    try:
        # Get access token from credentials for direct API call
        token = credentials.get_token("https://graph.microsoft.com/.default").token
        
        # Prepare license payload
        license_payload = {
            "addLicenses": [
                {"skuId": sku_id} for sku_id in license_skus
            ],
            "removeLicenses": []
        }
        
        # Assign licenses using direct HTTP request
        url = f"https://graph.microsoft.com/v1.0/users/{user_id}/assignLicense"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, headers=headers, json=license_payload)
        
        if response.status_code in [200, 201]:
            result["success"] = True
            result["assigned_licenses"] = license_skus
            print(f"Successfully assigned licenses to user {user_id}")
        else:
            result["success"] = False
            result["reason"] = f"HTTP {response.status_code}: {response.text}"
            print(f"Failed to assign licenses to user: HTTP {response.status_code}")
                
    except Exception as e:
        result["success"] = False
        result["reason"] = str(e)
        print(f"Error assigning licenses to user: {str(e)}")
    
    return result

def send_welcome_email(to_email, first_name, last_name, new_username, temp_password, smtp_server, smtp_port, sender_email, sender_password):
    """
    Send a welcome email to new users with login instructions
    
    Args:
        to_email (str): Recipient's original email address
        first_name (str): Recipient's first name
        last_name (str): Recipient's last name
        new_username (str): New username in aiskillsfest.net domain
        temp_password (str): Temporary password for first login
        smtp_server (str): SMTP server address
        smtp_port (int): SMTP server port
        sender_email (str): Sender's email address
        sender_password (str): Sender's email password
        
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        # Set up email content
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Cc'] = "admins@aiskillsfest.net"
        msg['Subject'] = "Welcome to AI Skills Fest Organization"
        
        # Create email body with HTML formatting
        body = f"""
        <html>
        <body>
            <p>Hello {first_name} {last_name or 'Student'},</p>
            
            <p>Welcome to the AI Skills Fest organization! We're excited to have you join us.</p>
            
            <p>Your account has been created in our Microsoft Entra ID system. Below are your login credentials:</p>
            
            <ul>
                <li><strong>Username:</strong> {new_username}</li>
                <li><strong>Temporary Password:</strong> {temp_password}</li>
            </ul>
            
            <p><strong>Login Instructions:</strong></p>
            <ol>
                <li>Go to <a href="https://login.microsoftonline.com">https://login.microsoftonline.com</a></li>
                <li>Enter your username: {new_username}</li>
                <li>Enter your temporary password: {temp_password}</li>
                <li>You will be prompted to change your password upon first login</li>
                <li>Choose a strong, unique password that you haven't used elsewhere</li>
            </ol>
            
            <p>If you have any questions or need assistance, please contact our <a href="mailto:admins@aiskillsfest.net?subject=Inquiry&body=Hello,%20I%20have%20a%20question%20about..." >support team.</a></p>            
            <p>Best regards,<br>
            <a href="https://aiskillsfest.com">AI Skills Fest Team</a></p>
        </body>
        </html>
        """
        
        # Attach HTML content
        msg.attach(MIMEText(body, 'html'))
        
        # Set up SMTP server and send email
        cc_emails = ["admins@aiskillsfest.net"]
        recipients = [to_email] + cc_emails
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()  # Secure the connection
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipients, msg.as_string())
        
        return True
    
    except Exception as e:
        print(f"Failed to send email to {to_email}: {str(e)}")
        return False

async def test_with_dummy_record(tenant_id, client_id, client_secret, group_id, smtp_server, smtp_port, sender_email, sender_password):
    """
    Test the user creation and email functionality with a single dummy record
    
    Args:
        tenant_id (str): Microsoft Entra ID tenant ID
        client_id (str): Application ID for authentication
        client_secret (str): Application secret for authentication
        group_id (str): ID of the group to add user to
        smtp_server (str): SMTP server for sending welcome emails
        smtp_port (int): SMTP server port
        sender_email (str): Email address to send welcome emails from
        sender_password (str): Password for sender email account
        
    Returns:
        dict: Result of the test operation
    """
    print("Starting test with dummy record...")
    
    # Create a dummy user record
    dummy_user = {
        "Email Address": "test.user@example.com",
        "First Name": "Test",
        "Last Name": "User"
    }
    
    # Initialize Microsoft Graph client
    credentials = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    graph_client = GraphServiceClient(credentials=credentials)
    
    # Extract the handle from the email address
    email = dummy_user["Email Address"]
    first_name = dummy_user["First Name"]
    last_name = dummy_user["Last Name"]
    
    handle = get_email_handle(email)
    new_user_principal_name = f"{handle}@aiskillsfest.net"
    
    # Check if user already exists
    print(f"Checking if user {new_user_principal_name} already exists...")
    user_exists, existing_user_id = await check_user_exists(
        new_user_principal_name,
        tenant_id,
        client_id,
        client_secret
    )
    
    result = {}
    
    if user_exists:
        print(f"User {new_user_principal_name} already exists with ID: {existing_user_id}")
        result["user_creation"] = "skipped"
        result["reason"] = "User already exists"
        result["user_id"] = existing_user_id
        result["username"] = new_user_principal_name
        
        # We still continue with group operations in case the user wasn't added to the group yet
        user_id = existing_user_id
    else:
        # Generate temporary password
        temp_password = generate_temporary_password()
        print(f"Generated temporary password: {temp_password}")
        
        # Prepare user data
        # Create proper model objects instead of dictionaries
        password_profile = PasswordProfile(
            force_change_password_next_sign_in=True,
            password=temp_password
        )
        
        user = User(
            account_enabled=True,
            display_name=f"{first_name} {last_name or 'Student'}".strip(),
            mail_nickname=handle,
            user_principal_name=new_user_principal_name,
            password_profile=password_profile,
            given_name=first_name,
            surname=last_name or "Student",
            mail=email
        )
        
        try:
            # Create user using GraphServiceClient
            print(f"Creating user: {new_user_principal_name}...")
            # With GraphServiceClient, we use the users endpoint
            response = await graph_client.users.post(body=user)
            
            if response:
                user_id = response.id
                result["user_creation"] = "success"
                result["user_id"] = user_id
                result["username"] = new_user_principal_name
                result["temp_password"] = temp_password
                
                print(f"User created successfully with ID: {user_id}")
                
                # Send welcome email if SMTP details are provided
                if all([smtp_server, smtp_port, sender_email, sender_password]):
                    print("Sending welcome email...")
                    email_sent = send_welcome_email(
                        to_email=email,
                        first_name=first_name,
                        last_name=last_name,
                        new_username=new_user_principal_name,
                        temp_password=temp_password,
                        smtp_server=smtp_server,
                        smtp_port=smtp_port,
                        sender_email=sender_email,
                        sender_password=sender_password
                    )
                    result["email_sent"] = email_sent
                    print(f"Email {'sent successfully' if email_sent else 'failed to send'}")
            else:
                result["user_creation"] = "failed"
                result["reason"] = "Failed to create user"
                print("Failed to create user: No response received")
                return result  # Exit early if user creation failed
        except Exception as e:
            result["user_creation"] = "failed"
            result["reason"] = str(e)
            print(f"Error during test: {str(e)}")
            return result
    
    # Add user to group
    if group_id and "user_id" in result:
        print(f"Adding user to group: {group_id}...")
        
        # Get access token from credentials for direct API call
        token = credentials.get_token("https://graph.microsoft.com/.default").token
        
        # Create the request body to add a user to a group
        request_body = {
            "@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{user_id}"
        }
        
        # Add member to group using direct HTTP request
        url = f"https://graph.microsoft.com/v1.0/groups/{group_id}/members/$ref"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, headers=headers, json=request_body)
        
        # 204 No Content is success for this operation
        if response.status_code == 204:
            result["group_add"] = "success"
            print("User added to group successfully")
        else:
            result["group_add"] = "failed"
            result["group_add_reason"] = f"HTTP {response.status_code}: {response.text}"
            print(f"Failed to add user to group: HTTP {response.status_code}")
    
    return result

async def cleanup_test_user(user_id, group_id, tenant_id, client_id, client_secret):
    """
    Clean up a test user by first removing them from the group and then deleting from tenant
    
    Args:
        user_id (str): ID of the user to clean up
        group_id (str): ID of the group the user was added to
        tenant_id (str): Microsoft Entra ID tenant ID
        client_id (str): Application ID for authentication
        client_secret (str): Application secret for authentication
        
    Returns:
        dict: Results of the cleanup operations
    """
    results = {"group_removal": False, "user_deletion": False}
    
    # First remove from group
    if group_id:
        print(f"Removing user {user_id} from group {group_id}...")
        group_result = await remove_user_from_group(
            user_id,
            group_id,
            tenant_id,
            client_id,
            client_secret
        )
        results["group_removal"] = group_result["success"]
        
        if not group_result["success"]:
            results["group_removal_reason"] = group_result.get("reason", "Unknown error")
    
    # Then delete the user
    print(f"Deleting user {user_id} from tenant...")
    user_result = await delete_user_from_tenant(
        user_id,
        tenant_id,
        client_id,
        client_secret
    )
    results["user_deletion"] = user_result["success"]
    
    if not user_result["success"]:
        results["user_deletion_reason"] = user_result.get("reason", "Unknown error")
        
    return results

if __name__ == "__main__":
    # Load values from .env file (already done at the top, but explicit here for clarity)
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
   
    # Create an event loop for async operations
    loop = asyncio.get_event_loop()
    
    """
    # STEP 1: Create a test user
    print("=== STEP 1: CREATING TEST USER ===")
    test_result = loop.run_until_complete(test_with_dummy_record(
        tenant_id,
        client_id,
        client_secret,
        group_id,
        smtp_server,
        smtp_port,
        sender_email,
        sender_password
    ))
    
    print("\n=== TEST USER CREATION RESULTS ===")
    for key, value in test_result.items():
        print(f"{key}: {value}")
    
    # STEP 2: Verify the user was added to the group
    if test_result.get("user_creation") == "success" and test_result.get("group_add") == "success" or test_result.get("user_creation") == "skipped":
        user_id = test_result.get("user_id")
        print(f"\n=== STEP 2: VERIFYING USER IN GROUP ===")
        
        # Get token for verification
        credentials = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret
        )
        token = credentials.get_token("https://graph.microsoft.com/.default").token
        
        # Check group membership
        url = f"https://graph.microsoft.com/v1.0/groups/{group_id}/members"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            members = response.json().get("value", [])
            member_ids = [member.get("id") for member in members]
            
            if user_id in member_ids:
                print(f"✓ Verification successful: User {user_id} is a member of the group")
            else:
                print(f"✗ Verification failed: User {user_id} is NOT a member of the group")
        else:
            print(f"Failed to verify group membership: HTTP {response.status_code}")
    
        # STEP 3: Clean up by deleting the test user
        print(f"\n=== STEP 3: CLEANING UP TEST USER ===")
        cleanup_result = loop.run_until_complete(cleanup_test_user(
            user_id,
            group_id,
            tenant_id,
            client_id,
            client_secret
        ))
        
        print("\n=== CLEANUP RESULTS ===")
        for key, value in cleanup_result.items():
            print(f"{key}: {value}")
        
        # Final verification that user was deleted
        print("\n=== VERIFYING USER DELETION ===")
        url = f"https://graph.microsoft.com/v1.0/users/{user_id}"
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 404:
            print(f"✓ Verification successful: User {user_id} has been deleted")
        else:
            print(f"✗ Verification failed: User {user_id} still exists (HTTP {response.status_code})")
    else:
        print("\nSkipping verification and cleanup as user creation or group addition failed")
    
    print("\n=== TEST COMPLETED ===")
    """
    
    # Process full CSV file
    print("\n=== PROCESSING CSV FILE ===")
    csv_file_path = "./data/registered.csv"
    print(f"Reading users from {csv_file_path}...")
    created_users = loop.run_until_complete(create_entra_users_from_csv(
        csv_file_path, 
        tenant_id, 
        client_id, 
        client_secret,
        smtp_server,
        smtp_port,
        sender_email,
        sender_password
    ))
    
    # Get IDs of successfully created users
    successful_user_ids = [user["user_id"] for user in created_users if user["status"] == "created"]
    
    # Add users to a group
    group_results = loop.run_until_complete(add_users_to_group(
        successful_user_ids, 
        group_id, 
        tenant_id, 
        client_id, 
        client_secret
    ))
    
    # Add users to a SharePoint group
    sharepoint_group_results = loop.run_until_complete(add_users_to_group(
        successful_user_ids, 
        sp_group_id, 
        tenant_id, 
        client_id, 
        client_secret
    ))
    
    # Print results
    print(f"Created {len(successful_user_ids)} users")
        
    print(f"Added {len(group_results['success'])} users to group")
    print(f"Added {len(sharepoint_group_results['success'])} users to SharePoint Team Site group")    
    print(f"Failed to add {len(group_results['failed'])} users to group")
    print(f"Failed to add {len(sharepoint_group_results['failed'])} users to SharePoint Team Site group")
    print("=== PROCESSING COMPLETED ===")
