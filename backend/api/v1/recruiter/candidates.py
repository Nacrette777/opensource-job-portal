"""
GradBridge: the candidate pool recruiters search (S2-07).

A job seeker is a candidate only while they have a published resume version
(ResumePublication.version). Publishing is their consent to be found;
withdrawing removes them from search, detail and download at once, because
every request re-evaluates `candidate_pool()`.

Search uses the PeelJobs profile (the structured, comparable data); the
published Reactive Resume PDF is what recruiters download.
"""

from django.db.models import Count, Q

from peeldb.models import CandidateNote, CandidateShortlist, User
from peeldb.resume_export import SKILL_LEVELS

SUMMARY_PREVIEW = 240


class InvalidFilter(ValueError):
    pass


def candidate_pool():
    return User.objects.filter(
        user_type="JS", is_active=True, resume_publication__version__isnull=False
    )


def is_recruiter(user):
    return user.is_authenticated and user.user_type == "EM" and user.is_active


def _int_list(raw, name):
    if not raw:
        return []
    try:
        values = [int(v) for v in str(raw).split(",") if v.strip()]
    except ValueError as exc:
        raise InvalidFilter(f"{name} must be a comma-separated list of ids") from exc
    if len(values) > 20:
        raise InvalidFilter(f"Too many {name}")
    return values


def _int(raw, name, low=None, high=None):
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise InvalidFilter(f"{name} must be a number") from exc
    if (low is not None and value < low) or (high is not None and value > high):
        raise InvalidFilter(f"{name} is out of range")
    return value


def search(params):
    """Filter the pool. Raises InvalidFilter for malformed parameters.

    - skills: every listed skill id must be on the profile (ALL, not ANY).
    - qualification / degree / graduation_year: must hold for the same
      education entry, so "Bachelor graduating 2024" cannot be met by a
      Bachelor from 2019 plus some other course ending in 2024.
    - q: name, target role, summary, skill or project name.
    """
    skill_ids = _int_list(params.get("skills"), "skills")
    qualification = _int(params.get("qualification"), "qualification", 1)
    degree = _int(params.get("degree"), "degree", 1)
    year = _int(params.get("graduation_year"), "graduation_year", 1950, 2100)
    q = (params.get("q") or "").strip()[:100]

    qs = candidate_pool()
    for skill_id in skill_ids:
        # One filter() per skill: separate joins, so all must be present.
        qs = qs.filter(skills__skill_id=skill_id)

    education = {}
    if qualification:
        education["education__degree__degree_name_id"] = qualification
    if degree:
        education["education__degree_id"] = degree
    if year:
        education["education__to_date__year"] = year
    if education:
        qs = qs.filter(**education)

    if q:
        qs = qs.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(job_role__icontains=q)
            | Q(profile_description__icontains=q)
            | Q(skills__skill__name__icontains=q)
            | Q(project__name__icontains=q)
        )
    return qs.distinct().order_by("-resume_publication__published_at", "id")


def full_name(user):
    return " ".join(p for p in [user.first_name, user.last_name] if p).strip() or "Unnamed candidate"


def _education(user):
    rows = user.education.select_related("degree__degree_name", "institute").order_by("-to_date", "-from_date")
    return [
        {
            "qualification": e.degree.degree_name.name,
            "specialization": e.degree.specialization,
            "institute": e.institute.name,
            "from_date": e.from_date,
            "to_date": e.to_date,
            "current": e.current_education,
            "score": e.score,
        }
        for e in rows
    ]


def _skills(user):
    return [
        {
            "id": t.skill_id,
            "name": t.skill.name,
            "level": SKILL_LEVELS.get(t.proficiency or "", ""),
            "years": t.year,
        }
        for t in user.skills.select_related("skill").order_by("skill__name")
    ]


def _graduation_year(education):
    years = [e["to_date"].year for e in education if e["to_date"]]
    return max(years) if years else None


def list_item(user, recruiter, shortlisted_ids, note_counts):
    education = _education(user)
    latest = education[0] if education else None
    publication = user.resume_publication
    return {
        "id": user.id,
        "name": full_name(user),
        "job_role": user.job_role,
        "summary": (user.profile_description or "")[:SUMMARY_PREVIEW],
        "skills": [s["name"] for s in _skills(user)],
        "latest_education": (
            {k: latest[k] for k in ("qualification", "specialization", "institute")} if latest else None
        ),
        "graduation_year": _graduation_year(education),
        "published_at": publication.published_at,
        "shortlisted": user.id in shortlisted_ids,
        "note_count": note_counts.get(user.id, 0),
    }


def list_context(recruiter, candidate_ids):
    shortlisted = set(
        CandidateShortlist.objects.filter(recruiter=recruiter, candidate_id__in=candidate_ids).values_list(
            "candidate_id", flat=True
        )
    )
    counts = dict(
        CandidateNote.objects.filter(recruiter=recruiter, candidate_id__in=candidate_ids)
        .values("candidate_id")
        .annotate(n=Count("id"))
        .values_list("candidate_id", "n")
    )
    return shortlisted, counts


def detail(user, recruiter):
    """What a recruiter may see about a candidate. Contact details are left out
    unless the job seeker chose to show their email; phone, address, date of
    birth and salary are never included."""
    version = user.resume_publication.version
    education = _education(user)
    return {
        "id": user.id,
        "name": full_name(user),
        "job_role": user.job_role,
        "summary": user.profile_description,
        "email": user.email if user.show_email else None,
        "skills": _skills(user),
        "education": education,
        "graduation_year": _graduation_year(education),
        "employment": [
            {
                "company": e.company,
                "designation": e.designation,
                "from_date": e.from_date,
                "to_date": e.to_date,
                "current": e.current_job,
                "description": e.job_profile,
            }
            for e in user.employment_history.order_by("-from_date")
        ],
        "projects": [
            {
                "name": p.name,
                "description": p.description,
                "role": p.role,
                "size": p.size,
                "from_date": p.from_date,
                "to_date": p.to_date,
                "skills": [s.name for s in p.skills.order_by("name")],
            }
            for p in user.project.prefetch_related("skills").order_by("-from_date")
        ],
        "resume": {
            "title": version.title,
            "published_at": user.resume_publication.published_at,
            "pdf_size": version.pdf_size,
        },
        "shortlisted": CandidateShortlist.objects.filter(recruiter=recruiter, candidate=user).exists(),
    }
