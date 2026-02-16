import { benchmarkSystems, chartTicks, maxScore } from './benchmarkData';

const CHART_WIDTH = 1040;
const CHART_HEIGHT = 430;
const MARGIN = {
  top: 24,
  right: 36,
  bottom: 96,
  left: 62,
};

function scoreToY(score, plotHeight) {
  return MARGIN.top + ((maxScore - score) / maxScore) * plotHeight;
}

function splitLabel(label, maxCharsPerLine = 14) {
  const words = label.split(' ');
  const lines = [];
  let currentLine = '';

  words.forEach((word) => {
    if (!currentLine) {
      currentLine = word;
      return;
    }

    if (`${currentLine} ${word}`.length <= maxCharsPerLine) {
      currentLine = `${currentLine} ${word}`;
    } else {
      lines.push(currentLine);
      currentLine = word;
    }
  });

  if (currentLine) {
    lines.push(currentLine);
  }

  return lines;
}

export default function OverallComparisonChart() {
  const sorted = [...benchmarkSystems].sort((a, b) => b.overall - a.overall);
  const plotWidth = CHART_WIDTH - MARGIN.left - MARGIN.right;
  const plotHeight = CHART_HEIGHT - MARGIN.top - MARGIN.bottom;
  const slotWidth = plotWidth / sorted.length;
  const barWidth = Math.min(78, slotWidth * 0.72);
  const plotBottom = MARGIN.top + plotHeight;

  return (
    <article className="rounded-2xl border border-blue-100 bg-white p-5 shadow-sm md:p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-xl font-bold text-slate-900">Overall Score Comparison</h3>
          <p className="mt-1 text-sm text-slate-600">
            DeepResearch Bench overall leaderboard performance across selected systems.
          </p>
        </div>
        <div className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-800">
          <span className="h-2.5 w-2.5 rounded-full bg-blue-700" />
          ResearchAI Highlighted
        </div>
      </div>

      <div className="overflow-x-auto pb-2">
        <svg
          width={CHART_WIDTH}
          height={CHART_HEIGHT}
          viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
          role="img"
          aria-label="Bar chart comparing overall DeepResearch Bench scores."
          className="min-w-[760px]"
        >
          {chartTicks.map((tick) => {
            const y = scoreToY(tick, plotHeight);
            return (
              <g key={tick}>
                <line
                  x1={MARGIN.left}
                  y1={y}
                  x2={CHART_WIDTH - MARGIN.right}
                  y2={y}
                  stroke="#cbd5e1"
                  strokeDasharray="4 4"
                  strokeWidth="1"
                />
                <text
                  x={MARGIN.left - 10}
                  y={y + 4}
                  textAnchor="end"
                  fontSize="12"
                  fill="#475569"
                >
                  {tick}
                </text>
              </g>
            );
          })}

          <line
            x1={MARGIN.left}
            y1={plotBottom}
            x2={CHART_WIDTH - MARGIN.right}
            y2={plotBottom}
            stroke="#64748b"
            strokeWidth="1.2"
          />

          {sorted.map((system, index) => {
            const barX = MARGIN.left + index * slotWidth + (slotWidth - barWidth) / 2;
            const barY = scoreToY(system.overall, plotHeight);
            const barHeight = plotBottom - barY;
            const labelX = barX + barWidth / 2;
            const isResearchAI = system.name === 'ResearchAI';
            const wrappedLabel = splitLabel(system.name);

            return (
              <g key={system.name}>
                <rect
                  x={barX}
                  y={barY}
                  width={barWidth}
                  height={barHeight}
                  rx="8"
                  fill={isResearchAI ? '#1d4ed8' : '#93c5fd'}
                  stroke={isResearchAI ? '#1e3a8a' : '#3b82f6'}
                  strokeWidth="1.2"
                  className="benchmark-bar"
                  style={{ animationDelay: `${index * 80}ms` }}
                >
                  <title>{`${system.name}: ${system.overall.toFixed(2)}`}</title>
                </rect>
                <text
                  x={labelX}
                  y={barY - 8}
                  textAnchor="middle"
                  fontSize="12"
                  fontWeight="700"
                  fill="#0f172a"
                  className="benchmark-value"
                  style={{ animationDelay: `${index * 80 + 200}ms` }}
                >
                  {system.overall.toFixed(2)}
                </text>
                <text
                  x={labelX}
                  y={plotBottom + 18}
                  textAnchor="middle"
                  fontSize="12"
                  fill="#334155"
                  className="benchmark-axis-label"
                  style={{ animationDelay: `${index * 80 + 240}ms` }}
                >
                  {wrappedLabel.map((line, lineIndex) => (
                    <tspan key={`${system.name}-${line}`} x={labelX} dy={lineIndex === 0 ? 0 : 14}>
                      {line}
                    </tspan>
                  ))}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </article>
  );
}
