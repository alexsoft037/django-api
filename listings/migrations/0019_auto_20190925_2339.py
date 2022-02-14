# Generated by Django 2.0.9 on 2019-09-25 23:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0018_auto_20190829_0815'),
    ]

    operations = [
        migrations.AddField(
            model_name='reservation',
            name='cancellation_notes',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='reservation',
            name='cancellation_reason',
            field=models.PositiveSmallIntegerField(choices=[(0, 'other'), (1, 'renter cancelled'), (2, 'dates unavailable'), (3, 'payment issue'), (4, 'fraudulent')], default=None, null=True),
        ),
    ]
