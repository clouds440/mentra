"""Read-only, offline release preflight. Never prints secret values or connects.

python backend/scripts/validate_production.py --env-file .env.production
"""
import argparse
import ipaddress
import os
import re
from urllib.parse import parse_qs, urlsplit

from dotenv import dotenv_values


def validate(values, *, allow_network_bind=False):
    errors = []

    def require(name):
        value = str(values.get(name) or '').strip()
        if not value:
            errors.append(f'{name}: required')
        return value

    def https(name, value, *, origin=False):
        try:
            parsed = urlsplit(value)
            parsed.port
            if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                    or parsed.password or parsed.query or parsed.fragment
                    or (origin and parsed.path not in {'', '/'})):
                raise ValueError()
            host = parsed.hostname.lower()
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                host = host.encode('idna').decode('ascii')
                bare_host = host.rstrip('.')
                if (len(host) > 253 or '.' not in bare_host or host.replace('.', '').isdigit()
                        or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                               for label in host.rstrip('.').split('.'))
                        or bare_host == 'localhost' or bare_host.endswith(('.localhost', '.invalid', '.example', '.test'))):
                    raise ValueError()
            else:
                if not address.is_global or address.is_multicast or address.is_reserved:
                    raise ValueError()
                host = f'[{address.compressed}]' if address.version == 6 else str(address)
            suffix = '' if parsed.port in (None, 443) else f':{parsed.port}'
            return f'https://{host}{suffix}' if origin else value.rstrip('/')
        except ValueError:
            errors.append(f'{name}: use the actual public HTTPS {"origin" if origin else "URL"}, without credentials/query/fragment')
            return ''

    if require('APP_ENV') != 'production':
        errors.append('APP_ENV: must be production; preserve existing storage paths with FILES_ENVIRONMENT')
    frontend = https('FRONTEND_ORIGIN', require('FRONTEND_ORIGIN'), origin=True)
    https('VITE_API_URL', require('VITE_API_URL'), origin=True)
    origins = [https('CORS_ORIGINS', item.strip(), origin=True)
               for item in require('CORS_ORIGINS').split(',') if item.strip()]
    if frontend and frontend not in origins:
        errors.append('CORS_ORIGINS: must include FRONTEND_ORIGIN')
    if require('AUTH_COOKIE_SECURE').lower() != 'true':
        errors.append('AUTH_COOKIE_SECURE: must explicitly be true')
    if values.get('AUTH_COOKIE_SAME_SITE', 'lax') not in {'lax', 'strict', 'none'}:
        errors.append('AUTH_COOKIE_SAME_SITE: use lax, strict or none')
    for name in ('BACKEND_IMAGE', 'FRONTEND_IMAGE'):
        image = require(name)
        if image and ('@sha256:' not in image and (':' not in image.rsplit('/', 1)[-1] or image.endswith(':latest'))):
            errors.append(f'{name}: use a versioned release tag or digest, not latest')
    for name in ('BACKEND_BIND_ADDRESS', 'FRONTEND_BIND_ADDRESS'):
        try:
            address = ipaddress.ip_address(values.get(name, '127.0.0.1'))
            if not address.is_loopback and not allow_network_bind:
                errors.append(f'{name}: requires --allow-network-bind and a reviewed firewall/proxy network')
        except ValueError:
            errors.append(f'{name}: must be an explicit listener IP')
    for address in require('FORWARDED_ALLOW_IPS').split(','):
        try:
            network = ipaddress.ip_network(address.strip(), strict=False)
            if network.prefixlen == 0:
                raise ValueError()
        except ValueError:
            errors.append('FORWARDED_ALLOW_IPS: supply only actual proxy source IPs/CIDRs; never * or all addresses')
    database = require('DATABASE_URL')
    try:
        parsed = urlsplit(database)
        parsed.port
        if parsed.scheme not in {'postgresql', 'postgresql+psycopg', 'postgres'} or not all((parsed.hostname, parsed.username, parsed.password, parsed.path.strip('/'))):
            raise ValueError()
        modes = parse_qs(parsed.query).get('sslmode', [])
        if len(modes) != 1 or modes[0] not in {'require', 'verify-ca', 'verify-full'}:
            errors.append('DATABASE_URL: explicitly require provider-compatible TLS (sslmode=require or verify-full)')
    except ValueError:
        errors.append('DATABASE_URL: invalid complete PostgreSQL URL')
    try:
        parsed = urlsplit(require('CLOUDINARY_URL'))
        if parsed.scheme != 'cloudinary' or not all((parsed.hostname, parsed.username, parsed.password)):
            raise ValueError()
    except ValueError:
        errors.append('CLOUDINARY_URL: complete authenticated server-only URL required')
    https('AI_BASE_URL', require('AI_BASE_URL'))
    https('QDRANT_URL', require('QDRANT_URL'))
    for name in ('AI_API_KEY', 'AI_MODEL', 'QDRANT_API_KEY', 'QDRANT_COLLECTION'):
        require(name)
    if values.get('AI_PROVIDER', 'openai_compatible') != 'openai_compatible':
        errors.append('AI_PROVIDER: must be openai_compatible')
    if not re.fullmatch(r'[A-Za-z0-9_-]{0,80}', values.get('FILES_ENVIRONMENT') or ''):
        errors.append('FILES_ENVIRONMENT: use a stable namespace suffix containing only letters, numbers, underscores or hyphens')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,50}', values.get('FILES_NAMESPACE', 'mentra') or ''):
        errors.append('FILES_NAMESPACE: use a stable namespace containing only letters, numbers, underscores or hyphens')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--allow-network-bind', action='store_true')
    args = parser.parse_args()
    if not os.path.isfile(args.env_file):
        parser.error('Environment file does not exist')
    # Match Compose precedence: shell overrides the explicitly selected file.
    values = {**dotenv_values(args.env_file, interpolate=False), **os.environ}
    if any('${' in str(value) for value in dotenv_values(args.env_file, interpolate=False).values()):
        parser.error('Resolve variable interpolation before preflight; use literal release values')
    errors = validate(values, allow_network_bind=args.allow_network_bind)
    for error in errors:
        print(error)
    if errors:
        raise SystemExit(1)
    print('Offline production configuration passed. Public TLS, DNS, proxy behavior, quotas and recovery acceptance still require deployment verification.')


if __name__ == '__main__':
    main()
