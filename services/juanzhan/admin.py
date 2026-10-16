"""Local-only credential setup: python -m juanzhan.admin set-password."""
import argparse
import getpass
import sys

from .auth import set_password
from .config import Settings
from .database import migrate


def main():
    parser = argparse.ArgumentParser(description='Initialize/reset admin; revokes all sessions and API tokens')
    parser.add_argument('command', choices=['set-password'])
    parser.add_argument('--stdin', action='store_true', help='Read one password line from a secure pipe')
    args = parser.parse_args()
    if args.stdin:
        password = sys.stdin.readline().rstrip('\r\n')
    else:
        if not sys.stdin.isatty():
            parser.error('Interactive terminal required, or explicitly use --stdin with a secure pipe')
        password = getpass.getpass('New admin password (12+ characters): ')
        if password != getpass.getpass('Confirm password: '):
            parser.error('Passwords do not match')
    if not 12 <= len(password) <= 1024:
        parser.error('Password must contain 12 to 1024 characters')
    settings = Settings.from_env()
    settings.prepare_archive()
    migrate(settings.database)
    set_password(settings, password)
    print('Administrator configured. Existing sessions and API tokens revoked.')


if __name__ == '__main__':
    main()
