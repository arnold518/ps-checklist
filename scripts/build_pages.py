"""Build an allowlisted GitHub Pages artifact with public configuration only."""

import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from preview import PUBLIC_FILES  # noqa: E402


def public_config(values):
    api = values.get('PS_API_URL', '').rstrip('/')
    supabase = values.get('PS_SUPABASE_URL', '').rstrip('/')
    key = values.get('PS_SUPABASE_ANON_KEY', '')
    for name, value in [('PS_API_URL', api), ('PS_SUPABASE_URL', supabase)]:
        parts = urlsplit(value)
        if (not parts.hostname or parts.username or parts.password or parts.query or parts.fragment
                or parts.scheme != 'https' and not (parts.scheme == 'http' and parts.hostname in ('127.0.0.1', 'localhost'))):
            raise ValueError(f'Set {name} to the public HTTPS URL.')
    if not key or key.startswith('sb_secret_'):
        raise ValueError('PS_SUPABASE_ANON_KEY must be the public publishable/anon key, never a secret key.')
    if key.count('.') == 2:
        try:
            claims = json.loads(base64.urlsafe_b64decode(key.split('.')[1] + '==='))
        except (ValueError, UnicodeDecodeError):
            raise ValueError('Invalid public Supabase key.') from None
        if claims.get('role') != 'anon':
            raise ValueError('Only the anon key may be published to Pages.')
    elif not key.startswith('sb_publishable_'):
        raise ValueError('Use a Supabase publishable key or legacy anon JWT.')
    providers = values.get('PS_AUTH_PROVIDERS', 'google,github').split(',')
    providers = [provider.strip() for provider in providers if provider.strip()]
    if any(provider not in ('google', 'github') for provider in providers):
        raise ValueError('PS_AUTH_PROVIDERS accepts google,github, or an empty value for email only.')
    return {'apiBase': api, 'supabaseUrl': supabase, 'supabaseAnonKey': key, 'authProviders': providers}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(ROOT / 'dist'))
    args = parser.parse_args()
    values = {}
    local = ROOT / '.env.pages'
    if local.exists():
        for line in local.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                name, value = line.split('=', 1)
                values[name.strip()] = value.strip().strip('\"').strip("'")
    values.update(os.environ)
    config = public_config(values)
    output = Path(args.output).resolve()
    if output == ROOT or ROOT.is_relative_to(output):
        raise ValueError('Choose a build output directory beneath the repository or /tmp.')
    if not output.is_relative_to(ROOT) and not output.is_relative_to(Path('/tmp')):
        raise ValueError('Choose an output directory beneath the repository or /tmp.')
    output.mkdir(parents=True, exist_ok=True)
    # Only this marker permits cleaning an existing output directory.
    marker = output / '.ps-checklist-build'
    if any(output.iterdir()) and not marker.exists():
        raise ValueError('The output directory is not empty and was not created by this builder.')
    for path in list(output.iterdir()):
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    marker.touch()
    for name in PUBLIC_FILES:
        source, target = ROOT / name, output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    (output / 'config.js').write_text('globalThis.PS_CHECKLIST_CONFIG = ' + json.dumps(config) + ';\n')
    (output / '.nojekyll').touch()
    esbuild = ROOT / 'node_modules/.bin/esbuild'
    if not esbuild.exists():
        raise ValueError('Run npm ci before building Pages.')
    subprocess.run([str(esbuild), 'src/main.js', '--bundle', '--splitting', '--format=esm',
        '--minify', '--target=es2022', f'--outdir={output / "src"}', '--entry-names=main',
        '--chunk-names=chunks/[name]-[hash]'], cwd=ROOT, check=True)
    print(f'Pages artifact ready: {output}. Only frontend files and public configuration were copied.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from None
