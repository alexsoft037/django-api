# Generated by Django 2.0.9 on 2019-08-29 00:43

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('vendors', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='job',
            options={'permissions': (('view_jobr', 'Can view jobs'),)},
        ),
        migrations.AlterModelOptions(
            name='vendor',
            options={'permissions': (('view_vendor', 'Can view vendors'),)},
        ),
    ]
