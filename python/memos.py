import os
import json
import urllib.request
import pyotherside

class MemosAPI:
    def __init__(self):
        config_dir = os.path.expanduser('~/.config/harbour-memos')
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)

        self.config_file = os.path.join(config_dir, 'settings.json')
        self.queue_file = os.path.join(config_dir, 'queue.json')
        self.cache_file = os.path.join(config_dir, 'cache.json')

        self.base_url = ""
        self.token = ""
        self.auto_upload = False
        self.line_count = 2
        self.cover_mode = 0 # UUSI: 0 = Uusin luotu, 1 = Viimeksi muokattu

        self.load_settings()

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
            except:
                pass

    def get_settings(self):
        return {
            'base_url': self.base_url,
            'token': self.token,
            'auto_upload': self.auto_upload,
            'line_count': self.line_count,
            'cover_mode': self.cover_mode
        }

    def save_settings(self, base_url, token, auto_upload, line_count, cover_mode):
        self.base_url = base_url.rstrip('/')
        self.token = token.strip()
        self.auto_upload = auto_upload
        self.line_count = line_count
        self.cover_mode = cover_mode

        try:
            with open(self.config_file, 'w') as f:
                json.dump({
                    'base_url': self.base_url,
                    'token': self.token,
                    'auto_upload': self.auto_upload,
                    'line_count': self.line_count,
                    'cover_mode': self.cover_mode
                }, f)
            return True
        except Exception as e:
            pyotherside.send('error', f"Asetusten tallennus epäonnistui: {str(e)}")
            return False

    def save_to_queue(self, content):
        queue = []
        if os.path.exists(self.queue_file):
            try:
                with open(self.queue_file, 'r') as f:
                    queue = json.load(f)
            except:
                pass

        queue.append(content)
        with open(self.queue_file, 'w') as f:
            json.dump(queue, f)

    def sync_queue(self):
        if not self.base_url or not self.token or not os.path.exists(self.queue_file):
            return False

        try:
            with open(self.queue_file, 'r') as f:
                queue = json.load(f)
        except:
            return False

        if not queue:
            return False

        remaining_queue = []
        synced_any = False

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "SailfishMemos/1.0"
        }

        for content in queue:
            url = f"{self.base_url}/api/v1/memos"
            payload = json.dumps({"content": content}).encode('utf-8')
            try:
                req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
                with urllib.request.urlopen(req, timeout=5):
                    synced_any = True
            except:
                remaining_queue.append(content)

        if remaining_queue:
            with open(self.queue_file, 'w') as f:
                json.dump(remaining_queue, f)
        else:
            os.remove(self.queue_file)

        if synced_any:
            pyotherside.send('queue_synced')
        return True

    def fetch_memos(self):
        if not self.base_url or not self.token:
            return False

        url = f"{self.base_url}/api/v1/memos"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "SailfishMemos/1.0"
        }

        memos_list = []
        fetch_success = False

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                memos_list = data.get('memos', data) if isinstance(data, dict) else data
                fetch_success = True

                with open(self.cache_file, 'w') as f:
                    json.dump(memos_list, f)
        except Exception as e:
            pyotherside.send('error', "Ei verkkoyhteyttä (näytetään välimuisti).")

            if os.path.exists(self.cache_file):
                try:
                    with open(self.cache_file, 'r') as f:
                        memos_list = json.load(f)
                except:
                    pass

        if os.path.exists(self.queue_file):
            try:
                with open(self.queue_file, 'r') as f:
                    queue = json.load(f)
                    queued_memos = [{"name": "queued", "content": f"⏳ Odottaa lähetystä:\n{q}"} for q in queue]
                    memos_list = queued_memos + memos_list
            except:
                pass

        if memos_list or fetch_success:
            pyotherside.send('memos_fetched', memos_list)
        return True

    def create_memo(self, content):
        if not self.base_url or not self.token:
            pyotherside.send('error', "Aseta palvelimen osoite ja token asetuksista.")
            return False

        url = f"{self.base_url}/api/v1/memos"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "SailfishMemos/1.0"
        }
        payload = json.dumps({"content": content}).encode('utf-8')

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
            else:
                pyotherside.send('error', "Ei verkkoyhteyttä, eikä auto-upload ole päällä.")
                return False

    def delete_memo(self, memo_id):
        if not str(memo_id).startswith('memos/'):
            memo_id = f"memos/{memo_id}"

        url = f"{self.base_url}/api/v1/{memo_id}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "SailfishMemos/1.0"
        }

        try:
            req = urllib.request.Request(url, headers=headers, method='DELETE')
            with urllib.request.urlopen(req, timeout=5):
                pyotherside.send('memo_deleted')
                return True
        except Exception as e:
            pyotherside.send('error', f"Poistovirhe: {str(e)}")
            return False

    def edit_memo(self, memo_id, content):
        if not str(memo_id).startswith('memos/'):
            memo_id = f"memos/{memo_id}"

        url = f"{self.base_url}/api/v1/{memo_id}?updateMask=content"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "SailfishMemos/1.0"
        }
        payload = json.dumps({"content": content}).encode('utf-8')

        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method='PATCH')
            with urllib.request.urlopen(req, timeout=5):
                pyotherside.send('memo_edited')
                return True
        except Exception as e:
            pyotherside.send('error', f"Muokkausvirhe: {str(e)}")
            return False

api = MemosAPI()
