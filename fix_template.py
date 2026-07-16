import asyncio
from app.database import templates_col

async def main():
    result = await templates_col.update_one(
        {"name": "hostelnode_owner_invite_full_v1"},
        {"$set": {
            "header_type": "IMAGE",
            "header_image_url": "https://crm.hostelnode.com/static/images/hostelnode_owner_invite_full_v1.png"
        }},
        upsert=True
    )
    print("Matched:", result.matched_count)
    print("Modified:", result.modified_count)
    print("Upserted ID:", result.upserted_id)

asyncio.run(main())