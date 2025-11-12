# Cover Letter Generator

Generate tailored cover letters from a job posting URL or pasted description. Now with user accounts, persistent profiles, and user-scoped RAG for smarter context.

## Features
- Account auth: sign up / log in (local, hashed passwords)
- Persistent user profile: name, education, contacts, links, skills, resume text
- Manage Portfolio items (title, URL, skills, description)
- Manage Certifications (title, issuer, date, skills)
- Manage Experiences (role, organization, years, skills, description)
- User-scoped RAG via ChromaDB: pulls relevant links from your own portfolio/certs/experiences
- Input job via URL or paste description; preferences for tone/style/length
- Download generated cover letter(s)

## Setup
1. Create a virtual environment (optional but recommended) and install dependencies:

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
```

2. Create a `.env` file in `app/` or project root with your Groq API key:

```
GROQ_API_KEY=your_key_here
# Optional: override model
# GROQ_MODEL=llama-3.3-70b-versatile
```

3. (Optional) Enable Google Login

Create OAuth credentials in Google Cloud Console (OAuth client ID):
- Application type: Web application
- Authorized redirect URI (local): http://localhost:8501
- Copy Client ID and Client Secret

Add to your `.env`:

```
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
# If running on a different host/port, set the redirect URI explicitly
# OAUTH_REDIRECT_URI=http://localhost:8501
```

4. Run the app:

```powershell
streamlit run app/main.py
```

## Notes
- URL scraping uses LangChain's WebBaseLoader (BeautifulSoup + requests). If a site blocks scraping, paste the job description instead.
- A local SQLite DB is created at `app/data/app.db` for users and profile data.
- User-scoped RAG indexes your profile, portfolio items, certifications, and experiences into a ChromaDB collection under `vectorstore2/`.
- If Google login is configured, the sidebar will show a “Continue with Google” button.

## Troubleshooting
- If resume text extraction fails, ensure the file is a valid PDF/DOCX/TXT. For DOCX, `python-docx` is used; for PDF, `pypdf`.
- If imports are missing, reinstall dependencies: `pip install -r requirements.txt`.
- If `passlib` import fails, run `pip install -r requirements.txt` to install new dependencies.
- On Windows PowerShell, activate the venv with `\.\.venv\Scripts\Activate.ps1`.

## Roadmap
- Add templates gallery and theme-able outputs (DOCX export)
- Add unit tests and CI workflow
- Support additional LLM providers via config
- OAuth login (GitHub/Google) option