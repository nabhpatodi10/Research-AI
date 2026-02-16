import { benchmarkSystems, chartTicks, maxScore, parameterSeries } from './benchmarkData';

const CHART_WIDTH = 1040;
const CHART_HEIGHT = 480;
const MARGIN = {
  top: 24,
  right: 36,
  bottom: 102,
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

export default function ParameterComparisonChart() {
  const systems = [...benchmarkSystems];
  const plotWidth = CHART_WIDTH - MARGIN.left - MARGIN.right;
  const plotHeight = CHART_HEIGHT - MARGIN.top - MARGIN.bottom;
  const plotBottom = MARGIN.top + plotHeight;
  const groupWidth = plotWidth / systems.length;
  const barGap = 5;
  const barWidth = Math.min(16, (groupWidth - 24 - barGap * (parameterSeries.length - 1)) / parameterSeries.length);
  const groupInnerWidth = parameterSeries.length * barWidth + (parameterSeries.length - 1) * barGap;

  return (
    <article className="rounded-2xl border border-blue-100 bg-white p-5 shadow-sm md:p-6">
      <div className="mb-4">
        <h3 className="text-xl font-bold text-slate-900">Parameter-wise Comparison</h3>
        <p className="mt-1 text-sm text-slate-600">
          ResearchAI is intentionally shown first, followed by benchmark peers.
        </p>
      </div>

      <div className="mb-4 flex flex-wrap gap-3">
        {parameterSeries.map((parameter) => (
          <span
            key={parameter.key}
            className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700"
          >
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: parameter.color }} />
            {parameter.label}
          </span>
        ))}
      </div>

      <div className="overflow-x-auto pb-2">
        <svg
          width={CHART_WIDTH}
          height={CHART_HEIGHT}
          viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
          role="img"
          aria-label="Grouped bar chart for DeepResearch Bench parameter scores."
          className="min-w-[900px]"
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

          {systems.map((system, systemIndex) => {
            const groupX = MARGIN.left + systemIndex * groupWidth + (groupWidth - groupInnerWidth) / 2;
            const groupCenter = MARGIN.left + systemIndex * groupWidth + groupWidth / 2;
            const wrappedLabel = splitLabel(system.name);

            return (
              <g key={system.name}>
                {parameterSeries.map((parameter, parameterIndex) => {
                  const value = system[parameter.key];
                  const barX = groupX + parameterIndex * (barWidth + barGap);
                  const barY = scoreToY(value, plotHeight);
                  const barHeight = plotBottom - barY;

                  return (
                    <g key={`${system.name}-${parameter.key}`}>
                      <rect
                        x={barX}
                        y={barY}
                        width={barWidth}
                        height={barHeight}
                        rx="4"
                        fill={parameter.color}
                        opacity={system.name === 'ResearchAI' ? 1 : 0.9}
                        className="benchmark-bar"
                        style={{ animationDelay: `${systemIndex * 90 + parameterIndex * 45}ms` }}
                      >
                        <title>{`${system.name} - ${parameter.label}: ${value.toFixed(2)}`}</title>
                      </rect>
                    </g>
                  );
                })}

                <text
                  x={groupCenter}
                  y={plotBottom + 18}
                  textAnchor="middle"
                  fontSize="12"
                  fill="#334155"
                  fontWeight={system.name === 'ResearchAI' ? '700' : '500'}
                  className="benchmark-axis-label"
                  style={{ animationDelay: `${systemIndex * 90 + 220}ms` }}
                >
                  {wrappedLabel.map((line, lineIndex) => (
                    <tspan key={`${system.name}-${line}`} x={groupCenter} dy={lineIndex === 0 ? 0 : 14}>
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
