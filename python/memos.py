import sys
import os
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

class MemosAPI:
    def __init__(self):
        config_dir = os.path.expanduser('~/.config/harbour-memos')
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        self.config_file = os.path.join(config_dir, 'settings.json')
        self.queue_file = os.path.join(config_dir, 'queue.json')
        self.cache_file = os.path.join(config_dir, 'cache.json')
        self.image_cache_dir = os.path.join(config_dir, 'image_cache')
        if not os.path.exists(self.image_cache_dir):
            os.makedirs(self.image_cache_dir)
        self.md = mistune.create_markdown(escape=True)
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

    def _protect_local_urls(self, content):
        mapping = {}

        def replace(match):
            url = match.group(1)
            key = f'MEMOSLOCALIMAGE{len(mapping)}END'
            mapping[key] = url
            return key
        protected = re.sub('(?<![A-Za-z0-9])(file:///[^\\s)\\]"<>]+)', replace, content)
        return (protected, mapping)

    def _restore_local_urls(self, html, mapping):
        for key, url in mapping.items():
            html = html.replace(key, url)
        return html

    def _style_hashtags_in_text(self, html):
        parts = re.split('(<[^>]+>)', html)
        for i in range(0, len(parts), 2):
            text = parts[i]
            parts[i] = re.sub('(?<![\\w&])(#\\w+)', '<font color="#00d1e5">\\1</font>', text)
        return ''.join(parts)

    def _image_dimensions(self, path_or_url):
        """Return (width, height) for a cached local image, or None."""
        try:
            if not path_or_url.startswith('file://'):
                return None

            path = urllib.parse.unquote(path_or_url[7:])
            with open(path, 'rb') as f:
                data = f.read(65536)

            # PNG
            if data.startswith(b'\\x89PNG\\r\\n\\x1a\\n') and len(data) >= 24:
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
            if data.startswith(b'\\xff\\xd8\\xff'):
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
            identity = (str(attachment.get('name', '')) + '\x00' + str(attachment.get('updateTime', '')) + '\x00').encode('utf-8') + data
            digest = hashlib.sha256(identity).hexdigest()
            if not extension:
                extension = os.path.splitext(filename)[1].lower()
            if not extension:
                extension = '.img'
            local_name = digest + extension
            local_path = os.path.join(self.image_cache_dir, local_name)
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
            if not attachment_type.startswith('image/'):
                continue
            local_url = self._download_attachment(attachment)
            if not local_url:
                continue
            if local_url in content:
                continue
            alt = filename.replace('\n', ' ').strip() or 'image'
            added.append(f'![{alt}]({local_url})')
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

                if data:
                    digest = hashlib.sha256(data).hexdigest()
                    ext = os.path.splitext(url.split('?')[0])[1].lower()
                    if not ext:
                        ext = '.png'
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

    # UUSI: Lisätty img_width parametri (oletuksena 800)
    def render_markdown(self, content, img_width=800):
        if not content:
            return ''
        content = self._normalize_image_markdown(content)
        protected_content, local_urls = self._protect_local_urls(content)

        html = self.md(protected_content)
        html = html.replace('[ ]', '☐')
        html = html.replace('[x]', '☑')
        html = html.replace('[X]', '☑')
        html = self._style_hashtags_in_text(html)

        def process_url(match):
            attr = match.group(1)
            url = match.group(2)
            if url in local_urls:
                url = local_urls[url]
            if url.startswith('/'):
                url = self.base_url.rstrip('/') + url
                if self.token:
                    separator = '&' if '?' in url else '?'
                    url += f'{separator}token={self.token}'

            # Qt StyledText käsittelee img-tagit inline-kuvina.
            # Pelkkä width ei ole riittävä kaikissa Qt 5 -versioissa:
            # anna aina sekä width että height, säilyttäen kuvan kuvasuhde.
            if attr == 'src':
                target_width = max(1, int(img_width))
                dimensions = self._image_dimensions(url)

                if dimensions:
                    natural_width, natural_height = dimensions
                    if natural_width > 0 and natural_height > 0:
                        display_width = min(natural_width, target_width)
                        display_height = max(
                            1,
                            int(round(natural_height * display_width / natural_width))
                        )
                        return (
                            f'src="{url}" width="{display_width}" '
                            f'height="{display_height}"'
                        )

                # Jos kokoa ei saada selville, käytetään silti molempia
                # mittoja, jotta kuva ei jää alkuperäiseen kokoonsa.
                return f'src="{url}" width="{target_width}" height="{target_width}"'
            return f'{attr}="{url}"'

        html = re.sub('(src|href)="([^"]+)"', process_url, html)
        html = self._restore_local_urls(html, local_urls)

        return html

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
            return True
        except Exception as e:
            self._send_error(f'Failed to save settings: {str(e)}')
            return False

    def save_to_queue(self, content):
        queue = []
        if os.path.exists(self.queue_file):
            try:
                with open(self.queue_file, 'r') as f:
                    queue = json.load(f)
            except Exception:
                pass
        queue.append(content)
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
        remaining_queue = []
        synced_any = False
        headers = {'Authorization': f'Bearer {self.token}', 'Accept': 'application/json', 'Content-Type': 'application/json', 'User-Agent': 'SailfishMemos/1.0'}
        for content in queue:
            url = f'{self.base_url}/api/v1/memos'
            payload = json.dumps({'content': content}).encode('utf-8')
            try:
                req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
                with urllib.request.urlopen(req, timeout=5):
                    synced_any = True
            except Exception:
                remaining_queue.append(content)
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

    def fetch_memos(self):
        if not self.base_url or not self.token:
            self._send_error('URL or Token missing!')
            return False
        url = f'{self.base_url}/api/v1/memos'
        headers = self._auth_headers('application/json')
        memos_list = []
        try:
            req = urllib.request.Request(url, headers=headers, method='GET')
            with urllib.request.urlopen(req, timeout=10) as response:
                raw_data = response.read().decode('utf-8')
                data = json.loads(raw_data)
                if isinstance(data, dict):
                    memos_list = data.get('memos', [])
                elif isinstance(data, list):
                    memos_list = data
                else:
                    memos_list = []
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
        if os.path.exists(self.queue_file):
            try:
                with open(self.queue_file, 'r') as f:
                    queue = json.load(f)
                queued_memos = [{'name': 'queued', 'content': f'⏳ Waiting to sync:\n{q}'} for q in queue]
                memos_list = queued_memos + memos_list
            except Exception:
                pass
        if memos_list:
            pyotherside.send('memos_fetched', memos_list)
        return True

    def create_memo(self, content):
        if not self.base_url or not self.token:
            self._send_error('Set server URL and token in settings.')
            return False
        url = f'{self.base_url}/api/v1/memos'
        headers = {'Authorization': f'Bearer {self.token}', 'Accept': 'application/json', 'Content-Type': 'application/json', 'User-Agent': 'SailfishMemos/1.0'}
        payload = json.dumps({'content': content}).encode('utf-8')
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=5):
                pyotherside.send('memo_created')
                return True
        except Exception as e:
            if self.auto_upload:
                self.save_to_queue(content)
                pyotherside.send('memo_queued', content)
                return True
            self._send_error(f'Create error: {str(e)}')
            return False

    def delete_memo(self, memo_id):
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
            self._send_error(f'Edit error: {str(e)}')
            return False

    def upload_resource(self, file_path):
        if not self.base_url or not self.token:
            return "Error: URL or Token missing."

        if not os.path.exists(file_path):
            return "Error: File not found."

        filename = os.path.basename(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = 'application/octet-stream'

        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"

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
                        if r_type.startswith('image/'):
                            return f"![{r_filename}]({res_url})"
                        else:
                            return f"[📎 {r_filename}]({res_url})"

                return f"Error: Unexpected response: {res_data[:50]}..."

        except urllib.error.HTTPError as e:
            try:
                error_msg = e.read().decode('utf-8')
            except:
                error_msg = e.reason
            return f"HTTP Error {e.code}: {error_msg[:100]}"
        except Exception as e:
            return f"Upload error: {str(e)}"

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
        # Lähetetään onnistumisviesti käyttöliittymälle näkyviin
        self._send_error("Välimuistit tyhjennetty!")
        return True

api = MemosAPI()
