# Generated by Django 2.0.9 on 2019-10-25 00:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0026_auto_20191024_2007'),
    ]

    operations = [
        migrations.AddField(
            model_name='schedulingassistant',
            name='enabled',
            field=models.BooleanField(default=False),
        ),
    ]
