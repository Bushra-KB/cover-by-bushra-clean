from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl, EmailStr


class Preferences(BaseModel):
    tone: str = Field(default="professional", description="Overall tone, e.g., professional, friendly, enthusiastic")
    style: str = Field(default="concise", description="Writing style, e.g., concise, narrative, technical")
    length: str = Field(default="medium", description="Length preference: short, medium, long")
    template: Optional[str] = Field(default=None, description="Optional template name or custom instructions")


class UserProfile(BaseModel):
    name: str
    education: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    links: List[HttpUrl] = []
    skills: List[str] = []
    resume_text: Optional[str] = None


class JobInput(BaseModel):
    url: Optional[HttpUrl] = None
    description: Optional[str] = None


class ExtractedJob(BaseModel):
    role: Optional[str] = None
    experience: Optional[str] = None
    skills: List[str] = []
    description: Optional[str] = None


# Auth & Profile management schemas

class UserCreate(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class ProfileIn(BaseModel):
    name: str
    education: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    links: List[HttpUrl] = []
    skills: List[str] = []
    resume_text: Optional[str] = None


class PortfolioItemIn(BaseModel):
    title: str
    url: Optional[HttpUrl] = None
    skills: List[str] = []
    description: Optional[str] = None


class CertificationIn(BaseModel):
    title: str
    issuer: Optional[str] = None
    date: Optional[str] = None
    skills: List[str] = []


class ExperienceIn(BaseModel):
    role: str
    organization: Optional[str] = None
    years: Optional[str] = None
    skills: List[str] = []
    description: Optional[str] = None
