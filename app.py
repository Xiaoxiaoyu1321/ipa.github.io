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
IPA_EXTENSION = 'xyi'


class Format:
    @staticmethod
    def size(size: int) -> str:
        SIZE_KB = 1024
        SIZE_MB = SIZE_KB * 1024
        SIZE_GB = SIZE_MB * 1024
        SIZE_TB = SIZE_GB * 1024
        if size < SIZE_KB:
            return f"{size:>6.2f} B"
        if size < SIZE_MB:
            return f"{size / SIZE_KB:>6.2f} KB"
        if size < SIZE_GB:
            return f"{size / SIZE_MB:>6.2f} MB"
        if size < SIZE_TB:
            return f"{size / SIZE_GB:>6.2f} GB"
        return f"{size / SIZE_TB:>6.2f} TB"
    
    @staticmethod
    def iso_date(date: datetime) -> str:
        return date.strftime('%Y-%m-%d')
    
    @staticmethod
    def iso_datetime(date: datetime) -> str:
        return date.strftime('%Y-%m-%dT%H:%M:%S')

    @staticmethod
    def timestamp(date: datetime) -> float:
        return date.timestamp()
    
    @staticmethod
    def encode_email(email: str) -> str:
        result = []
        for i, char in enumerate(email):
            if (i % 2 == 0):
                result.append(ord(char) + 0x66ccff)
            else:
                result.append(ord(char) - 0xee0000)
        return '.'.join([str(r) for r in result])
    
    @staticmethod
    def initial(text: str) -> str:
        if text[0].upper() in ALPHABET:
            return text[0].upper()
        initial = pinyin(text[0], style=PinyinStyle.FIRST_LETTER, strict=False)[0][0].upper()
        if initial in ALPHABET:
            return initial
        return '0'


class OSS:
    def __init__(self, endpoint: str, bucket: str, prefix: str):
        self.endpoint = endpoint
        self.bucket = bucket
        self.prefix = prefix.strip('/')
        self.origin = f"https://{self.bucket}.{self.endpoint}"
        self.host = f"{self.bucket}.{self.endpoint}"
        self.base_url = f"https://{self.host}/{self.prefix}"
        self.auth = oss2.ProviderAuth(EnvironmentVariableCredentialsProvider())
        self.bucket = oss2.Bucket(self.auth, f"https://{self.endpoint}", self.bucket)

    def list_ipa(self) -> list:
        return [x for x in oss2.ObjectIteratorV2(self.bucket, prefix=self.prefix) if x.key.endswith(f'.{IPA_EXTENSION}')]

    def package_path(self, bundle: str) -> str:
        return f"{self.prefix}/package/{bundle}"
    
    def package_url(self, bundle: str) -> str:
        return f"{self.origin}/{self.package_path(bundle)}"
    
    def ipa_path(self, bundle: str, version: str) -> str:
        return f"{self.package_path(bundle)}/{bundle}_{version}.{IPA_EXTENSION}"

    def plist_path(self, bundle: str, version: str) -> str:
        return f"{self.package_path(bundle)}/{version}.plist"
    
    def ipa_url(self, bundle: str, version: str) -> str:
        return f"{self.origin}/{self.ipa_path(bundle, version)}"
    
    def plist_url(self, bundle: str, version: str) -> str:
        return f"{self.origin}/{self.plist_path(bundle, version)}"
    
    def upload(self, filename: str, content: Union[str, bytes]) -> None:
        if isinstance(content, str):
            content = content.encode('utf-8')
        return self.bucket.put_object(filename, content)


class Render:
    def __init__(self, prefix: str = '', update_size: bool = False):
        data = Render.load_data()
        oss = OSS(**data['oss'])
        data['cdn_base'] = oss.base_url
        self.data = Render.index(data)
        self.env = Render.load_render(prefix, oss)
        self.oss = oss
        if update_size:
            self.update_size(oss.list_ipa())

    @staticmethod
    def load_render(prefix: str, oss: OSS) -> Environment:
        env = Environment(loader=FileSystemLoader(PUBLIC_PATH))
        env.globals["now"] = datetime.now()
        env.globals["len"] = len
        env.globals["ipa_url"] = oss.ipa_url
        env.globals["plist_url"] = oss.plist_url
        env.globals["prefix"] = prefix
        env.globals["size_format"] = Format.size
        env.globals["alphabet"] = ALPHABET_WITH_ZERO
        env.globals["encode_email"] = Format.encode_email
        return env

    @staticmethod
    def load_data() -> dict:
        # Load manifest main file
        with open(f"{DATA_PATH}/{MANIFEST_PATH}", encoding="utf-8") as f:
            data = yaml.load(f.read(), Loader=YAMLLoader)
        # Load extra files
        for filename in os.listdir(DATA_PATH):
            if filename == MANIFEST_PATH:
                continue
            if filename.endswith('.yml') or filename.endswith('.yaml'):
                with open(f"{DATA_PATH}/{filename}", encoding="utf-8") as f:
                    conf = yaml.load(f.read(), Loader=YAMLLoader) or {}
                    data['packages'].extend(conf.get('packages') or [])
        return data

    @staticmethod
    def index(data: dict) -> dict:
        # Sort package versions
        for package in data['packages']:
            package.update({
                'versions': sorted(
                    package['versions'],
                    reverse=True,
                    key=functools.cmp_to_key(lambda x, y: semver.compare(x['version'], y['version']))
                ),
                'initial': Format.initial(package['name']),
            })
        data['initials'] = {
            k: v for k, v in {
                i: list(filter(lambda b: b['initial'] == i, data['packages']))
                for i in ALPHABET_WITH_ZERO
            }.items()
            if len(v) != 0
        }
        return data

    def update_size(self, ipa_files: list) -> list:
        for i, packages in enumerate(self.data['packages']):
            for j, version in enumerate(packages['versions']):
                for ipa_file in ipa_files:
                    if ipa_file.key == self.oss.ipa_path(packages['bundle'], version['version']):
                        self.data['packages'][i]['versions'][j]['size'] = ipa_file.size
                        break

    def render(self, template_name: str, data: dict = None) -> str:
        template = self.env.get_template(template_name)
        view = self.data.copy()
        if data is not None:
            for k, v in data.items():
                view[k] = v
        html = template.render(view)
        return html
    
    def render_manifest(self) -> str:
        date = datetime.now()
        manifest_data = self.data.copy()
        manifest_data.update({
            'date': Format.iso_date(date),
            'time': Format.iso_datetime(date),
            'timestamp': Format.timestamp(date),
        })
        for i, packages in enumerate(manifest_data['packages']):
            for j, version in enumerate(packages['versions']):
                manifest_data['packages'][i]['versions'][j]['url'] = self.oss.ipa_url(packages['bundle'], version['version'])
        del manifest_data['oss']
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
        return self.render('package/{bundle}/{version}.plist', version)

    def render_404(self):
        return self.render('404.html')


def start(args: argparse.Namespace) -> None:
    ipa_files = Render().oss.list_ipa()
    StatusCode = int
    MIMEType = str
    HTTPBody = Union[str, bytes]
    def handle(path: str) -> tuple[StatusCode, MIMEType, HTTPBody]:
        render = Render()
        render.update_size(ipa_files)
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

    def log_action(path: str, action_type: Union[Literal['GEN'], Literal['COPY']], size: int):
        abspath = os.path.join(dist, path)
        dirname = os.path.dirname(abspath)
        os.makedirs(dirname, exist_ok=True)
        print(f"{action_type:<4} {path[:50]:<50} {Format.size(size)}")
        return abspath

    def generage(path: str, content: str) -> None:
        abspath = log_action(path, 'GEN', len(content.encode('utf-8')))
        with open(abspath, "w+", encoding="utf-8") as f:
            f.write(content)

    def copy(path: str, source: str) -> None:
        abspath = log_action(path, 'COPY', os.path.getsize(source))
        shutil.copy(source, abspath)

    render = Render(args.prefix, update_size=True)
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
    def log_upload(oss: OSS, filename: str, content: bytes) -> None:
        print(f"Uploading: {filename[:60]:<60} [{Format.size(len(content))}]", end='', flush=True)
        oss.upload(filename, content)
        print(' OK ✓')

    rander = Render()
    print(f"OSS Endpoint URL: {rander.oss.base_url}")
    log_upload(rander.oss, f"{rander.oss.prefix}/{MANIFEST_JSON}", rander.render_manifest())
    for package in rander.data['packages']:
        for version in package['versions']:
            log_upload(
                oss=rander.oss,
                filename=rander.oss.plist_path(package['bundle'], version['version']),
                content=rander.render_plist(package['bundle'], version['version'])
            )


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

    subcommand_upload = subparsers.add_parser('upload', help='Upload to OSS')
    
    args = parser.parse_args()
    if args.command == 'start':
        start(args)
    if args.command == 'build':
        build(args)
    if args.command == 'upload':
        upload(args)


if __name__ == '__main__':
    main()
