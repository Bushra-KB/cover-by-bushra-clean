import streamlit as st
import os
import base64
from langchain_community.document_loaders import WebBaseLoader
from chains import Chain
from portfolio import UserPortfolioRAG
from models import UserProfile, Preferences
from utils import (
    clean_text,
    validate_url,
    parse_skills,
    sanitize_links,
    extract_text_from_upload,
    safe_truncate,
)
from auth import authenticate_user, create_user, upsert_user_oauth
from oauth import google_login_button, has_google_oauth_config, can_render_google_button, oauth_diagnostics
from dotenv import load_dotenv

load_dotenv()
from db import (
    get_session,
    get_or_create_profile,
    update_profile,
    list_portfolio_items,
    upsert_portfolio_item,
    delete_portfolio_item,
    list_certifications,
    upsert_certification,
    delete_certification,
    list_experiences,
    upsert_experience,
    delete_experience,
)
from email_validator import validate_email, EmailNotValidError


def get_job_text_from_url(url: str) -> str:
    loader = WebBaseLoader([url])
    docs = loader.load()
    if not docs:
        return ""
    return clean_text(docs[0].page_content)


def ensure_session_keys():
    for k, v in {
        "user_id": None,
        "user_email": None,
        "active_page": "Generate",
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _is_valid_email(email: str) -> bool:
    try:
        validate_email(email or "", check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def _password_strength_errors(pw: str) -> list[str]:
    errors = []
    if len(pw) < 8:
        errors.append("At least 8 characters")
    if not any(c.islower() for c in pw):
        errors.append("Include a lowercase letter")
    if not any(c.isupper() for c in pw):
        errors.append("Include an uppercase letter")
    if not any(c.isdigit() for c in pw):
        errors.append("Include a number")
    if not any(c in "!@#$%^&*()_+-=[]{}|;:'\",.<>/?`~" for c in pw):
        errors.append("Include a special character")
    return errors


def sidebar_auth_and_nav():
    st.sidebar.header("Account")
    if st.session_state.get("user_id"):
        st.sidebar.success(f"Logged in as {st.session_state.get('user_email')}")
        if st.sidebar.button("Log out"):
            st.session_state.user_id = None
            st.session_state.user_email = None
            st.rerun()
        st.sidebar.divider()
        _inject_sidebar_nav_css()
        st.sidebar.markdown(
            """
            <div class=\"cbb-side-section-header\">
              <span class=\"cbb-side-title\">Navigation</span>
              <span class=\"cbb-side-chevron\">⌄</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        nav_items = [
            ("Generate", "✨"),
            ("Profile", "👤"),
            ("Portfolio", "🗂️"),
            ("Certifications", "🎓"),
            ("Experiences", "💼"),
            ("Docs", "📘"),
        ]
        labels = [f"{icon} {name}" for name, icon in nav_items]
        by_label = {f"{icon} {name}": name for name, icon in nav_items}
        current = st.session_state.get("active_page") or "Generate"
        current_label = [l for l in labels if by_label[l] == current][0]
        choice = st.sidebar.radio(
            label="Go to",
            options=labels,
            index=labels.index(current_label),
            label_visibility="collapsed",
        )
        st.session_state.active_page = by_label[choice]
    else:
        # OAuth login shown first in the sidebar
        if can_render_google_button():
            with st.sidebar:
                info = google_login_button("Continue with Google")
            if info and info.get("email") and info.get("sub"):
                try:
                    with get_session() as db:
                        user = upsert_user_oauth(
                            db,
                            provider="google",
                            provider_id=info["sub"],
                            email=info.get("email"),
                            name=info.get("name"),
                        )
                    st.session_state.user_id = user.id
                    st.session_state.user_email = user.email or info.get("email")
                    st.success("Logged in with Google!")
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"Google login failed: {e}")
            st.sidebar.markdown("**Or**")
        elif has_google_oauth_config():
            st.sidebar.info("Google login available. Please restart the app to load the OAuth component.")
            # Provide diagnostics to help resolve issues
            with st.sidebar.expander("Google login diagnostics", expanded=False):
                diag = oauth_diagnostics()
                st.write({k: v for k, v in diag.items()})
        else:
            # No config present; surface helpful diagnostics
            with st.sidebar.expander("Google login diagnostics", expanded=False):
                diag = oauth_diagnostics()
                st.write({k: v for k, v in diag.items()})

        # Login form (email/password)
        with st.sidebar.form("login_form", clear_on_submit=False):
            lemail = st.text_input("Email", placeholder="you@example.com")
            lpassword = st.text_input("Password", type="password", placeholder="••••••••")
            lsubmit = st.form_submit_button("Log in")
        if lsubmit:
            if not _is_valid_email(lemail):
                st.sidebar.error("Please enter a valid email")
            else:
                with get_session() as db:
                    user = authenticate_user(db, lemail, lpassword)
                if user:
                    st.session_state.user_id = user.id
                    st.session_state.user_email = user.email
                    st.success("Logged in!")
                    st.rerun()
                else:
                    st.sidebar.error("Invalid credentials")

        st.sidebar.markdown("---")
        st.sidebar.subheader("Sign up")
        with st.sidebar.form("signup_form", clear_on_submit=True):
            semail = st.text_input("Email", placeholder="you@example.com")
            spassword = st.text_input("Password", type="password", placeholder="At least 8 characters")
            spassword2 = st.text_input("Confirm Password", type="password")
            ssubmit = st.form_submit_button("Create account")
        if ssubmit:
            errs = []
            if not _is_valid_email(semail):
                errs.append("Valid email is required")
            if spassword != spassword2:
                errs.append("Passwords do not match")
            errs.extend(_password_strength_errors(spassword))
            if errs:
                st.sidebar.error("; ".join(errs))
            else:
                try:
                    with get_session() as db:
                        user = create_user(db, semail, spassword)
                        get_or_create_profile(db, user.id)
                    st.sidebar.success("Account created. Please log in.")
                except Exception as e:
                    st.sidebar.error(f"Sign up failed: {e}")

    # About section at bottom
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "Created by [Bushra KB](https://github.com/Bushra-KB) · ⭐ [Star on GitHub](https://github.com/Bushra-KB)"
    )


def _save_uploaded_resume(user_id: int, uploaded_file) -> tuple[str, str, str]:
    # Returns (saved_path, original_name, mime_type)
    uploads_dir = os.path.join(os.path.dirname(__file__), "data", "uploads", str(user_id))
    os.makedirs(uploads_dir, exist_ok=True)
    original_name = getattr(uploaded_file, "name", "resume")
    # basic sanitize
    safe_name = "".join(c for c in original_name if c.isalnum() or c in (".", "_", "-")) or "resume"
    import time
    ts = int(time.time())
    fname = f"{ts}_{safe_name}"
    saved_path = os.path.join(uploads_dir, fname)
    # Write bytes
    with open(saved_path, "wb") as out:
        out.write(uploaded_file.getbuffer())
    mime_type = getattr(uploaded_file, "type", None) or "application/octet-stream"
    return saved_path, original_name, mime_type


def _pdf_embed_html(file_path: str, height: int = 480) -> str:
    try:
        with open(file_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f'<iframe src="data:application/pdf;base64,{b64}#toolbar=0" width="100%" height="{height}" style="border:1px solid #222; border-radius:6px;"></iframe>'
    except Exception:
        return ""


def profile_tab(rag: UserPortfolioRAG):
    st.subheader("Profile")
    user_id = st.session_state.get("user_id")
    if not user_id:
        st.info("Log in to manage your profile.")
        return
    with get_session() as db:
        prof = get_or_create_profile(db, user_id)

    # Display current CV if present
    if (prof.resume_file_path and os.path.exists(prof.resume_file_path)) or (prof.resume_text):
        with st.expander("Current CV on file", expanded=False):
            if prof.resume_file_path and os.path.exists(prof.resume_file_path):
                st.write(f"Stored file: {os.path.basename(prof.resume_file_path)}")
                # Offer download of the original file
                try:
                    with open(prof.resume_file_path, "rb") as f:
                        st.download_button(
                            label="Download original CV",
                            data=f.read(),
                            file_name=prof.resume_file_name or os.path.basename(prof.resume_file_path),
                            mime=prof.resume_file_mime or "application/octet-stream",
                        )
                except Exception as e:
                    st.warning(f"Couldn't read stored file: {e}")
                # Preview PDF inline if it's a PDF
                if (prof.resume_file_mime or "").lower().startswith("application/pdf") or (prof.resume_file_path.lower().endswith(".pdf")):
                    html = _pdf_embed_html(prof.resume_file_path)
                    if html:
                        st.markdown(html, unsafe_allow_html=True)
            # Always allow downloading extracted text (if any)
            if prof.resume_text:
                st.download_button(
                    label="Download extracted text (.txt)",
                    data=prof.resume_text,
                    file_name="resume_extracted.txt",
                    mime="text/plain",
                )

    # Editable form
    with st.form("profile_form"):
        name = st.text_input("Full name", value=prof.name or "")
        bio = st.text_area("Bio / About", value=prof.bio or "", height=100)
        education = st.text_input("Education", value=prof.education or "")
        email = st.text_input("Email (required)", value=prof.email or "")
        phone = st.text_input("Phone (+country code)", value=prof.phone or "", placeholder="+1 555 123 4567")
        linkedin = st.text_input("LinkedIn", value=prof.linkedin or "", placeholder="https://www.linkedin.com/in/username")
        github = st.text_input("GitHub", value=prof.github or "", placeholder="https://github.com/username")
        skills_text = st.text_area("Skills (comma or newline)", value=", ".join(prof.skills) if prof.skills else "", height=80)
        uploaded_resume = st.file_uploader("Upload/Replace resume (PDF/DOCX/TXT)", type=["pdf", "docx", "txt"], key="resume_upload")
        save = st.form_submit_button("Save profile")

    resume_text = prof.resume_text
    resume_file_path = None
    resume_file_name = None
    resume_file_mime = None
    if uploaded_resume is not None:
        try:
            # Persist original file
            saved_path, original_name, mime_type = _save_uploaded_resume(user_id, uploaded_resume)
            resume_file_path, resume_file_name, resume_file_mime = saved_path, original_name, mime_type
        except Exception as e:
            st.warning(f"Couldn't store uploaded file: {e}")
        try:
            # Extract text for downstream use
            resume_text = extract_text_from_upload(uploaded_resume)
        except Exception as e:
            st.warning(f"Couldn't read resume: {e}")

    if save:
        if not _is_valid_email(email or ""):
            st.error("Valid email is required")
            return
        # Compose links list from dedicated fields
        links = sanitize_links([l for l in [linkedin, github] if l])
        skills = parse_skills(skills_text)
        with get_session() as db:
            prof = update_profile(
                db,
                user_id,
                name=name.strip(),
                education=education.strip() or None,
                email=email.strip().lower() or None,
                phone=phone.strip() or None,
                links=links,
                skills=skills,
                resume_text=safe_truncate(resume_text or "", 6000),
                resume_file_path=resume_file_path if uploaded_resume is not None else None,
                resume_file_name=resume_file_name if uploaded_resume is not None else None,
                resume_file_mime=resume_file_mime if uploaded_resume is not None else None,
            )
            # Update new fields saved in Profile model
            prof.bio = bio.strip() or None
            prof.linkedin = linkedin.strip() or None
            prof.github = github.strip() or None
            db.add(prof)
            db.commit()
            # Reindex RAG with updated data
            rag.reindex_user(
                user_id,
                profile={
                    "name": prof.name,
                    "education": prof.education,
                    "skills": prof.skills,
                    "links": prof.links,
                    "bio": prof.bio,
                    "linkedin": prof.linkedin,
                    "github": prof.github,
                },
                portfolio_items=[
                    {"id": it.id, "title": it.title, "url": it.url, "skills": it.skills, "description": it.description}
                    for it in list_portfolio_items(db, user_id)
                ],
                certifications=[
                    {"id": c.id, "title": c.title, "issuer": c.issuer, "date": c.date, "skills": c.skills}
                    for c in list_certifications(db, user_id)
                ],
                experiences=[
                    {
                        "id": e.id,
                        "role": e.role,
                        "organization": e.organization,
                        "years": e.years,
                        "skills": e.skills,
                        "description": e.description,
                    }
                    for e in list_experiences(db, user_id)
                ],
            )
        st.success("Profile saved")


def portfolio_tab(rag: UserPortfolioRAG):
    st.subheader("Portfolio items")
    user_id = st.session_state.get("user_id")
    if not user_id:
        st.info("Log in to manage your portfolio.")
        return
    with get_session() as db:
        items = list_portfolio_items(db, user_id)
    # Table-like header
    h1, h2, h3, h4 = st.columns([3, 3, 3, 2])
    h1.markdown("**Title**")
    h2.markdown("**URL**")
    h3.markdown("**Skills**")
    h4.markdown("**Actions**")
    edit_target = None
    for it in items:
        c1, c2, c3, c4 = st.columns([3, 3, 3, 2])
        c1.write(it.title)
        c2.write(it.url or "-")
        c3.write(", ".join(it.skills) if it.skills else "-")
        col_edit, col_del = c4.columns(2)
        if col_edit.button("Edit", key=f"edit_pf_{it.id}"):
            edit_target = it
        if col_del.button("Delete", key=f"del_pf_{it.id}"):
            with get_session() as db:
                delete_portfolio_item(db, user_id, it.id)
                _reindex_user_quick(db, rag, user_id)
            st.rerun()

    st.divider()
    st.markdown("### Add / Update Item")
    default_id = str(edit_target.id) if edit_target else ""
    default_title = edit_target.title if edit_target else ""
    default_url = edit_target.url if edit_target else ""
    default_skills = ", ".join(edit_target.skills) if edit_target and edit_target.skills else ""
    default_desc = edit_target.description if edit_target else ""
    with st.form("pf_form", clear_on_submit=True):
        if edit_target:
            st.text_input("Editing ID", value=default_id, help="ID is assigned automatically", disabled=True)
        title = st.text_input("Title", value=default_title)
        url = st.text_input("URL", value=default_url)
        skills_text = st.text_area("Skills (comma or newline)", value=default_skills, height=60)
        description = st.text_area("Description (optional)", value=default_desc, height=100)
        submit = st.form_submit_button("Save item")
    if submit:
        try:
            with get_session() as db:
                item = upsert_portfolio_item(
                    db,
                    user_id,
                    item_id=edit_target.id if edit_target else None,
                    title=title.strip(),
                    url=url.strip() or None,
                    skills=parse_skills(skills_text),
                    description=description.strip() or None,
                )
                _reindex_user_quick(db, rag, user_id)
            st.success(f"Saved item #{item.id}")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to save: {e}")


def certifications_tab(rag: UserPortfolioRAG):
    st.subheader("Certifications")
    user_id = st.session_state.get("user_id")
    if not user_id:
        st.info("Log in to manage your certifications.")
        return
    with get_session() as db:
        certs = list_certifications(db, user_id)
    h1, h2, h3, h4 = st.columns([3, 3, 3, 2])
    h1.markdown("**Title**")
    h2.markdown("**Issuer / Date**")
    h3.markdown("**Skills**")
    h4.markdown("**Actions**")
    edit_target = None
    for c in certs:
        c1, c2, c3, c4 = st.columns([3, 3, 3, 2])
        c1.write(c.title)
        c2.write(f"{c.issuer or ''} {('· ' + c.date) if c.date else ''}")
        c3.write(", ".join(c.skills) if c.skills else "-")
        col_edit, col_del = c4.columns(2)
        if col_edit.button("Edit", key=f"edit_cert_{c.id}"):
            edit_target = c
        if col_del.button("Delete", key=f"del_cert_{c.id}"):
            with get_session() as db:
                delete_certification(db, user_id, c.id)
                _reindex_user_quick(db, rag, user_id)
            st.rerun()

    st.divider()
    st.markdown("### Add / Update Certification")
    default_id = str(edit_target.id) if edit_target else ""
    default_title = edit_target.title if edit_target else ""
    default_issuer = edit_target.issuer if edit_target else ""
    default_date = edit_target.date if edit_target else ""
    default_skills = ", ".join(edit_target.skills) if edit_target and edit_target.skills else ""
    with st.form("cert_form", clear_on_submit=True):
        if edit_target:
            st.text_input("Editing ID", value=default_id, help="ID is assigned automatically", disabled=True)
        title = st.text_input("Title", value=default_title)
        issuer = st.text_input("Issuer (optional)", value=default_issuer)
        date = st.text_input("Date (optional)", value=default_date)
        skills_text = st.text_area("Skills (comma or newline)", value=default_skills, height=60)
        submit = st.form_submit_button("Save certification")
    if submit:
        try:
            with get_session() as db:
                cert = upsert_certification(
                    db,
                    user_id,
                    cert_id=edit_target.id if edit_target else None,
                    title=title.strip(),
                    issuer=issuer.strip() or None,
                    date=date.strip() or None,
                    skills=parse_skills(skills_text),
                )
                _reindex_user_quick(db, rag, user_id)
            st.success(f"Saved certification #{cert.id}")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to save: {e}")


def experiences_tab(rag: UserPortfolioRAG):
    st.subheader("Experiences")
    user_id = st.session_state.get("user_id")
    if not user_id:
        st.info("Log in to manage your experiences.")
        return
    with get_session() as db:
        exps = list_experiences(db, user_id)
    h1, h2, h3, h4, h5 = st.columns([3, 3, 3, 2, 2])
    h1.markdown("**Role**")
    h2.markdown("**Organization**")
    h3.markdown("**Years**")
    h4.markdown("**Skills**")
    h5.markdown("**Actions**")
    edit_target = None
    for e in exps:
        c1, c2, c3, c4, c5 = st.columns([3, 3, 3, 2, 2])
        c1.write(e.role)
        c2.write(e.organization or "-")
        c3.write(e.years or "-")
        c4.write(", ".join(e.skills) if e.skills else "-")
        col_edit, col_del = c5.columns(2)
        if col_edit.button("Edit", key=f"edit_exp_{e.id}"):
            edit_target = e
        if col_del.button("Delete", key=f"del_exp_{e.id}"):
            with get_session() as db:
                delete_experience(db, user_id, e.id)
                _reindex_user_quick(db, rag, user_id)
            st.rerun()

    st.divider()
    st.markdown("### Add / Update Experience")
    default_id = str(edit_target.id) if edit_target else ""
    default_role = edit_target.role if edit_target else ""
    default_org = edit_target.organization if edit_target else ""
    default_years = edit_target.years if edit_target else ""
    default_skills = ", ".join(edit_target.skills) if edit_target and edit_target.skills else ""
    default_desc = edit_target.description if edit_target else ""
    with st.form("exp_form", clear_on_submit=True):
        if edit_target:
            st.text_input("Editing ID", value=default_id, help="ID is assigned automatically", disabled=True)
        role = st.text_input("Role", value=default_role)
        organization = st.text_input("Organization (optional)", value=default_org)
        years = st.text_input("Years (From–To)", value=default_years)
        skills_text = st.text_area("Skills (comma or newline)", value=default_skills, height=60)
        description = st.text_area("Description (optional)", value=default_desc, height=100)
        submit = st.form_submit_button("Save experience")
    if submit:
        try:
            with get_session() as db:
                exp = upsert_experience(
                    db,
                    user_id,
                    exp_id=edit_target.id if edit_target else None,
                    role=role.strip(),
                    organization=organization.strip() or None,
                    years=years.strip() or None,
                    skills=parse_skills(skills_text),
                    description=description.strip() or None,
                )
                _reindex_user_quick(db, rag, user_id)
            st.success(f"Saved experience #{exp.id}")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to save: {e}")


def _reindex_user_quick(db_session, rag: UserPortfolioRAG, user_id: int):
    # Helper to rebuild the user's index using current DB state
    prof = get_or_create_profile(db_session, user_id)
    rag.reindex_user(
        user_id,
        profile={
            "name": prof.name,
            "education": prof.education,
            "skills": prof.skills,
            "links": prof.links,
        },
        portfolio_items=[
            {"id": it.id, "title": it.title, "url": it.url, "skills": it.skills, "description": it.description}
            for it in list_portfolio_items(db_session, user_id)
        ],
        certifications=[
            {"id": c.id, "title": c.title, "issuer": c.issuer, "date": c.date, "skills": c.skills}
            for c in list_certifications(db_session, user_id)
        ],
        experiences=[
            {
                "id": e.id,
                "role": e.role,
                "organization": e.organization,
                "years": e.years,
                "skills": e.skills,
                "description": e.description,
            }
            for e in list_experiences(db_session, user_id)
        ],
    )


def generate_tab(chain: Chain, rag: UserPortfolioRAG):
    st.subheader("Generate cover letter")

    user_id = st.session_state.get("user_id")
    if not user_id:
        st.info("Log in to generate a personalized cover letter with your saved profile.")
        return

    # Preferences
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        tone = st.selectbox("Tone", ["professional", "friendly", "enthusiastic", "confident", "polite"], index=0)
    with c2:
        style = st.selectbox("Style", ["concise", "narrative", "technical", "impactful"], index=0)
    with c3:
        length = st.selectbox("Length", ["short", "medium", "long"], index=1)
    with c4:
        template_hint = st.text_input("Template (optional)", value="")
    preferences = Preferences(tone=tone, style=style, length=length, template=template_hint or None)

    # Main input: Job URL or pasted description
    input_mode = st.radio("Provide job posting via:", ["URL", "Paste description"], horizontal=True)
    job_text = ""
    url_input = ""
    if input_mode == "URL":
        url_input = st.text_input("Job posting URL", value="")
        if url_input and validate_url(url_input):
            if st.button("Fetch job details"):
                try:
                    job_text = get_job_text_from_url(url_input)
                    if not job_text:
                        st.warning("Couldn't extract text from the URL. Try pasting the description instead.")
                except Exception as e:
                    st.error(f"Failed to fetch URL: {e}")
        elif url_input:
            st.warning("Please enter a valid http(s) URL.")
    else:
        job_text = st.text_area("Paste job description", height=240)

    st.divider()
    submit = st.button("Generate Cover Letter", type="primary")
    if submit:
        if input_mode == "URL" and not (url_input and validate_url(url_input)) and not job_text:
            st.error("Please provide a valid URL or paste a job description.")
            return
        source_text = clean_text(job_text) if job_text else (get_job_text_from_url(url_input) if url_input else "")
        if not source_text:
            st.error("No job description text found.")
            return
        with get_session() as db:
            prof = get_or_create_profile(db, user_id)
            if not (prof.name or "").strip():
                st.error("Please complete your Profile (name) before generating.")
                return
            # Ensure RAG index exists for user
            _reindex_user_quick(db, rag, user_id)
        try:
            jobs = chain.extract_jobs(source_text)
        except Exception as e:
            st.error(f"Couldn't parse job data from the posting. You can paste the description directly. Details: {e}")
            return

        profile_model = UserProfile(
            name=prof.name or "",
            education=prof.education or None,
            email=prof.email or None,
            phone=prof.phone or None,
            links=prof.links,
            skills=prof.skills,
            resume_text=safe_truncate(prof.resume_text or "", 6000),
        )

        st.subheader("Generated Cover Letter(s)")
        for idx, job in enumerate(jobs, start=1):
            job_skills = job.get('skills') if isinstance(job, dict) else getattr(job, 'skills', [])
            search_skills = list({*(prof.skills or []), *([s for s in (job_skills or [])])})
            portfolio_links = rag.query_links(user_id, search_skills, n_results=3)
            try:
                letter = chain.generate_cover_letter(job, profile_model, preferences, links=(portfolio_links or prof.links))
                st.markdown(f"### Option {idx}")
                st.write(letter)
                st.download_button(
                    label="Download as .txt",
                    data=letter,
                    file_name=f"cover_letter_{idx}.txt",
                    mime="text/plain",
                )
            except Exception as e:
                st.error(f"Generation failed: {e}")


def create_streamlit_app(chain: Chain, rag: UserPortfolioRAG):
    # Resolve logo path for page icon (falls back to emoji if not found)
    logo_path = os.path.join(os.path.dirname(__file__), "resources", "logo1.jpg")
    page_icon = logo_path if os.path.exists(logo_path) else "📝"
    st.set_page_config(layout="wide", page_title="CoverByBushra", page_icon=page_icon)
    ensure_session_keys()
    _render_top_nav()
    sidebar_auth_and_nav()

    st.markdown("## ")
    st.caption("Generate a personalized cover letter using your saved profile and portfolio.")

    page = st.session_state.get("active_page") or "Generate"
    if page == "Generate":
        generate_tab(chain, rag)
    elif page == "Profile":
        profile_tab(rag)
    elif page == "Portfolio":
        portfolio_tab(rag)
    elif page == "Certifications":
        certifications_tab(rag)
    elif page == "Experiences":
        experiences_tab(rag)
    elif page == "Docs":
        docs_tab()

    _render_footer()


def _render_top_nav():
        # Navbar with embedded logo image.
        logo_path = os.path.join(os.path.dirname(__file__), "resources", "logo1.jpg")
        logo_b64 = None
        if os.path.exists(logo_path):
                try:
                        with open(logo_path, "rb") as f:
                                logo_b64 = base64.b64encode(f.read()).decode("utf-8")
                except Exception:
                        logo_b64 = None
        img_tag = (
                f'<img src="data:image/jpeg;base64,{logo_b64}" class="cbb-logo" alt="logo" />' if logo_b64 else '<span class="cbb-logo-fallback">📝</span>'
        )
        st.markdown(
                f"""
                <style>
                .cbb-navbar {{position: sticky; top: 0; z-index: 999; background: #0e1117; padding: 10px 16px; border-bottom: 1px solid #222;}}
                .cbb-container {{display: flex; align-items: center; justify-content: space-between;}}
                .cbb-left {{display: flex; align-items: center; gap: 10px;}}
                .cbb-logo {{width: 32px; height: 32px; border-radius: 6px; object-fit: cover; box-shadow: 0 0 0 1px #222, 0 2px 4px rgba(0,0,0,.4);}}
                .cbb-logo-fallback {{width:32px; height:32px; display:inline-flex; align-items:center; justify-content:center; font-size:20px; background:#1e2530; border-radius:6px; box-shadow: 0 0 0 1px #222;}}
                .cbb-title {{font-weight:700; color:#fff;}}
                .cbb-links a {{color:#ddd; margin-left:16px; text-decoration:none;}}
                .cbb-links a:hover {{color:#fff;}}
                </style>
                <div class="cbb-navbar">
                    <div class="cbb-container">
                        <div class="cbb-left">
                            {img_tag}
                            <span class="cbb-title">CoverByBushra</span>
                        </div>
                        <div class="cbb-links">
                            <a href="https://github.com/Bushra-KB" target="_blank">🐱 GitHub</a>
                            <a href="#" title="Open Docs from the left menu">📄 Docs</a>
                            <a href="mailto:bushra.kmb@gmail.com" target="_blank">✉️ Contact Me</a>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
        )


def _render_footer():
    from datetime import datetime
    year = datetime.now().year
    st.markdown("---")
    st.markdown(f"© {year} CoverByBushra · Developed by Bushra KB")


def _inject_sidebar_nav_css():
        st.sidebar.markdown(
                """
                <style>
                /* Sidebar section header */
                .cbb-side-section-header {display:flex; align-items:center; justify-content:space-between; padding:6px 4px 2px 4px;}
                .cbb-side-title {font-weight:600; color:#ddd;}
                .cbb-side-chevron {color:#aaa;}

                /* Radio group styling to resemble clean nav list */
                [data-testid="stSidebar"] div[role="radiogroup"] > label {
                    display:flex; align-items:center; gap:10px; padding:8px 10px; border-radius:8px; margin:4px 0; border:1px solid transparent;
                }
                [data-testid="stSidebar"] div[role="radiogroup"] > label:hover {
                    background:#1b1f2a; border-color:#2a3142;
                }
                [data-testid="stSidebar"] div[role="radiogroup"] > div label p {
                    margin:0; padding:0; font-weight:500;
                }
                </style>
                """,
                unsafe_allow_html=True,
        )


def docs_tab():
    st.subheader("Docs")
    st.markdown("""
    Welcome to the CoverByBushra documentation.

    What you can do:
    - Create an account and save your profile (name, bio, contact, links, skills, resume)
    - Add Portfolio items, Certifications, and Experiences with skills
    - Generate tailored cover letters from a job URL or pasted description
    - RAG retrieves your most relevant links to include

    How generation works:
    1. We parse the job description to extract role, experience, and skills.
    2. We build a profile context from your saved data.
    3. We query your user-specific Chroma collection to fetch relevant links.
    4. We prompt the LLM with your preferences (tone, style, length) and optional template hint.

    Tips:
    - Keep your profile skills concise and accurate.
    - Add URLs for Portfolio items (GitHub repos, demos) to let RAG surface them.
    - Use the Template field to hint format (e.g., "ATS-friendly", "bulleted intro").

    """)


if __name__ == "__main__":
    chain = Chain()
    rag = UserPortfolioRAG()
    create_streamlit_app(chain, rag)
