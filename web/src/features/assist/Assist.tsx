import { pct } from "../../app/theme";
import type { Run } from "../../shared/types";

export function Assist({ run, names }: { run: Run; names: Record<string, string> }) {
  const r = run.assist.retrieval;
  const rows: [string, number][] = [
    ["Asked in the tariff's own words", r.tariff_words],
    ["Asked in the customer's own words", r.paraphrased],
    ["Same questions, restated by the model first", r.paraphrased_after_rewrite],
  ];
  return (
    <div className="pair">
      <div>
        <p className="lede">How often the right clause is among the three retrieved:</p>
        <ul className="meters">
          {rows.map(([label, v]) => (
            <li key={label}>
              <span>{label}</span>
              <span className="meter" style={{ ["--v" as string]: v }} aria-hidden="true" />
              <b>{pct(v, 0)}</b>
            </li>
          ))}
        </ul>
      </div>
      <table className="plain">
        <thead>
          <tr>
            <th scope="col">Design</th>
            <th scope="col">Drafts sent as they are</th>
            <th scope="col">Wrong answers per 1,000</th>
          </tr>
        </thead>
        <tbody>
          {["memory_large", "rag_large", "platform"].map((k) => {
            const d = run.assist.designs[k];
            return (
              <tr key={k} className={k === "platform" ? "is-platform" : ""}>
                <th scope="row">{names[k]}</th>
                <td>{pct(d.drafts_used)}</td>
                <td>{d.wrong_answers_per_1000}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
