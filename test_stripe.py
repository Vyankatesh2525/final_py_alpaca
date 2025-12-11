from stripe_service import create_connected_account, attach_test_bank_account

# Test creating connected account
print("Testing connected account creation...")
result = create_connected_account("test@example.com")
print("Result:", result)

if result.get("status") == "created":
    account_id = result["account_id"]
    print(f"Account created: {account_id}")
    
    # Test attaching bank account
    print("Testing bank account attachment...")
    bank_result = attach_test_bank_account(account_id)
    print("Bank result:", bank_result)
else:
    print("Failed to create account:", result.get("error"))