# Generated by Django 2.0.9 on 2019-09-11 01:05

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0002_auto_20190906_2220'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='subscription',
            options={'permissions': (('view_subscription', 'Can view subscriptions'),)},
        )
    ]
