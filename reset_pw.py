import asyncio
from services.auth_service import hash_password, _verify_password
from models.user import get_user_by_email, update_password_hash

async def reset():
    h = hash_password("123456")
    user = await get_user_by_email("grx1242064203@163.com")
    await update_password_hash(user["id"], h)
    u2 = await get_user_by_email("grx1242064203@163.com")
    ok = _verify_password("123456", u2["password_hash"])
    print("verify=" + str(ok))

asyncio.run(reset())
