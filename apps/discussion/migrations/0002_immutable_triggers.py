"""Comments and project messages are append-only at database level."""
from django.db import migrations

from apps.core_immutable import immutable_trigger_sql


class Migration(migrations.Migration):
    dependencies = [("discussion", "0001_initial")]

    operations = [
        migrations.RunSQL(*immutable_trigger_sql(table))
        for table in ["discussion_comment", "discussion_projectmessage"]
    ]
