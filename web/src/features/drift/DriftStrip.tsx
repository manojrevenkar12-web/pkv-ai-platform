import { motion } from "framer-motion";
import { chart, motion as m, pct } from "../../app/theme";
import type { Run } from "../../shared/types";
import { Empty } from "../../shared/ui";

/** Every live day: the share of emails the classifier was unsure of. Amber while the alarm is open. */
export function DriftStrip({ run }: { run: Run }) {
  const days = run.routing.daily;
  if (!days.length) return <Empty>This report has no daily routing data. Run python scripts/evaluate.py.</Empty>;
  const { width, pad } = chart;
  const height = 120;
  const top = Math.max(0.4, ...days.map((d) => d.low_confidence));
  const step = (width - pad) / days.length;
  const first = days[0].week;
  const x = (d: { week: number; day: number }) => pad + ((d.week - first) * 7 + d.day) * step;
  const h = (v: number) => (v / top) * (height - 22);
  const letter = { week: run.routing.drift.letter_week, day: 0 };
  const a = run.routing.drift.alarm;
  return (
    <figure className="strip">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Daily share of emails under the confidence floor, weeks ${first} to ${days[days.length - 1].week}`}>
        <line className="axis" x1={pad} x2={width} y1={height - 18} y2={height - 18} />
        {days.map((d, i) => (
          <motion.rect
            key={`${d.week}-${d.day}`}
            className={d.alarm ? "bar alarm" : "bar"}
            x={x(d)}
            width={Math.max(1, step - 1.5)}
            initial={{ height: 0, y: height - 18 }}
            animate={{ height: h(d.low_confidence), y: height - 18 - h(d.low_confidence) }}
            transition={{ ...m.grow, delay: i * m.stagger }}
          />
        ))}
        <line className="marker" x1={x(letter)} x2={x(letter)} y1={4} y2={height - 18} />
        <text className="marker-label" x={x(letter) + 4} y={14}>
          Premium letters sent
        </text>
        {a && <circle className="alarm-dot" cx={x(a) + step / 2} cy={height - 9} r={3.5} />}
        {Array.from({ length: days[days.length - 1].week - first + 1 }, (_, k) => (
          <text key={k} className="tick" x={pad + k * 7 * step} y={height - 2}>
            {first + k}
          </text>
        ))}
        <text className="tick" x={0} y={12}>
          {pct(top, 0)}
        </text>
      </svg>
      <figcaption>
        Share of each day&apos;s emails the classifier was unsure of, weeks {first}–{days[days.length - 1].week}. Amber days: the alarm is open, a person labels a few of
        the new emails and the classifier is retrained that night.
      </figcaption>
    </figure>
  );
}
