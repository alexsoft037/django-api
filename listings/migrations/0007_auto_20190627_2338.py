# Generated by Django 2.0.9 on 2019-06-27 23:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0006_reservation_base_total'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricingsettings',
            name='monthly',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=9),
        ),
        migrations.AddField(
            model_name='pricingsettings',
            name='weekly',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=9),
        ),
        migrations.AddField(
            model_name='property',
            name='size',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
