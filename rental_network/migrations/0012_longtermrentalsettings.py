# Generated by Django 2.0.9 on 2019-07-23 00:37

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0008_auto_20190723_0037'),
        ('rental_network', '0011_account_organization'),
    ]

    operations = [
        migrations.CreateModel(
            name='LongTermRentalSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_created', models.DateTimeField(auto_now_add=True, null=True)),
                ('date_updated', models.DateTimeField(auto_now=True, null=True)),
                ('lease_duration', models.IntegerField()),
                ('date_available', models.DateField(default=None, null=True)),
                ('lease_terms', models.TextField(blank=True)),
                ('prop', models.OneToOneField(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='long_term_rental_settings', to='listings.Property')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
