"""
Job Serializers for API v1
"""

from django.utils import timezone
from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from peeldb.models import (
    AppliedJobs,
    City,
    Company,
    Industry,
    JobPost,
    Qualification,
    SavedJobs,
    Skill,
)

CURRENCY_SYMBOLS = {"AUD": "A$", "SGD": "S$"}


def currency_symbol(code: str | None) -> str:
    """A$ / S$ for the job's salary currency (AUD when unset)."""
    return CURRENCY_SYMBOLS.get(code or "AUD", f"{code} ")


def thousands(amount: int) -> str:
    """85000 -> "85k", 92500 -> "92.5k", 800 -> "800"."""
    if amount < 1000:
        return str(amount)
    value = amount / 1000
    return f"{value:.0f}k" if value == int(value) else f"{value:.1f}k"


class LocationSerializer(serializers.ModelSerializer):
    """Serializer for job locations (cities)"""

    state = serializers.CharField(source="state.name", read_only=True)
    state_slug = serializers.CharField(source="state.slug", read_only=True)
    country = serializers.CharField(source="state.country.name", read_only=True)

    class Meta:
        model = City
        fields = ["id", "name", "slug", "state", "state_slug", "country"]


@extend_schema_serializer(component_name="JobSkill")
class SkillSerializer(serializers.ModelSerializer):
    """Serializer for job skills"""

    class Meta:
        model = Skill
        fields = ["id", "name", "slug"]


class IndustrySerializer(serializers.ModelSerializer):
    """Serializer for industries"""

    class Meta:
        model = Industry
        fields = ["id", "name", "slug"]


class QualificationSerializer(serializers.ModelSerializer):
    """Serializer for educational qualifications"""

    class Meta:
        model = Qualification
        fields = ["id", "name", "slug"]


class CompanySerializer(serializers.ModelSerializer):
    """Serializer for company details"""

    logo = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = ["id", "name", "slug", "logo", "profile_pic", "company_type"]

    def get_logo(self, obj) -> str | None:
        """Return company logo URL"""
        if obj.profile_pic:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.profile_pic.url)
        return None


class JobListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for job listings
    Used in paginated list views for performance
    """

    locations = LocationSerializer(many=True, source="location", read_only=True)
    skills = SkillSerializer(many=True, read_only=True)
    industries = IndustrySerializer(many=True, source="industry", read_only=True)
    company_logo = serializers.SerializerMethodField()
    experience_display = serializers.SerializerMethodField()
    salary_display = serializers.SerializerMethodField()
    location_display = serializers.SerializerMethodField()
    time_ago = serializers.SerializerMethodField()
    applicants_count = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    is_applied = serializers.SerializerMethodField()
    accepts_applications = serializers.SerializerMethodField()

    class Meta:
        model = JobPost
        fields = [
            "id",
            "title",
            "slug",
            "company_name",
            "company_logo",
            "job_type",
            "locations",
            "skills",
            "industries",
            "min_salary",
            "max_salary",
            "salary_type",
            "salary_currency",
            "min_year",
            "max_year",
            "min_month",
            "max_month",
            "fresher",
            "published_on",
            "vacancies",
            "experience_display",
            "salary_display",
            "location_display",
            "time_ago",
            "applicants_count",
            "is_saved",
            "is_applied",
            "accepts_applications",
        ]

    def get_company_logo(self, obj) -> str | None:
        """Get company logo URL"""
        if obj.company and obj.company.profile_pic:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.company.profile_pic.url)
        return None

    def get_experience_display(self, obj) -> str:
        """Format experience requirement as readable string"""
        if obj.fresher:
            return "Fresher"

        min_exp = obj.min_year
        max_exp = obj.max_year

        if min_exp == 0 and max_exp == 0:
            return "Fresher"
        elif min_exp == max_exp:
            return f"{min_exp} year{'s' if min_exp != 1 else ''}"
        else:
            return f"{min_exp}-{max_exp} years"

    def get_salary_display(self, obj) -> str:
        """Format the salary as a yearly range, e.g. "A$85k–95k a year"."""
        if obj.min_salary == 0 and obj.max_salary == 0:
            return "Not Disclosed"

        # Normalise to a yearly amount
        months = 12 if obj.salary_type == "Month" else 1
        min_sal = obj.min_salary * months
        max_sal = obj.max_salary * months
        symbol = currency_symbol(obj.salary_currency)

        if min_sal == 0 and max_sal > 0:
            return f"Up to {symbol}{thousands(max_sal)} a year"
        elif min_sal > 0 and max_sal == 0:
            return f"From {symbol}{thousands(min_sal)} a year"
        elif min_sal == max_sal:
            return f"{symbol}{thousands(min_sal)} a year"
        else:
            return f"{symbol}{thousands(min_sal)}–{thousands(max_sal)} a year"

    def get_location_display(self, obj) -> str:
        """Get primary location for display"""
        locations = obj.location.all()
        if locations:
            location_names = [loc.name for loc in locations[:2]]
            if len(locations) > 2:
                return f"{', '.join(location_names)} +{len(locations) - 2} more"
            return ", ".join(location_names)
        return "Location not specified"

    def get_time_ago(self, obj) -> str:
        """Calculate and format time since job was published"""
        if not obj.published_on:
            return "Recently posted"

        now = timezone.now()
        diff = now - obj.published_on

        if diff.days == 0:
            hours = diff.seconds // 3600
            if hours == 0:
                minutes = diff.seconds // 60
                return (
                    f"{minutes} minute{'s' if minutes != 1 else ''} ago"
                    if minutes > 0
                    else "Just now"
                )
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif diff.days == 1:
            return "1 day ago"
        elif diff.days < 7:
            return f"{diff.days} days ago"
        elif diff.days < 30:
            weeks = diff.days // 7
            return f"{weeks} week{'s' if weeks != 1 else ''} ago"
        elif diff.days < 365:
            months = diff.days // 30
            return f"{months} month{'s' if months != 1 else ''} ago"
        else:
            years = diff.days // 365
            return f"{years} year{'s' if years != 1 else ''} ago"

    def get_applicants_count(self, obj) -> int:
        """Get number of applicants for this job"""
        return AppliedJobs.objects.filter(job_post=obj).count()

    def get_is_saved(self, obj) -> bool:
        """Check if job is saved by current user"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return SavedJobs.objects.filter(job_post=obj, user=request.user).exists()
        return False

    def get_is_applied(self, obj) -> bool:
        """Check if user has already applied for this job"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return AppliedJobs.objects.filter(job_post=obj, user=request.user).exists()
        return False

    def get_accepts_applications(self, obj) -> bool:
        """Check if this job post can still accept applications (30-day rule)"""
        return obj.can_accept_applications()


class JobDetailSerializer(JobListSerializer):
    """
    Comprehensive serializer for job detail view
    Extends JobListSerializer with additional fields
    """

    company = CompanySerializer(read_only=True)
    edu_qualification = QualificationSerializer(many=True, read_only=True)

    class Meta(JobListSerializer.Meta):
        fields = JobListSerializer.Meta.fields + [
            "description",
            "job_role",
            "company",
            "company_description",
            "company_address",
            "company_links",
            "company_emails",
            "edu_qualification",
            # Walk-in specific fields
            "walkin_contactinfo",
            "walkin_show_contact_info",
            "walkin_from_date",
            "walkin_to_date",
            "walkin_time",
            # Government job specific fields
            "govt_job_type",
            "application_fee",
            "selection_process",
            "how_to_apply",
            "important_dates",
            "govt_from_date",
            "govt_to_date",
            "govt_exam_date",
            "age_relaxation",
        ]


class AppliedJobSerializer(serializers.ModelSerializer):
    """
    One row of "my applications" — the job, plus this user's application to it.

    The job is nested with JobListSerializer so the applications page renders
    the same card as every other job listing.
    """

    job = JobListSerializer(source="job_post", read_only=True)

    class Meta:
        model = AppliedJobs
        fields = [
            "id",
            "job",
            "status",
            "applied_on",
        ]
        read_only_fields = fields
