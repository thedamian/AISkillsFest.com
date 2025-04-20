import asyncio
from Util_modified import assign_licenses_to_users
from license_skuids import LICENSE_SKUIDS
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def main():
    # Azure settings
    # Get Azure settings from environment variables
    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    
    # You can either:
    # 1. Provide a list of specific user IDs 
    # 2. Import them from a CSV file
    # 3. Read them from a text file
    
    # Example with specific user IDs:
    user_ids = [
        # Add your user IDs here, for example:
        # "00000000-0000-0000-0000-000000000000",
        # "11111111-1111-1111-1111-111111111111",
    ]
    
    # If the list is empty, ask the user if they want to provide a file
    if not user_ids:
        file_path = input("Enter the path to a file with user IDs (one per line) or press Enter to cancel: ")
        if file_path:
            try:
                with open(file_path, 'r') as file:
                    user_ids = [line.strip() for line in file if line.strip()]
            except Exception as e:
                print(f"Error reading file: {str(e)}")
                return
    
    if not user_ids:
        print("No user IDs provided. Exiting.")
        return
    
    # Licenses to assign
    licenses_to_assign = [
        LICENSE_SKUIDS["MICROSOFT_COPILOT_STUDIO_VIRAL_TRIAL"],
        LICENSE_SKUIDS["MICROSOFT_POWER_APPS_DEV"]
    ]
    
    print(f"\n=== STARTING LICENSE ASSIGNMENT ===")
    print(f"Assigning the following licenses to {len(user_ids)} users:")
    print(f"- Microsoft Copilot Studio Viral Trial")
    print(f"- Microsoft Power Apps for Developer")
    
    # Assign licenses to the users
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
    loop.run_until_complete(main())
