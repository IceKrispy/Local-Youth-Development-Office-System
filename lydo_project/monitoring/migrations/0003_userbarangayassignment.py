from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('monitoring', '0002_sync_is_unemployed_state'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserBarangayAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('barangay', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assigned_users', to='monitoring.barangay')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='barangay_assignment', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
