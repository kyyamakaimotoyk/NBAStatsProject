"use client";

import Link from "next/link";
import { useLang } from "@/lib/i18n";

// Same convention as AboutContent: two full JSX versions, and the Japanese is
// a transcreation, not a sentence-by-sentence translation — keep it that way.

// Forwarded to the owner's inbox by the mail-forwarding service configured on
// the hoopmodel.com MX records (see docs/ad_monetization_plan.md).
const CONTACT_EMAIL = "contact@hoopmodel.com";

function ContactEnglish() {
  return (
    <section>
      <h1>Contact</h1>
      <p className="subtle">
        HoopModel is built and run by one person, Kai Y. Every message is read
        by a human.
      </p>

      <h2>Email</h2>
      <p>
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
      </p>
      <p>Expect a reply within a few days; it&apos;s a side project, not a help desk.</p>

      <h2>Good reasons to write</h2>
      <ul>
        <li>
          A score, stat or result on the site looks wrong. Include the page and the
          game date, and I&apos;ll check it against the source data.
        </li>
        <li>Something is broken, or a page doesn&apos;t work on your device.</li>
        <li>
          Questions about how the models work beyond what the{" "}
          <Link href="/about">About</Link> page covers.
        </li>
        <li>
          Privacy requests about the data described in the{" "}
          <Link href="/privacy">privacy policy</Link>.
        </li>
      </ul>

      <h2>What I can&apos;t help with</h2>
      <p>
        I don&apos;t give personal betting advice or sell picks, and I can&apos;t answer
        individual fantasy questions by email. The{" "}
        <Link href="/advisor">fantasy advisor</Link> is there for that.
      </p>
    </section>
  );
}

function ContactJapanese() {
  return (
    <section>
      <h1>お問い合わせ</h1>
      <p className="subtle">
        HoopModel は Kai Y. が個人で制作・運営しています。いただいたメッセージは、すべて本人が目を通しています。
      </p>

      <h2>メール</h2>
      <p>
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
      </p>
      <p>
        個人で運営しているため、返信までに数日いただくことがあります。英語・日本語どちらでもお気軽にどうぞ。
      </p>

      <h2>こんなときにご連絡ください</h2>
      <ul>
        <li>
          スコアやスタッツ、試合結果の表示がおかしいと感じたとき。ページ名と試合日を添えていただければ、元データと照らし合わせて確認します。
        </li>
        <li>表示が崩れている、お使いの端末でページが動かないなどの不具合。</li>
        <li>
          「<Link href="/about">このサイトについて</Link>」のページで触れていない、モデルのしくみに関するご質問。
        </li>
        <li>
          <Link href="/privacy">プライバシーポリシー</Link>に記載したデータについてのご依頼。
        </li>
      </ul>

      <h2>お受けできないご相談</h2>
      <p>
        賭けに関する個別の助言や予想の販売は行っていません。ファンタジーの個別のご相談もメールではお答えできませんので、
        「<Link href="/advisor">ファンタジー・バスケ相談所</Link>」をご利用ください。
      </p>
    </section>
  );
}

export default function ContactContent() {
  const { lang } = useLang();
  return lang === "ja" ? <ContactJapanese /> : <ContactEnglish />;
}
