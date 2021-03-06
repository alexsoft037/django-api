# Generated by Django 2.0.9 on 2019-05-16 20:58

import cozmo.storages
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('listings', '0005_auto_20190509_0118'),
    ]

    operations = [
        migrations.CreateModel(
            name='Account',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_created', models.DateTimeField(auto_now_add=True, null=True)),
                ('date_updated', models.DateTimeField(auto_now=True, null=True)),
                ('username', models.CharField(max_length=64)),
                ('password', models.CharField(max_length=64)),
                ('account_type', models.PositiveSmallIntegerField(choices=[(1, 'ZILLOW')])),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Proxy',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_created', models.DateTimeField(auto_now_add=True, null=True)),
                ('date_updated', models.DateTimeField(auto_now=True, null=True)),
                ('username', models.CharField(max_length=64)),
                ('password', models.CharField(max_length=64)),
                ('host', models.URLField()),
                ('port', models.CharField(max_length=16)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ProxyAssignment',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_created', models.DateTimeField(auto_now_add=True, null=True)),
                ('date_updated', models.DateTimeField(auto_now=True, null=True)),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rental_network.Account')),
                ('prop', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='listings.Property')),
                ('proxy', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rental_network.Proxy')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='RentalNetworkJob',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_created', models.DateTimeField(auto_now_add=True, null=True)),
                ('date_updated', models.DateTimeField(auto_now=True, null=True)),
                ('status', models.PositiveSmallIntegerField(choices=[(1, 'INIT'), (2, 'STARTED'), (3, 'PAUSED'), (4, 'ERROR'), (5, 'STOPPED'), (6, 'COMPLETED'), (7, 'CANCELLED')], default=1)),
                ('step', models.CharField(max_length=36)),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rental_network.Account')),
                ('prop', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='listings.Property')),
                ('proxy', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rental_network.Proxy')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Screenshot',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_created', models.DateTimeField(auto_now_add=True, null=True)),
                ('date_updated', models.DateTimeField(auto_now=True, null=True)),
                ('url', models.ImageField(max_length=500, upload_to=cozmo.storages.UploadImageTo('selenium/images'))),
                ('caption', models.TextField(blank=True, default='')),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rental_network.RentalNetworkJob')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
