# Generated by Django 2.0.9 on 2019-10-18 20:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0024_reservationrefund'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reservation',
            name='source',
            field=models.PositiveSmallIntegerField(choices=[(1, 'App'), (2, 'Web'), (3, 'Airbnb'), (4, 'VRBO'), (5, 'Booking'), (6, 'Tripadvisor'), (7, 'Recommended'), (8, 'Homeaway')], default=1),
        ),
    ]
