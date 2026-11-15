import { eur, pct } from "../../app/theme";
import type { Run } from "../../shared/types";
import { Empty } from "../../shared/ui";

export function InvoiceExample({ run, names }: { run: Run; names: Record<string, string> }) {
  const ex = run.invoices.platform.example;
  return (
    <div className="pair">
      {ex ? (
        <figure className="invoice">
          <pre lang="de">{ex.invoice}</pre>
          <figcaption>
            Billed {eur(ex.billed, 2)}, paid <b>{eur(ex.paid, 2)}</b>
            <ul>
              {ex.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </figcaption>
        </figure>
      ) : (
        <Empty>No settled example in this report.</Empty>
      )}
      <table className="plain">
        <thead>
          <tr>
            <th scope="col">Design</th>
            <th scope="col">Overpaid per 1,000</th>
            <th scope="col">Underpaid per 1,000</th>
            <th scope="col">Without a person</th>
          </tr>
        </thead>
        <tbody>
          {["llm_decides", "code_rules", "platform"].map((k) => {
            const d = run.invoices[k];
            return (
              <tr key={k} className={k === "platform" ? "is-platform" : ""}>
                <th scope="row">{names[k]}</th>
                <td>{eur(d.overpaid_per_1000_eur)}</td>
                <td>{eur(d.underpaid_per_1000_eur)}</td>
                <td>{pct(d.settled_without_person)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
