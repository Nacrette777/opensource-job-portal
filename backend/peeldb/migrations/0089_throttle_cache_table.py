from django.core.management import call_command
from django.db import migrations


def create_cache_tables(apps, schema_editor):
    # Creates the table of every DatabaseCache in CACHES (settings_gradbridge
    # uses one for API rate limits) and skips tables that exist, so this is a
    # no-op where no database cache is configured (development, tests).
    call_command("createcachetable", database=schema_editor.connection.alias)


class Migration(migrations.Migration):
    dependencies = [
        ("peeldb", "0088_sg_au_choice_labels"),
    ]

    operations = [
        migrations.RunPython(create_cache_tables, migrations.RunPython.noop),
    ]
