// Wrapper for every chart in an article: numbered title, the chart, a caption
// saying what to notice, the data source, and the underlying numbers as a
// table. Server-rendered, so the caption and table are in the prerendered HTML
// even though the chart itself draws client-side.

export type FigureTable = { head: string[]; rows: (string | number)[][] };

const LABELS = {
  en: { fig: (n: number) => `Figure ${n}.`, source: "Source:", data: "Show the data" },
  ja: { fig: (n: number) => `図${n}　`, source: "出典：", data: "データを表示" },
};

export default function Figure({
  n,
  title,
  caption,
  source,
  table,
  lang,
  children,
}: {
  n: number;
  title: string;
  caption: React.ReactNode;
  source: string;
  table: FigureTable;
  lang: "en" | "ja";
  children: React.ReactNode;
}) {
  const l = LABELS[lang];
  return (
    <figure className="article-figure">
      <p className="article-figure-title">
        <strong>{l.fig(n)}</strong> {title}
      </p>
      <div className="article-figure-chart">{children}</div>
      <figcaption>{caption}</figcaption>
      <p className="article-figure-source">
        {l.source} {source}
      </p>
      <details>
        <summary>{l.data}</summary>
        <table>
          <thead>
            <tr>
              {table.head.map((h, i) => (
                <th key={i}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i}>
                {row.map((c, j) => (
                  <td key={j}>{c}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
