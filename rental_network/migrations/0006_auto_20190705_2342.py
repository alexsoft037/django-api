# Generated by Django 2.0.9 on 2019-07-05 23:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rental_network', '0005_auto_20190705_2240'),
    ]

    operations = [
        migrations.AlterField(
            model_name='proxy',
            name='host',
            field=models.CharField(max_length=512),
        ),
    ]
