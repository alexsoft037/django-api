# Generated by Django 2.0.9 on 2019-10-02 00:29

import cozmo.storages
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contact',
            name='avatar',
            field=models.ImageField(blank=True, max_length=500, null=True, upload_to=cozmo.storages.UploadImageTo('crm/guests')),
        ),
    ]
