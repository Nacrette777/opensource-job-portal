"""Read-only conversion of an existing job seeker to standard JSON Resume.

This is deliberately an allowlist, not a serialization of the User model.
Reactive Resume owns conversion to its native schema and presentation defaults.
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

# Same labels shown by the student SkillsSection, not inferred proficiency.
SKILL_LEVELS = {
    "Poor": "Beginner",
    "Average": "Intermediate",
    "Good": "Advanced",
    "Expert": "Expert",
}


@dataclass
class ResumeExport:
    data: dict
    warnings: list[str]


def _text(value):
    return str(value).strip() if value is not None else ""


def _compact(values):
    return {key: value for key, value in values.items() if value not in ("", None, [])}


def _dates(record, path, warnings, *, current=False):
    dates = {}
    if record.from_date:
        dates["startDate"] = record.from_date.isoformat()
    else:
        warnings.append(f"{path}.startDate: missing; omitted.")
    if current:
        if record.to_date:
            warnings.append(f"{path}.endDate: omitted because marked current.")
    elif record.to_date:
        dates["endDate"] = record.to_date.isoformat()
    elif record.from_date:
        warnings.append(
            f"{path}.endDate: missing without a current-status flag; "
            "RR displays Present. Verify the date in the student profile or RR."
        )
    return dates


def build_json_resume(user):
    """Convert only this user's related records; never save or contact RR."""
    if user.user_type != "JS":
        raise ValueError("Only a job seeker (user_type=JS) can be exported.")

    warnings = []
    basics = _compact(
        {
            "name": " ".join(
                part for part in (_text(user.first_name), _text(user.last_name)) if part
            ),
            "email": _text(user.email),
            "phone": _text(user.mobile),
            "label": _text(user.job_role),
            "summary": _text(user.profile_description),
        }
    )
    if basics.get("email"):
        try:
            validate_email(basics["email"])
        except ValidationError:
            del basics["email"]
            warnings.append("basics.email: invalid email; omitted.")
    for field in ("name", "email", "phone", "label", "summary"):
        if field not in basics:
            warnings.append(f"basics.{field}: missing; omitted.")

    city = user.current_city or user.city
    state = city.state if city and city.state_id else user.state
    country = state.country if state and state.country_id else user.country
    location = _compact(
        {
            "city": _text(city.name) if city else "",
            "region": _text(state.name) if state else "",
            "address": _text(user.address),
            "postalCode": _text(user.pincode),
        }
    )
    if location:
        basics["location"] = location
    if country:
        warnings.append(
            "basics.location.countryCode: Country has no ISO code field; omitted."
        )
    if "address" in location or "postalCode" in location:
        warnings.append(
            "RR ignores location.address/postalCode; retained in JSON Resume."
        )

    # Keep basics even when empty: RR uses it to detect JSON Resume format.
    data = {"basics": basics}
    education = []
    for index, entry in enumerate(
        user.education.select_related("institute", "degree__degree_name").order_by("pk")
    ):
        path = f"education[{index}]"
        item = _compact(
            {
                "institution": _text(entry.institute.name),
                "studyType": _text(entry.degree.degree_name.name),
                "area": _text(entry.degree.specialization),
                "score": _text(entry.score),
            }
        )
        item.update(_dates(entry, path, warnings, current=entry.current_education))
        if not item.get("institution"):
            warnings.append(f"{path}: institution missing; RR will discard this entry.")
        education.append(item)

    work = []
    for index, entry in enumerate(user.employment_history.order_by("pk")):
        path = f"work[{index}]"
        item = _compact(
            {
                "name": _text(entry.company),
                "position": _text(entry.designation),
                "summary": _text(entry.job_profile),
            }
        )
        item.update(_dates(entry, path, warnings, current=entry.current_job))
        if not (item.get("name") or item.get("position")):
            warnings.append(
                f"{path}: company/position missing; RR will discard this entry."
            )
        work.append(item)

    skills = []
    for index, entry in enumerate(user.skills.select_related("skill").order_by("pk")):
        item = _compact(
            {
                "name": _text(entry.skill.name),
                "level": SKILL_LEVELS.get(entry.proficiency, _text(entry.proficiency)),
            }
        )
        if not item.get("name"):
            warnings.append(
                f"skills[{index}]: name missing; RR will discard this entry."
            )
        skills.append(item)

    projects = []
    for index, entry in enumerate(
        user.project.select_related("location")
        .prefetch_related("skills")
        .order_by("pk")
    ):
        path = f"projects[{index}]"
        keywords = [
            _text(skill.name) for skill in entry.skills.all() if _text(skill.name)
        ]
        role = _text(entry.role)
        # RR currently ignores roles/keywords; highlights preserve their visible text.
        highlights = []
        if role:
            highlights.append(f"Role: {role}")
        if keywords:
            highlights.append(f"Skills: {', '.join(keywords)}")
        if entry.location:
            highlights.append(f"Location: {entry.location.name}")
        if entry.size is not None:
            highlights.append(f"Team size: {entry.size}")
        item = _compact(
            {
                "name": _text(entry.name),
                "description": _text(entry.description),
                "roles": [role] if role else [],
                "keywords": keywords,
                "highlights": highlights,
            }
        )
        item.update(_dates(entry, path, warnings))
        if not item.get("name"):
            warnings.append(f"{path}: name missing; RR will discard this entry.")
        projects.append(item)

    for section, items in (
        ("education", education),
        ("work", work),
        ("skills", skills),
        ("projects", projects),
    ):
        if items:
            data[section] = items
        else:
            warnings.append(f"{section}: no saved records; omitted.")

    return ResumeExport(data, warnings)
