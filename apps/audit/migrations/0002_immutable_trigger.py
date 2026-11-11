"""PostgreSQL trigger that makes the audit table append-only (NFR03, NFR04)."""
from django.db import migrations

from apps.core_immutable import immutable_trigger_sql


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [migrations.RunSQL(*immutable_trigger_sql("audit_auditevent"))]
