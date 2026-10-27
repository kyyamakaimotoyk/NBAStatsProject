"use client";

import Link from "next/link";
import { useLang } from "@/lib/i18n";

// Same convention as AboutContent: two full JSX versions, and the Japanese is
// a transcreation, not a sentence-by-sentence translation — keep it that way.

function PrivacyEnglish() {
  return (
    <section>
      <h1>Privacy policy</h1>
      <p className="subtle">
        HoopModel is a personal side project. It has no user accounts and never
        sells personal information. This page lists everything the site
        collects and why. Last updated: October 27, 2026.
      </p>

      <h2>Server logs</h2>
      <p>
        Like almost every website, the servers that deliver these pages record
        standard access logs (IP address, browser type, pages requested,
        timestamps). They are used only to measure traffic and investigate
        abuse, and are not joined with any other data about you.
      </p>

      <h2>Analytics</h2>
      <p>
        The site uses Google Analytics to understand which pages people visit
        and roughly where visitors come from. Google Analytics sets cookies and
        collects usage data under{" "}
        <a href="https://policies.google.com/privacy" rel="noreferrer" target="_blank">
          Google&apos;s privacy policy
        </a>
        . In regions that require consent (the EEA, UK, Switzerland, and
        Canada), analytics stays off until you accept the consent banner.
      </p>

      <h2>Advertising</h2>
      <p>
        The site shows ads served by Google AdSense to help cover hosting
        costs. Ad providers may use cookies to show ads based on your
        interests; in consent-required regions, personalized ads are off
        unless you opt in via the banner, and elsewhere you can opt out any
        time in{" "}
        <a href="https://adssettings.google.com" rel="noreferrer" target="_blank">
          Google&apos;s ad settings
        </a>
        . Gambling and betting ads are blocked on this site.
      </p>

      <h2>The fantasy advisor</h2>
      <p>
        Questions submitted to the <Link href="/advisor">fantasy advisor</Link>{" "}
        and the answers generated may be stored to improve the service. Please
        don&apos;t include personal information in them. The form is protected
        by Cloudflare Turnstile, which performs a privacy-preserving bot check.
      </p>

      <h2>Stored preferences</h2>
      <p>
        Your language choice (English / Japanese) is kept in your browser&apos;s
        local storage. It never leaves your device and is not a tracking
        mechanism.
      </p>

      <h2>Your choices</h2>
      <p>
        You can decline or withdraw consent via the banner where it appears,
        clear cookies and local storage in your browser at any time, and use an
        ad or content blocker — the site works fine with one. For any privacy
        question or request (including deletion of advisor submissions),{" "}
        <Link href="/contact">contact me</Link>
        .
      </p>
    </section>
  );
}

function PrivacyJapanese() {
  return (
    <section>
      <h1>プライバシーポリシー</h1>
      <p className="subtle">
        HoopModelは個人が運営する趣味のプロジェクトです。会員登録の仕組みはなく、
        個人情報を販売することもありません。このページでは、本サイトが収集する情報と
        その目的をすべて記載しています。最終更新日: 2026年10月27日
      </p>

      <h2>サーバーログ</h2>
      <p>
        一般的なウェブサイトと同様に、ページを配信するサーバーは標準的なアクセスログ
        （IPアドレス、ブラウザの種類、閲覧ページ、日時）を記録します。ログの用途は
        アクセス数の把握と不正アクセスの調査に限られ、他の情報と結び付けることはありません。
      </p>

      <h2>アクセス解析</h2>
      <p>
        どのページがよく見られているか、どの地域からの閲覧が多いかを把握するために
        Googleアナリティクスを利用しています。Googleアナリティクスは
        <a href="https://policies.google.com/privacy" rel="noreferrer" target="_blank">
          Googleのプライバシーポリシー
        </a>
        に基づいてCookieを設定し、利用状況データを収集します。同意が必要な地域
        （EEA・英国・スイス・カナダ）では、同意バナーで承諾いただくまで解析は無効のままです。
      </p>

      <h2>広告</h2>
      <p>
        サーバー費用の足しにするため、Google AdSenseによる広告を掲載しています。
        広告事業者は、興味・関心に基づく広告表示のためにCookieを使用することがあります。
        同意が必要な地域ではバナーで承諾しない限りパーソナライズ広告は表示されず、
        それ以外の地域でも
        <a href="https://adssettings.google.com" rel="noreferrer" target="_blank">
          Googleの広告設定
        </a>
        からいつでも無効にできます。なお、本サイトではギャンブル・賭博関連の広告を
        ブロックしています。
      </p>

      <h2>ファンタジー・バスケ相談所</h2>
      <p>
        <Link href="/advisor">ファンタジー・バスケ相談所</Link>
        に送信された質問と生成された回答は、サービス改善のために保存されることがあります。
        個人情報は入力しないようお願いします。フォームはCloudflare Turnstileによる
        ボット対策で保護されています。
      </p>

      <h2>ブラウザに保存される設定</h2>
      <p>
        言語設定（英語・日本語）はブラウザのローカルストレージに保存されます。
        この情報が端末の外に送信されることはなく、トラッキングにも使用しません。
      </p>

      <h2>ご自身でできること</h2>
      <p>
        同意バナーが表示される地域では、同意を断る・後から取り消すことができます。
        ブラウザのCookieとローカルストレージはいつでも削除できますし、広告ブロッカーを
        使っていてもサイトは問題なく動作します。プライバシーに関するご質問やご要望
        （相談所への送信内容の削除依頼を含む）は、
        「<Link href="/contact">お問い合わせ</Link>」のページからご連絡ください。
      </p>
    </section>
  );
}

export default function PrivacyContent() {
  const { lang } = useLang();
  return lang === "ja" ? <PrivacyJapanese /> : <PrivacyEnglish />;
}
