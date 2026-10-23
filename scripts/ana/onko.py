# -*- coding: utf-8 -*-
"""東スポ競馬の連載「温故知新」（白井寿昭元調教師と学ぶ血統学）を取る。

  python3 scripts/ana/onko.py            … 一覧にある記事を順に取って notes/onko/ に保存
  python3 scripts/ana/onko.py --list     … 一覧だけ取り直す

本文はサーバーのHTMLに入っておらず、JavaScriptで後から差し込まれる。
さらにヘッドレスの既定UAはWAFに弾かれるので、通常のChromeのUAを渡す。
このコンテナではプロキシのCAをChromiumの信頼ストア（~/.pki/nssdb）に
登録しておかないと ERR_CERT_AUTHORITY_INVALID で止まる。
"""
import json, os, re, sys, time
from playwright.sync_api import sync_playwright

ROOT = '/home/user/keiba/notes/onko'
LIST = os.path.join(ROOT, '_list.json')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')
CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
HEAD = ('レース情報', 'ニュース', '予想', 'データベース', '連載コラム', '新聞PDF',
        'ログイン', 'よくある質問', 'お知らせ', 'メニュー', '閉じる', 'TOPページ')


def clean(t):
    lines = [l.rstrip() for l in t.split('\n')]
    while lines and (not lines[0].strip() or lines[0].strip() in HEAD):
        lines.pop(0)
    out, blank = [], 0
    for l in lines:
        if not l.strip():
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        out.append(l)
    return '\n'.join(out).strip()


def main():
    urls = json.load(open(LIST, encoding='utf-8'))
    todo = [i for i in sorted(urls, key=int) if not os.path.exists(os.path.join(ROOT, i + '.txt'))]
    print('全%d本 ／ 未取得%d本' % (len(urls), len(todo)), flush=True)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
        ctx = b.new_context(user_agent=UA, locale='ja-JP')
        pg = ctx.new_page()
        for k, i in enumerate(todo, 1):
            u = 'https://tospo-keiba.jp/onkochishin/%s' % i
            try:
                pg.goto(u, wait_until='domcontentloaded', timeout=60000)
                pg.wait_for_timeout(2500)
                t = clean(pg.inner_text('body'))
            except Exception as e:
                print('  %s 取得NG %s' % (i, str(e)[:60]), flush=True)
                time.sleep(3)
                continue
            if len(t) < 400:
                print('  %s 本文が短い（%d字）' % (i, len(t)), flush=True)
            open(os.path.join(ROOT, i + '.txt'), 'w', encoding='utf-8').write(
                '# %s\n# %s\n\n%s\n' % (urls[i], u, t))
            print('[%d/%d] %s %d字 %s' % (k, len(todo), i, len(t), urls[i][:34]), flush=True)
            time.sleep(1.0)
        b.close()
    print('完了')


if __name__ == '__main__':
    main()
