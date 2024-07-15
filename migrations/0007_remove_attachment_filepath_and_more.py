# Generated by Django 5.0.6 on 2024-07-14 09:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Blog', '0006_note_post_type'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='attachment',
            name='filepath',
        ),
        migrations.RemoveField(
            model_name='attachment',
            name='thumbnail_path',
        ),
        migrations.AddField(
            model_name='attachment',
            name='image',
            field=models.ImageField(null=True, upload_to='attachments'),
        ),
    ]