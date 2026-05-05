"""
Management command: cleanup_trash

Permanently deletes files/folders in ERP_TRASH_ROOT that are older than
ERP_TRASH_RETENTION_DAYS (default: 30) days.

Usage:
    python manage.py cleanup_trash
    python manage.py cleanup_trash --dry-run
    python manage.py cleanup_trash --days 7
"""

import shutil
from datetime import datetime, timedelta
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.docs_utils import trash_root, trash_retention_days
from core.models import DocumentAuditLog


class Command(BaseCommand):
    help = "Remove trash items older than ERP_TRASH_RETENTION_DAYS days."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting.',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help='Override retention days (default: ERP_TRASH_RETENTION_DAYS setting).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        days = options['days'] if options['days'] is not None else trash_retention_days()
        cutoff = timezone.now() - timedelta(days=days)

        t_root = trash_root()
        if not t_root.is_dir():
            self.stdout.write(self.style.WARNING(f"Trash root does not exist: {t_root}"))
            return

        self.stdout.write(f"Trash root: {t_root}")
        self.stdout.write(f"Retention: {days} days  (cutoff: {cutoff:%Y-%m-%d %H:%M})")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — nothing will be deleted."))

        deleted_count = 0
        error_count = 0

        # Trash entries are stored as: <trash_root>/<timestamp>__<user>/<original_rel_path>
        # We scan the first-level "prefix" directories and check their modification time.
        for prefix_dir in sorted(t_root.iterdir()):
            if not prefix_dir.is_dir():
                continue

            # Use directory mtime as age indicator (set when item was trashed).
            try:
                mtime = prefix_dir.stat().st_mtime
            except OSError:
                continue

            item_time = timezone.make_aware(
                datetime.fromtimestamp(mtime),
                timezone.get_default_timezone(),
            )

            if item_time <= cutoff:
                self.stdout.write(f"  {'[DRY] ' if dry_run else ''}Deleting: {prefix_dir.name}  (age: {(timezone.now() - item_time).days} days)")
                if not dry_run:
                    try:
                        shutil.rmtree(prefix_dir)
                        # Log the cleanup
                        DocumentAuditLog.objects.create(
                            user=None,
                            produkt=None,
                            action=DocumentAuditLog.ACTION_CLEANUP,
                            src_rel_path=prefix_dir.name,
                            dest_rel_path='',
                        )
                        deleted_count += 1
                    except Exception as exc:
                        self.stderr.write(f"    ERROR deleting {prefix_dir}: {exc}")
                        error_count += 1
                else:
                    deleted_count += 1

        summary = f"Done. {'Would delete' if dry_run else 'Deleted'}: {deleted_count}, Errors: {error_count}"
        if error_count:
            self.stdout.write(self.style.ERROR(summary))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
