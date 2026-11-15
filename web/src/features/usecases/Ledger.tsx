import { AnimatePresence, motion } from "framer-motion";
import { Fragment, useState } from "react";
import { eur, motion as m, pct, useCaseOrder } from "../../app/theme";
import type { Run } from "../../shared/types";

function outcome(key: string, run: Run): string {
  if (key === "routing") return `${pct(run.routing.designs.platform.accuracy)} routed right`;
  if (key === "invoices") return `${eur(run.invoices.platform.overpaid_per_1000_eur)} overpaid per 1,000 invoices`;
  return `${run.assist.designs.platform.wrong_answers_per_1000} wrong answers per 1,000 chats`;
}

export function Ledger({ run, names }: { run: Run; names: Record<string, string> }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <table className="plain ledger">
      <thead>
        <tr>
          <th scope="col">Use case</th>
          <th scope="col">Model the platform chose</th>
          <th scope="col">Runs on</th>
          <th scope="col">Outcome</th>
        </tr>
      </thead>
      <tbody>
        {useCaseOrder.map((k) => {
          const s = run.selection[k];
          const f = run.feasibility[k];
          const isOpen = open === k;
          return (
            <Fragment key={k}>
              <tr>
                <th scope="row">
                  <button className="row-toggle" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : k)}>
                    {names[k]}
                  </button>
                </th>
                <td>{s.chosen}</td>
                <td>
                  {f.runtime}, {f.concurrency} at peak
                </td>
                <td>{outcome(k, run)}</td>
              </tr>
              <AnimatePresence initial={false}>
                {isOpen && (
                  <tr className="trials-row">
                    <td colSpan={4}>
                      <motion.ul className="trials" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} transition={m.open}>
                        {s.trials.map((t) => (
                          <li key={t.model} className={t.model === s.chosen ? "chosen" : t.passes ? "" : "failed"}>
                            <b>{t.model}</b> {pct(t.quality)} on the holdout weeks, {eur(t.cost_per_case_eur + t.people_and_leakage_per_case_eur, 3)} a case with people&apos;s time.{" "}
                            {t.passes ? "Clears the gate." : `Fails: ${t.why}.`}
                          </li>
                        ))}
                        <li className="note">{f.why}.</li>
                      </motion.ul>
                    </td>
                  </tr>
                )}
              </AnimatePresence>
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}
