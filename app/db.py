import os
import json
from datetime import datetime
from typing import List, Optional
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy import text as sql_text
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session

# Database path under app/data
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "app.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # needed for SQLite + threads
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _json_dump(value: Optional[List[str]]) -> str:
    try:
        return json.dumps(value or [])
    except Exception:
        return "[]"


def _json_load(value: Optional[str]) -> List[str]:
    try:
        if not value:
            return []
        return json.loads(value)
    except Exception:
        return []


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=True)
    password_hash = Column(String(256), nullable=False)
    provider = Column(String(50), nullable=True)       # e.g., 'google'
    provider_id = Column(String(200), nullable=True)   # subject id from provider
    created_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    portfolio_items = relationship("PortfolioItem", back_populates="user", cascade="all, delete-orphan")
    certifications = relationship("Certification", back_populates="user", cascade="all, delete-orphan")
    experiences = relationship("Experience", back_populates="user", cascade="all, delete-orphan")


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    name = Column(String(120), nullable=False)
    education = Column(String(200), nullable=True)
    email = Column(String(120), nullable=True)
    phone = Column(String(50), nullable=True)

    links_json = Column(Text, default="[]")  # JSON list[str]
    skills_json = Column(Text, default="[]")  # JSON list[str]
    resume_text = Column(Text, nullable=True)
    # Optional stored resume file info
    resume_file_path = Column(String(500), nullable=True)
    resume_file_name = Column(String(200), nullable=True)
    resume_file_mime = Column(String(100), nullable=True)
    # New optional fields
    bio = Column(Text, nullable=True)
    linkedin = Column(String(400), nullable=True)
    github = Column(String(400), nullable=True)

    user = relationship("User", back_populates="profile")

    # helpers
    @property
    def links(self) -> List[str]:
        return _json_load(self.links_json)

    @links.setter
    def links(self, value: List[str]):
        self.links_json = _json_dump(value)

    @property
    def skills(self) -> List[str]:
        return _json_load(self.skills_json)

    @skills.setter
    def skills(self, value: List[str]):
        self.skills_json = _json_dump(value)


class PortfolioItem(Base):
    __tablename__ = "portfolio_items"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)

    title = Column(String(200), nullable=False)
    url = Column(String(400), nullable=True)
    skills_json = Column(Text, default="[]")
    description = Column(Text, nullable=True)

    user = relationship("User", back_populates="portfolio_items")

    @property
    def skills(self) -> List[str]:
        return _json_load(self.skills_json)

    @skills.setter
    def skills(self, value: List[str]):
        self.skills_json = _json_dump(value)


class Certification(Base):
    __tablename__ = "certifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)

    title = Column(String(200), nullable=False)
    issuer = Column(String(200), nullable=True)
    date = Column(String(50), nullable=True)  # free-form date string
    skills_json = Column(Text, default="[]")

    user = relationship("User", back_populates="certifications")

    @property
    def skills(self) -> List[str]:
        return _json_load(self.skills_json)

    @skills.setter
    def skills(self, value: List[str]):
        self.skills_json = _json_dump(value)


class Experience(Base):
    __tablename__ = "experiences"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)

    role = Column(String(200), nullable=False)
    organization = Column(String(200), nullable=True)
    years = Column(String(50), nullable=True)
    skills_json = Column(Text, default="[]")
    description = Column(Text, nullable=True)

    user = relationship("User", back_populates="experiences")

    @property
    def skills(self) -> List[str]:
        return _json_load(self.skills_json)

    @skills.setter
    def skills(self, value: List[str]):
        self.skills_json = _json_dump(value)


# Create tables on import
Base.metadata.create_all(bind=engine)


# Session helpers

def get_session() -> Session:
    return SessionLocal()


def _column_exists(table: str, column: str) -> bool:
    with engine.connect() as conn:
        res = conn.execute(sql_text(f"PRAGMA table_info({table})"))
        cols = [row[1] for row in res.fetchall()]
        return column in cols


def ensure_schema():
    """Lightweight migrations for SQLite: add missing columns if needed."""
    # Profile: bio, linkedin, github
    with engine.connect() as conn:
        if not _column_exists("profiles", "bio"):
            conn.execute(sql_text("ALTER TABLE profiles ADD COLUMN bio TEXT"))
        if not _column_exists("profiles", "linkedin"):
            conn.execute(sql_text("ALTER TABLE profiles ADD COLUMN linkedin VARCHAR(400)"))
        if not _column_exists("profiles", "github"):
            conn.execute(sql_text("ALTER TABLE profiles ADD COLUMN github VARCHAR(400)"))
        # Profile: resume file metadata
        if not _column_exists("profiles", "resume_file_path"):
            conn.execute(sql_text("ALTER TABLE profiles ADD COLUMN resume_file_path VARCHAR(500)"))
        if not _column_exists("profiles", "resume_file_name"):
            conn.execute(sql_text("ALTER TABLE profiles ADD COLUMN resume_file_name VARCHAR(200)"))
        if not _column_exists("profiles", "resume_file_mime"):
            conn.execute(sql_text("ALTER TABLE profiles ADD COLUMN resume_file_mime VARCHAR(100)"))
        # Users: provider, provider_id
        if not _column_exists("users", "provider"):
            conn.execute(sql_text("ALTER TABLE users ADD COLUMN provider VARCHAR(50)"))
        if not _column_exists("users", "provider_id"):
            conn.execute(sql_text("ALTER TABLE users ADD COLUMN provider_id VARCHAR(200)"))


# Run migrations on import
ensure_schema()


# CRUD helper functions

def get_or_create_profile(db: Session, user_id: int) -> Profile:
    prof = db.query(Profile).filter(Profile.user_id == user_id).first()
    if prof:
        return prof
    # create minimal profile with placeholder name
    prof = Profile(user_id=user_id, name="")
    db.add(prof)
    db.commit()
    db.refresh(prof)
    return prof


def update_profile(
    db: Session,
    user_id: int,
    *,
    name: str,
    education: Optional[str],
    email: Optional[str],
    phone: Optional[str],
    links: Optional[list],
    skills: Optional[list],
    resume_text: Optional[str],
    resume_file_path: Optional[str] = None,
    resume_file_name: Optional[str] = None,
    resume_file_mime: Optional[str] = None,
) -> Profile:
    prof = get_or_create_profile(db, user_id)
    prof.name = name
    prof.education = education
    prof.email = email
    prof.phone = phone
    prof.links = links or []
    prof.skills = skills or []
    prof.resume_text = resume_text
    if resume_file_path is not None:
        prof.resume_file_path = resume_file_path
    if resume_file_name is not None:
        prof.resume_file_name = resume_file_name
    if resume_file_mime is not None:
        prof.resume_file_mime = resume_file_mime
    db.add(prof)
    db.commit()
    db.refresh(prof)
    return prof


def list_portfolio_items(db: Session, user_id: int) -> list[PortfolioItem]:
    return db.query(PortfolioItem).filter(PortfolioItem.user_id == user_id).order_by(PortfolioItem.id.desc()).all()


def upsert_portfolio_item(
    db: Session, user_id: int, *, item_id: Optional[int], title: str, url: Optional[str], skills: list, description: Optional[str]
) -> PortfolioItem:
    if item_id:
        item = db.query(PortfolioItem).filter(PortfolioItem.id == item_id, PortfolioItem.user_id == user_id).first()
        if not item:
            raise ValueError("Item not found")
    else:
        item = PortfolioItem(user_id=user_id)
    item.title = title
    item.url = url
    item.skills = skills or []
    item.description = description
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def delete_portfolio_item(db: Session, user_id: int, item_id: int) -> None:
    item = db.query(PortfolioItem).filter(PortfolioItem.id == item_id, PortfolioItem.user_id == user_id).first()
    if item:
        db.delete(item)
        db.commit()


def list_certifications(db: Session, user_id: int) -> list[Certification]:
    return db.query(Certification).filter(Certification.user_id == user_id).order_by(Certification.id.desc()).all()


def upsert_certification(
    db: Session,
    user_id: int,
    *,
    cert_id: Optional[int],
    title: str,
    issuer: Optional[str],
    date: Optional[str],
    skills: list,
) -> Certification:
    if cert_id:
        cert = db.query(Certification).filter(Certification.id == cert_id, Certification.user_id == user_id).first()
        if not cert:
            raise ValueError("Certification not found")
    else:
        cert = Certification(user_id=user_id)
    cert.title = title
    cert.issuer = issuer
    cert.date = date
    cert.skills = skills or []
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


def delete_certification(db: Session, user_id: int, cert_id: int) -> None:
    cert = db.query(Certification).filter(Certification.id == cert_id, Certification.user_id == user_id).first()
    if cert:
        db.delete(cert)
        db.commit()


def list_experiences(db: Session, user_id: int) -> list[Experience]:
    return db.query(Experience).filter(Experience.user_id == user_id).order_by(Experience.id.desc()).all()


def upsert_experience(
    db: Session,
    user_id: int,
    *,
    exp_id: Optional[int],
    role: str,
    organization: Optional[str],
    years: Optional[str],
    skills: list,
    description: Optional[str],
) -> Experience:
    if exp_id:
        exp = db.query(Experience).filter(Experience.id == exp_id, Experience.user_id == user_id).first()
        if not exp:
            raise ValueError("Experience not found")
    else:
        exp = Experience(user_id=user_id)
    exp.role = role
    exp.organization = organization
    exp.years = years
    exp.skills = skills or []
    exp.description = description
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def delete_experience(db: Session, user_id: int, exp_id: int) -> None:
    exp = db.query(Experience).filter(Experience.id == exp_id, Experience.user_id == user_id).first()
    if exp:
        db.delete(exp)
        db.commit()
