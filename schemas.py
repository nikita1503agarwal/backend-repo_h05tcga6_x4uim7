"""
Database Schemas for Matrimonial App

Each Pydantic model maps to a MongoDB collection with the lowercase class name.
- User -> "user"
- Session -> "session"
- Swipe -> "swipe"
- Match -> "match"

These are used by the database viewer and for validation inside the API.
"""

from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from datetime import datetime

class User(BaseModel):
    """
    User profiles
    Collection name: "user"
    """
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    password_hash: str = Field(..., description="SHA256 password hash")
    gender: Optional[str] = Field(None, description="Gender identity")
    date_of_birth: Optional[str] = Field(None, description="YYYY-MM-DD")
    location: Optional[str] = Field(None, description="City or region")
    bio: Optional[str] = Field(None, description="Short bio")
    interests: List[str] = Field(default_factory=list, description="List of interests")
    photos: List[str] = Field(default_factory=list, description="Photo URLs")
    is_active: bool = Field(True, description="Whether user is active")

class Session(BaseModel):
    """
    User sessions (auth tokens)
    Collection name: "session"
    """
    user_id: str = Field(..., description="User ObjectId as string")
    token: str = Field(..., description="Auth token")
    expires_at: datetime = Field(..., description="Expiration time (UTC)")

class Swipe(BaseModel):
    """
    Swipe actions
    Collection name: "swipe"
    """
    user_id: str = Field(..., description="Who performed the swipe")
    target_id: str = Field(..., description="Whom they swiped on")
    action: str = Field(..., description="like or pass")

class Match(BaseModel):
    """
    Mutual matches
    Collection name: "match"
    """
    user_a: str = Field(..., description="First user id")
    user_b: str = Field(..., description="Second user id")
