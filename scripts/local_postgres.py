#!/usr/bin/env python3
"""Manage a private, user-owned PostgreSQL service without system service changes."""
import argparse
import os
import re
from pathlib import Path
import secrets
import shlex
import shutil
import subprocess
import sys


def postgres_program(name):
    program = shutil.which(name)
    if program:
        return program
    pg_config = shutil.which('pg_config')
    if pg_config:
        directory = subprocess.check_output([pg_config, '--bindir'], text=True).strip()
        candidate = Path(directory) / name
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError(f'{name} is unavailable. Install PostgreSQL 16–18 and add its bin directory to PATH.')


def private_file(path, text):
    with path.open('x') as handle:
        os.chmod(path, 0o600)
        handle.write(text)


def conninfo_value(value):
    return "'" + str(value).replace('\\', '\\\\').replace("'", "\\'") + "'"


def configuration(directory):
    return ' '.join(f'{key}={conninfo_value(value)}' for key, value in (
        ('host', directory / 'socket'), ('port', '5432'), ('dbname', 'tuldok'),
        ('user', 'tuldok'), ('passfile', directory / 'app.pgpass')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('init', 'start', 'stop', 'status', 'env'))
    parser.add_argument('--directory', type=Path, default=Path.home() / '.local/share/tuldok/postgres')
    args = parser.parse_args()
    directory = args.directory.expanduser().resolve()
    cluster = directory / 'cluster'
    socket = directory / 'socket'
    if args.action == 'env':
        if not (directory / 'app.pgpass').is_file():
            raise RuntimeError('Initialize this service before requesting its configuration.')
        print('export TULDOK_DATABASE_URL=' + shlex.quote(configuration(directory)))
        return
    pg_ctl = postgres_program('pg_ctl')
    version = subprocess.check_output([pg_ctl, '--version'], text=True)
    match = re.search(r'PostgreSQL\) (\d+)', version)
    if not match or not 16 <= int(match.group(1)) <= 18:
        raise RuntimeError('This helper requires PostgreSQL 16–18.')
    if args.action == 'init':
        if directory.exists() and any(directory.iterdir()):
            raise RuntimeError('Service directory is not empty; initialization never replaces existing state.')
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        socket.mkdir(mode=0o700)
        if len(str(socket).encode()) > 90:
            raise RuntimeError('Socket path is too long; choose a shorter --directory.')
        admin_password, app_password = secrets.token_urlsafe(40), secrets.token_urlsafe(40)
        password_file = directory / 'bootstrap.password'
        private_file(password_file, admin_password + '\n')
        subprocess.run([postgres_program('initdb'), '-D', str(cluster), '-U', 'postgres',
                        '--auth-local=scram-sha-256', '--auth-host=scram-sha-256', '--encoding=UTF8',
                        '--pwfile', str(password_file), '--no-instructions'], check=True)
        with (cluster / 'postgresql.conf').open('a') as handle:
            handle.write("\nlisten_addresses = ''\nport = 5432\nunix_socket_permissions = 0700\nunix_socket_directories = "
                         + "'" + str(socket).replace("'", "''") + "'\n")
        # The enclosing directory is private and the libpq password files are 0600.
        escaped_socket = str(socket).replace('\\', '\\\\').replace(':', '\\:')
        admin_passfile = directory / 'admin.pgpass'
        private_file(admin_passfile, f'{escaped_socket}:5432:*:postgres:{admin_password}\n')
        private_file(directory / 'app.pgpass', f'{escaped_socket}:5432:tuldok:tuldok:{app_password}\n')
        password_file.unlink()
        subprocess.run([pg_ctl, '-D', str(cluster), '-l', str(directory / 'postgres.log'), '-w', 'start'], check=True)
        # Generated URL-safe passwords contain no SQL quote characters. SQL stays
        # on stdin; neither password is put in command arguments or printed.
        environment = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
        environment['PGPASSFILE'] = str(admin_passfile)
        subprocess.run([postgres_program('psql'), '-X', '-h', str(socket), '-p', '5432',
                        '-U', 'postgres', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1'],
                       input=f"CREATE ROLE tuldok LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '{app_password}';\n"
                             'CREATE DATABASE tuldok OWNER tuldok;\n',
                       text=True, env=environment, check=True)
        print('Private PostgreSQL initialized and started. Run this script with env to configure Tuldok.')
    else:
        if not (cluster / 'PG_VERSION').is_file():
            raise RuntimeError('No cluster exists in this directory. Run init first.')
        command = [pg_ctl, '-D', str(cluster)]
        if args.action == 'start':
            command += ['-l', str(directory / 'postgres.log'), '-w', 'start']
        elif args.action == 'stop':
            command += ['-w', '-m', 'fast', 'stop']
        else:
            command += ['status']
        subprocess.run(command, check=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'Local PostgreSQL: {error}', file=sys.stderr)
        raise SystemExit(1)
