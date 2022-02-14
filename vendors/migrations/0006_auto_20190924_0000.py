# Generated by Django 2.0.9 on 2019-09-24 00:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vendors', '0005_auto_20190829_2220'),
    ]

    operations = [
        migrations.AlterField(
            model_name='vendor',
            name='payout_preference',
            field=models.SmallIntegerField(choices=[(0, 'Check'), (1, 'ACH'), (2, 'Cash')], default=2),
        ),
    ]
