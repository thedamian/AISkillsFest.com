import asyncio
from Util_modified import assign_licenses_to_users, check_user_exists
from license_skuids import LICENSE_SKUIDS
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

async def assign_specific_licenses():
    """
    This script focuses only on assigning licenses to users after they have been created.
    """
    # Azure settings
    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    
    # Set up which licenses to assign
    licenses_to_assign = [
        LICENSE_SKUIDS["MICROSOFT_COPILOT_STUDIO_VIRAL_TRIAL"],
        LICENSE_SKUIDS["MICROSOFT_POWER_APPS_DEV"]
    ]
    
    # Get the list of user IDs either from a file or manual entry
    print("=== LICENSE ASSIGNMENT MODULE ===")
    print("This module assigns Microsoft Copilot Studio Viral Trial and Microsoft Power Apps for Developer licenses to users")
    
    input_method = input("Enter '1' to provide user IDs in a file or '2' to enter a specific user ID: ")
    
    user_ids = []
    
    if input_method == "1":
        file_path = input("Enter the path to the file containing user IDs (one per line): ")
        try:
            with open(file_path, 'r') as file:
                user_ids = [line.strip() for line in file if line.strip()]
            print(f"Loaded {len(user_ids)} user IDs from file")
        except Exception as e:
            print(f"Error reading file: {str(e)}")
            return
    elif input_method == "2":
        user_id = input("Enter the user ID to assign licenses to: ")
        if user_id.strip():
            user_ids.append(user_id.strip())
        else:
            print("No user ID provided. Exiting.")
            return
    else:
        print("Invalid option. Exiting.")
        return
    
    if not user_ids:
        print("No user IDs provided. Exiting.")
        return
    
    # Confirm before proceeding
    print(f"\nReady to assign the following licenses to {len(user_ids)} users:")
    print("1. Microsoft Copilot Studio Viral Trial")
    print("2. Microsoft Power Apps for Developer")
    
    confirm = input("\nProceed with license assignment? (y/n): ")
    
    if confirm.lower() != 'y':
        print("License assignment cancelled.")
        return
    
    # Assign licenses
    print(f"\n=== ASSIGNING LICENSES TO {len(user_ids)} USERS ===")
    license_results = await assign_licenses_to_users(
        user_ids,
        licenses_to_assign,
        tenant_id,
        client_id,
        client_secret
    )
    
    # Print detailed results
    print("\n=== DETAILED RESULTS ===")
    if license_results["success"]:
        print("\nSuccessfully assigned licenses to:")
        for success in license_results["success"]:
            print(f"- User ID: {success['user_id']}")
    
    if license_results["failed"]:
        print("\nFailed to assign licenses to:")
        for failure in license_results["failed"]:
            print(f"- User ID: {failure['user_id']}")
            print(f"  Reason: {failure['reason']}")
    
    print("\n=== LICENSE ASSIGNMENT COMPLETE ===")

if __name__ == "__main__":
    # Create an event loop for async operations
    loop = asyncio.get_event_loop()
    loop.run_until_complete(assign_specific_licenses())
