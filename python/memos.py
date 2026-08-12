import sys
import os
import stat
import json
import re
import hashlib
import mimetypes
import urllib.request
import urllib.parse
import urllib.error
import pyotherside
import base64

base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(base_dir, 'libs'))

import mistune
from mistune.util import striptags, safe_entity
from mistune.util import escape as escape_text


class MemosRenderer(mistune.HTMLRenderer):
    """Renders memo markdown to the HTML Qt's StyledText displays.

    This overrides specific mistune render hooks (image/link/text/
    task_list_item) instead of the previous approach of pre-processing
    the raw markdown text with regexes and then post-processing the
    rendered HTML string with more regexes. That older approach worked,
    but every one of its edge cases (double-escaped "&" in URLs, the
    "file://" cache paths needing to be protected/restored around mistune,
    hashtag styling risking matching inside a tag) existed only because it
    was working around mistune from the outside. Hooking mistune's own
    per-token renderer methods gets the already-parsed pieces (a URL, a
    plain-text run, a title) directly as arguments, so there's nothing
    left to regex out of finished HTML.
    """

    def __init__(self, api):
        super().__init__(escape=True)
        self.api = api
        # Set by render_markdown() before each call, since the available
        # width depends on the QML item asking for it, not on the memo
        # content itself.
        self.img_width = 800

    def safe_url(self, url):
        # HTMLRenderer's default safe_url() treats "file://" as an
        # unrecognized/harmful protocol and replaces it with
        # '#harmful-link'. We generate every file:// URL ourselves (hashed
        # filenames in our own local image cache), so it's safe to allow.
        if url.startswith('file://'):
            return escape_text(url)
        return super().safe_url(url)

    def _resolve_url(self, url, with_token):
        if not url.startswith('/'):
            return url
        resolved = self.api.base_url.rstrip('/') + url
        # Qt's StyledText can't send an Authorization header when it
        # fetches an <img src="...">, so a token has to be embedded in the
        # URL for images to load. We deliberately do NOT do this for
        # plain links: those open in the external browser via
        # Qt.openUrlExternally, and embedding the token there would leak
        # it into browser history/referrers.
        if with_token and self.api.token:
            sep = '&' if '?' in resolved else '?'
            resolved += f'{sep}token={self.api.token}'
        return resolved

    def image(self, text, url, title=None):
        resolved = self._resolve_url(url, with_token=True)
        src = self.safe_url(resolved)
        alt = striptags(text)
        width, height = self._sized(resolved)
        s = f'<img src="{src}" width="{width}" height="{height}" alt="{alt}"'
        if title:
            s += f' title="{safe_entity(title)}"'
        return s + ' />'

    def link(self, text, url, title=None):
        resolved = self._resolve_url(url, with_token=False)
        return super().link(text, resolved, title)

    def _sized(self, url):
        """Qt's StyledText renders <img> at its natural size unless both
        width and height are given, so always supply both - falling back
        to a square guess if the real dimensions can't be determined."""
        target = max(1, int(self.img_width))
        dims = self.api._image_dimensions(url)
        if dims and dims[0] > 0 and dims[1] > 0:
            natural_width, natural_height = dims
            display_width = min(natural_width, target)
            display_height = max(1, round(natural_height * display_width / natural_width))
            return display_width, display_height
        return target, target

    _HASHTAG_RE = re.compile(r'(?<![\w&])(#\w+)')

    def text(self, text):
        # Operating on the raw (not-yet-escaped) text run means "#tag"
        # detection never has to worry about matching inside a real HTML
        # tag or an entity reference - there aren't any at this point,
        # since escaping happens per-segment below, after splitting.
        parts = self._HASHTAG_RE.split(text)
        out = []
        for i, part in enumerate(parts):
            if not part:
                continue
            if i % 2 == 1:
                out.append(f'<font color="#00d1e5">{escape_text(part)}</font>')
            else:
                out.append(super().text(part))
        return ''.join(out)

    def task_list_item(self, text, checked=False):
        # Requires the 'task_lists' plugin, which identifies genuine
        # "- [ ] foo" / "- [x] foo" list items during parsing - unlike
        # the previous blind str.replace('[ ]', ...) over the whole
        # rendered HTML, which would also match "[ ]" or "[x]" appearing
        # anywhere else in a memo (plain prose, a code block, etc).
        #
        # NOTE: deliberately a plain <li>, no class attribute. Qt's
        # Text.StyledText only understands a narrow, specific HTML
        # subset - an unrecognized attribute like class="..." on <li>
        # is enough to break its line-layout for that item (verified:
        # it's the one difference from the plain <li> the old blind
        # str.replace() approach produced, which rendered correctly).
        mark = '☑' if checked else '☐'
        if text.startswith('<p>'):
            text = text.replace('<p>', '<p>' + mark + ' ', 1)
        else:
            text = mark + ' ' + text
        return '<li>' + text + '</li>\n'

    # Qt's Text.StyledText has no real block/grid layout engine - it does
    # not lay out <table>/<tr>/<td> as a grid at all, so real table
    # markup (which the 'table' plugin produces by default) just
    # collapses into a single run of text with no visible structure.
    # Render a lightweight text table instead: one line per row (via
    # <br/>), cells separated by " | ", header cells bolded. Not an
    # aligned grid (StyledText has no monospace/column guarantees
    # either), but it's actually readable, which real <table> markup
    # currently is not.
    _TABLE_CELL_SEP = ' | '

    def table(self, text):
        return text if text.endswith('\n') else text + '\n'

    def table_head(self, text):
        return self._strip_trailing_cell_sep(text) + '<br/>\n'

    def table_body(self, text):
        return text

    def table_row(self, text):
        return self._strip_trailing_cell_sep(text) + '<br/>\n'

    def table_cell(self, text, align=None, head=False):
        if head:
            text = f'<b>{text}</b>'
        return text + self._TABLE_CELL_SEP

    def _strip_trailing_cell_sep(self, text):
        if text.endswith(self._TABLE_CELL_SEP):
            return text[:-len(self._TABLE_CELL_SEP)]
        return text

class MemosAPI:
    def __init__(self):
        config_dir = os.path.expanduser('~/.config/harbour-memos')
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, mode=0o700)
        else:
            # An existing install (from before this was restricted) may
            # still have the old, more permissive directory mode.
            self._secure_dir(config_dir)
        self.config_file = os.path.join(config_dir, 'settings.json')
        self.queue_file = os.path.join(config_dir, 'queue.json')
        self.cache_file = os.path.join(config_dir, 'cache.json')
        self.image_cache_dir = os.path.join(config_dir, 'image_cache')
        if not os.path.exists(self.image_cache_dir):
            os.makedirs(self.image_cache_dir)
        self.md = mistune.create_markdown(
            renderer=MemosRenderer(self),
            plugins=['table', 'strikethrough', 'task_lists']
        )
        self.base_url = ''
        self.token = ''
        self.auto_upload = False
        self.line_count = 2
        self.cover_mode = 0
        self.load_settings()

    def _send_error(self, message):
        try:
            pyotherside.send('error', str(message))
        except Exception:
            pass

    def _send_success(self, message_key, message_args=None):
        # Sends a success/info notification identified by a translation key
        # rather than a hardcoded, already-localized string, so the QML side
        # can translate it with qsTr() instead of displaying raw backend text.
        try:
            pyotherside.send('success', message_key, message_args or {})
        except Exception:
            pass

    def _secure_file(self, path):
        # Restrict sensitive files (settings containing the API token) to
        # owner-only read/write.
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass

    def _secure_dir(self, path):
        # Same idea as _secure_file(), but for directories: needs the
        # execute bit too, or the owner loses the ability to traverse/list
        # the directory at all (S_IRUSR|S_IWUSR alone is not enough).
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        except Exception:
            pass

    def _auth_headers(self, accept='*/*'):
        headers = {'Accept': accept, 'User-Agent': 'SailfishMemos/1.0'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        return headers

    def _normalize_image_markdown(self, content):
        if not content:
            return content
        pattern = re.compile('!\\[([^\\]]*)\\]\\(\\[([^\\]]+)\\]\\(([^)]+)\\)\\)')

        def replace(match):
            alt = match.group(1)
            outer_url = match.group(2).strip()
            inner_url = match.group(3).strip()
            url = inner_url or outer_url
            return f'![{alt}]({url})'
        return pattern.sub(replace, content)

    _JPEG_SOF_MARKERS = (
        0xC0, 0xC1, 0xC2, 0xC3,
        0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB,
        0xCD, 0xCE, 0xCF,
    )

    def _jpeg_sof_present(self, data):
        """Quick scan: does the buffer so far contain a complete SOF segment?
        Used to stop reading a JPEG early once we have enough data."""
        pos = 2
        length = len(data)
        while pos + 9 < length:
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            pos += 2
            if marker in (0xD8, 0xD9):
                continue
            if marker == 0xDA:
                return False
            if pos + 2 > length:
                return False
            seglen = int.from_bytes(data[pos:pos + 2], 'big')
            if seglen < 2:
                return False
            if marker in self._JPEG_SOF_MARKERS:
                return pos + seglen <= length
            if pos + seglen > length:
                return False
            pos += seglen
        return False

    def _image_dimensions(self, path_or_url):
        """Return (width, height) for a cached local image, or None."""
        try:
            if not path_or_url.startswith('file://'):
                return None

            path = urllib.parse.unquote(path_or_url[7:])
            with open(path, 'rb') as f:
                data = f.read(65536)
                is_jpeg = data.startswith(b'\xff\xd8\xff')
                # A JPEG's SOF marker (which carries the dimensions) can sit
                # after a large embedded EXIF/ICC profile and fall outside
                # the first 64KB. Keep reading in chunks (bounded, so we
                # never load an entire huge file into memory) until we
                # either find it or give up.
                while is_jpeg and len(data) < 8 * 1024 * 1024:
                    more = f.read(65536)
                    if not more:
                        break
                    data += more
                    if self._jpeg_sof_present(data):
                        break

            # PNG
            # NOTE: this literal previously had doubled backslashes
            # (b'\\x89PNG\\r\\n\\x1a\\n'), which matches the literal text
            # "\x89PNG..." rather than the real binary PNG signature, so
            # this branch never matched an actual PNG file.
            if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) >= 24:
                import struct
                return struct.unpack('>II', data[16:24])

            # GIF
            if (data.startswith(b'GIF87a') or data.startswith(b'GIF89a')) and len(data) >= 10:
                import struct
                return struct.unpack('<HH', data[6:10])

            # BMP
            if data.startswith(b'BM') and len(data) >= 26:
                import struct
                w = struct.unpack('<i', data[18:22])[0]
                h = abs(struct.unpack('<i', data[22:26])[0])
                return (abs(w), h)

            # JPEG
            # Same doubled-backslash issue as PNG above - fixed to match
            # the real JPEG SOI marker bytes.
            if data.startswith(b'\xff\xd8\xff'):
                pos = 2
                length = len(data)
                while pos + 9 < length:
                    if data[pos] != 0xFF:
                        pos += 1
                        continue
                    marker = data[pos + 1]
                    pos += 2

                    if marker in (0xD8, 0xD9):
                        continue
                    if marker == 0xDA:
                        break
                    if pos + 2 > length:
                        break

                    seglen = int.from_bytes(data[pos:pos + 2], 'big')
                    if seglen < 2 or pos + seglen > length:
                        break

                    # SOF markers containing image dimensions
                    if marker in (
                        0xC0, 0xC1, 0xC2, 0xC3,
                        0xC5, 0xC6, 0xC7,
                        0xC9, 0xCA, 0xCB,
                        0xCD, 0xCE, 0xCF
                    ):
                        if seglen >= 7:
                            h = int.from_bytes(data[pos + 3:pos + 5], 'big')
                            w = int.from_bytes(data[pos + 5:pos + 7], 'big')
                            return (w, h)

                    pos += seglen

            # WebP
            if data.startswith(b'RIFF') and len(data) >= 16 and data[8:12] == b'WEBP':
                chunk = data[12:16]

                # VP8X
                if chunk == b'VP8X' and len(data) >= 30:
                    w = 1 + int.from_bytes(data[24:27], 'little')
                    h = 1 + int.from_bytes(data[27:30], 'little')
                    return (w, h)

                # VP8 lossy
                if chunk == b'VP8 ' and len(data) >= 30:
                    p = data.find(b'\\x9d\\x01\\x2a', 20)
                    if p != -1 and p + 7 <= len(data):
                        w = int.from_bytes(data[p + 3:p + 5], 'little') & 0x3fff
                        h = int.from_bytes(data[p + 5:p + 7], 'little') & 0x3fff
                        return (w, h)

                # VP8L lossless
                if chunk == b'VP8L' and len(data) >= 25 and data[20] == 0x2f:
                    b0, b1, b2, b3 = data[21:25]
                    w = 1 + (((b2 & 0x3f) << 8) | b1 << 0)
                    h = 1 + (((b3 & 0xf0) << 4) | b2 >> 6)
                    return (w, h)

        except Exception:
            pass

        return None

    def _detect_image_type(self, data, declared_type='', filename=''):
        if data.startswith(b'\x89PNG\r\n\x1a\n'):
            return ('image/png', '.png')
        if data.startswith(b'\xff\xd8\xff'):
            return ('image/jpeg', '.jpg')
        if data.startswith(b'GIF87a') or data.startswith(b'GIF89a'):
            return ('image/gif', '.gif')
        if data.startswith(b'RIFF') and len(data) >= 12 and (data[8:12] == b'WEBP'):
            return ('image/webp', '.webp')
        if data.startswith(b'BM'):
            return ('image/bmp', '.bmp')
        content_type = (declared_type or '').split(';', 1)[0].strip().lower()
        known_types = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/jpg': '.jpg', 'image/gif': '.gif', 'image/webp': '.webp', 'image/bmp': '.bmp', 'image/svg+xml': '.svg'}
        if content_type in known_types:
            return (content_type, known_types[content_type])
        ext = os.path.splitext(filename)[1].lower()
        if ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'):
            if ext == '.jpeg':
                ext = '.jpg'
            return (mimetypes.types_map.get(ext, 'application/octet-stream'), ext)
        return (content_type or 'application/octet-stream', '')

    def _attachment_uid(self, attachment):
        name = str(attachment.get('name', ''))
        if '/' in name:
            return name.rsplit('/', 1)[1]
        return name

    def _attachment_url(self, attachment):
        # Prefer a URL the server itself hands us (field names differ across
        # usememos versions/forks: externalLink, url, ...) over reconstructing
        # one, since the /file/... path scheme has changed between releases
        # and guessing it is fragile.
        for field in ('externalLink', 'url', 'link'):
            server_url = attachment.get(field)
            if server_url:
                server_url = str(server_url)
                if server_url.startswith('http://') or server_url.startswith('https://'):
                    return server_url
                if server_url.startswith('/'):
                    return self.base_url.rstrip('/') + server_url

        uid = self._attachment_uid(attachment)
        filename = str(attachment.get('filename', 'attachment'))
        return f"{self.base_url.rstrip('/')}/file/attachments/{uid}/{urllib.request.quote(filename, safe='')}"

    def _download_attachment(self, attachment):
        filename = str(attachment.get('filename', 'attachment'))
        declared_type = str(attachment.get('type', ''))
        url = self._attachment_url(attachment)
        try:
            req = urllib.request.Request(url, headers=self._auth_headers(), method='GET')
            with urllib.request.urlopen(req, timeout=20) as response:
                data = response.read()
                content_type = response.headers.get('Content-Type', '')
            if not data:
                return None
            actual_type, extension = self._detect_image_type(data, content_type or declared_type, filename)
            if not actual_type.startswith('image/'):
                return None
            if not extension:
                extension = os.path.splitext(filename)[1].lower()
            if not extension:
                extension = '.img'
            # Identity is the content hash alone (not name/updateTime) so
            # that the same image cached via an inline markdown reference
            # (_cache_inline_images) and via this memo-attachments path
            # resolve to the exact same cache file - otherwise the same
            # photo can be shown twice in one memo.
            digest = hashlib.sha256(data).hexdigest()
            local_name = digest + extension
            local_path = os.path.join(self.image_cache_dir, local_name)
            if not os.path.exists(local_path):
                with open(local_path, 'wb') as f:
                    f.write(data)
            return 'file://' + local_path
        except Exception:
            return None

    def _download_generic_attachment(self, attachment):
        """Download any attachment (not just images) into the local cache and
        return a file:// URL. Used so non-image attachments can be linked
        without exposing the API token in an externally-opened URL."""
        filename = str(attachment.get('filename', 'attachment'))
        url = self._attachment_url(attachment)
        try:
            req = urllib.request.Request(url, headers=self._auth_headers(), method='GET')
            with urllib.request.urlopen(req, timeout=20) as response:
                data = response.read()
            if not data:
                return None
            digest = hashlib.sha256(data).hexdigest()
            ext = os.path.splitext(filename)[1] or ''
            local_path = os.path.join(self.image_cache_dir, digest + ext)
            if not os.path.exists(local_path):
                with open(local_path, 'wb') as f:
                    f.write(data)
            return 'file://' + local_path
        except Exception:
            return None

    def _process_memo_attachments(self, memo):
        content = memo.get('content', '') or ''
        attachments = memo.get('attachments') or []
        if not attachments:
            return content
        added = []
        for attachment in attachments:
            filename = str(attachment.get('filename', 'attachment'))
            attachment_type = str(attachment.get('type', ''))

            if attachment_type.startswith('image/'):
                local_url = self._download_attachment(attachment)
                if not local_url or local_url in content:
                    continue
                alt = filename.replace('\n', ' ').strip() or 'image'
                added.append(f'![{alt}]({local_url})')
            else:
                # Non-image attachments (PDFs, docs, etc.) were previously
                # dropped entirely. Download them (using the auth header,
                # not a URL query token) and link to the local copy so the
                # link works without leaking the API token when opened
                # externally.
                local_url = self._download_generic_attachment(attachment)
                if not local_url or local_url in content:
                    continue
                label = filename.replace('\n', ' ').strip() or 'attachment'
                added.append(f'[📎 {label}]({local_url})')
        if added:
            if content and (not content.endswith('\n')):
                content += '\n'
            content += '\n' + '\n'.join(added) + '\n'
        return content

    def _cache_inline_images(self, content):
        if not content:
            return content

        pattern = re.compile(r'!\[([^\]]*)\]\((/[^)]+)\)')

        def replace(match):
            alt = match.group(1)
            url = match.group(2)
            full_url = self.base_url.rstrip('/') + url

            try:
                req = urllib.request.Request(full_url, headers=self._auth_headers(), method='GET')
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = response.read()
                    content_type = response.headers.get('Content-Type', '')

                if data:
                    # Use the same identity scheme (content hash + sniffed
                    # type) as _download_attachment()/_download_generic_
                    # attachment() below, rather than deriving the filename
                    # from the URL path. Otherwise the same physical image
                    # can get cached under two different filenames - once
                    # here (inline markdown reference) and once via the
                    # memo's separate 'attachments' list - and end up
                    # rendered twice in the same memo.
                    filename_hint = url.split('?')[0].rsplit('/', 1)[-1]
                    _, ext = self._detect_image_type(data, content_type, filename_hint)
                    if not ext:
                        ext = '.png'
                    digest = hashlib.sha256(data).hexdigest()
                    local_name = digest + ext
                    local_path = os.path.join(self.image_cache_dir, local_name)

                    if not os.path.exists(local_path):
                        with open(local_path, 'wb') as f:
                            f.write(data)
                    return f'![{alt}](file://{local_path})'
            except Exception:
                pass

            return match.group(0)

        return pattern.sub(replace, content)

    def render_markdown(self, content, img_width=800):
        if not content:
            return ''
        content = self._normalize_image_markdown(content)
        # The renderer resolves relative URLs against self.base_url/token
        # and sizes images itself (see MemosRenderer); img_width is the
        # only thing that varies per call (it depends on the QML item
        # asking, not on the memo content), so it's set here just before
        # rendering.
        self.md.renderer.img_width = img_width
        return self.md(content)

    def load_settings(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                self.base_url = data.get('base_url', '')
                self.token = data.get('token', '')
                self.auto_upload = data.get('auto_upload', False)
                self.line_count = data.get('line_count', 2)
                self.cover_mode = data.get('cover_mode', 0)
                # Older installs may have written this file with default
                # (world-readable) permissions before this was fixed.
                self._secure_file(self.config_file)
            except Exception:
                pass

    def get_settings(self):
        return {'base_url': self.base_url, 'token': self.token, 'auto_upload': self.auto_upload, 'line_count': self.line_count, 'cover_mode': self.cover_mode}

    def save_settings(self, base_url, token, auto_upload, line_count, cover_mode):
        self.base_url = str(base_url or '').rstrip('/')
        self.token = str(token or '').strip()
        self.auto_upload = auto_upload
        self.line_count = line_count
        self.cover_mode = cover_mode
        try:
            with open(self.config_file, 'w') as f:
                json.dump({'base_url': self.base_url, 'token': self.token, 'auto_upload': self.auto_upload, 'line_count': self.line_count, 'cover_mode': self.cover_mode}, f)
            # settings.json holds the API token in plaintext; restrict it to
            # the owner so other local users/apps can't read it off disk.
            self._secure_file(self.config_file)
            # A URL typed without "http(s)://" (e.g. just "memos.example.com")
            # is saved as-is (so the person doesn't lose what they typed),
            # but every subsequent network call would otherwise fail with an
            # opaque low-level error ("unknown url type"). Flag it clearly
            # here instead, right when they hit Save.
            if self.base_url and not (self.base_url.startswith('http://') or self.base_url.startswith('https://')):
                self._send_error('Server URL should start with http:// or https://')
            return True
        except Exception as e:
            self._send_error(f'Failed to save settings: {str(e)}')
            return False

    def save_to_queue(self, op, content=None, memo_id=None):
        # Queue entries are now {"op": "create"|"edit"|"delete", ...} so
        # edits and deletes made offline can be retried too, not just new
        # memos.
        queue = []
        if os.path.exists(self.queue_file):
            try:
                with open(self.queue_file, 'r') as f:
                    queue = json.load(f)
            except Exception:
                pass
        if not queue or not isinstance(queue, list):
            queue = []
        # Migrate any legacy queue entries (plain content strings) from
        # older versions of the app into the new dict format.
        queue = [
            q if isinstance(q, dict) else {'op': 'create', 'content': q}
            for q in queue
        ]
        entry = {'op': op}
        if content is not None:
            entry['content'] = content
        if memo_id is not None:
            entry['memo_id'] = str(memo_id)

        if op == 'delete':
            # No point editing/creating something we're about to delete
            # (or deleting it twice), and an edit queued after a delete
            # should just replace the delete's outcome.
            queue = [q for q in queue if q.get('memo_id') != entry.get('memo_id')]
        elif op == 'edit':
            queue = [
                q for q in queue
                if not (q.get('op') == 'edit' and q.get('memo_id') == entry.get('memo_id'))
            ]

        queue.append(entry)
        with open(self.queue_file, 'w') as f:
            json.dump(queue, f)

    def sync_queue(self):
        if not self.base_url or not self.token or (not os.path.exists(self.queue_file)):
            return False
        try:
            with open(self.queue_file, 'r') as f:
                queue = json.load(f)
        except Exception:
            return False
        if not queue:
            return False

        queue = [
            q if isinstance(q, dict) else {'op': 'create', 'content': q}
            for q in queue
        ]

        remaining_queue = []
        synced_any = False
        headers = {'Authorization': f'Bearer {self.token}', 'Accept': 'application/json', 'Content-Type': 'application/json', 'User-Agent': 'SailfishMemos/1.0'}
        for entry in queue:
            op = entry.get('op', 'create')
            content = entry.get('content')
            memo_id = entry.get('memo_id')
            try:
                if op == 'create':
                    url = f'{self.base_url}/api/v1/memos'
                    payload = json.dumps({'content': content}).encode('utf-8')
                    req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
                    with urllib.request.urlopen(req, timeout=5):
                        synced_any = True
                elif op == 'edit':
                    mid = memo_id if str(memo_id).startswith('memos/') else f'memos/{memo_id}'
                    url = f'{self.base_url}/api/v1/{mid}?updateMask=content'
                    payload = json.dumps({'content': content}).encode('utf-8')
                    req = urllib.request.Request(url, data=payload, headers=headers, method='PATCH')
                    with urllib.request.urlopen(req, timeout=5):
                        synced_any = True
                elif op == 'delete':
                    mid = memo_id if str(memo_id).startswith('memos/') else f'memos/{memo_id}'
                    url = f'{self.base_url}/api/v1/{mid}'
                    req = urllib.request.Request(url, headers=headers, method='DELETE')
                    with urllib.request.urlopen(req, timeout=5):
                        synced_any = True
                else:
                    continue
            except Exception:
                remaining_queue.append(entry)
        if remaining_queue:
            with open(self.queue_file, 'w') as f:
                json.dump(remaining_queue, f)
        else:
            try:
                os.remove(self.queue_file)
            except OSError:
                pass
        if synced_any:
            pyotherside.send('queue_synced')
        return True

    def _load_queue(self):
        if not os.path.exists(self.queue_file):
            return []
        try:
            with open(self.queue_file, 'r') as f:
                queue = json.load(f)
        except Exception:
            return []
        if not isinstance(queue, list):
            return []
        return [
            q if isinstance(q, dict) else {'op': 'create', 'content': q}
            for q in queue
        ]

    def _apply_pending_queue(self, memos_list):
        """Overlay not-yet-synced offline changes on top of the fetched (or
        cached) memo list: pending edits show the new content, pending
        deletes are hidden, and pending creations are prepended as
        placeholder entries — so a memo you edited/deleted while offline
        doesn't confusingly show its old state until the next sync."""
        queue = self._load_queue()
        if not queue:
            return memos_list

        pending_edits = {}
        pending_deletes = set()
        pending_creates = []
        for entry in queue:
            op = entry.get('op', 'create')
            if op == 'edit' and entry.get('memo_id'):
                pending_edits[str(entry['memo_id'])] = entry.get('content', '')
            elif op == 'delete' and entry.get('memo_id'):
                pending_deletes.add(str(entry['memo_id']))
            elif op == 'create':
                pending_creates.append(entry.get('content', ''))

        result = []
        for memo in memos_list:
            if not isinstance(memo, dict):
                result.append(memo)
                continue
            mid = str(memo.get('name') or memo.get('id') or '')
            if mid in pending_deletes:
                continue
            if mid in pending_edits:
                memo = dict(memo)
                memo['content'] = f"⏳ {pending_edits[mid]}"
            result.append(memo)

        queued_memos = [
            {'name': 'queued', 'content': f'⏳ Waiting to sync:\n{c}'}
            for c in pending_creates
        ]
        return queued_memos + result

    def fetch_memos(self):
        if not self.base_url or not self.token:
            self._send_error('URL or Token missing!')
            return False
        if not (self.base_url.startswith('http://') or self.base_url.startswith('https://')):
            # Avoids a raw, hard-to-read exception ("unknown url type")
            # from urllib below - most likely to be hit right after saving
            # settings with the scheme left off, since this is what
            # auto-refreshes immediately afterward.
            self._send_error('Server URL should start with http:// or https://')
            return False
        headers = self._auth_headers('application/json')
        memos_list = []
        page_token = ''
        try:
            # The memos API paginates results; without following
            # nextPageToken only the server's default page (as few as ~a
            # few dozen memos on some versions) would ever be fetched.
            for _ in range(200):  # hard safety cap against a malformed/looping server response
                url = f'{self.base_url}/api/v1/memos?pageSize=100'
                if page_token:
                    url += f'&pageToken={urllib.request.quote(page_token, safe="")}'
                req = urllib.request.Request(url, headers=headers, method='GET')
                with urllib.request.urlopen(req, timeout=10) as response:
                    raw_data = response.read().decode('utf-8')
                data = json.loads(raw_data)
                if isinstance(data, dict):
                    page_memos = data.get('memos', [])
                    page_token = data.get('nextPageToken', '') or ''
                elif isinstance(data, list):
                    page_memos = data
                    page_token = ''
                else:
                    page_memos = []
                    page_token = ''
                memos_list.extend(page_memos)
                if not page_token or not page_memos:
                    break

            processed_memos = []
            for memo in memos_list:
                if not isinstance(memo, dict):
                    processed_memos.append(memo)
                    continue
                memo_copy = dict(memo)

                memo_copy['content'] = self._cache_inline_images(memo_copy.get('content', ''))
                memo_copy['content'] = self._process_memo_attachments(memo_copy)

                processed_memos.append(memo_copy)
            memos_list = processed_memos
            with open(self.cache_file, 'w') as f:
                json.dump(memos_list, f)
        except Exception as e:
            self._send_error(f'Fetch error: {str(e)}')
            if os.path.exists(self.cache_file):
                try:
                    with open(self.cache_file, 'r') as f:
                        memos_list = json.load(f)
                except Exception:
                    pass

        memos_list = self._apply_pending_queue(memos_list)

        # Tell the UI directly whether anything is waiting to sync, rather
        # than making it infer this from scanning the memo list - a queued
        # delete leaves no visible marker there (the memo is just hidden),
        # so that inference would miss a delete-only queue, e.g. after the
        # app was restarted.
        pyotherside.send('queue_status', bool(self._load_queue()))

        if memos_list:
            pyotherside.send('memos_fetched', memos_list)
        return True

    def create_memo(self, content, allow_queue=True):
        if not self.base_url or not self.token:
            self._send_error('Set server URL and token in settings.')
            return {'ok': False, 'error': 'Set server URL and token in settings.'}
        url = f'{self.base_url}/api/v1/memos'
        headers = {'Authorization': f'Bearer {self.token}', 'Accept': 'application/json', 'Content-Type': 'application/json', 'User-Agent': 'SailfishMemos/1.0'}
        payload = json.dumps({'content': content}).encode('utf-8')
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=10) as response:
                raw = response.read().decode('utf-8')
                pyotherside.send('memo_created')
                try:
                    name = json.loads(raw).get('name', '')
                except Exception:
                    name = ''
                return {'ok': True, 'name': name}
        except Exception as e:
            if self.auto_upload and allow_queue:
                self.save_to_queue('create', content=content)
                pyotherside.send('memo_queued', content)
                return {'ok': True, 'queued': True}
            self._send_error(f'Create error: {str(e)}')
            return {'ok': False, 'error': str(e)}

    def delete_attachment(self, attachment_name):
        """Best-effort delete of a standalone/linked attachment - used to
        clean up an upload made during a NewMemoDialog session that then
        got cancelled, so it doesn't sit around linked to a real memo (or
        as an orphaned "unused" attachment) without ever being referenced
        anywhere. Failures here are non-fatal: worst case is a leftover
        unused attachment visible in the web UI, not a broken memo."""
        if not self.base_url or not self.token or not attachment_name:
            return False
        if not str(attachment_name).startswith('attachments/'):
            attachment_name = f'attachments/{attachment_name}'
        url = f"{self.base_url}/api/v1/{attachment_name}"
        headers = {'Authorization': f'Bearer {self.token}', 'Accept': 'application/json', 'User-Agent': 'SailfishMemos/1.0'}
        try:
            req = urllib.request.Request(url, headers=headers, method='DELETE')
            with urllib.request.urlopen(req, timeout=10):
                return True
        except Exception:
            return False

    def delete_memo(self, memo_id, force_queue=False):
        if not str(memo_id).startswith('memos/'):
            memo_id = f'memos/{memo_id}'
        url = f'{self.base_url}/api/v1/{memo_id}'
        headers = {'Authorization': f'Bearer {self.token}', 'Accept': 'application/json', 'User-Agent': 'SailfishMemos/1.0'}
        try:
            req = urllib.request.Request(url, headers=headers, method='DELETE')
            with urllib.request.urlopen(req, timeout=5):
                pyotherside.send('memo_deleted')
                return True
        except Exception as e:
            # force_queue is used for internal cleanup deletes (e.g. removing
            # a provisional memo after a cancelled NewMemoDialog) - those
            # should always be retried once connectivity returns, regardless
            # of the user's auto_upload preference, since leaving one behind
            # isn't something the user asked for or can easily notice.
            if self.auto_upload or force_queue:
                self.save_to_queue('delete', memo_id=memo_id)
                pyotherside.send('memo_queued', '')
                return True
            self._send_error(f'Delete error: {str(e)}')
            return False

    def edit_memo(self, memo_id, content):
        if not str(memo_id).startswith('memos/'):
            memo_id = f'memos/{memo_id}'
        url = f'{self.base_url}/api/v1/{memo_id}?updateMask=content'
        headers = {'Authorization': f'Bearer {self.token}', 'Accept': 'application/json', 'Content-Type': 'application/json', 'User-Agent': 'SailfishMemos/1.0'}
        payload = json.dumps({'content': content}).encode('utf-8')
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method='PATCH')
            with urllib.request.urlopen(req, timeout=5):
                pyotherside.send('memo_edited')
                return True
        except Exception as e:
            if self.auto_upload:
                self.save_to_queue('edit', content=content, memo_id=memo_id)
                pyotherside.send('memo_queued', content)
                return True
            self._send_error(f'Edit error: {str(e)}')
            return False

    def upload_resource(self, file_path, memo_name=None):
        if not self.base_url or not self.token:
            return {'ok': False, 'error': 'Error: URL or Token missing.'}

        if not os.path.exists(file_path):
            return {'ok': False, 'error': 'Error: File not found.'}

        filename = os.path.basename(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = 'application/octet-stream'

        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
        except Exception as e:
            return {'ok': False, 'error': f"Error reading file: {str(e)}"}

        b64_content = base64.b64encode(file_data).decode('utf-8')

        headers = {
            'Authorization': f'Bearer {self.token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'SailfishMemos/1.0'
        }

        url = f"{self.base_url}/api/v1/attachments"

        payload = {
            "filename": filename,
            "type": mime_type,
            "content": b64_content
        }
        if memo_name:
            # If the memo already exists (editing), link the attachment to
            # it right away instead of leaving it standalone. This is the
            # same mechanism usememos' own integrations use.
            if not str(memo_name).startswith('memos/'):
                memo_name = f'memos/{memo_name}'
            payload["memo"] = memo_name

        body = json.dumps(payload).encode('utf-8')

        try:
            req = urllib.request.Request(url, data=body, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=30) as response:
                res_data = response.read().decode('utf-8')
                res_json = json.loads(res_data)

                if isinstance(res_json, dict):
                    r_name = res_json.get('name', '')
                    r_id = res_json.get('id', '')
                    r_filename = res_json.get('filename', filename)
                    r_type = res_json.get('type', mime_type)

                    res_url = ""
                    if r_name:
                        if not r_name.startswith('attachments/'):
                            uid = r_name.rsplit('/', 1)[-1]
                            res_url = f"/file/attachments/{uid}/{urllib.request.quote(r_filename, safe='')}"
                        else:
                            res_url = f"/file/{r_name}/{urllib.request.quote(r_filename, safe='')}"
                    elif r_id:
                        res_url = f"/o/r/{r_id}/{urllib.request.quote(r_filename, safe='')}"

                    if res_url:
                        # NOTE: unless memo_name was given above, this only
                        # creates a *standalone* attachment - the caller
                        # must know the memo's id before uploading (e.g. by
                        # creating the memo first) to get it linked; there's
                        # no reliable way to link it after the fact across
                        # usememos versions.
                        markdown = (
                            f"![{r_filename}]({res_url})"
                            if r_type.startswith('image/')
                            else f"[📎 {r_filename}]({res_url})"
                        )
                        return {'ok': True, 'markdown': markdown, 'name': r_name or ''}

                return {'ok': False, 'error': f"Error: Unexpected response: {res_data[:50]}..."}

        except urllib.error.HTTPError as e:
            try:
                error_msg = e.read().decode('utf-8')
            except:
                error_msg = e.reason
            return {'ok': False, 'error': f"HTTP Error {e.code}: {error_msg[:100]}"}
        except Exception as e:
            return {'ok': False, 'error': f"Upload error: {str(e)}"}

    def clear_cache(self):
        # 1. Poistetaan muistiinpanojen tekstivälimuisti (cache.json)
        if os.path.exists(self.cache_file):
            try:
                os.remove(self.cache_file)
            except Exception as e:
                self._send_error(f"Cache clear error: {str(e)}")
        # 2. Tyhjennetään ladatut kuvat image_cache -kansiosta
        if os.path.exists(self.image_cache_dir):
            try:
                for filename in os.listdir(self.image_cache_dir):
                    file_path = os.path.join(self.image_cache_dir, filename)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
            except Exception as e:
                self._send_error(f"Image cache clear error: {str(e)}")
        # Notify the UI via a dedicated "success" channel with a translation
        # key, instead of piggy-backing a hardcoded Finnish string on the
        # error channel (which bypassed the app's own translation files and
        # showed up styled as an error).
        self._send_success('cache_cleared')
        return True

api = MemosAPI()
