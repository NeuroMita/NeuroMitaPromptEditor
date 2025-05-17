from pydantic import BaseModel, Field
from pathlib import Path

class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    invite_code: str

class UserLogin(UserBase):
    password: str

class UserInDBBase(UserBase):
    hashed_password: str
    prompts_dir_relative: str

    class Config:
        from_attributes = True 

class User(UserInDBBase):
    pass

class UserInDB(UserInDBBase):
    pass

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: str | None = None