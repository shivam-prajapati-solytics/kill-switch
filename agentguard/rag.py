def retrieve(query, role):
    # Synthetic demo corpus only. Apply real document/tenant ACLs at retrieval time.
    if "customer record" in query.lower():
        return {
            "source": "mock://restricted/customer-001",
            "text": "Customer contact: demo.customer@example.com; phone: +91 9876543210",
            "classification": "restricted",
            "allowed_roles": ["support_admin"],
        }
    return {
        "source": "mock://public/holiday-policy",
        "text": "The company holiday policy provides designated public holidays and paid leave subject to the employee handbook.",
        "classification": "public",
        "allowed_roles": ["general", "support_admin"],
    }
