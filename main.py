import os
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson import ObjectId

from database import db, create_document, get_documents

app = FastAPI(title="Matrimonial API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utility

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def now_utc():
    return datetime.now(timezone.utc)


# Pydantic models
class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    location: Optional[str] = None
    bio: Optional[str] = None
    interests: Optional[List[str]] = None
    photos: Optional[List[str]] = None


# Auth helpers
async def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token = authorization.replace("Bearer ", "")
    session = db["session"].find_one({"token": token, "expires_at": {"$gt": now_utc()}})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db["user"].find_one({"_id": ObjectId(session["user_id"])})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    user["id"] = str(user["_id"])  # serialize
    return user


@app.get("/")
def root():
    return {"message": "Matrimonial API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Connected & Working"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# Auth endpoints
@app.post("/auth/signup")
def signup(payload: SignupRequest):
    email = payload.email.lower()
    if db["user"].find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    user_doc = {
        "name": payload.name,
        "email": email,
        "password_hash": hash_password(payload.password),
        "is_active": True,
        "gender": None,
        "date_of_birth": None,
        "location": None,
        "bio": None,
        "interests": [],
        "photos": [],
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    inserted_id = db["user"].insert_one(user_doc).inserted_id
    return {"id": str(inserted_id), "email": email, "name": payload.name}


@app.post("/auth/login")
def login(payload: LoginRequest):
    email = payload.email.lower()
    user = db["user"].find_one({"email": email})
    if not user or user.get("password_hash") != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create session
    token = secrets.token_urlsafe(32)
    expires = now_utc() + timedelta(days=7)
    db["session"].insert_one({"user_id": str(user["_id"]), "token": token, "expires_at": expires})
    return {"token": token, "user": {"id": str(user["_id"]), "name": user["name"], "email": user["email"]}}


# Profile endpoints
@app.get("/me")
def get_me(user=Depends(get_current_user)):
    safe = {k: v for k, v in user.items() if k not in ["password_hash", "_id"]}
    return safe


@app.put("/me")
def update_me(update: ProfileUpdate, user=Depends(get_current_user)):
    updates = {k: v for k, v in update.model_dump(exclude_none=True).items()}
    if not updates:
        return {"updated": False}
    updates["updated_at"] = now_utc()
    db["user"].update_one({"_id": ObjectId(user["id"])}, {"$set": updates})
    return {"updated": True}


# Discovery and swipes
@app.get("/discover")
def discover(user=Depends(get_current_user)):
    # Exclude current user and already-swiped users
    swiped_ids = set(
        s["target_id"] for s in db["swipe"].find({"user_id": user["id"]}, {"target_id": 1, "_id": 0})
    )
    swiped_ids.add(user["id"])  # don't show self

    candidates = []
    for u in db["user"].find({}, {"password_hash": 0}).limit(50):
        uid = str(u["_id"])
        if uid not in swiped_ids:
            u["id"] = uid
            candidates.append(u)
    return {"profiles": candidates}


class SwipeRequest(BaseModel):
    target_id: str
    action: str  # like or pass


@app.post("/swipe")
def swipe(payload: SwipeRequest, user=Depends(get_current_user)):
    if payload.action not in ["like", "pass"]:
        raise HTTPException(status_code=400, detail="Invalid action")

    # Record swipe
    db["swipe"].insert_one({
        "user_id": user["id"],
        "target_id": payload.target_id,
        "action": payload.action,
        "created_at": now_utc()
    })

    # If like, check for mutual
    is_match = False
    if payload.action == "like":
        reciprocal = db["swipe"].find_one({
            "user_id": payload.target_id,
            "target_id": user["id"],
            "action": "like"
        })
        if reciprocal:
            # Create match if not exists
            exists = db["match"].find_one({
                "$or": [
                    {"user_a": user["id"], "user_b": payload.target_id},
                    {"user_a": payload.target_id, "user_b": user["id"]}
                ]
            })
            if not exists:
                db["match"].insert_one({
                    "user_a": user["id"],
                    "user_b": payload.target_id,
                    "created_at": now_utc()
                })
            is_match = True

    return {"ok": True, "match": is_match}


@app.get("/matches")
def matches(user=Depends(get_current_user)):
    ms = list(db["match"].find({
        "$or": [{"user_a": user["id"]}, {"user_b": user["id"]}]
    }))
    partner_ids = [m["user_b"] if m["user_a"] == user["id"] else m["user_a"] for m in ms]
    partners = []
    for pid in partner_ids:
        u = db["user"].find_one({"_id": ObjectId(pid)}, {"password_hash": 0})
        if u:
            u["id"] = str(u["_id"]) 
            partners.append(u)
    return {"matches": partners}


# Public endpoint to fetch minimal profile
@app.get("/profile/{user_id}")
def public_profile(user_id: str):
    u = db["user"].find_one({"_id": ObjectId(user_id)}, {"password_hash": 0})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u["id"] = str(u["_id"]) 
    return u


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
