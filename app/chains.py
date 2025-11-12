import os
from typing import List, Optional
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.exceptions import OutputParserException
from dotenv import load_dotenv
from models import UserProfile, Preferences, ExtractedJob
from utils import coerce_skills

load_dotenv()

class Chain:
    def __init__(self):
        self.llm = ChatGroq(
            temperature=0.3,
            groq_api_key=os.getenv("GROQ_API_KEY"),
            model_name=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        )

    def extract_jobs(self, cleaned_text):
        prompt_extract = PromptTemplate.from_template(
            """
            ### SCRAPED TEXT FROM WEBSITE:
            {page_data}
            ### INSTRUCTION:
            The scraped text is from the career's page of a website.
            Your job is to extract the job postings and return them in JSON format containing the following keys: `role`, `experience`, `skills` and `description`.
            Only return the valid JSON.
            ### VALID JSON (NO PREAMBLE):
            """
        )
        chain_extract = prompt_extract | self.llm
        res = chain_extract.invoke(input={"page_data": cleaned_text})
        try:
            json_parser = JsonOutputParser()
            res = json_parser.parse(res.content)
        except OutputParserException:
            raise OutputParserException("Context too big. Unable to parse jobs.")
        return res if isinstance(res, list) else [res]

    def generate_cover_letter(
        self,
        job: ExtractedJob | dict,
        profile: UserProfile,
        preferences: Preferences,
        links: Optional[List[str]] = None,
    ) -> str:
        """Generate a personalized cover letter based on job, profile, and preferences."""
        # Ensure we can handle dicts from parser gracefully
        if isinstance(job, dict):
            job = ExtractedJob(**{
                "role": job.get("role"),
                "experience": job.get("experience"),
                "skills": coerce_skills(job.get("skills", [])),
                "description": job.get("description"),
            })

        prompt_email = PromptTemplate.from_template(
            """
            You are an expert technical career writer.

            ### Candidate Profile
            - Name: {name}
            - Education: {education}
            - Email: {email}
            - Phone: {phone}
            - Key skills: {skills}
            - Links: {links}
            - Resume highlights:
            {resume_text}

            ### Job Posting
            - Role: {job_role}
            - Experience: {job_experience}
            - Required/Preferred skills: {job_skills}
            - Description:
            {job_description}

            ### Preferences
            - Tone: {tone}
            - Style: {style}
            - Length: {length}
            - Template hint: {template}

            Write a tailored cover letter addressed to the hiring manager. Requirements:
            - Start with a strong introduction specific to the role "{job_role}"
            - Align the candidate's experience and skills to the job.
            - Reference 1-3 relevant links if applicable.
            - Keep it {length} in length, with {tone} tone and {style} style.
            - End with a concise, confident closing and a call to action.

            Output only the final cover letter. No headings, no JSON, no extra commentary.
            """
        )

        chain_email = prompt_email | self.llm
        res = chain_email.invoke(
            {
                "name": profile.name,
                "education": profile.education or "",
                "email": profile.email or "",
                "phone": profile.phone or "",
                "skills": ", ".join(profile.skills[:20]),
                "links": ", ".join((links or profile.links)[:5]),
                "resume_text": (profile.resume_text or "").strip()[:4000],
                "job_role": job.role or "",
                "job_experience": job.experience or "",
                "job_skills": ", ".join(job.skills[:20]) if job.skills else "",
                "job_description": (job.description or "")[:6000],
                "tone": preferences.tone,
                "style": preferences.style,
                "length": preferences.length,
                "template": preferences.template or "",
            }
        )
        return res.content

if __name__ == "__main__":
    print(os.getenv("GROQ_API_KEY"))