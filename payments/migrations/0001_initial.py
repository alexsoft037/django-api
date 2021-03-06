# Generated by Django 2.0.9 on 2019-03-07 23:49

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Charge',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_id', models.CharField(max_length=150)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=8)),
                ('refunded_amount', models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=8)),
                ('is_refundable', models.BooleanField(default=False)),
                ('payment_for_id', models.PositiveIntegerField()),
                ('status', models.PositiveIntegerField(choices=[(1, 'Succeeded'), (2, 'Pending'), (3, 'Failed'), (4, 'Delayed')], default=4, null=True)),
                ('source_id', models.CharField(default='', max_length=150)),
                ('schedule', models.PositiveSmallIntegerField(choices=[(1, 'Now'), (2, 'Custom'), (3, 'Specific Date'), (4, 'At time of check in'), (5, 'At time of booking')], null=True)),
                ('schedule_value', models.DateField(blank=True, null=True)),
                ('date_updated', models.DateTimeField(auto_now=True, null=True)),
                ('date_created', models.DateTimeField(auto_now_add=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Coupon',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_id', models.CharField(max_length=200)),
                ('name', models.CharField(blank=True, max_length=40, null=True)),
                ('percent_off', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('amount_off', models.PositiveIntegerField(blank=True, null=True)),
                ('currency', models.CharField(blank=True, choices=[('AFN', 'AFN'), ('DZD', 'DZD'), ('ARS', 'ARS'), ('AMD', 'AMD'), ('AWG', 'AWG'), ('AUD', 'AUD'), ('AZN', 'AZN'), ('BSD', 'BSD'), ('BHD', 'BHD'), ('THB', 'THB'), ('PAB', 'PAB'), ('BBD', 'BBD'), ('BYN', 'BYN'), ('BZD', 'BZD'), ('BMD', 'BMD'), ('BOB', 'BOB'), ('VEF', 'VEF'), ('BRL', 'BRL'), ('BND', 'BND'), ('BGN', 'BGN'), ('BIF', 'BIF'), ('CVE', 'CVE'), ('CAD', 'CAD'), ('KYD', 'KYD'), ('CLP', 'CLP'), ('COP', 'COP'), ('KMF', 'KMF'), ('CDF', 'CDF'), ('BAM', 'BAM'), ('NIO', 'NIO'), ('CRC', 'CRC'), ('CUP', 'CUP'), ('CZK', 'CZK'), ('GMD', 'GMD'), ('DKK', 'DKK'), ('MKD', 'MKD'), ('DJF', 'DJF'), ('STN', 'STN'), ('DOP', 'DOP'), ('VND', 'VND'), ('XCD', 'XCD'), ('EGP', 'EGP'), ('SVC', 'SVC'), ('ETB', 'ETB'), ('EUR', 'EUR'), ('FKP', 'FKP'), ('FJD', 'FJD'), ('HUF', 'HUF'), ('GHS', 'GHS'), ('GIP', 'GIP'), ('HTG', 'HTG'), ('PYG', 'PYG'), ('GNF', 'GNF'), ('GYD', 'GYD'), ('HKD', 'HKD'), ('UAH', 'UAH'), ('ISK', 'ISK'), ('INR', 'INR'), ('IRR', 'IRR'), ('IQD', 'IQD'), ('JMD', 'JMD'), ('JOD', 'JOD'), ('KES', 'KES'), ('PGK', 'PGK'), ('HRK', 'HRK'), ('KWD', 'KWD'), ('AOA', 'AOA'), ('MMK', 'MMK'), ('LAK', 'LAK'), ('GEL', 'GEL'), ('LBP', 'LBP'), ('ALL', 'ALL'), ('HNL', 'HNL'), ('SLL', 'SLL'), ('LRD', 'LRD'), ('LYD', 'LYD'), ('SZL', 'SZL'), ('LSL', 'LSL'), ('MGA', 'MGA'), ('MWK', 'MWK'), ('MYR', 'MYR'), ('MUR', 'MUR'), ('MXN', 'MXN'), ('MDL', 'MDL'), ('MAD', 'MAD'), ('MZN', 'MZN'), ('BOV', 'BOV'), ('NGN', 'NGN'), ('ERN', 'ERN'), ('NAD', 'NAD'), ('NPR', 'NPR'), ('ANG', 'ANG'), ('ILS', 'ILS'), ('TWD', 'TWD'), ('NZD', 'NZD'), ('BTN', 'BTN'), ('KPW', 'KPW'), ('NOK', 'NOK'), ('MRU', 'MRU'), ('PKR', 'PKR'), ('MOP', 'MOP'), ('TOP', 'TOP'), ('CUC', 'CUC'), ('UYU', 'UYU'), ('PHP', 'PHP'), ('GBP', 'GBP'), ('BWP', 'BWP'), ('QAR', 'QAR'), ('GTQ', 'GTQ'), ('ZAR', 'ZAR'), ('OMR', 'OMR'), ('KHR', 'KHR'), ('RON', 'RON'), ('MVR', 'MVR'), ('IDR', 'IDR'), ('RUB', 'RUB'), ('RWF', 'RWF'), ('SHP', 'SHP'), ('SAR', 'SAR'), ('RSD', 'RSD'), ('SCR', 'SCR'), ('SGD', 'SGD'), ('PEN', 'PEN'), ('SBD', 'SBD'), ('KGS', 'KGS'), ('SOS', 'SOS'), ('TJS', 'TJS'), ('SSP', 'SSP'), ('LKR', 'LKR'), ('XSU', 'XSU'), ('SDG', 'SDG'), ('SRD', 'SRD'), ('SEK', 'SEK'), ('CHF', 'CHF'), ('SYP', 'SYP'), ('BDT', 'BDT'), ('WST', 'WST'), ('TZS', 'TZS'), ('KZT', 'KZT'), ('TTD', 'TTD'), ('MNT', 'MNT'), ('TND', 'TND'), ('TRY', 'TRY'), ('TMT', 'TMT'), ('AED', 'AED'), ('USD', 'USD'), ('UGX', 'UGX'), ('CLF', 'CLF'), ('COU', 'COU'), ('UZS', 'UZS'), ('VUV', 'VUV'), ('KRW', 'KRW'), ('YER', 'YER'), ('JPY', 'JPY'), ('CNY', 'CNY'), ('ZMW', 'ZMW'), ('ZWL', 'ZWL'), ('PLN', 'PLN')], default='USD', max_length=3, null=True)),
                ('duration', models.CharField(choices=[('forever', 'Forever'), ('once', 'Once'), ('repeating', 'Repeating')], max_length=15)),
                ('duration_in_months', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('max_redemptions', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('redeem_by', models.DateTimeField(blank=True, null=True)),
                ('is_valid', models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name='CreditCard',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_id', models.CharField(default='', max_length=150)),
                ('last4', models.CharField(default='', max_length=4)),
                ('brand', models.PositiveSmallIntegerField(choices=[(1, 'Visa'), (2, 'American Express'), (3, 'MasterCard'), (4, 'Discover'), (5, 'JCB'), (6, 'Diners Club'), (7, 'Unknown')], default=7)),
                ('exp_year', models.PositiveSmallIntegerField(null=True)),
                ('exp_month', models.PositiveSmallIntegerField(null=True)),
                ('customer_obj_id', models.PositiveIntegerField(null=True)),
                ('date_updated', models.DateTimeField(auto_now=True, null=True)),
                ('date_created', models.DateTimeField(auto_now_add=True, null=True)),
                ('content_type', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.ContentType')),
            ],
        ),
        migrations.CreateModel(
            name='Customer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_id', models.CharField(max_length=150)),
                ('organization', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='accounts.Organization')),
            ],
        ),
        migrations.CreateModel(
            name='Dispute',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_id', models.CharField(max_length=150)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=8)),
                ('balance_transaction', models.CharField(blank=True, default='', max_length=150)),
                ('status', models.CharField(max_length=50)),
                ('reason', models.CharField(max_length=50)),
                ('livemode', models.BooleanField(default=False)),
                ('is_charge_refundable', models.BooleanField(default=False)),
                ('currency', models.CharField(choices=[('AFN', 'AFN'), ('DZD', 'DZD'), ('ARS', 'ARS'), ('AMD', 'AMD'), ('AWG', 'AWG'), ('AUD', 'AUD'), ('AZN', 'AZN'), ('BSD', 'BSD'), ('BHD', 'BHD'), ('THB', 'THB'), ('PAB', 'PAB'), ('BBD', 'BBD'), ('BYN', 'BYN'), ('BZD', 'BZD'), ('BMD', 'BMD'), ('BOB', 'BOB'), ('VEF', 'VEF'), ('BRL', 'BRL'), ('BND', 'BND'), ('BGN', 'BGN'), ('BIF', 'BIF'), ('CVE', 'CVE'), ('CAD', 'CAD'), ('KYD', 'KYD'), ('CLP', 'CLP'), ('COP', 'COP'), ('KMF', 'KMF'), ('CDF', 'CDF'), ('BAM', 'BAM'), ('NIO', 'NIO'), ('CRC', 'CRC'), ('CUP', 'CUP'), ('CZK', 'CZK'), ('GMD', 'GMD'), ('DKK', 'DKK'), ('MKD', 'MKD'), ('DJF', 'DJF'), ('STN', 'STN'), ('DOP', 'DOP'), ('VND', 'VND'), ('XCD', 'XCD'), ('EGP', 'EGP'), ('SVC', 'SVC'), ('ETB', 'ETB'), ('EUR', 'EUR'), ('FKP', 'FKP'), ('FJD', 'FJD'), ('HUF', 'HUF'), ('GHS', 'GHS'), ('GIP', 'GIP'), ('HTG', 'HTG'), ('PYG', 'PYG'), ('GNF', 'GNF'), ('GYD', 'GYD'), ('HKD', 'HKD'), ('UAH', 'UAH'), ('ISK', 'ISK'), ('INR', 'INR'), ('IRR', 'IRR'), ('IQD', 'IQD'), ('JMD', 'JMD'), ('JOD', 'JOD'), ('KES', 'KES'), ('PGK', 'PGK'), ('HRK', 'HRK'), ('KWD', 'KWD'), ('AOA', 'AOA'), ('MMK', 'MMK'), ('LAK', 'LAK'), ('GEL', 'GEL'), ('LBP', 'LBP'), ('ALL', 'ALL'), ('HNL', 'HNL'), ('SLL', 'SLL'), ('LRD', 'LRD'), ('LYD', 'LYD'), ('SZL', 'SZL'), ('LSL', 'LSL'), ('MGA', 'MGA'), ('MWK', 'MWK'), ('MYR', 'MYR'), ('MUR', 'MUR'), ('MXN', 'MXN'), ('MDL', 'MDL'), ('MAD', 'MAD'), ('MZN', 'MZN'), ('BOV', 'BOV'), ('NGN', 'NGN'), ('ERN', 'ERN'), ('NAD', 'NAD'), ('NPR', 'NPR'), ('ANG', 'ANG'), ('ILS', 'ILS'), ('TWD', 'TWD'), ('NZD', 'NZD'), ('BTN', 'BTN'), ('KPW', 'KPW'), ('NOK', 'NOK'), ('MRU', 'MRU'), ('PKR', 'PKR'), ('MOP', 'MOP'), ('TOP', 'TOP'), ('CUC', 'CUC'), ('UYU', 'UYU'), ('PHP', 'PHP'), ('GBP', 'GBP'), ('BWP', 'BWP'), ('QAR', 'QAR'), ('GTQ', 'GTQ'), ('ZAR', 'ZAR'), ('OMR', 'OMR'), ('KHR', 'KHR'), ('RON', 'RON'), ('MVR', 'MVR'), ('IDR', 'IDR'), ('RUB', 'RUB'), ('RWF', 'RWF'), ('SHP', 'SHP'), ('SAR', 'SAR'), ('RSD', 'RSD'), ('SCR', 'SCR'), ('SGD', 'SGD'), ('PEN', 'PEN'), ('SBD', 'SBD'), ('KGS', 'KGS'), ('SOS', 'SOS'), ('TJS', 'TJS'), ('SSP', 'SSP'), ('LKR', 'LKR'), ('XSU', 'XSU'), ('SDG', 'SDG'), ('SRD', 'SRD'), ('SEK', 'SEK'), ('CHF', 'CHF'), ('SYP', 'SYP'), ('BDT', 'BDT'), ('WST', 'WST'), ('TZS', 'TZS'), ('KZT', 'KZT'), ('TTD', 'TTD'), ('MNT', 'MNT'), ('TND', 'TND'), ('TRY', 'TRY'), ('TMT', 'TMT'), ('AED', 'AED'), ('USD', 'USD'), ('UGX', 'UGX'), ('CLF', 'CLF'), ('COU', 'COU'), ('UZS', 'UZS'), ('VUV', 'VUV'), ('KRW', 'KRW'), ('YER', 'YER'), ('JPY', 'JPY'), ('CNY', 'CNY'), ('ZMW', 'ZMW'), ('ZWL', 'ZWL'), ('PLN', 'PLN')], default='USD', max_length=50)),
                ('created', models.PositiveIntegerField()),
                ('metadata', django.contrib.postgres.fields.jsonb.JSONField(blank=True, null=True)),
                ('evidence', django.contrib.postgres.fields.jsonb.JSONField(blank=True, null=True)),
                ('evidence_details', django.contrib.postgres.fields.jsonb.JSONField(blank=True, null=True)),
                ('balance_transactions', django.contrib.postgres.fields.jsonb.JSONField(blank=True, null=True)),
                ('date_updated', models.DateTimeField(auto_now=True, null=True)),
                ('date_created', models.DateTimeField(auto_now_add=True, null=True)),
                ('charge', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='payments.Charge')),
            ],
        ),
        migrations.CreateModel(
            name='PlaidApp',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='', help_text='User-friendly name', max_length=100)),
                ('item_id', models.CharField(max_length=100)),
                ('access_token', models.CharField(max_length=100)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.Organization')),
            ],
        ),
        migrations.CreateModel(
            name='PlaidTransaction',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_id', models.CharField(max_length=100)),
                ('value', models.DecimalField(decimal_places=2, max_digits=8)),
                ('title', models.CharField(max_length=250)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.Organization')),
            ],
        ),
        migrations.CreateModel(
            name='PricingPlan',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('alias', models.CharField(help_text='External service nick name', max_length=100)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=8)),
                ('currency', models.CharField(choices=[('AFN', 'AFN'), ('DZD', 'DZD'), ('ARS', 'ARS'), ('AMD', 'AMD'), ('AWG', 'AWG'), ('AUD', 'AUD'), ('AZN', 'AZN'), ('BSD', 'BSD'), ('BHD', 'BHD'), ('THB', 'THB'), ('PAB', 'PAB'), ('BBD', 'BBD'), ('BYN', 'BYN'), ('BZD', 'BZD'), ('BMD', 'BMD'), ('BOB', 'BOB'), ('VEF', 'VEF'), ('BRL', 'BRL'), ('BND', 'BND'), ('BGN', 'BGN'), ('BIF', 'BIF'), ('CVE', 'CVE'), ('CAD', 'CAD'), ('KYD', 'KYD'), ('CLP', 'CLP'), ('COP', 'COP'), ('KMF', 'KMF'), ('CDF', 'CDF'), ('BAM', 'BAM'), ('NIO', 'NIO'), ('CRC', 'CRC'), ('CUP', 'CUP'), ('CZK', 'CZK'), ('GMD', 'GMD'), ('DKK', 'DKK'), ('MKD', 'MKD'), ('DJF', 'DJF'), ('STN', 'STN'), ('DOP', 'DOP'), ('VND', 'VND'), ('XCD', 'XCD'), ('EGP', 'EGP'), ('SVC', 'SVC'), ('ETB', 'ETB'), ('EUR', 'EUR'), ('FKP', 'FKP'), ('FJD', 'FJD'), ('HUF', 'HUF'), ('GHS', 'GHS'), ('GIP', 'GIP'), ('HTG', 'HTG'), ('PYG', 'PYG'), ('GNF', 'GNF'), ('GYD', 'GYD'), ('HKD', 'HKD'), ('UAH', 'UAH'), ('ISK', 'ISK'), ('INR', 'INR'), ('IRR', 'IRR'), ('IQD', 'IQD'), ('JMD', 'JMD'), ('JOD', 'JOD'), ('KES', 'KES'), ('PGK', 'PGK'), ('HRK', 'HRK'), ('KWD', 'KWD'), ('AOA', 'AOA'), ('MMK', 'MMK'), ('LAK', 'LAK'), ('GEL', 'GEL'), ('LBP', 'LBP'), ('ALL', 'ALL'), ('HNL', 'HNL'), ('SLL', 'SLL'), ('LRD', 'LRD'), ('LYD', 'LYD'), ('SZL', 'SZL'), ('LSL', 'LSL'), ('MGA', 'MGA'), ('MWK', 'MWK'), ('MYR', 'MYR'), ('MUR', 'MUR'), ('MXN', 'MXN'), ('MDL', 'MDL'), ('MAD', 'MAD'), ('MZN', 'MZN'), ('BOV', 'BOV'), ('NGN', 'NGN'), ('ERN', 'ERN'), ('NAD', 'NAD'), ('NPR', 'NPR'), ('ANG', 'ANG'), ('ILS', 'ILS'), ('TWD', 'TWD'), ('NZD', 'NZD'), ('BTN', 'BTN'), ('KPW', 'KPW'), ('NOK', 'NOK'), ('MRU', 'MRU'), ('PKR', 'PKR'), ('MOP', 'MOP'), ('TOP', 'TOP'), ('CUC', 'CUC'), ('UYU', 'UYU'), ('PHP', 'PHP'), ('GBP', 'GBP'), ('BWP', 'BWP'), ('QAR', 'QAR'), ('GTQ', 'GTQ'), ('ZAR', 'ZAR'), ('OMR', 'OMR'), ('KHR', 'KHR'), ('RON', 'RON'), ('MVR', 'MVR'), ('IDR', 'IDR'), ('RUB', 'RUB'), ('RWF', 'RWF'), ('SHP', 'SHP'), ('SAR', 'SAR'), ('RSD', 'RSD'), ('SCR', 'SCR'), ('SGD', 'SGD'), ('PEN', 'PEN'), ('SBD', 'SBD'), ('KGS', 'KGS'), ('SOS', 'SOS'), ('TJS', 'TJS'), ('SSP', 'SSP'), ('LKR', 'LKR'), ('XSU', 'XSU'), ('SDG', 'SDG'), ('SRD', 'SRD'), ('SEK', 'SEK'), ('CHF', 'CHF'), ('SYP', 'SYP'), ('BDT', 'BDT'), ('WST', 'WST'), ('TZS', 'TZS'), ('KZT', 'KZT'), ('TTD', 'TTD'), ('MNT', 'MNT'), ('TND', 'TND'), ('TRY', 'TRY'), ('TMT', 'TMT'), ('AED', 'AED'), ('USD', 'USD'), ('UGX', 'UGX'), ('CLF', 'CLF'), ('COU', 'COU'), ('UZS', 'UZS'), ('VUV', 'VUV'), ('KRW', 'KRW'), ('YER', 'YER'), ('JPY', 'JPY'), ('CNY', 'CNY'), ('ZMW', 'ZMW'), ('ZWL', 'ZWL'), ('PLN', 'PLN')], default='USD', max_length=3)),
                ('interval', models.CharField(choices=[('month', 'monthly'), ('year', 'yearly')], default='month', max_length=10)),
                ('external_id', models.CharField(default='', max_length=150)),
            ],
        ),
        migrations.CreateModel(
            name='ProductTier',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Name displayable to users', max_length=100)),
                ('external_id', models.CharField(max_length=150)),
            ],
        ),
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fee', models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ('external_id', models.CharField(max_length=150)),
                ('coupon_external_id', models.CharField(blank=True, max_length=200, null=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='payments.Customer')),
            ],
        ),
        migrations.AddField(
            model_name='pricingplan',
            name='tier',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='payments.ProductTier'),
        ),
        migrations.AddField(
            model_name='charge',
            name='card',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='payments.CreditCard'),
        ),
        migrations.AddField(
            model_name='charge',
            name='content_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.ContentType'),
        ),
        migrations.AddField(
            model_name='charge',
            name='organization',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.Organization'),
        ),
        migrations.AddIndex(
            model_name='charge',
            index=models.Index(fields=['external_id'], name='payments_ch_externa_5a2908_idx'),
        ),
    ]
