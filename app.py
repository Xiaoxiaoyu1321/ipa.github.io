import os
import json
import oss2
import yaml
import shutil
import semver
import argparse
import functools
from datetime import datetime
from typing import Union, Literal
from dataclasses import dataclass
from yaml import Loader as YAMLLoader
from jinja2 import Environment, FileSystemLoader
from pypinyin import Style as PinyinStyle, pinyin
from http.server import BaseHTTPRequestHandler, HTTPServer
from oss2.credentials import EnvironmentVariableCredentialsProvider


ALPHABET = [chr(i) for i in range(ord('A'), ord('Z') + 1)]
ALPHABET_WITH_ZERO = ['0'] + ALPHABET
DATA_PATH = 'data'
ICON_PATH = f'{DATA_PATH}/icon'
PUBLIC_PATH = 'public'
MANIFEST_PATH = 'manifest.yaml'
MANIFEST_JSON = 'manifest.json'


@dataclass
class Render:
    env: Environment
    data: dict

    @staticmethod
    def load():
        return Render(
            env=Render.load_render(),
            data=Render.load_data(),
        )

    @staticmethod
    def load_data() -> dict:
        def load_extra_files():
            packages = []
            for filename in os.listdir(DATA_PATH):
                if filename == MANIFEST_PATH:
                    continue
                if filename.endswith('.yml') or filename.endswith('.yaml'):
                    with open(f"{DATA_PATH}/{filename}", encoding="utf-8") as f:
                        configuration = yaml.load(f.read(), Loader=YAMLLoader) or {}
                        packages.extend(configuration.get('packages') or [])
            return packages

        def initial(text: str) -> str:
            if text[0].upper() in ALPHABET:
                return text[0].upper()
            initial = pinyin(text[0], style=PinyinStyle.FIRST_LETTER, strict=False)[0][0].upper()
            if initial in ALPHABET:
                return initial
            return '0'

        def ensure_initials(data: dict) -> dict:
            for i, package in enumerate(data['packages']):
                data['packages'][i]['initial'] = initial(package['name'])
            data['initials'] = {
                k: v for k, v in {
                    i: list(filter(lambda b: b['initial'] == i, data['packages']))
                    for i in ALPHABET_WITH_ZERO
                }.items()
                if len(v) != 0
            }
            return data
        
        def sort_versions(data: dict) -> dict:
            for i, package in enumerate(data['packages']):
                data['packages'][i]['versions'] = sorted(
                    package['versions'],
                    reverse=True,
                    key=functools.cmp_to_key(lambda x, y: semver.compare(x['version'], y['version']))
                )
                for j, version in enumerate(data['packages'][i]['versions']):
                    data['packages'][i]['versions'][j]['url'] = f"{data['cdn_base_url']}/package/{package['bundle']}/{package['bundle']}_{version['version']}.ipa"
            return data

        with open(f"{DATA_PATH}/{MANIFEST_PATH}", encoding="utf-8") as f:
            data = yaml.load(f.read(), Loader=YAMLLoader)
        data['packages'].extend(load_extra_files())
        data['cdn_base_url'] = f"https://{data['oss']['bucket']}.{data['oss']['endpoint']}/{data['oss']['prefix']}".rstrip('/')
        data = ensure_initials(data)
        data = sort_versions(data)
        data['prefix'] = ''
        return data

    @staticmethod
    def load_render() -> Environment:
        def encode_email(email: str) -> str:
            result = []
            for i, char in enumerate(email):
                if (i % 2 == 0):
                    result.append(ord(char) + 0x66ccff)
                else:
                    result.append(ord(char) - 0xee0000)
            return '.'.join([str(r) for r in result])

        env = Environment(loader=FileSystemLoader(PUBLIC_PATH))
        env.globals["now"] = datetime.now()
        env.globals["len"] = len
        env.globals["alphabet"] = ALPHABET_WITH_ZERO
        env.globals["encode_email"] = encode_email
        return env
    
    def render(self, template_name: str, data: dict = None, minify: bool = True) -> str:
        template = self.env.get_template(template_name)
        view = self.data.copy()
        if data is not None:
            for k, v in data.items():
                view[k] = v
        html = template.render(view)
        return html
    
    def render_manifest(self) -> str:
        manifest_data = self.data.copy()
        del manifest_data['oss']
        manifest_data['date'] = datetime.now().strftime('%Y-%m-%d')
        manifest_data['time'] = { 'iso': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'), 'timestamp': datetime.now().timestamp() }
        return json.dumps(manifest_data)
    
    def render_index(self) -> str:
        return self.render('index.html')

    def render_package(self, bundle: str) -> str:
        package = next(filter(lambda x: x['bundle'] == bundle, self.data['packages']))
        return self.render('package/{bundle}/index.html', package)
    
    def render_plist(self, bundle: str, version: str) -> str:
        package = next(filter(lambda x: x['bundle'] == bundle, self.data['packages']))
        version = next(filter(lambda x: x['version'] == version, package['versions']))
        version.update(package)
        return self.render('package/{bundle}/{version}.plist', version, minify=False)

    def render_404(self):
        return self.render('404.html')


def start(args: argparse.Namespace) -> None:
    StatusCode = int
    MIMEType = str
    HTTPBody = Union[str, bytes]
    def handle(path: str) -> tuple[StatusCode, MIMEType, HTTPBody]:
        render = Render.load()
        slugs = path.split('/')
        if path == '':
            return 200, 'text/html', render.render_index()
        if path == MANIFEST_JSON:
            return 200, 'application/json', render.render_manifest()
        if path.startswith('package/') and (len(slugs) == 2):
            return 200, 'text/html', render.render_package(slugs[1])
        if path.startswith('package/') and (len(slugs) == 3):
            return 200, 'application/plist', render.render_plist(slugs[1], slugs[2][:len('.plist') - 1])
        if path.startswith('assets/icon/'):
            with open(f'{ICON_PATH}/{slugs[2]}', 'rb') as f:
                return 200, 'image/png', f.read()
        if path.startswith('assets/'):
            with open(f'{PUBLIC_PATH}/assets/{slugs[1]}', 'rb') as f:
                return 200, 'image/png', f.read()
        return 404, 'text/html', render.render_404()
    
    class HTTPRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            status_code, mime_type, http_body = handle(
                path=self.path.strip().strip('/')
            )
            if isinstance(http_body, str):
                http_body = http_body.encode('utf-8')
            self.send_response(status_code)
            self.send_header('Content-type', mime_type)
            self.end_headers()
            self.wfile.write(http_body)
    
    server = HTTPServer((args.host, args.port), HTTPRequestHandler)
    print(f"Listening on http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


def build(args: argparse.Namespace) -> None:
    dist = os.path.abspath(args.dist)
    print(f"Output directory is '{dist}'")
    if (args.clean):
        print('Cleaning output directory...')
        shutil.rmtree(dist, ignore_errors=True)

    def prepre_writefile(path: str, action_type: Union[Literal['GEN'], Literal['COPY']], size: int):
        abspath = os.path.join(dist, path)
        dirname = os.path.dirname(abspath)
        size_kb = size / 1024
        os.makedirs(dirname, exist_ok=True)
        print(f"{action_type:<4} {path[:40]:<40} {size_kb:>8.2f} KB")
        return abspath
    
    def generage(path: str, content: str) -> None:
        abspath = prepre_writefile(path, 'GEN', len(content.encode('utf-8')))
        with open(abspath, "w+", encoding="utf-8") as f:
            f.write(content)
    
    def copy(path: str, source: str) -> None:
        abspath = prepre_writefile(path, 'COPY', os.path.getsize(source))
        shutil.copy(source, abspath)
    
    render = Render.load()
    render.data['prefix'] = args.prefix
    generage('index.html', render.render_index())
    generage('404.html', render.render_404())
    generage(MANIFEST_JSON, render.render_manifest())
    if args.cname is not None:
        generage('CNAME', str(args.cname))
    for asset in os.listdir(f"{PUBLIC_PATH}/assets"):
        if asset.startswith('.'):
            continue
        if os.path.isdir(f"{PUBLIC_PATH}/assets/{asset}"):
            continue
        copy(f"assets/{asset}", f"{PUBLIC_PATH}/assets/{asset}")
    for package in render.data['packages']:
        copy(f"assets/icon/{package['bundle']}.png", f"{ICON_PATH}/{package['bundle']}.png")
        generage(f"package/{package['bundle']}/index.html", render.render_package(package['bundle']))
        for version in package['versions']:
            generage(f"package/{package['bundle']}/{version['version']}.plist", render.render_plist(package['bundle'], version['version']))


def upload(args: argparse.Namespace) -> None:
    args.clean = True
    args.dist = 'ossdist'
    args.cname = None
    args.prefix = ''
    build(args)

    data = Render.load().data
    bucket = oss2.Bucket(oss2.ProviderAuth(EnvironmentVariableCredentialsProvider()), f"https://{data['oss']['endpoint']}", data['oss']['bucket'])
    print(f"OSS with endpoint: https://{data['oss']['bucket']}.{data['oss']['endpoint']}/")
    print(f"Uploading: {'manifest':<60}", end='', flush=True)
    bucket.put_object_from_file(f"{data['oss']['prefix']}/{MANIFEST_JSON}", f'{args.dist}/{MANIFEST_JSON}')
    print(' ✓ OK')
    for package in data['packages']:
        for version in package['versions']:
            plist_url = f"{data['oss']['prefix']}/package/{package['bundle']}/{version['version']}.plist"
            print(f"Uploading: {plist_url:<60}", end='', flush=True)
            bucket.put_object_from_file(plist_url, f"{args.dist}/package/{package['bundle']}/{version['version']}.plist")
            print(' ✓ OK')


def main() -> None:
    parser = argparse.ArgumentParser(description='The main application')
    subparsers = parser.add_subparsers(dest='command', required=True)

    subcommand_start = subparsers.add_parser('start', help='Start a local HTTP server for preview')
    subcommand_start.add_argument('-p', '--port', type=int, default=5500, help='The HTTP server listen port')
    subcommand_start.add_argument('-b', '--host', type=str, default='127.0.0.1', help='The HTTP server listen IP address')

    subcommand_build = subparsers.add_parser('build', help='Build to static website')
    subcommand_build.add_argument('-c', '--clean', action='store_true', help='Clean the dist folder before running')
    subcommand_build.add_argument('-d', '--dist', type=str, default='dist', help='the dist folder, default to dist/')
    subcommand_build.add_argument('--cname', type=str, default=None, help='the CNAME for GitHub Pages')
    subcommand_build.add_argument('--prefix', type=str, default='', help='the prefix of web root path')

    subcommand_build = subparsers.add_parser('upload', help='Upload to OSS')
    
    args = parser.parse_args()
    if args.command == 'start':
        start(args)
    if args.command == 'build':
        build(args)
    if args.command == 'upload':
        upload(args)


if __name__ == '__main__':
    main()
