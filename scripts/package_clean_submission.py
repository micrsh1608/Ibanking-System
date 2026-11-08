"""Create the curated hand-in package without deleting or changing the workspace.

Run from the original project: python -m scripts.package_clean_submission
The PDF/Markdown and acceptance-summary inputs must be generated first.
Only the Python standard library is required for packaging.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
from urllib.parse import unquote
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile, is_zipfile


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'submission'
PACKAGE_NAME = 'NHOM12_IBANKING'
ROOT_FILES = (
    '.dockerignore', '.env.example', '.gitattributes', '.gitignore', 'compose.yaml',
    'start.ps1', 'demo-data.ps1', 'requirements.txt',
    'requirements-dev.txt', 'package.json', 'package-lock.json',
    'playwright.config.cjs', 'pytest.ini',
)
CODE_TREES = {
    'services': {'.py'}, 'shared': {'.py'}, 'frontend': {'.html', '.css', '.js'},
    'infra': {'.py', '.yaml', '.yml', '.sql', '.example'},
    'tests': {'.py', '.cjs'},
}
SCRIPT_FILES = (
    'scripts/__init__.py', 'scripts/setup_demo_env.py', 'scripts/export_openapi.py',
    'scripts/build_detailed_report.py',
)
DOC_FILES = (
    'docs/architecture.md', 'docs/api.md', 'docs/migrations.md', 'docs/runbook.md',
    'docs/demo-script.md', 'docs/demo-data-reset.md', 'docs/pre-submit.md',
    'docs/observability.md', 'docs/email-verification.md', 'docs/final-acceptance.md',
    'docs/submission-checklist.md', 'docs/team.json', 'docs/team-completion.md',
    'docs/final-report-detailed.md', 'docs/submission-filter.md', 'docs/consistency-demo.md',
    'docs/diagrams/use-cases.puml',
)
JSON_EVIDENCE = (
    'backend-acceptance.json', 'browser-acceptance.json', 'release-acceptance-latest.json',
    'otp-consistency-acceptance.json', 'email-verification-acceptance.json',
    'observability-acceptance.json', 'acceptance-summary.json',
    'shared-tuition-acceptance-latest.json',
)
IMAGE_EVIDENCE = (
    'payment-history-desktop.png', 'payment-success-mobile.png',
    'tuition-full-debt-desktop.png', 'email-proof-confirmed.png',
)
BLOCKED_PARTS = {
    '.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache',
    '.codex', '.agents', 'test-results', 'playwright-report',
}
HISTORICAL_ALIASES = {
    'README.md': 'MaNguon/README.md',
    'docs/final-report.md': 'MaNguon/docs/final-report-detailed.md',
    'docs/assessment.md': 'MaNguon/docs/final-acceptance.md',
    'docs/backend-delivery.md': 'MaNguon/docs/final-acceptance.md',
    'docs/ui-email-delivery.md': 'MaNguon/docs/email-verification.md',
    'docs/account-ui-delivery.md': 'MaNguon/docs/email-verification.md',
    'docs/login-user-requirements-review.md': 'MaNguon/docs/final-report-detailed.md',
    'docs/tuition-requirements-review.md': 'MaNguon/docs/final-report-detailed.md',
    'docs/otp-success-consistency-review.md': 'MaNguon/docs/final-report-detailed.md',
    'docs/rubric-review-2026-11-05.md': 'MaNguon/docs/final-acceptance.md',
    'docs/implementation-plan.md': 'MaNguon/docs/pre-submit.md',
    'docs/reorganization.md': 'MaNguon/README.md',
    'docs/services/account.md': 'MaNguon/docs/architecture.md',
    'docs/services/payment.md': 'MaNguon/docs/architecture.md',
    'docs/services/tuition.md': 'MaNguon/docs/architecture.md',
    'submission/bao-cao-ibanking.pdf': 'BaoCao.pdf',
    'submission/bao-cao-ibanking.md': 'BaoCao.md',
    'submission/trinh-bay-ibanking-v3.pptx': 'Slide.pptx',
    'submission/SOURCE-MANIFEST.json': 'MANIFEST.json',
    'submission/SHA256SUMS.txt': 'SHA256SUMS.txt',
    'artifacts/final-delivery-acceptance.json': 'MaNguon/artifacts/acceptance-summary.json',
    'submission/evidence/final-delivery-acceptance.json': 'MaNguon/artifacts/acceptance-summary.json',
}
LINK = re.compile(r'(!?\[[^\]\n]*\])\(([^)\n]+)\)')


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ensure_inside(path: Path, base: Path) -> Path:
    resolved = path.resolve()
    if resolved == base.resolve() or not resolved.is_relative_to(base.resolve()):
        raise RuntimeError(f'Refusing path outside the intended directory: {path.name}')
    return resolved


def reject_link(path: Path) -> None:
    current = path
    while current != ROOT.parent:
        if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
            raise RuntimeError(f'Refusing symlink/junction: {path.relative_to(ROOT)}')
        if current == ROOT:
            break
        current = current.parent


def read_source(relative: str) -> bytes:
    path = ROOT / relative
    ensure_inside(path, ROOT)
    reject_link(path)
    if not path.is_file():
        raise FileNotFoundError(f'Required submission input is not ready: {relative}')
    return path.read_bytes()


def private_literals() -> list[tuple[str, bytes]]:
    values = []
    for relative in ('.env', 'infra/env/docker.env'):
        path = ROOT / relative
        if not path.exists():
            continue
        reject_link(path)
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip() or line.lstrip().startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            value = value.strip().strip('"\'')
            if re.search(r'(SECRET|PASSWORD|KEY)$', key.strip(), re.IGNORECASE) and len(value) >= 8:
                values.append((key.strip(), value.encode('utf-8')))
    return values


def verify_no_secrets(entries: dict[str, bytes]) -> None:
    values = private_literals()
    for name, data in entries.items():
        payloads = [data]
        if name.lower().endswith('.pptx'):
            with ZipFile(io.BytesIO(data)) as deck:
                payloads.extend(deck.read(part) for part in deck.namelist() if part.endswith('.xml'))
        for key, value in values:
            if any(value in payload for payload in payloads):
                raise RuntimeError(f'Private configuration value ({key}) found in {name}; no package published.')


def is_external(target: str) -> bool:
    return bool(re.match(r'^(?:[A-Za-z][A-Za-z0-9+.-]*:|#|//)', target))


def split_link_target(raw: str) -> tuple[str, str]:
    raw = raw.strip()
    if raw.startswith('<') and '>' in raw:
        end = raw.index('>')
        return raw[1:end], raw[end + 1:]
    match = re.match(r'^(\S+)(\s+["\'].*)?$', raw)
    return (match.group(1), match.group(2) or '') if match else (raw, '')


def rewrite_markdown(data: bytes, source: str, destination: str,
                     source_map: dict[str, str], available: set[str], changes: list[dict]) -> bytes:
    text = data.decode('utf-8-sig')
    directories = {str(parent) for name in available for parent in PurePosixPath(name).parents}
    valid_targets = available | directories | {'MANIFEST.json', 'SHA256SUMS.txt'}

    def rewrite(match):
        label, raw = match.groups()
        target, title = split_link_target(raw)
        if is_external(target):
            return match.group(0)
        file_part, separator, fragment = target.partition('#')
        source_target = posixpath.normpath(posixpath.join(posixpath.dirname(source), unquote(file_part)))
        if source_target.startswith('../') or source_target.startswith('/'):
            replacement = None
        else:
            replacement = source_map.get(source_target) or HISTORICAL_ALIASES.get(source_target)
            # Directory links such as docs/api/ remain useful in the filtered source.
            candidate = posixpath.normpath('MaNguon/' + source_target)
            if replacement is None and candidate in directories:
                replacement = candidate
        # Root report exports may already use the source document's image paths.
        if replacement is None and destination == 'BaoCao.md':
            # A root report copied from an earlier clean package can already
            # contain MaNguon/... paths; they are final package targets.
            ready_target = posixpath.normpath(unquote(file_part))
            if ready_target in valid_targets:
                replacement = ready_target
            elif file_part.startswith('diagrams/exported/'):
                replacement = 'MaNguon/docs/' + file_part
            elif file_part.startswith('../artifacts/'):
                replacement = 'MaNguon/artifacts/' + file_part.removeprefix('../artifacts/')
            elif file_part.startswith('../docs/'):
                replacement = 'MaNguon/docs/' + file_part.removeprefix('../docs/')
        if replacement in valid_targets:
            relative = posixpath.relpath(replacement, posixpath.dirname(destination) or '.')
            # A historical section anchor need not exist in the current replacement.
            anchor = '#' + fragment if separator and source_target in source_map else ''
            result = f'{label}({relative}{anchor}{title})'
        else:
            if label.startswith('![') and destination in {'BaoCao.md', 'MaNguon/docs/final-report-detailed.md'}:
                raise RuntimeError(f'Report image is outside the hand-in allowlist: {target}')
            # Omitted milestone links become readable text rather than dead links.
            result = label[2:-1] if label.startswith('![') else label[1:-1]
        if result != match.group(0):
            changes.append({'document': destination, 'old_target': target,
                            'new_target': replacement if replacement in valid_targets else None})
        return result

    text = LINK.sub(rewrite, text)
    # These code-formatted paths are project-root references in the original guides.
    path_replacements = {
        'submission/bao-cao-ibanking.pdf': '../BaoCao.pdf',
        'submission/bao-cao-ibanking.md': '../BaoCao.md',
        'submission/trinh-bay-ibanking-v3.pptx': '../Slide.pptx',
        'submission/SOURCE-MANIFEST.json': '../MANIFEST.json',
        'submission/SHA256SUMS.txt': '../SHA256SUMS.txt',
        'submission/ibanking-source.zip': '../',
        'submission/evidence/final-delivery-acceptance.json': 'artifacts/acceptance-summary.json',
        'artifacts/final-delivery-acceptance.json': 'artifacts/acceptance-summary.json',
        'docs/final-report.md': 'docs/final-report-detailed.md',
    }
    for old, new in path_replacements.items():
        text = text.replace(f'`{old}`', f'`{new}`')
    return text.encode('utf-8')


def verify_markdown_links(entries: dict[str, bytes]) -> None:
    available = set(entries) | {'MANIFEST.json', 'SHA256SUMS.txt'}
    directories = {'.'}
    for name in available:
        directories.update(str(parent) for parent in PurePosixPath(name).parents)
    for name, data in entries.items():
        if not name.endswith('.md'):
            continue
        for match in LINK.finditer(data.decode('utf-8')):
            target, _ = split_link_target(match.group(2))
            if is_external(target):
                continue
            relative = unquote(target.partition('#')[0])
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), relative))
            if resolved not in available and resolved not in directories:
                raise RuntimeError(f'Dangling local Markdown link: {name} -> {target}')


def source_readme() -> str:
    # The current project README is the source of truth; do not maintain a second
    # startup/demo template that can drift from the actual application.
    return read_source('README.md').decode('utf-8-sig')


def hand_in_readme(summary: dict) -> str:
    tests = summary.get('tests') or summary.get('test_results') or {}
    counts = ', '.join(f'{name}: {value}' for name, value in tests.items()
                       if isinstance(value, (int, float)) and not isinstance(value, bool))
    return f'''# Bộ nộp giữa kỳ — Nhóm 12 — iBanking

Môn Kiến trúc hướng dịch vụ, giảng viên TS. Dương Hữu Phúc.
Đây là bộ nộp đã lọc; thư mục làm việc và database của máy phát triển được giữ nguyên.

- [Báo cáo PDF](BaoCao.pdf) và [bản Markdown có thể biên tập](BaoCao.md).
- [Slide trình bày](Slide.pptx).
- [Mã nguồn và cách chạy một lệnh](MaNguon/README.md).
- [Kết quả kiểm thử tổng hợp](MaNguon/artifacts/acceptance-summary.json).
- [Danh sách tệp và hash](MANIFEST.json), [SHA-256](SHA256SUMS.txt).

## Bắt đầu

Giải nén toàn bộ thư mục, cài Docker Desktop Linux containers, mở PowerShell:

```powershell
cd .\\MaNguon
powershell -ExecutionPolicy Bypass -File .\\start.ps1 -PrepareDemo -Detached
```

Lệnh chuẩn bị khởi động ứng dụng chính rồi cấp catalog demo01–demo10 còn
thiếu. Tài khoản mới dùng Demo_123! và có 10 triệu; chạy lại giữ dữ liệu đã có.
Mỗi tài khoản cần nhập và tự xác minh email thật trên Web bằng SMTP đã cấu
hình; lệnh chuẩn bị không tự gửi mã hoặc xác minh hộp thư.
Web ở cổng 8001, SQL ở 14330. Thanh toán thực hiện hoàn toàn trên Web.
Máy mới cần Internet cho lần build đầu; ZIP không chứa image hoặc dữ liệu SQL.
Xem README trong MaNguon để cấu hình SMTP và kiểm tra trạng thái catalog.

## Bằng chứng và thông tin nhóm

Trạng thái kiểm thử tổng hợp: {summary.get('status', 'không xác định')}.
{('Số liệu: ' + counts + '.') if counts else 'Phạm vi và số liệu được ghi trong JSON tổng hợp.'}
Các JSON/ảnh là bằng chứng nghiệm thu đã chọn, không phải dữ liệu database
được chép sang máy khác. Tên/MSSV hai thành viên và phân công thực tế còn thiếu
được đánh dấu để nhóm tự bổ sung. Không tự gán tên hoặc công việc chưa xác nhận.

Nếu biên tập Markdown/PDF hoặc mã nguồn, hãy đóng gói và tính lại hash trước
khi nộp. SHA256SUMS.txt xác minh mọi tệp trong bộ nộp trừ chính nó; ZIP có CRC
và kiểm tra readback khi tạo. Mở thử Slide.pptx trên máy trình chiếu trước bảo vệ.
'''


def collect_entries() -> tuple[dict[str, bytes], dict[str, str], dict]:
    entries: dict[str, bytes] = {}
    source_map: dict[str, str] = {}

    def add(source: str, destination: str | None = None):
        destination = destination or 'MaNguon/' + source
        if destination in entries:
            raise RuntimeError(f'Duplicate destination in allowlist: {destination}')
        entries[destination] = read_source(source)
        source_map[source] = destination

    deliverables = {
        'BaoCao.pdf': ('BaoCao.pdf', 'submission/bao-cao-ibanking-chi-tiet.pdf'),
        'BaoCao.md': ('BaoCao.md', 'submission/bao-cao-ibanking-chi-tiet.md'),
        'Slide.pptx': ('Slide.pptx', 'submission/trinh-bay-ibanking-v3.pptx'),
    }
    for destination, candidates in deliverables.items():
        source = next((relative for relative in candidates if (ROOT / relative).is_file()), None)
        if source is None:
            raise FileNotFoundError('Required deliverable is not ready: ' + ' or '.join(candidates))
        add(source, destination)
    if not entries['BaoCao.pdf'].startswith(b'%PDF-') or not is_zipfile(io.BytesIO(entries['Slide.pptx'])):
        raise RuntimeError('Report or presentation input is not a valid PDF/PPTX container.')
    for relative in ROOT_FILES + SCRIPT_FILES + DOC_FILES:
        add(relative)
    for optional in ('requirements-report.txt', 'requirements-authoring.txt'):
        if (ROOT / optional).is_file():
            add(optional)
    for directory, extensions in CODE_TREES.items():
        for path in sorted((ROOT / directory).rglob('*')):
            relative = path.relative_to(ROOT)
            if BLOCKED_PARTS.intersection(relative.parts):
                continue
            reject_link(path)
            if path.is_file() and (path.suffix.lower() in extensions or path.name == 'Dockerfile'):
                add(relative.as_posix())
    for directory, pattern in (('docs/api', '*.json'), ('docs/diagrams/exported', '*.png')):
        for path in sorted((ROOT / directory).glob(pattern)):
            add(path.relative_to(ROOT).as_posix())
    for name in JSON_EVIDENCE + IMAGE_EVIDENCE:
        add('artifacts/' + name)
    summary = json.loads(entries['MaNguon/artifacts/acceptance-summary.json'].decode('utf-8-sig'))
    if summary.get('status') != 'PASS':
        raise RuntimeError('acceptance-summary.json must record a PASS result before publication.')
    entries['MaNguon/README.md'] = source_readme().encode('utf-8')
    entries['README_NOP.md'] = hand_in_readme(summary).encode('utf-8')
    source_map['README.md'] = 'MaNguon/README.md'
    # Prevent Windows case-insensitive filename ambiguity.
    if len({name.casefold() for name in entries}) != len(entries):
        raise RuntimeError('Case-insensitive destination collision in package.')
    return entries, source_map, summary


def main() -> None:
    ensure_inside(OUTPUT, ROOT)
    reject_link(OUTPUT)
    destination = OUTPUT / PACKAGE_NAME
    archive = OUTPUT / (PACKAGE_NAME + '.zip')
    if destination.exists() or archive.exists():
        raise FileExistsError(
            'Clean package output already exists and was kept unchanged. '
            'Archive/rename submission/NHOM12_IBANKING and its ZIP before rebuilding.'
        )
    entries, source_map, summary = collect_entries()
    changes: list[dict] = []
    available = set(entries)
    reverse_map = {destination: source for source, destination in source_map.items()}
    for name, data in list(entries.items()):
        if name.endswith('.md') and name in reverse_map:
            entries[name] = rewrite_markdown(data, reverse_map[name], name, source_map, available, changes)
    verify_markdown_links(entries)
    verify_no_secrets(entries)
    manifest = {
        'package': PACKAGE_NAME, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'policy': 'Positive allowlist; original workspace and databases are not modified.',
        'acceptance_summary': summary, 'payload_file_count': len(entries),
        'excluded': ['private .env files', 'dependency folders', '.git', 'caches',
                     'raw logs/build previews', 'SQL files containing data/backups',
                     'Docker images/volumes', 'historical reports/slides/reviews'],
        'markdown_link_changes': changes,
        'files': [{'path': name, 'bytes': len(data), 'sha256': sha256(data)}
                  for name, data in sorted(entries.items())],
    }
    entries['MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    entries['SHA256SUMS.txt'] = ''.join(f'{sha256(data)}  {name}\n'
                                      for name, data in sorted(entries.items())).encode('utf-8')
    OUTPUT.mkdir(exist_ok=True)
    staging = OUTPUT / (PACKAGE_NAME + '.staging-' + uuid4().hex[:12])
    temporary_archive = OUTPUT / (PACKAGE_NAME + '.staging-' + uuid4().hex[:12] + '.zip')
    # No recursive cleanup. A failed build remains as an explicitly named staging artifact.
    ensure_inside(staging, OUTPUT)
    ensure_inside(temporary_archive, OUTPUT)
    staging.mkdir()
    for name, data in sorted(entries.items()):
        target = staging / PurePosixPath(name)
        ensure_inside(target, staging)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as file:
            file.write(data)
        if sha256(target.read_bytes()) != sha256(data):
            raise RuntimeError(f'Staging readback failed: {name}')
    with ZipFile(temporary_archive, 'x', compression=ZIP_DEFLATED, compresslevel=9) as zipfile:
        for name, data in sorted(entries.items()):
            zipfile.writestr(PACKAGE_NAME + '/' + name, data)
    with ZipFile(temporary_archive) as zipfile:
        if zipfile.testzip() is not None:
            raise RuntimeError('ZIP CRC validation failed.')
        expected_names = {PACKAGE_NAME + '/' + name for name in entries}
        if set(zipfile.namelist()) != expected_names:
            raise RuntimeError('ZIP entries differ from the positive allowlist.')
        for name, data in entries.items():
            if sha256(zipfile.read(PACKAGE_NAME + '/' + name)) != sha256(data):
                raise RuntimeError(f'ZIP readback hash mismatch: {name}')
    # Both resolved targets must be direct children of submission before either rename.
    for target in (staging, temporary_archive, destination, archive):
        if ensure_inside(target, OUTPUT).parent != OUTPUT.resolve():
            raise RuntimeError('Refusing publication outside the submission directory.')
    if destination.exists() or archive.exists():
        raise FileExistsError('Another package appeared during the build; staging was kept, existing output untouched.')
    staging.rename(destination)
    temporary_archive.rename(archive)
    print(json.dumps({'directory': str(destination), 'archive': str(archive),
                      'files': len(entries), 'bytes': archive.stat().st_size,
                      'archive_sha256': sha256(archive.read_bytes()),
                      'private_literal_scan': 'PASS', 'markdown_links': 'PASS',
                      'staging_and_zip_readback': 'PASS'}, ensure_ascii=True))


if __name__ == '__main__':
    main()
