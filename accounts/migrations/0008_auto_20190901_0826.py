# Generated by Django 2.0.9 on 2019-09-01 08:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_auto_20190830_1855'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.IntegerField(choices=[(1, 'owner'), (2, 'admin'), (3, 'contributor'), (4, 'contributor group'), (5, 'cleaner'), (6, 'property owner'), (7, 'developer'), (8, 'contractor'), (9, 'analyst')], default=None, null=True),
        ),
    ]
