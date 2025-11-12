import pandas as pd
import chromadb
import uuid
from typing import List, Optional


class Portfolio:
    def __init__(self, file_path="app/resources/my_portfolio.csv"):
        self.file_path = file_path
        self.data = pd.read_csv(file_path)
        self.chroma_client = chromadb.PersistentClient('vectorstore2')
        self.collection = self.chroma_client.get_or_create_collection(name="portfolio")

    def load_portfolio(self):
        if not self.collection.count():
            for _, row in self.data.iterrows():
                self.collection.add(documents=row["Techstack"],
                                    metadatas={"links": row["Links"]},
                                    ids=[str(uuid.uuid4())])

    def query_links(self, skills):
        if not skills:
            return []
        result = self.collection.query(query_texts=skills, n_results=2)
        metadatas = result.get('metadatas', []) or []
        # Flatten and deduplicate links
        links = []
        seen = set()
        for group in metadatas:
            for md in group:
                link = (md or {}).get('links')
                if link and link not in seen:
                    seen.add(link)
                    links.append(link)
        return links


class UserPortfolioRAG:
    """User-specific RAG index built on ChromaDB.

    - Stores portfolio items, certs, experiences per user in a single collection with a user_id metadata filter.
    - Allows querying for relevant links/text snippets by skills with user scoping.
    """

    def __init__(self, persist_dir: str = 'vectorstore2', collection_name: str = 'user_portfolio'):
        self.chroma_client = chromadb.PersistentClient(persist_dir)
        self.collection = self.chroma_client.get_or_create_collection(name=collection_name)

    def reindex_user(
        self,
        user_id: int | str,
        profile: Optional[dict] = None,
        portfolio_items: Optional[List[dict]] = None,
        certifications: Optional[List[dict]] = None,
        experiences: Optional[List[dict]] = None,
    ) -> None:
        """Rebuild the user's index from provided data.

        We delete prior docs for this user and add fresh documents constructed from the provided records.
        """
        uid = str(user_id)
        # Clear existing docs for the user to avoid duplicates
        try:
            self.collection.delete(where={"user_id": uid})
        except Exception:
            # If delete where is unsupported in some versions, ignore
            pass

        documents = []
        metadatas = []
        ids = []

        # Profile doc (skills + links help retrieval even if no URL)
        if profile:
            skills = ", ".join(profile.get("skills", []) or [])
            links = ", ".join(profile.get("links", []) or [])
            bio = (profile.get("bio") or "").strip()
            linkedin = profile.get("linkedin") or ""
            github = profile.get("github") or ""
            text = (
                f"Profile of {profile.get('name','')}. Education: {profile.get('education','')}. "
                f"Skills: {skills}. Links: {links}. Bio: {bio}. LinkedIn: {linkedin}. GitHub: {github}."
            )
            documents.append(text)
            metadatas.append({"user_id": uid, "type": "profile", "title": profile.get("name", "")})
            ids.append(str(uuid.uuid4()))

        # Portfolio items
        for item in (portfolio_items or []):
            skills = ", ".join(item.get("skills", []) or [])
            desc = (item.get("description") or "").strip()
            text = f"Portfolio: {item.get('title','')}. Skills: {skills}. {desc}"
            documents.append(text)
            metadatas.append({
                "user_id": uid,
                "type": "portfolio_item",
                "title": item.get("title", ""),
                "url": item.get("url"),
            })
            ids.append(f"pf-{item.get('id') or uuid.uuid4()}")

        # Certifications
        for cert in (certifications or []):
            skills = ", ".join(cert.get("skills", []) or [])
            text = f"Certification: {cert.get('title','')} by {cert.get('issuer','')}, date {cert.get('date','')}. Skills: {skills}."
            documents.append(text)
            metadatas.append({
                "user_id": uid,
                "type": "certification",
                "title": cert.get("title", ""),
            })
            ids.append(f"ct-{cert.get('id') or uuid.uuid4()}")

        # Experiences
        for exp in (experiences or []):
            skills = ", ".join(exp.get("skills", []) or [])
            desc = (exp.get("description") or "").strip()
            text = f"Experience: {exp.get('role','')} at {exp.get('organization','')} ({exp.get('years','')}). Skills: {skills}. {desc}"
            documents.append(text)
            metadatas.append({
                "user_id": uid,
                "type": "experience",
                "title": exp.get("role", ""),
            })
            ids.append(f"xp-{exp.get('id') or uuid.uuid4()}")

        if documents:
            self.collection.add(documents=documents, metadatas=metadatas, ids=ids)

    def query_links(self, user_id: int | str, skills: List[str], n_results: int = 3) -> List[str]:
        if not skills:
            return []
        res = self.collection.query(query_texts=skills, n_results=n_results, where={"user_id": str(user_id)})
        metadatas = res.get("metadatas", []) or []
        links: List[str] = []
        seen = set()
        for group in metadatas:
            for md in group:
                url = (md or {}).get("url")
                if url and url not in seen:
                    seen.add(url)
                    links.append(url)
        return links