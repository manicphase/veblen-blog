# Generated by Django 5.0.6 on 2024-07-13 10:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Blog', '0005_attachment'),
    ]

    operations = [
        migrations.AddField(
            model_name='note',
            name='post_type',
            field=models.TextField(default='Note', max_length=20),
            preserve_default=False,
        ),
    ]
