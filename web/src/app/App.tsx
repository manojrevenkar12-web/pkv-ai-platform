import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { Assist } from "../features/assist/Assist";
import { DriftStrip } from "../features/drift/DriftStrip";
import { InvoiceExample } from "../features/invoice/InvoiceExample";
import { Weekly } from "../features/routing/Weekly";
import { Ledger } from "../features/usecases/Ledger";
import { useConsole } from "../shared/api";
import type { Console, Run } from "../shared/types";
import { Empty, ErrorState, Section, Segmented, Skeleton } from "../shared/ui";
import { eur, motion as m, pct } from "./theme";

type Which = "dev" | "heldout";

export function headline(run: Run): string {
  const d = run.routing.drift;
  const when = d.detected_after_days === null ? "never noticed" : d.detected_after_days === 0 ? "noticed the same day" : `noticed after ${d.detected_after_days} days`;
  return `Premium letters went out in week ${d.letter_week}. The platform ${when}, and kept routing ${pct(run.routing.designs.platform.accuracy_on_letter_answers, 0)} of the replies right.`;
}

function Platform({ run, data }: { run: Run; data: Console }) {
  if (!run.selection || !Object.keys(run.selection).length) return <Empty>This report has no use cases. Run python scripts/evaluate.py, then python scripts/readme.py.</Empty>;
  const t = run.totals;
  return (
    <>
      <div className="hero">
        <AnimatePresence mode="wait" initial={false}>
          <motion.h1 key={run.world} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={m.open}>
            {headline(run)}
          </motion.h1>
        </AnimatePresence>
        <p className="lede">
          Three AI use cases of a digital private health insurer on one platform: {run.volume.emails.toLocaleString("en")} emails, {run.volume.invoices.toLocaleString("en")} doctors&apos; invoices and{" "}
          {run.volume.chats.toLocaleString("en")} chat questions, simulated. All in, {eur(t.platform.all_in_eur_per_month)} a month against {eur(t.large_everywhere.all_in_eur_per_month)} with the large model
          everywhere, counting model calls, people&apos;s time and money paid out wrongly.
        </p>
      </div>
      <DriftStrip run={run} />
      <Section id="usecases" title="One contract per use case, one model chosen for each">
        <Ledger run={run} names={data.names.usecases} />
      </Section>
      <Section id="routing" title="Email routing, week by week">
        <Weekly run={run} names={data.names.routing} />
      </Section>
      <Section id="invoice" title="An invoice, settled by code after the model read it">
        <InvoiceExample run={run} names={data.names.invoices} />
      </Section>
      <Section id="assist" title="Chat drafts the agent can trust">
        <Assist run={run} names={data.names.assist} />
      </Section>
    </>
  );
}

export function App() {
  const q = useConsole();
  const [which, setWhich] = useState<Which>("dev");
  const run = q.data ? (which === "heldout" && q.data.heldout ? q.data.heldout : q.data.dev) : null;
  return (
    <div className="page">
      <header className="masthead">
        <span className="product">pkv-ai-platform</span>
        {q.data && (
          <Segmented<Which>
            label="Which world"
            options={(q.data.heldout ? { dev: "Dev world", heldout: "Held-out world" } : { dev: "Dev world" }) as Record<Which, string>}
            value={which}
            onChange={setWhich}
          />
        )}
      </header>
      <main>
        {q.isPending && <Skeleton />}
        {q.isError && <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} />}
        {run && q.data && <Platform key={run.world} run={run} data={q.data} />}
      </main>
    </div>
  );
}
