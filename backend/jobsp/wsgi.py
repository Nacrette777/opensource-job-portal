import os
import sys

from django.core.wsgi import get_wsgi_application

PROJECT_DIR = os.path.abspath(__file__)
sys.path.append(PROJECT_DIR)

# Default to the peeljobs.com production settings as before, but let a
# deployment choose its own module (GradBridge containers set
# DJANGO_SETTINGS_MODULE=jobsp.settings_gradbridge).
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jobsp.settings_server")

application = get_wsgi_application()
