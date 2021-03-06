# Generated by Django 2.0.9 on 2019-05-09 01:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0004_auto_20190420_0038'),
    ]

    operations = [
        migrations.CreateModel(
            name='AdvancedAmenities',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('wifi_ssid', models.CharField(blank=True, default='', max_length=64)),
                ('wifi_password', models.CharField(blank=True, default='', max_length=64)),
            ],
        ),
        migrations.AddField(
            model_name='property',
            name='channel_network_enabled',
            field=models.BooleanField(default=False),
        ),
    ]
