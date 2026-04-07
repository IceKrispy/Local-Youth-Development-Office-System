from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0005_youth_is_non_voter'),
    ]

    operations = [
        migrations.AddField(
            model_name='youth',
            name='sports_preference_other',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='youth',
            name='sports_preferences',
            field=models.TextField(blank=True, default='[]'),
        ),
        migrations.AddField(
            model_name='youth',
            name='talent_preference_other',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='youth',
            name='talent_preferences',
            field=models.TextField(blank=True, default='[]'),
        ),
    ]
