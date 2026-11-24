#!/usr/bin/env python3
"""门户 Python 入口；原有生成器保留其示例内容。"""
import argparse
import os
import runpy
import sys
from pathlib import Path

WORKSPACE = Path('/workspace') if Path('/workspace').is_dir() else Path.cwd()
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from publish_result import PublishError, publish_ppt, validate_publish_config

def main():
    parser = argparse.ArgumentParser(
        description='PPT 示例生成器；默认按本地真实文件名强制替换公开结果仓库中的 PPT',
        epilog='默认发布开启。设置 PPT_AUTO_PUBLISH=0 或传入 --no-publish 可关闭；发布必须配置 PPT_GITHUB_TOKEN。',
    )
    parser.add_argument('--mode', choices=['standard', 'full', 'grand', 'mbe'], default='standard')
    parser.add_argument('--topic', default='演示文稿')
    parser.add_argument('--subtitle', default='AI 智能生成')
    parser.add_argument('--palette', choices=['midnight-executive', 'tech-dark', 'coral-energy'], default='midnight-executive')
    parser.add_argument('--output', '--out', default='outputs/presentation.pptx')
    publish_group = parser.add_mutually_exclusive_group()
    publish_group.add_argument(
        '--publish',
        dest='publish',
        action='store_true',
        default=None,
        help='生成后按本地真实文件名发布到 wushuangtian/results；该仓库当前公开可见',
    )
    publish_group.add_argument(
        '--no-publish',
        dest='publish',
        action='store_false',
        default=None,
        help='只生成并保留本地文件，不发布',
    )
    args = parser.parse_args()
    if args.publish is None:
        publish_requested = os.environ.get('PPT_AUTO_PUBLISH', '1') != '0'
    else:
        publish_requested = args.publish
    if publish_requested:
        try:
            validate_publish_config()
        except PublishError as exc:
            parser.error(str(exc))

    out = Path(args.output)
    out = (out if out.is_absolute() else WORKSPACE / out).resolve()
    allowed = (WORKSPACE / 'outputs').resolve()
    if not out.is_relative_to(allowed) or out.suffix.lower() != '.pptx':
        parser.error('输出必须是工作区 outputs/ 下的 .pptx 文件')
    out.parent.mkdir(parents=True, exist_ok=True)
    modules = {'standard': ('generate_ppt.py', 'create_presentation'), 'full': ('generate_full.py', 'create_full_ppt'), 'grand': ('generate_grand.py', 'create_grand_ppt'), 'mbe': ('generate_mbe.py', 'create_mbe_ppt')}
    filename, function = modules[args.mode]
    try:
        module = runpy.run_path(str(SCRIPTS / filename))
        kwargs = {'output_path': str(out)}
        if args.mode == 'standard':
            kwargs.update(title=args.topic, subtitle=args.subtitle, palette=args.palette)
        module[function](**kwargs)
    except ModuleNotFoundError as exc:
        raise SystemExit(f'缺少依赖 {exc.name}；请管理员在沙箱镜像中预装 python-pptx 及其依赖，禁止运行时安装。') from exc
    print(f'LOCAL_FILE: {out}')

    if publish_requested:
        try:
            result = publish_ppt(out, confirm_public=True)
        except PublishError as exc:
            print(f'PUBLISH_FAILED: {exc}', file=sys.stderr)
            print(f'本地文件已保留: {out}', file=sys.stderr)
            raise SystemExit(2) from exc
        print(f'PUBLISHED_URL: {result.public_url}')
        print(f'PUBLISHED_COMMIT: {result.commit_sha}')
        print(f'PUBLISHED_SHA256: {result.sha256}')
        print(f'PUBLISH_MODE: {"REPLACE_EXISTING" if result.overwrote_existing else "CREATE"}')
        if result.public_repo:
            print('PUBLISH_VISIBILITY: PUBLIC')

if __name__ == '__main__':
    main()
