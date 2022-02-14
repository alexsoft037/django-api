# Generated by Django 2.0.9 on 2019-05-09 01:36

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrganizationSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_created', models.DateTimeField(auto_now_add=True, null=True)),
                ('date_updated', models.DateTimeField(auto_now=True, null=True)),
                ('channel_network_enabled', models.BooleanField(default=False)),
                ('organization', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='settings', to='accounts.Organization')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
