# -*- coding: utf-8 -*-
"""netkeiba の血統表を読むための共通部分。

- 馬名検索は EUC-JP でエンコードして渡す（UTF-8 だと「該当データなし」になる）
- 5代血統表は 62セル。文書順は父から深さ優先なので、位置ラベルを当てられる
- セルには祖先の馬ID が入っているので、そのIDで血統表を追えば5代ずつ奥へ伸びる
"""
import re, time, urllib.request, urllib.parse

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')


def labels():
    out = []

    def rec(path):
        out.append(path)
        if len(path) < 5:
            rec(path + '父')
            rec(path + '母')
    rec('父')
    rec('母')
    return out


LAB = labels()


def get(u, tries=3, sleep=1.5):
    for i in range(tries):
        try:
            r = urllib.request.Request(u, headers={'User-Agent': UA})
            b = urllib.request.urlopen(r, timeout=30).read()
            time.sleep(sleep)
            return b.decode('euc_jp', 'replace')
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** i * 2)


def clean(h):
    h = re.sub(r'<[^>]+>', '', h).replace('&nbsp;', ' ').replace('&amp;', '&')
    return re.sub(r'\s+', ' ', h).strip()


COUNTRY = ('米|英|愛|仏|独|加|豪|新|伊|日|南阿|亜|伯|智|UAE|香|印|土|西|丁|белг|墺|洪|'
           'チェコ|スウェーデン|ノルウェー|ポーランド|露|ブ|星|韓|沙|カタール|鈴')


def cellname(c):
    """'Galileo (愛) 1998 鹿毛 [血統][産駒] 9-h' → 'Galileo'"""
    c = re.sub(r'\[血統\]|\[産駒\]', ' ', c)
    c = re.sub(r'\b(1[6-9]|20)\d\d\b.*$', '', c)       # 生年から後ろを落とす
    c = re.sub(rf'\s*\((?:{COUNTRY})\)', '', c)
    c = re.sub(r'\s*\([^)]{1,8}\)\s*$', '', c)
    c = re.sub(r'\s+\d{1,2}-[a-z]\s*$', '', c)
    return c.strip()


def search_id(nm):
    """馬名から netkeiba の馬ID。一意なら馬ページへ転送されるので canonical を見る。"""
    q = urllib.parse.quote(nm.encode('euc_jp'))
    t = get(f'https://db.netkeiba.com/?pid=horse_list&word={q}')
    if '該当データが存在しません' in t:
        return None, []
    m = re.search(r'<link[^>]+rel="canonical"[^>]+href="[^"]*?/horse/(\d{10})/?"', t)
    if m:
        return m.group(1), []
    cands = []
    for r in re.findall(r'<tr[^>]*>(.*?)</tr>', t, re.S):
        i = re.search(r'/horse/(\d{10})/', r)
        if i:
            cands.append((i.group(1), [clean(x) for x in
                                       re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.S)]))
    return (cands[0][0] if cands else None), cands


def ped62(hid):
    """{位置: (馬名, ID)} の62セル。取れなければ None。"""
    t = get(f'https://db.netkeiba.com/horse/ped/{hid}/')
    m = re.search(r'blood_table.*?</table>', t, re.S)
    if not m:
        return None
    tds = re.findall(r'<td[^>]*>(.*?)</td>', m.group(0), re.S)
    if len(tds) != 62:
        return None
    out = {}
    for lab, td in zip(LAB, tds):
        i = re.search(r'/horse/(?:ped/)?([0-9a-z]{10})/?', td)
        out[lab] = (cellname(clean(td)), i.group(1) if i else None)
    return out
