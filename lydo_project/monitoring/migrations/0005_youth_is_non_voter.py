from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0004_useraccesslog'),
    ]

    operations = [
        migrations.AddField(
            model_name='youth',
            name='is_non_voter',
            field=models.BooleanField(default=False, verbose_name='Non-Voter'),
        ),
    ]
