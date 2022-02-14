# Generated by Django 2.0.9 on 2019-10-24 20:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0025_auto_20191018_2023'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reservation',
            name='confirmation_code',
            field=models.CharField(blank=True, default=None, help_text='Friendly reservation identifier', max_length=255, null=True, unique=True),
        ),
    ]
