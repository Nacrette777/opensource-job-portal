# Constants for test data generation
# These match the choices in peeldb/models.py

# Company sizes
COMPANY_SIZES = ["1-10", "11-20", "21-50", "50-200", "200+"]

# Company types
COMPANY_TYPES = ["Company", "Consultant"]

# User types
USER_TYPE_JOBSEEKER = "JS"
USER_TYPE_EMPLOYER = "EM"

# Gender types
GENDERS = ["M", "F"]

# Job types
JOB_TYPES = [
    "full-time",
    "permanent",
    "contract",
    "internship",
    "part-time",
    "freelance",
    "walk-in",
    "government",
    "fresher",
]

# Most common job types (weighted for realistic distribution)
COMMON_JOB_TYPES = ["full-time", "permanent", "contract", "internship"]

# Work modes
WORK_MODES = ["in-office", "remote", "hybrid"]

# Job post statuses
JOB_POST_STATUSES = [
    "Draft",
    "Exprired",
    "Live",
    "Disabled",
    "Pending",
    "Published",
    "Hired",
    "Process",
]

# Common job statuses for test data
COMMON_JOB_STATUSES = ["Live", "Draft", "Disabled", "Exprired"]
JOB_STATUS_WEIGHTS = [70, 10, 10, 10]  # Weights for each status

# Application statuses
APPLICATION_STATUSES = ["Pending", "Shortlisted", "Hired", "Rejected"]
APPLICATION_STATUS_WEIGHTS = [50, 25, 10, 15]  # Weights for each status

# Seniority levels
SENIORITY_LEVELS = ["intern", "junior", "mid", "senior", "lead", "manager"]

# Skill proficiency levels
SKILL_PROFICIENCIES = ["Poor", "Average", "Good", "Expert"]
SKILL_PROFICIENCY_WEIGHTS = [10, 25, 40, 25]  # Weights for each level

# Salary types
SALARY_TYPES = ["Month", "Year"]

# Notice periods
NOTICE_PERIODS = ["Immediate", "15 Days", "1 Month", "2 Months", "3 Months"]

# Degree types
DEGREE_TYPES = ["Permanent", "PartTime"]

# Common qualifications (match load_gradbridge_reference_data)
COMMON_QUALIFICATIONS = [
    "Bachelor's Degree",
    "Bachelor's Degree (Honours)",
    "Master's Degree",
    "Diploma",
    "Polytechnic Diploma",
    "Advanced Diploma",
    "Graduate Certificate",
    "MBA",
]

# Yearly salary ranges by years of experience, in each market's currency.
# A job or job seeker in Singapore uses SGD, everywhere else AUD.
SALARY_RANGES = {
    "AUD": {
        0: (65000, 80000),  # Graduate
        1: (70000, 90000),  # 1 year
        2: (80000, 100000),  # 2 years
        3: (90000, 115000),  # 3 years
        5: (110000, 140000),  # 5 years
        7: (130000, 165000),  # 7 years
        10: (150000, 190000),  # 10 years
        15: (170000, 230000),  # 15+ years
    },
    "SGD": {
        0: (48000, 66000),  # Graduate
        1: (55000, 75000),  # 1 year
        2: (62000, 85000),  # 2 years
        3: (70000, 100000),  # 3 years
        5: (90000, 130000),  # 5 years
        7: (110000, 160000),  # 7 years
        10: (140000, 200000),  # 10 years
        15: (170000, 260000),  # 15+ years
    },
}

# Experience levels (years)
EXPERIENCE_LEVELS = [0, 1, 2, 3, 5, 7, 10, 12, 15]

# Hiring priorities
HIRING_PRIORITIES = ["Low", "Normal", "High"]

# Hiring timelines
HIRING_TIMELINES = ["1-3days", "1-2weeks", "1month", "1-3months"]

# Test data marker (for idempotency)
TEST_DATA_MARKER = "[TEST DATA]"

# Default counts
DEFAULT_COMPANIES = 50
DEFAULT_RECRUITERS = 100
DEFAULT_JOBSEEKERS = 500
DEFAULT_JOBS = 1000
DEFAULT_APPLICATIONS = 3000

# Batch size for bulk operations
BATCH_SIZE = 100

# Password for test users
TEST_PASSWORD = "testpass123"
