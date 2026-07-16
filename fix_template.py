import asyncio
from app.database import campaigns_col

async def main():
    doc = await campaigns_col.find_one(
        {"template_name": "hostelnode_owner_invite_full_v1"},
        sort=[("created_at", -1)]
    )
    print("Status:", doc.get("status"))
    print("Sent:", doc.get("sent_count"))
    print("Failed:", doc.get("failed_count"))
    print("Failed Details:", doc.get("failed_details"))

asyncio.run(main())