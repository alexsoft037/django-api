# Generated by Django 2.0.9 on 2019-10-02 00:00

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0020_auto_20190926_0009'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExternalListing',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.URLField()),
                ('source', models.PositiveSmallIntegerField(choices=[(1, 'Airbnb'), (2, 'VRBO'), (3, 'Booking'), (4, 'Tripadvisor'), (5, 'Other')])),
                ('listing_id', models.CharField(max_length=64)),
                ('prop', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='external_listings', to='listings.Property')),
            ],
        ),
    ]
