import os
import sys
import subprocess
import re
import json
import requests

# ----------------------------
# 1) Helper fonksiyonlar
# ----------------------------

def get_changed_files(extensions, base_branch, current_branch):
    """
    origin/{base_branch}...origin/{current_branch} arasındaki
    M, A, R, C tipindeki değişen dosyaları döner.
    """
    try:
        out = subprocess.check_output([
            'git', 'diff', '--name-only', '--diff-filter=MARC',
            f'origin/{base_branch}...origin/{current_branch}'
        ]).decode().splitlines()
        return [f for f in out if any(f.endswith(ext) for ext in extensions)]
    except subprocess.CalledProcessError as e:
        print("Git diff hata:", e)
        return []

def has_aapt_in_diff(file_path, base_commit, target_commit):
    """
    Belirtilen dosya için base..target diff'inde
    + veya - ile başlayan satırlarda "<aapt>" arar.
    Bulduğu tüm satırları liste halinde döner.
    """
    try:
        diff = subprocess.check_output(
            f'git diff --unified=0 {base_commit}..{target_commit} -- "{file_path}"',
            shell=True
        ).decode('utf-8')
    except subprocess.CalledProcessError:
        return []

    hits = []
    for line in diff.splitlines():
        if (line.startswith('+') or line.startswith('-')) and '<aapt>' in line:
            hits.append(line)
    return hits

def post_pr_comment(collection_uri, project, repo, pr_id, token, comment):
    """
    Azure DevOps REST API ile PR'a thread (yorum) ekler.
    POST {org}/{project}/_apis/git/repositories/{repo}/pullRequests/{pr_id}/threads?api-version=7.1 :contentReference[oaicite:0]{index=0}
    """
    url = (
        f"{collection_uri.rstrip('/')}/{project}/_apis/git/"
        f"repositories/{repo}/pullRequests/{pr_id}/threads?api-version=7.1"
    )
    headers = {
        "Authorization": f"Bearer {token}",           # OAuth token ile Bearer auth :contentReference[oaicite:1]{index=1}
        "Content-Type": "application/json"
    }
    payload = {
        "comments": [
            {
                "parentCommentId": 0,
                "content": comment,
                "commentType": 1
            }
        ],
        "status": "active"
    }
    resp = requests.post(url, headers=headers, data=json.dumps(payload))
    resp.raise_for_status()
    print("PR yorumu eklendi:", resp.json().get('id'))

# ----------------------------
# 2) Main akışı
# ----------------------------

def main():
    # 2.a) Ortam değişkenleri
    collection_uri = os.getenv('SYSTEM_COLLECTIONURI')
    project        = os.getenv('SYSTEM_TEAMPROJECT')
    repo           = os.getenv('BUILD_REPOSITORY_NAME')
    pr_id          = os.getenv('SYSTEM_PULLREQUEST_PULLREQUESTID')
    token          = os.getenv('SYSTEM_ACCESSTOKEN')  # Allow OAuth token access!

    if not all([collection_uri, project, repo, pr_id, token]):
        print("Gerekli ortam değişkenleri bulunamadı.")
        sys.exit(1)

    # 2.b) Branch bilgileri
    base_branch    = os.getenv('SYSTEM_PULLREQUEST_TARGETBRANCH', 'development').replace('refs/heads/','')
    current_branch = os.getenv('SYSTEM_PULLREQUEST_SOURCEBRANCH', 'HEAD').replace('refs/heads/','')
    commit_hash    = os.getenv('BUILD_SOURCEVERSION')

    os.chdir(os.getenv('BUILD_REPOSITORY_LOCALPATH', '.'))

    # 2.c) Hangi dosyalar değişmiş?
    extensions = ["toml", "kts", "gradle", "pro"]
    files = get_changed_files(extensions, base_branch, current_branch)
    if not files:
        print("İlgili uzantılarda değişen dosya yok.")
        sys.exit(0)

    # 2.d) Her dosyada "<aapt>" araması
    hits = {}
    for f in files:
        lines = has_aapt_in_diff(f, f'origin/{base_branch}', commit_hash)
        if lines:
            hits[f] = lines

    if not hits:
        print("Hiç '<aapt>' içeren satır bulunamadı.")
        sys.exit(0)

    # 2.e) Yorum içeriğini hazırla (Markdown destekler)
    comment = "⚠️ **`<aapt>` etiketi tespit edildi. Lütfen kontrol ediniz.**\n\n"
    for f, lines in hits.items():
        comment += f"**{f}**\n```\n" + "\n".join(lines) + "\n```\n\n"

    # 2.f) PR'a yorum ekle
    post_pr_comment(collection_uri, project, repo, pr_id, token, comment)

if __name__ == "__main__":
    main()
