from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime

# Auth
class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    username: str
    password: str

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    email: EmailStr
    code: str
    new_password: str = Field(..., min_length=6)

# Groups
class GroupCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    members: List[str] = []

class GroupRename(BaseModel):
    oldName: str
    newName: str

class GroupDelete(BaseModel):
    name: str

class AddGroupMembers(BaseModel):
    group: str
    members: List[str]

# Messages
class MessageCreate(BaseModel):
    target: str
    mode: str  # 'contacts' or 'groups'
    text: str
    time: str

class MessageDelete(BaseModel):
    mode: str
    target: str
    time: str
    text: str

# Contacts
class AddContact(BaseModel):
    contact_username: str

class RemoveContact(BaseModel):
    contact_username: str

# Translation
class TranslateRequest(BaseModel):
    text: str
    source_lang: Optional[str] = 'auto'

# Responses
class SuccessResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None