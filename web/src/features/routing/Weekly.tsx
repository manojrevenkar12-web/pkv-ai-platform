import { chart, pct, routingOrder, routingVar } from "../../app/theme";
import type { Run } from "../../shared/types";

export function Weekly({ run, names }: { run: Run; names: Record<string, string> }) {
  const { width, height, pad, low } = chart;
  const first = run.volume.live_from_week;
  const weeks = run.routing.designs.platform.weekly.length;
  const x = (i: number) => pad + (i / (weeks - 1)) * (width - pad * 2);
  const y = (v: number) => pad / 2 + (1 - (Math.max(v, low) - low) / (1 - low)) * (height - pad * 1.5);
  const v = run.routing.validation;
  return (
    <div className="pair">
      <figure className="chart">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Routing accuracy by week for three designs">
          {[low, (1 + low) / 2, 1].map((t) => (
            <g key={t}>
              <line className="grid" x1={pad} x2={width - pad} y1={y(t)} y2={y(t)} />
              <text className="tick" x={0} y={y(t) + 4}>
                {pct(t, 0)}
              </text>
            </g>
          ))}
          <line className="marker" x1={x(run.volume.letter_week - first)} x2={x(run.volume.letter_week - first)} y1={pad / 2} y2={height - pad} />
          {routingOrder.map((k) => (
            <polyline
              key={k}
              className={k === "platform" ? "line strong" : "line"}
              style={{ stroke: `var(${routingVar[k]})` }}
              points={run.routing.designs[k].weekly.map((a, i) => `${x(i)},${y(a)}`).join(" ")}
            />
          ))}
          {Array.from({ length: weeks }, (_, i) => (
            <text key={i} className="tick" x={x(i) - 6} y={height - 6}>
              {first + i}
            </text>
          ))}
        </svg>
        <figcaption className="legend">
          {routingOrder.map((k) => (
            <span key={k}>
              <i style={{ background: `var(${routingVar[k]})` }} aria-hidden="true" />
              {names[k]}: {pct(run.routing.designs[k].accuracy)}
            </span>
          ))}
        </figcaption>
      </figure>
      <div>
        <p className="lede">Before go-live, how good would the classifier be? Production before the letter was {pct(v.production_before_letter)}.</p>
        <table className="plain">
          <tbody>
            <tr>
              <th scope="row">Random split</th>
              <td>{pct(v.random_split)}</td>
              <td className="bad">{((v.random_split - v.production_before_letter) * 100).toFixed(1)} pts too high</td>
            </tr>
            <tr>
              <th scope="row">Later weeks, new customers</th>
              <td>{pct(v.grouped_by_time_and_customer)}</td>
              <td>{((v.grouped_by_time_and_customer - v.production_before_letter) * 100).toFixed(1)} pts too high</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
